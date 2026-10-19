import { ShieldAlert } from 'lucide-react'
import { Link } from 'react-router-dom'
import { cn } from '@/lib/utils'
import { buttonVariants } from './Button'
import { EmptyState } from './EmptyState'

/** Título único do estado de permissão negada — mesma copy no guard de rota,
 *  na seção financeira e nos erros 403 de carregamento. */
export const PERMISSION_DENIED_TITLE = 'Sem permissão'

const DEFAULT_DESCRIPTION = 'Seu usuário não tem acesso a esta área.'

export function PermissionDenied({
  description = DEFAULT_DESCRIPTION,
  className,
}: {
  description?: string
  className?: string
}) {
  return (
    <EmptyState
      className={cn('py-16', className)}
      icon={ShieldAlert}
      title={PERMISSION_DENIED_TITLE}
      description={description}
      action={
        <Link to="/" className={cn(buttonVariants({ variant: 'outline' }))}>
          Ir para o início
        </Link>
      }
    />
  )
}
