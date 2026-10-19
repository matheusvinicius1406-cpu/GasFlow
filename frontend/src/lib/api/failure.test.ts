import { describe, it, expect } from 'vitest'
import { classifyRequestFailure, failureTitle, FAILURE_TITLES } from './failure'

function httpError(status: number) {
  return { response: { status } }
}

describe('classifyRequestFailure', () => {
  it('403 é permissão', () => {
    expect(classifyRequestFailure(httpError(403))).toBe('permission')
  })

  it('403 de "senha pendente" também é permissão', () => {
    expect(
      classifyRequestFailure({
        response: { status: 403, data: { detail: 'Password change required' } },
      })
    ).toBe('permission')
  })

  it('404/500 são unknown — o backend respondeu, não é rede', () => {
    expect(classifyRequestFailure(httpError(404))).toBe('unknown')
    expect(classifyRequestFailure(httpError(500))).toBe('unknown')
    expect(classifyRequestFailure(httpError(422))).toBe('unknown')
  })

  it('sem resposta HTTP é offline', () => {
    expect(classifyRequestFailure(new Error('Network Error'))).toBe('offline')
    expect(classifyRequestFailure({ code: 'ERR_NETWORK' })).toBe('offline')
    expect(classifyRequestFailure({ code: 'ECONNABORTED' })).toBe('offline')
    expect(classifyRequestFailure({ code: 'ETIMEDOUT' })).toBe('offline')
  })

  it('nullish cai no genérico', () => {
    expect(classifyRequestFailure(null)).toBe('unknown')
    expect(classifyRequestFailure(undefined)).toBe('unknown')
  })

  it('booleano legado (estado antigo de erro) cai no genérico', () => {
    expect(classifyRequestFailure(true)).toBe('unknown')
    expect(classifyRequestFailure(false)).toBe('unknown')
  })

  it('toda classe tem título', () => {
    expect(failureTitle(httpError(403))).toBe('Sem permissão')
    expect(failureTitle(new Error('Network Error'))).toBe('Sem conexão')
    expect(failureTitle(httpError(500))).toBe('Algo deu errado')
    expect(failureTitle(undefined)).toBe(FAILURE_TITLES.unknown)
  })
})
