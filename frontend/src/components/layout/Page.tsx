import { type ReactNode } from 'react'
import { cn } from '@/lib/utils'

// ── Page ───────────────────────────────────────────────────

interface PageProps {
  children: ReactNode
  className?: string
}

export function Page({ children, className }: PageProps) {
  return (
    <div className={cn('space-y-6', className)}>
      {children}
    </div>
  )
}

// ── PageHeader ─────────────────────────────────────────────

interface PageHeaderProps {
  children: ReactNode
  className?: string
}

export function PageHeader({ children, className }: PageHeaderProps) {
  return (
    <div className={cn('flex flex-col gap-1 sm:flex-row sm:items-center sm:justify-between', className)}>
      {children}
    </div>
  )
}

// ── PageTitle ──────────────────────────────────────────────

interface PageTitleProps {
  children: ReactNode
  subtitle?: string
  className?: string
}

export function PageTitle({ children, subtitle, className }: PageTitleProps) {
  return (
    <div className={cn('', className)}>
      <h1 className="text-2xl font-bold tracking-tight text-foreground">{children}</h1>
      {subtitle && (
        <p className="text-sm text-muted-foreground mt-1">{subtitle}</p>
      )}
    </div>
  )
}

// ── PageActions ────────────────────────────────────────────

interface PageActionsProps {
  children: ReactNode
  className?: string
}

export function PageActions({ children, className }: PageActionsProps) {
  return (
    <div className={cn('flex items-center gap-2', className)}>
      {children}
    </div>
  )
}

// ── PageContent ────────────────────────────────────────────

interface PageContentProps {
  children: ReactNode
  className?: string
}

export function PageContent({ children, className }: PageContentProps) {
  return (
    <div className={cn('', className)}>
      {children}
    </div>
  )
}

// ── Section ────────────────────────────────────────────────

interface SectionProps {
  title?: string
  children: ReactNode
  className?: string
}

export function Section({ title, children, className }: SectionProps) {
  return (
    <div className={cn('space-y-4', className)}>
      {title && (
        <h2 className="text-lg font-semibold text-foreground">{title}</h2>
      )}
      {children}
    </div>
  )
}

// ── Stack / Inline ─────────────────────────────────────────

interface StackProps {
  children: ReactNode
  gap?: number
  className?: string
}

export function Stack({ children, gap = 4, className }: StackProps) {
  return (
    <div className={cn('flex flex-col', className)} style={{ gap: `${gap * 0.25}rem` }}>
      {children}
    </div>
  )
}

export function Inline({ children, gap = 2, className }: StackProps) {
  return (
    <div className={cn('flex items-center flex-wrap', className)} style={{ gap: `${gap * 0.25}rem` }}>
      {children}
    </div>
  )
}
