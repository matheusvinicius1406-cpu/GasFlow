import { screen, waitFor, fireEvent } from '@testing-library/react'
import { describe, it, expect, vi, beforeEach, beforeAll } from 'vitest'
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
import { ContactsRenamerPage } from './ContactsRenamerPage'

const conflicts = { total: 0, items: [] }

const origemVazia = {
  por_status: { OK: 0, NAO_ENCONTRADO: 0, PENDENTE: 0, SEM_ENDERECO: 0 },
  por_origem: { osm: 0, cep: 0 },
  total_ruas_cache: 0,
  total_ruas_cep: 0,
  ruas_cep: [],
}

describe('ContactsRenamerPage', () => {
  beforeAll(() => {
    // jsdom não implementa os helpers de Blob usados no download.
    Object.defineProperty(URL, 'createObjectURL', { value: vi.fn(() => 'blob:mock'), writable: true })
    Object.defineProperty(URL, 'revokeObjectURL', { value: vi.fn(), writable: true })
  })

  beforeEach(() => {
    vi.clearAllMocks()
    // A página faz dois GETs de triagem — roteia por URL em vez de devolver
    // o mesmo payload para os dois.
    vi.mocked(apiClient.get).mockImplementation(async (url: string) => {
      if (url.includes('geocode-origem')) return { data: origemVazia }
      return { data: conflicts }
    })
  })

  it('gera a prévia paginada com a regra e os filtros atuais', async () => {
    vi.mocked(apiClient.post).mockResolvedValueOnce({
      data: {
        changes: [
          {
            codigo: '000001',
            telefone: '11999990001',
            before: 'Maria',
            after: '1= Travessa São Roque Nº 145 - CEP 66811-120 (Maria)',
            bairro: 'Centro',
          },
        ],
        total: 30,
        page: 1,
        page_size: 25,
        total_pages: 2,
      },
    })

    renderWithProviders(<ContactsRenamerPage />)

    fireEvent.click(screen.getByRole('button', { name: /gerar prévia/i }))

    await waitFor(() => {
      expect(screen.getByText('Prévia — 30 mudança(s)')).toBeInTheDocument()
    })
    expect(screen.getByText('1= Travessa São Roque Nº 145 - CEP 66811-120 (Maria)')).toBeInTheDocument()
    expect(screen.getByText('Página 1 de 2')).toBeInTheDocument()
    expect(apiClient.post).toHaveBeenCalledWith(
      '/whatsapp/contacts/organizer/rename-preview',
      { trim: true, strip_prefixes: true, case: null, pattern_bairro: false, pattern_endereco: true },
      { params: { page: 1, page_size: 25, search: undefined, bairro: undefined, status: undefined } },
    )
  })

  it('roda o job APPLY até concluir e mostra o progresso', async () => {
    vi.mocked(apiClient.post).mockImplementation(async (url: string) => {
      if (url === '/whatsapp/contacts/jobs') {
        return {
          data: {
            id: 'j1',
            tipo: 'APPLY',
            status: 'PENDENTE',
            total: 2,
            processados: 0,
            alterados: 0,
            restantes: 2,
            metrica: {},
            erro: null,
          },
        }
      }
      return {
        data: {
          id: 'j1',
          tipo: 'APPLY',
          status: 'CONCLUIDO',
          total: 2,
          processados: 2,
          alterados: 2,
          restantes: 0,
          metrica: {},
          erro: null,
        },
      }
    })

    renderWithProviders(<ContactsRenamerPage />)

    fireEvent.click(screen.getByRole('button', { name: /renomear/i }))

    await waitFor(() => {
      expect(screen.getByTestId('job-progress')).toBeInTheDocument()
    })
    await waitFor(() => {
      expect(screen.getByText(/Job APPLY concluido: 2 processado/i)).toBeInTheDocument()
    })
    expect(apiClient.post).toHaveBeenCalledWith('/whatsapp/contacts/jobs', {
      tipo: 'APPLY',
      filtro: { search: undefined, bairro: undefined, status: undefined },
      regra: { trim: true, strip_prefixes: true, case: null, pattern_bairro: false, pattern_endereco: true },
    })
    expect(apiClient.post).toHaveBeenCalledWith('/whatsapp/contacts/jobs/j1/process')
  })

  it('lista a triagem de conflitos', async () => {
    vi.mocked(apiClient.get).mockResolvedValue({
      data: {
        total: 1,
        items: [
          { codigo: '000001', nome: 'Maria Silva', telefone: '11999990001', issues: ['duplicate_name'] },
        ],
      },
    })

    renderWithProviders(<ContactsRenamerPage />)

    await waitFor(() => {
      expect(screen.getByText('Maria Silva')).toBeInTheDocument()
    })
    expect(screen.getByText('Nome duplicado')).toBeInTheDocument()
  })

  it('mostra a origem do geocode (OSM × fallback de CEP)', async () => {
    vi.mocked(apiClient.get).mockImplementation(async (url: string) => {
      if (url.includes('geocode-origem')) {
        return {
          data: {
            por_status: { OK: 4, NAO_ENCONTRADO: 0, PENDENTE: 1, SEM_ENDERECO: 0 },
            por_origem: { osm: 3, cep: 1 },
            total_ruas_cache: 4,
            total_ruas_cep: 1,
            ruas_cep: [
              {
                rua: 'Passagem Ivan Leão',
                bairro: 'Agulha',
                cidade: 'Belém',
                uf: 'PA',
                cep: '66811-120',
                provider: 'brasilapi',
              },
            ],
          },
        }
      }
      return { data: conflicts }
    })

    renderWithProviders(<ContactsRenamerPage />)

    await waitFor(() => {
      expect(screen.getByTestId('origem-geocode')).toBeInTheDocument()
    })
    expect(screen.getByTestId('origem-osm')).toHaveTextContent('OSM: 3 rua(s)')
    expect(screen.getByTestId('origem-cep')).toHaveTextContent('CEP (fallback): 1 rua(s)')
    expect(screen.getByText('Passagem Ivan Leão — Agulha')).toBeInTheDocument()
    expect(screen.getByText('BrasilAPI')).toBeInTheDocument()
  })

  it('exporta o .vcf no formato de rota', async () => {
    vi.mocked(apiClient.get).mockImplementation(async (url: string) => {
      if (url.includes('export-vcf')) return { data: new Blob(['vcf']) }
      return { data: conflicts }
    })

    renderWithProviders(<ContactsRenamerPage />)

    fireEvent.click(screen.getByRole('button', { name: /exportar .vcf renomeado/i }))

    await waitFor(() => {
      expect(apiClient.get).toHaveBeenCalledWith('/whatsapp/contacts/export-vcf', {
        params: { formatar_rota: true },
        responseType: 'blob',
      })
    })
  })
})
