import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'

const { perms, toast, exportMock, eraseMock } = vi.hoisted(() => ({
  perms: { values: [] as string[] },
  toast: { success: vi.fn(), error: vi.fn(), info: vi.fn(), warning: vi.fn() },
  exportMock: vi.fn(),
  eraseMock: vi.fn(),
}))

vi.mock('@/features/auth', () => ({
  useAuth: () => ({
    hasPermission: (permission: string) => perms.values.includes(permission),
  }),
}))

vi.mock('@/components/ui/Toast', () => ({
  useToast: () => toast,
}))

vi.mock('@/lib/api/client', () => ({
  api: {
    clients: {
      exportData: exportMock,
      eraseData: eraseMock,
    },
  },
}))

import { ClientPrivacyCard } from '../ClientPrivacyCard'

function renderCard(onErased = vi.fn()) {
  return { onErased, ...render(
    <ClientPrivacyCard customerCodigo="CLT-1" customerNome="João da Silva" onErased={onErased} />,
  ) }
}

describe('ClientPrivacyCard (LGPD)', () => {
  beforeEach(() => {
    perms.values = []
    vi.clearAllMocks()
    exportMock.mockResolvedValue({ data: { cliente: { codigo: 'CLT-1' } } })
    eraseMock.mockResolvedValue({ data: { registros_afetados: 1 } })
    Object.defineProperty(URL, 'createObjectURL', { value: vi.fn(() => 'blob:mock'), writable: true })
    Object.defineProperty(URL, 'revokeObjectURL', { value: vi.fn(), writable: true })
    vi.spyOn(HTMLAnchorElement.prototype, 'click').mockImplementation(() => undefined)
  })

  it('não renderiza nada sem permissão de cliente', () => {
    const { container } = renderCard()
    expect(container).toBeEmptyDOMElement()
  })

  it('exporta os dados do titular com customer.write', async () => {
    perms.values = ['customer.write']
    renderCard()

    fireEvent.click(screen.getByRole('button', { name: /Exportar dados/ }))

    await waitFor(() => expect(exportMock).toHaveBeenCalledWith('CLT-1'))
    expect(URL.createObjectURL).toHaveBeenCalled()
    expect(toast.success).toHaveBeenCalledWith('Dados exportados', expect.stringContaining('João da Silva'))
    expect(screen.queryByRole('button', { name: /Anonimizar dados/ })).not.toBeInTheDocument()
  })

  it('anonimiza só após digitar o código exato do cliente', async () => {
    perms.values = ['customer.*']
    const prompt = vi.spyOn(window, 'prompt').mockReturnValue('CLT-1')
    const { onErased } = renderCard()

    fireEvent.click(screen.getByRole('button', { name: /Anonimizar dados de João da Silva/ }))

    await waitFor(() => expect(eraseMock).toHaveBeenCalledWith('CLT-1'))
    expect(prompt).toHaveBeenCalled()
    expect(onErased).toHaveBeenCalledTimes(1)
    expect(toast.success).toHaveBeenCalled()
  })

  it('não apaga nada quando o código digitado não confere', () => {
    perms.values = ['customer.*']
    vi.spyOn(window, 'prompt').mockReturnValue('CLT-2')
    const { onErased } = renderCard()

    fireEvent.click(screen.getByRole('button', { name: /Anonimizar dados de João da Silva/ }))

    expect(eraseMock).not.toHaveBeenCalled()
    expect(onErased).not.toHaveBeenCalled()
    expect(toast.error).toHaveBeenCalledWith('Confirmação inválida', expect.any(String))
  })

  it('trata 403 da anonimização sem prometer sucesso', async () => {
    perms.values = ['customer.*']
    vi.spyOn(window, 'prompt').mockReturnValue('CLT-1')
    eraseMock.mockRejectedValue({ response: { status: 403 } })
    renderCard()

    fireEvent.click(screen.getByRole('button', { name: /Anonimizar dados de João da Silva/ }))

    await waitFor(() =>
      expect(toast.error).toHaveBeenCalledWith('Sem permissão', expect.any(String)),
    )
  })
})
