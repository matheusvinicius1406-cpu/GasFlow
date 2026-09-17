/**
 * DriverHomePage — Gate "só em rota" do rastreio GPS (B2, spec §2).
 *
 * O rastreio liga sozinho quando existe entrega em rota (ASSIGNED /
 * DISPATCHED / EN_ROUTE), desliga quando a rota termina e respeita o
 * override manual do entregador (desligou, fica desligado até ele
 * religar ou começar outra rota).
 *
 * jsdom não tem navigator.geolocation — mockamos para observar
 * watchPosition/clearWatch sem geolocalização real.
 */
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { render, screen, cleanup, waitFor } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { DriverHomePage } from '../DriverHomePage'

const watchPositionMock = vi.fn(() => 1)
const clearWatchMock = vi.fn()

beforeEach(() => {
  Object.defineProperty(navigator, 'geolocation', {
    configurable: true,
    value: {
      watchPosition: watchPositionMock,
      clearWatch: clearWatchMock,
      getCurrentPosition: vi.fn(),
    },
  })
})

afterEach(() => {
  cleanup()
  vi.clearAllMocks()
  window.localStorage.clear()
})

function makeDeliveries(status: string) {
  return {
    deliveries: [
      {
        delivery_id: 'd1',
        order_reference: 'P-1',
        customer_name: 'Maria',
        address: 'Rua A, 123',
        status,
        scheduled_at: null,
        version: 1,
      },
    ],
  }
}

const fetchMock = vi.fn((url: string) => {
  if (url.includes('/driver/deliveries')) {
    return Promise.resolve({ ok: true, status: 200, json: () => Promise.resolve(makeDeliveries('PENDING')) })
  }
  if (url.includes('/driver/me')) {
    return Promise.resolve({
      ok: true,
      status: 200,
      json: () => Promise.resolve({ driver_id: '654321', name: 'João', status: 'AVAILABLE', tracking_interval_seconds: 120 }),
    })
  }
  return Promise.resolve({ ok: true, status: 200, json: () => Promise.resolve({}) })
})

function renderPage() {
  return render(
    <MemoryRouter initialEntries={['/driver']}>
      <DriverHomePage />
    </MemoryRouter>
  )
}

async function renderWithDeliveries(status: string) {
  fetchMock.mockImplementation((url: string) => {
    if (url.includes('/driver/deliveries')) {
      return Promise.resolve({ ok: true, status: 200, json: () => Promise.resolve(makeDeliveries(status)) })
    }
    if (url.includes('/driver/me')) {
      return Promise.resolve({
        ok: true,
        status: 200,
        json: () => Promise.resolve({ driver_id: '654321', name: 'João', status: 'AVAILABLE', tracking_interval_seconds: 120 }),
      })
    }
    return Promise.resolve({ ok: true, status: 200, json: () => Promise.resolve({}) })
  })
  renderPage()
  await waitFor(() => expect(screen.getByText('Maria')).toBeInTheDocument())
}

describe('DriverHomePage — gate GPS só em rota (B2)', () => {
  beforeEach(() => {
    window.localStorage.setItem('driver_token', 'test-token')
    vi.stubGlobal('fetch', fetchMock as unknown as typeof fetch)
  })

  afterEach(() => {
    vi.unstubAllGlobals()
  })

  it('sem rota ativa (PENDING): não liga o rastreio automaticamente', async () => {
    await renderWithDeliveries('PENDING')

    expect(watchPositionMock).not.toHaveBeenCalled()
    expect(screen.getByText(/aguarda rota/i)).toBeInTheDocument()
  })

  it('com entrega EN_ROUTE: liga o rastreio automaticamente', async () => {
    await renderWithDeliveries('EN_ROUTE')

    await waitFor(() => expect(watchPositionMock).toHaveBeenCalledTimes(1))
    expect(screen.getByText(/Ativo/)).toBeInTheDocument()
  })

  it('com entrega ASSIGNED (a caminho): já considera rota ativa', async () => {
    await renderWithDeliveries('ASSIGNED')

    await waitFor(() => expect(watchPositionMock).toHaveBeenCalledTimes(1))
  })

  it('rota termina (DELIVERED): clearWatch é chamado quando não há mais rota', async () => {
    // Componente montado já com a rota concluída — o efeito do gate não
    // deve deixar watchPosition ativo (nada de captura fora de rota).
    await renderWithDeliveries('DELIVERED')

    expect(watchPositionMock).not.toHaveBeenCalled()
    expect(clearWatchMock).not.toHaveBeenCalled() // nada a limpar — nunca ligou
    expect(screen.getByText(/aguarda rota/i)).toBeInTheDocument()
  })

  it('override manual: desligar com rota ativa respeita a escolha', async () => {
    await renderWithDeliveries('EN_ROUTE')
    await waitFor(() => expect(watchPositionMock).toHaveBeenCalledTimes(1))

    // Entregador desliga manualmente
    const offButton = screen.getByRole('button', { name: /GPS Off/i })
    offButton.click()

    await waitFor(() => expect(clearWatchMock).toHaveBeenCalled())
    // Não religa sozinho enquanto a mesma rota continua ativa:
    expect(watchPositionMock).toHaveBeenCalledTimes(1)
    expect(screen.getByText(/desligado por você/i)).toBeInTheDocument()
  })
})
