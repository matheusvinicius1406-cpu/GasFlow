import { render, screen, waitFor, fireEvent } from '@testing-library/react'
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { MemoryRouter } from 'react-router-dom'

const { mockStatus, mockSettings, mockUpdate, mockTest, mockDownload } = vi.hoisted(() => ({
  mockStatus: vi.fn<() => Promise<{ data: unknown }>>(),
  mockSettings: vi.fn<() => Promise<{ data: unknown }>>(),
  mockUpdate: vi.fn<(data: unknown) => Promise<{ data: unknown }>>(),
  mockTest: vi.fn<(prompt: string) => Promise<{ data: unknown }>>(),
  mockDownload: vi.fn<() => Promise<{ data: unknown }>>(),
}))

vi.mock('@/lib/api/client', () => ({
  api: {
    ai: {
      status: mockStatus,
      settings: mockSettings,
      updateSettings: mockUpdate,
      test: mockTest,
      downloadModel: mockDownload,
    },
  },
}))

import { AISettingsPage } from './AISettings'

function renderPage() {
  return render(
    <MemoryRouter>
      <AISettingsPage />
    </MemoryRouter>,
  )
}

const SETTINGS = {
  enabled: true,
  provider: 'ollama',
  model: 'qwen3:0.6b',
  timeout_seconds: 60,
  last_health_check: null,
}

describe('AISettingsPage', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    mockStatus.mockResolvedValue({ data: { state: 'ready', message: 'IA pronta.', progress: null } })
    mockSettings.mockResolvedValue({ data: SETTINGS })
    mockUpdate.mockResolvedValue({ data: { ...SETTINGS, enabled: false } })
    mockTest.mockResolvedValue({
      data: { response: 'Resposta de teste da IA.', provider: 'local', error: null },
    })
  })

  it('1. mostra status ready', async () => {
    renderPage()
    expect(await screen.findByText('IA pronta')).toBeInTheDocument()
    expect(screen.getByText('IA pronta.')).toBeInTheDocument()
  })

  it('2. mostra preparing com progresso', async () => {
    mockStatus.mockResolvedValue({
      data: { state: 'preparing', message: 'Preparando IA… 45%', progress: 45 },
    })
    renderPage()
    expect(await screen.findByText('Preparando IA…')).toBeInTheDocument()
    expect(screen.getByText('45%')).toBeInTheDocument()
  })

  it('3. toggle desativa a IA (PATCH enabled=false + reload)', async () => {
    renderPage()
    const toggle = await screen.findByRole('switch', { name: 'Ativar Inteligência' })
    fireEvent.click(toggle)
    await waitFor(() => {
      expect(mockUpdate).toHaveBeenCalledWith({ enabled: false })
    })
    // Após o toggle, a página recarrega status+settings
    await waitFor(() => {
      expect(mockStatus).toHaveBeenCalledTimes(2)
      expect(mockSettings).toHaveBeenCalledTimes(2)
    })
  })

  it('4. cenário B: sem toggle de serviço externo (fallback não existe)', async () => {
    renderPage()
    await screen.findByText('IA pronta')
    // Nenhum switch além do "Ativar Inteligência"
    const switches = screen.getAllByRole('switch')
    expect(switches).toHaveLength(1)
    // Aviso de privacidade: nada sai da máquina
    expect(screen.getByText(/Nenhuma informação sai da sua máquina/)).toBeInTheDocument()
  })

  it('5. teste rápido mostra resposta e marca provider local', async () => {
    renderPage()
    await screen.findByText('IA pronta')
    fireEvent.change(screen.getByLabelText('Pergunta de teste'), {
      target: { value: 'Olá, responda OK' },
    })
    fireEvent.click(screen.getByRole('button', { name: /testar/i }))
    const result = await screen.findByTestId('ai-test-result')
    expect(result).toHaveTextContent('Resposta de teste da IA.')
    expect(result).toHaveTextContent('Respondido pela IA local.')
    expect(mockTest).toHaveBeenCalledWith('Olá, responda OK')
  })
})
