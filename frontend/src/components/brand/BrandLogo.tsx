import { Flame } from 'lucide-react'
import { cn } from '@/lib/utils'
import { useTheme } from '@/lib/theme'

// ── BrandLogo ──────────────────────────────────────────────

interface BrandLogoProps {
  className?: string
  size?: 'sm' | 'md' | 'lg'
}

export function BrandLogo({ className, size = 'md' }: BrandLogoProps) {
  const { branding } = useTheme()
  const sizeClasses = {
    sm: 'h-5 w-5',
    md: 'h-6 w-6',
    lg: 'h-8 w-8',
  }

  if (branding.logoUrl) {
    return (
      <img
        src={branding.logoUrl}
        alt={`${branding.companyName} logo`}
        className={cn('object-contain', sizeClasses[size], className)}
      />
    )
  }

  return <Flame className={cn('text-primary', sizeClasses[size], className)} />
}

// ── BrandName ──────────────────────────────────────────────

interface BrandNameProps {
  className?: string
  size?: 'sm' | 'md' | 'lg'
  showTagline?: boolean
}

export function BrandName({ className, size = 'md', showTagline = false }: BrandNameProps) {
  const { branding } = useTheme()
  const sizeClasses = {
    sm: 'text-base',
    md: 'text-lg',
    lg: 'text-2xl',
  }

  return (
    <div className={cn('flex flex-col', className)}>
      <span className={cn('font-bold text-foreground', sizeClasses[size])}>
        {branding.companyName}
      </span>
      {showTagline && branding.mode === 'custom' && (
        <span className="text-xs text-muted-foreground">Powered by GasFlow</span>
      )}
    </div>
  )
}

// ── BrandMark ──────────────────────────────────────────────

interface BrandMarkProps {
  className?: string
}

export function BrandMark({ className }: BrandMarkProps) {
  return (
    <div className={cn('flex items-center gap-2', className)}>
      <BrandLogo size="md" />
      <BrandName size="md" showTagline />
    </div>
  )
}

// ── BrandBadge ─────────────────────────────────────────────

interface BrandBadgeProps {
  className?: string
}

export function BrandBadge({ className }: BrandBadgeProps) {
  const { branding } = useTheme()

  if (branding.mode === 'gasflow') return null

  return (
    <span
      className={cn(
        'text-[10px] text-muted-foreground/60 tracking-wider uppercase',
        className
      )}
    >
      Powered by GasFlow
    </span>
  )
}
