import { screen, waitFor, fireEvent, act } from '@testing-library/react'
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { renderWithProviders } from '@/test/utils'

const mockPost = vi.fn()
const mockGet = vi.fn()
vi.mock('@/lib/api/client', () => ({
  apiClient: {
    post: (...args: unknown[]) => mockPost(...args),
    get: (...args: unknown[]) => mockGet(...args),
  },
}))

import { InviteSignupPage } from '../InviteSignupPage'
import { clearAllPending, loadPending, savePending } from '../pendingSignup'

const TOKEN = 'GF-INV-abc123def456ghi789'

const SIGNUP_OK = {
  data: {
    status: 'created',
    referred_codigo: '000123',
    coupon_code: 'BEMVINDO-000123-A1B2C3',
    coupon_value: 10,
    coupon_valid_until: '2026-12-18T00:00:00',
    message: 'Cadastro realizado! Seu cupom de boas-vindas já está disponível.',
  },
}

/** Erro de rede (túnel caído): axiosError sem `response`. */
const NETWORK_ERROR = new Error('Network Error')

function renderAtCadastro(token: string) {
  return renderWithProviders(<InviteSignupPage />, { route: `/cadastro?token=${encodeURIComponent(token)}` })
}

async function fillForm() {
  await screen.findByText('Cadastro por convite')
  fireEvent.change(screen.getByLabelText(/nome completo/i), { target: { value: 'Maria Souza' } })
  fireEvent.change(screen.getByLabelText('WhatsApp'), { target: { value: '(11) 98888-7777' } })
  fireEvent.change(screen.getByLabelText(/^rua/i), { target: { value: 'Rua das Flores' } })
  fireEvent.change(screen.getByLabelText(/número/i), { target: { value: '120' } })
  fireEvent.change(screen.getByLabelText(/bairro/i), { target: { value: 'Jardim América' } })
  fireEvent.click(screen.getByRole('checkbox'))
}

function seedPending(payloadOverrides: Record<string, unknown> = {}) {
  return savePending(TOKEN, {
    inviteToken: TOKEN,
    name: 'Maria Souza',
    phone: '11988887777',
    rua: 'Rua das Flores',
    numero: '120',
    bairro: 'Jardim América',
    lgpdConsent: true,
    ...payloadOverrides,
  })
}

describe('InviteSignupPage', () => {
  beforeEach(() => {
    mockPost.mockReset()
    mockGet.mockReset()
    // Default: convite válido (a página consulta antes de mostrar o formulário)
    mockGet.mockResolvedValue({ data: { valid: true, reason: 'ok', coupon_value: 10, validity_days: 90 } })
    clearAllPending()
  })

  it('mostra estado de convite inválido para token sem prefixo GF-INV-', () => {
    renderAtCadastro('token-qualquer')
    expect(screen.getByText('Convite inválido')).toBeInTheDocument()
    expect(screen.queryByText('Cadastro por convite')).not.toBeInTheDocument()
  })

  it('renderiza formulário com token válido', async () => {
    renderAtCadastro(TOKEN)
    expect(await screen.findByText('Cadastro por convite')).toBeInTheDocument()
    // Valor do cupom vem da consulta do convite
    expect(screen.getByText(/você ganha R\$ 10\.00 em cupom/i)).toBeInTheDocument()
    expect(screen.getByLabelText(/nome completo/i)).toBeInTheDocument()
    expect(screen.getByLabelText('WhatsApp')).toBeInTheDocument()
    expect(screen.getByLabelText(/bairro/i)).toBeInTheDocument()
    // Consentimento LGPD presente
    expect(screen.getByRole('checkbox')).toBeInTheDocument()
  })

  it('submete cadastro e mostra cupom gerado', async () => {
    mockPost.mockResolvedValue({
      data: {
        status: 'created',
        referred_codigo: '000123',
        coupon_code: 'BEMVINDO-000123-A1B2C3',
        coupon_value: 10,
        coupon_valid_until: '2026-12-18T00:00:00',
        message: 'Cadastro realizado! Seu cupom de boas-vindas já está disponível.',
      },
    })

    renderAtCadastro(TOKEN)
    await fillForm()

    fireEvent.click(screen.getByRole('button', { name: /criar conta/i }))

    await waitFor(() => {
      expect(screen.getByText('Cadastro realizado!')).toBeInTheDocument()
    })
    expect(screen.getByText('BEMVINDO-000123-A1B2C3')).toBeInTheDocument()
    // Payload com alias esperado pela API
    expect(mockPost).toHaveBeenCalledWith('/public/referral/signup', expect.objectContaining({ inviteToken: TOKEN, lgpdConsent: true }))
  })

  it('não submete sem consentimento LGPD (botão desabilitado)', async () => {
    renderAtCadastro(TOKEN)
    await screen.findByText('Cadastro por convite')
    fireEvent.change(screen.getByLabelText(/nome completo/i), { target: { value: 'Maria Souza' } })
    fireEvent.change(screen.getByLabelText('WhatsApp'), { target: { value: '(11) 98888-7777' } })
    fireEvent.change(screen.getByLabelText(/^rua/i), { target: { value: 'Rua das Flores' } })
    fireEvent.change(screen.getByLabelText(/número/i), { target: { value: '120' } })
    fireEvent.change(screen.getByLabelText(/bairro/i), { target: { value: 'Jardim América' } })

    expect(screen.getByRole('button', { name: /criar conta/i })).toBeDisabled()
    expect(mockPost).not.toHaveBeenCalled()
  })

  it('mensagem amigável quando convite já foi usado (409)', async () => {
    mockPost.mockRejectedValue({
      response: { status: 409, data: { detail: 'Este token de convite já foi utilizado.' } },
    })

    renderAtCadastro(TOKEN)
    await fillForm()
    fireEvent.click(screen.getByRole('button', { name: /criar conta/i }))

    await waitFor(() => {
      expect(screen.getByRole('alert')).toHaveTextContent(/já foi utilizado/i)
    })
  })

  it('excesso de tentativas (429): guarda os dados e avisa em vez de erro final', async () => {
    mockPost.mockRejectedValue({ response: { status: 429, data: { detail: 'Muitas tentativas...' } } })

    renderAtCadastro(TOKEN)
    await fillForm()
    fireEvent.click(screen.getByRole('button', { name: /criar conta/i }))

    await waitFor(() => {
      expect(screen.getByRole('status')).toHaveTextContent(/muitas tentativas deste número/i)
    })
    expect(screen.getByRole('status')).toHaveTextContent(/cerca de 1 hora/i)
    // Nada de erro final: o cadastro fica guardado para reenviar
    expect(screen.queryByRole('alert')).not.toBeInTheDocument()
    expect(loadPending(TOKEN)).not.toBeNull()
  })

  it('loja fora do ar: guarda o cadastro e reenvia sozinho quando a conexão volta', async () => {
    mockPost.mockRejectedValueOnce(NETWORK_ERROR).mockResolvedValueOnce(SIGNUP_OK)

    renderAtCadastro(TOKEN)
    await fillForm()
    fireEvent.click(screen.getByRole('button', { name: /criar conta/i }))

    await waitFor(() => {
      expect(screen.getByRole('status')).toHaveTextContent(/a loja não respondeu agora/i)
    })
    const saved = loadPending(TOKEN)
    expect(saved?.payload.name).toBe('Maria Souza')
    expect(saved?.payload.phone).toBe('(11) 98888-7777')

    // Internet voltou → reenvia sem a pessoa refazer nada
    await act(async () => {
      window.dispatchEvent(new Event('online'))
    })

    await waitFor(() => {
      expect(screen.getByText('Cadastro realizado!')).toBeInTheDocument()
    })
    expect(screen.getByText('BEMVINDO-000123-A1B2C3')).toBeInTheDocument()
    expect(loadPending(TOKEN)).toBeNull()
  })

  it('reabrir o link com cadastro pendente preenche o formulário de novo', async () => {
    seedPending()
    mockPost.mockRejectedValue(NETWORK_ERROR) // loja ainda fora

    renderAtCadastro(TOKEN)

    // Reenvia na hora e devolve o que a pessoa já tinha digitado
    await waitFor(() => {
      expect(mockPost).toHaveBeenCalledWith('/public/referral/signup', expect.objectContaining({ inviteToken: TOKEN }))
    })
    expect(screen.getByLabelText(/nome completo/i)).toHaveValue('Maria Souza')
    expect(screen.getByLabelText('WhatsApp')).toHaveValue('11988887777')
    expect(screen.getByLabelText(/bairro/i)).toHaveValue('Jardim América')
    expect(screen.getByRole('checkbox')).toBeChecked()
    expect(screen.getByRole('status')).toHaveTextContent(/a loja não respondeu agora/i)
  })

  it('reabrir o link com cadastro pendente conclui sozinho quando a loja voltou', async () => {
    seedPending()
    mockPost.mockResolvedValue(SIGNUP_OK)

    renderAtCadastro(TOKEN)

    await waitFor(() => {
      expect(screen.getByText('Cadastro realizado!')).toBeInTheDocument()
    })
    expect(loadPending(TOKEN)).toBeNull()
  })

  it('falha definitiva (409) limpa o cadastro guardado anterior', async () => {
    seedPending()
    mockPost.mockRejectedValue({ response: { status: 409, data: { detail: 'já foi utilizado' } } })

    renderAtCadastro(TOKEN)

    await waitFor(() => {
      expect(screen.getByRole('alert')).toHaveTextContent(/já foi utilizado/i)
    })
    expect(loadPending(TOKEN)).toBeNull()
  })

  it('mensagem amigável para convite inexistente (404)', async () => {
    // Consulta não respondeu (segue para o formulário) e o envio descobriu que
    // o convite não existe — o caso realista de 404 no submit hoje.
    mockGet.mockRejectedValue(NETWORK_ERROR)
    mockPost.mockRejectedValue({ response: { status: 404, data: { detail: 'Token de convite inválido ou expirado.' } } })

    renderAtCadastro(TOKEN)
    await fillForm()
    fireEvent.click(screen.getByRole('button', { name: /criar conta/i }))

    await waitFor(() => {
      expect(screen.getByRole('alert')).toHaveTextContent(/convite não encontrado/i)
    })
  })

  it('avisa que o convite já foi usado antes de pedir qualquer dado', async () => {
    mockGet.mockResolvedValue({ data: { valid: false, reason: 'already_used' } })

    renderAtCadastro(TOKEN)

    expect(await screen.findByText('Este convite já foi usado')).toBeInTheDocument()
    // Nada de formulário: o cliente não preenche nada à toa
    expect(screen.queryByLabelText(/nome completo/i)).not.toBeInTheDocument()
    expect(mockPost).not.toHaveBeenCalled()
  })

  it('avisa convite não encontrado antes do formulário', async () => {
    mockGet.mockResolvedValue({ data: { valid: false, reason: 'not_found' } })

    renderAtCadastro(TOKEN)

    expect(await screen.findByText('Convite não encontrado')).toBeInTheDocument()
    expect(screen.queryByLabelText(/nome completo/i)).not.toBeInTheDocument()
  })

  it('quem já se cadastrou recupera o cupom informando o mesmo WhatsApp', async () => {
    mockGet.mockResolvedValue({ data: { valid: false, reason: 'already_used' } })
    mockPost.mockResolvedValue({
      data: {
        ...SIGNUP_OK.data,
        status: 'replayed',
        message: 'Seu cadastro já estava concluído — este é o seu cupom.',
      },
    })

    renderAtCadastro(TOKEN)
    fireEvent.click(await screen.findByRole('button', { name: /quero ver meu cupom/i }))

    await fillForm()
    fireEvent.click(screen.getByRole('button', { name: /criar conta/i }))

    await waitFor(() => {
      expect(screen.getByText('Seu cadastro já estava concluído — este é o seu cupom.')).toBeInTheDocument()
    })
    expect(screen.getByText('BEMVINDO-000123-A1B2C3')).toBeInTheDocument()
  })

  it('consulta fora do ar não bloqueia o formulário', async () => {
    mockGet.mockRejectedValue(NETWORK_ERROR)

    renderAtCadastro(TOKEN)

    expect(await screen.findByText('Cadastro por convite')).toBeInTheDocument()
    expect(screen.getByLabelText(/nome completo/i)).toBeInTheDocument()
  })

  it('com cadastro pendente nem consulta o convite (o reenvio pode tê-lo consumido)', async () => {
    seedPending()
    mockPost.mockResolvedValue(SIGNUP_OK)

    renderAtCadastro(TOKEN)

    await waitFor(() => {
      expect(screen.getByText('Cadastro realizado!')).toBeInTheDocument()
    })
    expect(mockGet).not.toHaveBeenCalled()
  })
})
