import { type ReactNode } from 'react'
import { AlertTriangle, CheckCircle, Info, AlertCircle } from 'lucide-react'
import { cn } from '@/lib/utils'

interface AlertProps {
  variant?: 'default' | 'success' | 'warning' | 'error' | 'info'
  title?: string
  children: ReactNode
  className?: string
}

const variantConfig = {
  default: { icon: Info, className: 'bg-muted border-border text-foreground' },
  success: { icon: CheckCircle, className: 'bg-success/10 border-success/20 text-success' },
  warning: { icon: AlertTriangle, className: 'bg-warning/10 border-warning/20 text-warning' },
  error: { icon: AlertCircle, className: 'bg-destructive/10 border-destructive/20 text-destructive' },
  info: { icon: Info, className: 'bg-info/10 border-info/20 text-info' },
}

export function Alert({ variant = 'default', title, children, className }: AlertProps) {
  const config = variantConfig[variant]
  const Icon = config.icon

  return (
    <div
      role="alert"
      className={cn(
        'relative w-full rounded-lg border p-4',
        config.className,
        className
      )}
    >
      <div className="flex items-start gap-3">
        <Icon className="h-5 w-5 mt-0.5 flex-shrink-0" />
        <div className="flex-1">
          {title && <h5 className="mb-1 font-medium leading-none">{title}</h5>}
          <div className="text-sm opacity-90">{children}</div>
        </div>
      </div>
    </div>
  )
}
