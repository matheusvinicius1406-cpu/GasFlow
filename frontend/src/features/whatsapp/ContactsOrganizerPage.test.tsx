import { screen, waitFor, fireEvent } from '@testing-library/react'
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { renderWithProviders } from '@/test/utils'

vi.mock('@/lib/api/client', () => ({
  apiClient: {
    get: vi.fn(),
    post: vi.fn(),
    put: vi.fn(),
    patch: vi.fn(),
    delete: vi.fn(),
  },
}))

import { apiClient } from '@/lib/api/client'
import { ContactsOrganizerPage } from './ContactsOrganizerPage'

const conflicts = { total: 0, items: [] }

describe('ContactsOrganizerPage', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    vi.mocked(apiClient.get).mockResolvedValue({ data: conflicts })
  })

  it('gera preview com as regras selecionadas e mostra mudanças', async () => {
    vi.mocked(apiClient.post).mockResolvedValueOnce({
      data: {
        changes: [{ codigo: '000001', telefone: '11999990001', before: 'WA-maria', after: 'Maria', bairro: '' }],
        total: 1,
      },
    })

    renderWithProviders(<ContactsOrganizerPage />)

    fireEvent.click(screen.getByRole('button', { name: /gerar preview/i }))

    await waitFor(() => {
      expect(screen.getByText('Preview — 1 mudança(s)')).toBeInTheDocument()
    })
    expect(screen.getByText('WA-maria')).toBeInTheDocument()
    expect(screen.getByText('Maria')).toBeInTheDocument()
    expect(apiClient.post).toHaveBeenCalledWith('/whatsapp/contacts/organizer/rename-preview', {
      trim: true,
      strip_prefixes: true,
      case: 'title',
      pattern_bairro: false,
    })
  })

  it('aplica renomeação com os códigos do preview e mostra toast de sucesso', async () => {
    vi.mocked(apiClient.post).mockImplementation(async (url: string) => {
      if (url.endsWith('/rename-preview')) {
        return {
          data: {
            changes: [{ codigo: '000001', telefone: '11999990001', before: 'WA-maria', after: 'Maria', bairro: '' }],
            total: 1,
          },
        }
      }
      return { data: { renamed: 1, conflicts_skipped: 0, skipped_missing: 0 } }
    })

    renderWithProviders(<ContactsOrganizerPage />)

    fireEvent.click(screen.getByRole('button', { name: /gerar preview/i }))
    await waitFor(() => screen.getByText('Preview — 1 mudança(s)'))

    // Seleciona a mudança e aplica (o 2º checkbox é o da linha da tabela;
    // o 1º é o "Selecionar todas")
    const checkboxes = screen.getAllByRole('checkbox')
    fireEvent.click(checkboxes[checkboxes.length - 1]!)
    fireEvent.click(screen.getByRole('button', { name: /aplicar/i }))

    await waitFor(() => {
      expect(screen.getByText(/Renomeação aplicada: 1 contato/i)).toBeInTheDocument()
    })
    expect(apiClient.post).toHaveBeenCalledWith('/whatsapp/contacts/organizer/rename-apply', {
      rule: { trim: true, strip_prefixes: true, case: 'title', pattern_bairro: false },
      codes: ['000001'],
    })
  })

  it('roda backfill e mostra quantidade fixada', async () => {
    vi.mocked(apiClient.post).mockResolvedValueOnce({ data: { fixed: 3 } })

    renderWithProviders(<ContactsOrganizerPage />)

    fireEvent.click(screen.getByRole('button', { name: /backfill de códigos/i }))

    await waitFor(() => {
      expect(screen.getByText(/Backfill concluído: 3 código\(s\)/i)).toBeInTheDocument()
    })
  })

  it('lista conflitos na seção Revisar com badges', async () => {
    vi.mocked(apiClient.get).mockResolvedValue({
      data: {
        total: 2,
        items: [
          { codigo: '000001', nome: 'Maria Silva', telefone: '11999990001', issues: ['duplicate_name'], duplicates_with: ['000002'] },
          { codigo: '000002', nome: 'Curto', telefone: '999', issues: ['bad_phone'], duplicates_with: [] },
        ],
      },
    })

    renderWithProviders(<ContactsOrganizerPage />)

    await waitFor(() => {
      expect(screen.getByText('Maria Silva')).toBeInTheDocument()
    })
    expect(screen.getByText('Nome duplicado')).toBeInTheDocument()
    expect(screen.getByText('Telefone inválido')).toBeInTheDocument()
  })

  it('preview vazio mostra estado "Nada a mudar"', async () => {
    vi.mocked(apiClient.post).mockResolvedValueOnce({ data: { changes: [], total: 0 } })

    renderWithProviders(<ContactsOrganizerPage />)

    fireEvent.click(screen.getByRole('button', { name: /gerar preview/i }))

    await waitFor(() => {
      expect(screen.getByText('Nada a mudar')).toBeInTheDocument()
    })
  })
})
