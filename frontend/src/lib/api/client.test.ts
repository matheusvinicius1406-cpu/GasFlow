/**
 * Renovação de sessão (B5) no cliente de API.
 *
 * O caso que estes testes mais protegem é o de **401 simultâneos**: o refresh é
 * rotativo e o backend revoga a sessão quando vê o mesmo refresh duas vezes
 * (tratando como vazamento). Sem single-flight, três requests paralelas
 * trocariam o mesmo refresh e o usuário seria deslogado pelo próprio app.
 */

import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import type { AxiosResponse, InternalAxiosRequestConfig } from 'axios'
import {
  api,
  apiClient,
  ACCESS_TOKEN_KEY,
  PASSWORD_CHANGE_REQUIRED_EVENT,
  REFRESH_TOKEN_KEY,
  SESSION_REFRESHED_EVENT,
} from './client'

const originalAdapter = apiClient.defaults.adapter

type Adapter = (config: InternalAxiosRequestConfig) => Promise<AxiosResponse>

/** Resposta 200, no formato cru que o adapter devolve. */
function ok<T>(config: InternalAxiosRequestConfig, data: T): AxiosResponse<T> {
  return { data, status: 200, statusText: 'OK', headers: {}, config } as AxiosResponse<T>
}

/** Rejeição 401 no formato que o interceptor de resposta consome. */
function unauthorized(config: InternalAxiosRequestConfig): Promise<never> {
  const error = Object.assign(new Error('Request failed with status code 401'), {
    config,
    response: {
      status: 401,
      statusText: 'Unauthorized',
      data: { detail: 'expirado' },
      headers: {},
      config,
    },
  })
  return Promise.reject(error)
}

function bearer(config: InternalAxiosRequestConfig): string {
  return String(config.headers?.Authorization ?? '')
}

beforeEach(() => {
  localStorage.clear()
  // O interceptor redireciona com `location.href`; jsdom não navega, então o
  // alvo é substituído por um objeto observável (mesmo padrão de realtime.test).
  Object.defineProperty(window, 'location', {
    writable: true,
    configurable: true,
    value: { ...window.location, href: '' },
  })
})

afterEach(() => {
  apiClient.defaults.adapter = originalAdapter
  vi.restoreAllMocks()
})

describe('apiClient — renovação do access token', () => {
  it('renova e repete a request quando o access expira', async () => {
    localStorage.setItem(ACCESS_TOKEN_KEY, 'access-antigo')
    localStorage.setItem(REFRESH_TOKEN_KEY, 'refresh-1')
    const urls: string[] = []

    apiClient.defaults.adapter = (async (config: InternalAxiosRequestConfig) => {
      urls.push(String(config.url))
      if (config.url === '/auth/refresh') {
        return ok(config, { access_token: 'access-novo', refresh_token: 'refresh-2' })
      }
      if (bearer(config) === 'Bearer access-novo') return ok(config, { value: 42 })
      return unauthorized(config)
    }) as Adapter

    const res = await apiClient.get('/dashboard')

    expect(res.data).toEqual({ value: 42 })
    // 1) falha com o token velho  2) troca o refresh  3) repete com o novo
    expect(urls).toEqual(['/dashboard', '/auth/refresh', '/dashboard'])
    expect(localStorage.getItem(ACCESS_TOKEN_KEY)).toBe('access-novo')
    expect(localStorage.getItem(REFRESH_TOKEN_KEY)).toBe('refresh-2')
  })

  it('avisa quem precisa do token novo (gate IPC do desktop)', async () => {
    localStorage.setItem(ACCESS_TOKEN_KEY, 'access-antigo')
    localStorage.setItem(REFRESH_TOKEN_KEY, 'refresh-1')
    const seen: string[] = []
    window.addEventListener(SESSION_REFRESHED_EVENT, (event) => {
      seen.push((event as CustomEvent<string>).detail)
    })

    apiClient.defaults.adapter = (async (config: InternalAxiosRequestConfig) => {
      if (config.url === '/auth/refresh') return ok(config, { access_token: 'access-novo', refresh_token: 'r2' })
      if (bearer(config) === 'Bearer access-novo') return ok(config, {})
      return unauthorized(config)
    }) as Adapter

    await apiClient.get('/dashboard')
    expect(seen).toEqual(['access-novo'])
  })

  it('faz uma única troca para vários 401 simultâneos', async () => {
    localStorage.setItem(ACCESS_TOKEN_KEY, 'velho')
    localStorage.setItem(REFRESH_TOKEN_KEY, 'refresh-1')
    let refreshCalls = 0

    apiClient.defaults.adapter = (async (config: InternalAxiosRequestConfig) => {
      if (config.url === '/auth/refresh') {
        refreshCalls += 1
        await new Promise((resolve) => setTimeout(resolve, 5))
        return ok(config, { access_token: 'novo', refresh_token: 'refresh-2' })
      }
      if (bearer(config) === 'Bearer novo') return ok(config, { ok: true })
      return unauthorized(config)
    }) as Adapter

    const results = await Promise.all([
      apiClient.get('/a'),
      apiClient.get('/b'),
      apiClient.get('/c'),
    ])

    expect(results.map((r) => r.data)).toEqual([{ ok: true }, { ok: true }, { ok: true }])
    expect(refreshCalls).toBe(1)
  })

  it('sem refresh guardado, um 401 encerra a sessão e manda para o login', async () => {
    localStorage.setItem(ACCESS_TOKEN_KEY, 'velho')
    const urls: string[] = []

    apiClient.defaults.adapter = (async (config: InternalAxiosRequestConfig) => {
      urls.push(String(config.url))
      return unauthorized(config)
    }) as Adapter

    await expect(apiClient.get('/dashboard')).rejects.toBeTruthy()

    // Nada de tentar refresh sem refresh: seria request perdida.
    expect(urls).toEqual(['/dashboard'])
    expect(localStorage.getItem(ACCESS_TOKEN_KEY)).toBeNull()
    expect(window.location.href).toBe('/login')
  })

  it('refresh recusado encerra a sessão em vez de insistir', async () => {
    localStorage.setItem(ACCESS_TOKEN_KEY, 'velho')
    localStorage.setItem(REFRESH_TOKEN_KEY, 'refresh-morto')
    let refreshCalls = 0

    apiClient.defaults.adapter = (async (config: InternalAxiosRequestConfig) => {
      if (config.url === '/auth/refresh') {
        refreshCalls += 1
        return unauthorized(config)
      }
      return unauthorized(config)
    }) as Adapter

    await expect(apiClient.get('/dashboard')).rejects.toBeTruthy()

    expect(refreshCalls).toBe(1)
    expect(localStorage.getItem(ACCESS_TOKEN_KEY)).toBeNull()
    expect(localStorage.getItem(REFRESH_TOKEN_KEY)).toBeNull()
    expect(window.location.href).toBe('/login')
  })

  it('401 no login é credencial errada — não renova nem redireciona', async () => {
    localStorage.setItem(ACCESS_TOKEN_KEY, 'sessao-antiga')
    localStorage.setItem(REFRESH_TOKEN_KEY, 'refresh-1')
    const urls: string[] = []

    apiClient.defaults.adapter = (async (config: InternalAxiosRequestConfig) => {
      urls.push(String(config.url))
      return unauthorized(config)
    }) as Adapter

    await expect(api.auth.login('operador', 'errada')).rejects.toBeTruthy()

    expect(urls).toEqual(['/auth/login'])
    expect(localStorage.getItem(REFRESH_TOKEN_KEY)).toBe('refresh-1')
    expect(window.location.href).toBe('')
  })
})

describe('apiClient — troca de senha pendente (P0 3.8)', () => {
  /** Rejeição 403 "Password change required" no formato do interceptor. */
  function forbid(config: InternalAxiosRequestConfig, detail: string): Promise<never> {
    const error = Object.assign(new Error('Request failed with status code 403'), {
      config,
      response: {
        status: 403,
        statusText: 'Forbidden',
        data: { detail },
        headers: {},
        config,
      },
    })
    return Promise.reject(error)
  }

  it('emite o evento de troca obrigatória quando o backend recusa a rota', async () => {
    localStorage.setItem(ACCESS_TOKEN_KEY, 'access')
    const seen = vi.fn()
    window.addEventListener(PASSWORD_CHANGE_REQUIRED_EVENT, seen)

    apiClient.defaults.adapter = (async (config: InternalAxiosRequestConfig) =>
      forbid(config, 'Password change required')) as Adapter

    await expect(apiClient.get('/dashboard')).rejects.toBeTruthy()

    expect(seen).toHaveBeenCalledTimes(1)
    window.removeEventListener(PASSWORD_CHANGE_REQUIRED_EVENT, seen)
  })

  it('não emite para 403 de permissão (detail diferente)', async () => {
    localStorage.setItem(ACCESS_TOKEN_KEY, 'access')
    const seen = vi.fn()
    window.addEventListener(PASSWORD_CHANGE_REQUIRED_EVENT, seen)

    apiClient.defaults.adapter = (async (config: InternalAxiosRequestConfig) =>
      forbid(config, "Permission 'user.create' required")) as Adapter

    await expect(apiClient.get('/dashboard')).rejects.toBeTruthy()

    expect(seen).not.toHaveBeenCalled()
    window.removeEventListener(PASSWORD_CHANGE_REQUIRED_EVENT, seen)
  })
})
