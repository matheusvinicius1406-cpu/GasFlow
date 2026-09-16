import { screen, waitFor, fireEvent } from '@testing-library/react'
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

import { CouponsPage } from '../CouponsPage'

describe('CouponsPage invite link', () => {
  beforeEach(() => {
    mockPost.mockReset()
    mockGet.mockReset()
    mockGet.mockResolvedValue({ data: { coupons: [], total: 0 } })
  })

  it('renders generate invite button', async () => {
    renderWithProviders(<CouponsPage />)
    await waitFor(() => {
      expect(screen.getByText('Gerar link de convite')).toBeInTheDocument()
    })
  })

  it('opens modal and generates token', async () => {
    mockPost.mockResolvedValue({ data: { invite_token: 'GF-INV-test123' } })

    renderWithProviders(<CouponsPage />)

    await waitFor(() => {
      expect(screen.getByText('Gerar link de convite')).toBeInTheDocument()
    })

    screen.getByText('Gerar link de convite').click()

    await waitFor(() => {
      expect(screen.getByPlaceholderText(/código do cliente/i)).toBeInTheDocument()
    })

    const codigoInput = screen.getByPlaceholderText(/código do cliente/i)
    fireEvent.change(codigoInput, { target: { value: '000001' } })

    const gerarBtn = screen.getByText('Gerar token')
    expect(gerarBtn).not.toBeDisabled()
    gerarBtn.click()

    await waitFor(() => {
      expect(mockPost).toHaveBeenCalledWith('/coupons/generate-invite-token', {
        client_codigo: '000001',
      })
    })
    expect(screen.getByText('GF-INV-test123')).toBeInTheDocument()
  })

  it('calls API on failed token generation', async () => {
    mockPost.mockRejectedValue(new Error('fail'))

    renderWithProviders(<CouponsPage />)

    await waitFor(() => {
      expect(screen.getByText('Gerar link de convite')).toBeInTheDocument()
    })

    screen.getByText('Gerar link de convite').click()

    await waitFor(() => {
      expect(screen.getByPlaceholderText(/código do cliente/i)).toBeInTheDocument()
    })

    fireEvent.change(screen.getByPlaceholderText(/código do cliente/i), {
      target: { value: '999999' },
    })

    screen.getByText('Gerar token').click()

    await waitFor(() => {
      expect(mockPost).toHaveBeenCalled()
    })
  })
})
