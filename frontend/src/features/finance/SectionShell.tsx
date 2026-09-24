import type { ReactNode } from 'react'
import { Inbox, type LucideIcon } from 'lucide-react'
import { Section } from '@/components/layout/Page'
import { EmptyState } from '@/components/ui/EmptyState'
import { ErrorState } from '@/components/ui/ErrorState'
import { LoadingSpinner } from '@/components/ui/LoadingSpinner'

interface SectionShellProps {
  title: string
  /** Estado de carregamento (o shell busca e injeta nas seções reais). */
  loading?: boolean
  /** Estado de erro — mostra ErrorState com retry. */
  error?: boolean
  /** Estado vazio (período sem dados) — mostra EmptyState. */
  empty?: boolean
  errorMessage?: string
  emptyIcon?: LucideIcon
  emptyTitle?: string
  emptyDescription?: string
  onRetry?: () => void
  children?: ReactNode
}

/**
 * Wrapper padrão de seção: título + estados loading / error / empty
 * padronizados (§2.2 do plano da Fase 2). Cada seção renderiza o conteúdo
 * aqui; sem fetch interno — o shell busca e injeta.
 */
export function SectionShell({
  title,
  loading,
  error,
  empty,
  errorMessage = 'Não foi possível carregar os dados.',
  emptyIcon = Inbox,
  emptyTitle = 'Sem dados no período',
  emptyDescription = 'Ajuste o período ou registre movimentações para ver esta seção.',
  onRetry,
  children,
}: SectionShellProps) {
  if (loading) {
    return (
      <Section title={title}>
        <div className="flex items-center justify-center py-16">
          <LoadingSpinner size="lg" />
        </div>
      </Section>
    )
  }
  if (error) {
    return (
      <Section title={title}>
        <ErrorState message={errorMessage} onRetry={onRetry} />
      </Section>
    )
  }
  if (empty) {
    return (
      <Section title={title}>
        <EmptyState icon={emptyIcon} title={emptyTitle} description={emptyDescription} />
      </Section>
    )
  }
  return <Section title={title}>{children}</Section>
}
