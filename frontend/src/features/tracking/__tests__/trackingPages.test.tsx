/**
 * Fase 7.2 / 7.4 — páginas de rastreio.
 *
 * DriverMap é mocked (jsdom não renderiza tiles). O que importa aqui:
 * - a página pública não vaza PII e trata 401/404 como estado, não erro;
 * - o replay monta o trajeto a partir do histórico real e formata o ETA.
 */
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { render, screen, waitFor, cleanup } from '@testing-library/react'
import { MemoryRouter, Route, Routes } from 'react-router-dom'

vi.mock('@/components/map/DriverMap', () => ({
  DriverMap: ({ points, trails }: { points: unknown[]; trails?: Record<string, unknown[]> }) => (
    <div data-testid="driver-map">
      pontos:{points.length} trajetos:{Object.values(trails ?? {}).reduce((n, t) => n + t.length, 0)}
    </div>
  ),
}))

const useDriverHistoryMock = vi.fn()
vi.mock('@/lib/api/hooks', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@/lib/api/hooks')>()
  return {
    ...actual,
    useDriverHistory: (...args: unknown[]) => useDriverHistoryMock(...args),
  }
})

import { PublicTracking } from '../PublicTracking'
import { RouteReplay } from '../RouteReplay'
import { formatEta } from '@/lib/api/hooks'

function renderPublic(path: string) {
  return render(
    <MemoryRouter initialEntries={[path]}>
      <Routes>
        <Route path="/track/:token" element={<PublicTracking />} />
      </Routes>
    </MemoryRouter>
  )
}

const fetchMock = vi.fn()

describe('PublicTracking (Fase 7.2)', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    vi.stubGlobal('fetch', fetchMock)
  })

  afterEach(() => {
    cleanup()
    vi.unstubAllGlobals()
  })

  it('mostra a posição quando o link é válido (sem PII)', async () => {
    fetchMock.mockResolvedValue({
      ok: true,
      status: 200,
      json: async () => ({
        driver_id: 'drv1',
        latitude: -23.55,
        longitude: -46.63,
        updated_at: '2026-09-22T12:00:00Z',
      }),
    })

    renderPublic('/track/abc')

    await waitFor(() => expect(screen.getByTestId('driver-map')).toBeInTheDocument())
    expect(screen.getByText(/Acompanhamento da entrega/i)).toBeInTheDocument()
    expect(screen.getByText(/nenhum dado pessoal/i)).toBeInTheDocument()
    // nenhum nome/telefone renderizado
    expect(document.body.textContent).not.toMatch(/Fulano|91999/)
  })

  it('trata 401 como link expirado (não como erro genérico)', async () => {
    fetchMock.mockResolvedValue({ ok: false, status: 401, json: async () => ({}) })

    renderPublic('/track/expirado')

    await waitFor(() => expect(screen.getByText(/expirou/i)).toBeInTheDocument())
    expect(screen.queryByTestId('driver-map')).not.toBeInTheDocument()
  })

  it('trata 404 como "ainda sem posição"', async () => {
    fetchMock.mockResolvedValue({ ok: false, status: 404, json: async () => ({}) })

    renderPublic('/track/sem-pos')

    await waitFor(() => expect(screen.getByText(/não há posição/i)).toBeInTheDocument())
  })

  it('chama o endpoint público sem header de sessão', async () => {
    fetchMock.mockResolvedValue({
      ok: true,
      status: 200,
      json: async () => ({ driver_id: 'd', latitude: 1, longitude: 2, updated_at: null }),
    })

    renderPublic('/track/tok123')

    await waitFor(() => expect(fetchMock).toHaveBeenCalled())
    const [url, init] = fetchMock.mock.calls[0] as [string, RequestInit | undefined]
    expect(url).toContain('/api/public/tracking/tok123')
    expect(init?.headers).toBeUndefined()
  })
})

describe('RouteReplay (Fase 7.4)', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  afterEach(cleanup)

  it('sem histórico suficiente mostra o estado vazio', () => {
    useDriverHistoryMock.mockReturnValue({ data: { points: [] }, isLoading: false })

    render(<RouteReplay driverId="drv1" />)

    expect(screen.getByText(/Sem trajeto registrado hoje/i)).toBeInTheDocument()
  })

  it('monta o trajeto a partir do histórico real', async () => {
    useDriverHistoryMock.mockReturnValue({
      isLoading: false,
      data: {
        driver_id: 'drv1',
        count: 3,
        points: [
          { latitude: -23.55, longitude: -46.63, recorded_at: '2026-09-22T12:00:00Z' },
          { latitude: -23.56, longitude: -46.63, recorded_at: '2026-09-22T12:01:00Z' },
          { latitude: -23.57, longitude: -46.63, recorded_at: '2026-09-22T12:02:00Z' },
        ],
      },
    })

    render(<RouteReplay driverId="drv1" />)

    await waitFor(() => expect(screen.getByTestId('driver-map')).toBeInTheDocument())
    expect(screen.getByText(/3 pontos/)).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /Pausar/i })).toBeInTheDocument()
  })
})

describe('formatEta', () => {
  it('formata minutos e horas', () => {
    expect(formatEta(60)).toBe('1 min')
    expect(formatEta(720)).toBe('12 min')
    expect(formatEta(3600)).toBe('1h')
    expect(formatEta(3900)).toBe('1h05')
  })

  it('nunca mostra menos de 1 minuto', () => {
    expect(formatEta(1)).toBe('1 min')
  })
})
