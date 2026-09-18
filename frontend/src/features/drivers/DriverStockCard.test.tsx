import { screen, waitFor, fireEvent } from '@testing-library/react'
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { render } from '@testing-library/react'
import { DriverStockCard } from './DriverStockCard'
import { driverStockApi, type DriverStockRow } from '@/lib/api/driverStock'

vi.mock('@/lib/api/driverStock', async () => {
  const actual = await vi.importActual<typeof import('@/lib/api/driverStock')>('@/lib/api/driverStock')
  return {
    ...actual,
    driverStockApi: {
      ...actual.driverStockApi,
      getStock: vi.fn(),
      load: vi.fn(),
      damage: vi.fn(),
      reconcile: vi.fn(),
    },
    useDriverStock: vi.fn(),
  }
})

const { useDriverStock } = await import('@/lib/api/driverStock')

function renderCard(stock: DriverStockRow[], isLoading = false) {
  ;(useDriverStock as ReturnType<typeof vi.fn>).mockReturnValue({
    data: stock,
    isLoading,
    refetch: vi.fn(),
  })
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return render(
    <QueryClientProvider client={queryClient}>
      <DriverStockCard driverId="D1" driverName="João" />
    </QueryClientProvider>,
  )
}

const loadedStock: DriverStockRow[] = [
  { product_codigo: 'P13', full_tanks_loaded: 10, empty_tanks_returned: 3, blocked: false, blocked_reason: null },
]

describe('DriverStockCard', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('mostra saldos por produto (cheios e vazios)', () => {
    renderCard(loadedStock)
    expect(screen.getByText('P13')).toBeInTheDocument()
    expect(screen.getByText('10')).toBeInTheDocument()
    expect(screen.getByText(/Vazios devolvidos: 3/)).toBeInTheDocument()
  })

  it('registra carga com a quantidade informada', async () => {
    ;(driverStockApi.load as ReturnType<typeof vi.fn>).mockResolvedValue({})
    renderCard(loadedStock)

    const loadInput = screen.getByLabelText('Quantidade de cheios carregados')
    fireEvent.change(loadInput, { target: { value: '15' } })
    fireEvent.click(screen.getByRole('button', { name: /carregar/i }))

    await waitFor(() => {
      expect(driverStockApi.load).toHaveBeenCalledWith('D1', 'P13', 15)
    })
  })

  it('avaria exige motivo — botão desabilitado sem preencher', () => {
    renderCard(loadedStock)
    const damageButton = screen.getByRole('button', { name: /avaria/i })
    expect(damageButton).toBeDisabled()

    fireEvent.change(screen.getByLabelText('Motivo da avaria'), { target: { value: 'queda' } })
    expect(damageButton).toBeEnabled()
  })

  it('mostra aviso de bloqueio quando divergência pendente', () => {
    renderCard([{ ...loadedStock[0]!, blocked: true, blocked_reason: 'divergência 6 > 2' }])
    expect(screen.getByText(/Bloqueado/)).toBeInTheDocument()
    expect(screen.getByText(/cargas bloqueadas até reconciliação/i)).toBeInTheDocument()
  })

  it('estado vazio quando não há carga registrada', () => {
    renderCard([])
    expect(screen.getByText('Sem carga registrada')).toBeInTheDocument()
  })
})
