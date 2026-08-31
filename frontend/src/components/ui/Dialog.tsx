import { useState, useEffect, useCallback, useRef, createContext, useContext, type ReactNode } from 'react'
import { X } from 'lucide-react'
import { cn } from '@/lib/utils'
import { Button } from './Button'

// ── Context ────────────────────────────────────────────────

interface DialogContextType {
  open: boolean
  onOpenChange: (open: boolean) => void
}

const DialogContext = createContext<DialogContextType | null>(null)

function useDialogContext() {
  const ctx = useContext(DialogContext)
  if (!ctx) throw new Error('Dialog components must be used within <Dialog>')
  return ctx
}

// ── Dialog ─────────────────────────────────────────────────

interface DialogProps {
  open?: boolean
  onOpenChange?: (open: boolean) => void
  defaultOpen?: boolean
  children: ReactNode
}

export function Dialog({ open: controlledOpen, onOpenChange, defaultOpen = false, children }: DialogProps) {
  const [uncontrolledOpen, setUncontrolledOpen] = useState(defaultOpen)
  const isControlled = controlledOpen !== undefined
  const open = isControlled ? controlledOpen : uncontrolledOpen

  const handleOpenChange = useCallback(
    (value: boolean) => {
      if (!isControlled) setUncontrolledOpen(value)
      onOpenChange?.(value)
    },
    [isControlled, onOpenChange]
  )

  return (
    <DialogContext.Provider value={{ open, onOpenChange: handleOpenChange }}>
      {children}
    </DialogContext.Provider>
  )
}

// ── DialogTrigger ──────────────────────────────────────────

interface DialogTriggerProps {
  children: ReactNode
  asChild?: boolean
  className?: string
}

export function DialogTrigger({ children, className }: DialogTriggerProps) {
  const { onOpenChange } = useDialogContext()
  return (
    <button className={className} onClick={() => onOpenChange(true)}>
      {children}
    </button>
  )
}

// ── DialogContent ──────────────────────────────────────────

interface DialogContentProps {
  children: ReactNode
  className?: string
  showClose?: boolean
}

export function DialogContent({ children, className, showClose = true }: DialogContentProps) {
  const { open, onOpenChange } = useDialogContext()
  const contentRef = useRef<HTMLDivElement>(null)
  const previousFocusRef = useRef<HTMLElement | null>(null)

  // Focus management
  useEffect(() => {
    if (open) {
      previousFocusRef.current = document.activeElement as HTMLElement
      // Focus the dialog after render
      requestAnimationFrame(() => {
        contentRef.current?.focus()
      })
    } else {
      previousFocusRef.current?.focus()
    }
  }, [open])

  // ESC to close
  useEffect(() => {
    if (!open) return
    const handler = (e: KeyboardEvent) => {
      if (e.key === 'Escape') onOpenChange(false)
    }
    document.addEventListener('keydown', handler)
    return () => document.removeEventListener('keydown', handler)
  }, [open, onOpenChange])

  // Prevent body scroll when open
  useEffect(() => {
    if (open) {
      document.body.style.overflow = 'hidden'
      return () => { document.body.style.overflow = '' }
    }
  }, [open])

  if (!open) return null

  return (
    <>
      {/* Overlay */}
      <div
        className="fixed inset-0 z-[var(--z-modal)] bg-black/60 backdrop-blur-sm"
        onClick={() => onOpenChange(false)}
        aria-hidden="true"
      />

      {/* Content */}
      <div className="fixed inset-0 z-[var(--z-modal)] flex items-center justify-center p-4">
        <div
          ref={contentRef}
          role="dialog"
          aria-modal="true"
          tabIndex={-1}
          className={cn(
            'relative w-full max-w-lg rounded-xl border border-border bg-card p-6 shadow-xl',
            'animate-in fade-in-0 zoom-in-95',
            className
          )}
          onClick={(e) => e.stopPropagation()}
        >
          {children}
          {showClose && (
            <button
              className="absolute right-4 top-4 rounded-sm opacity-70 transition-opacity hover:opacity-100"
              onClick={() => onOpenChange(false)}
              aria-label="Fechar"
            >
              <X className="h-4 w-4" />
            </button>
          )}
        </div>
      </div>
    </>
  )
}

// ── DialogHeader ───────────────────────────────────────────

export function DialogHeader({ children, className }: { children: ReactNode; className?: string }) {
  return (
    <div className={cn('flex flex-col space-y-1.5 text-center sm:text-left', className)}>
      {children}
    </div>
  )
}

// ── DialogTitle ────────────────────────────────────────────

export function DialogTitle({ children, className }: { children: ReactNode; className?: string }) {
  return (
    <h2 className={cn('text-lg font-semibold leading-none tracking-tight text-foreground', className)}>
      {children}
    </h2>
  )
}

// ── DialogDescription ──────────────────────────────────────

export function DialogDescription({ children, className }: { children: ReactNode; className?: string }) {
  return (
    <p className={cn('text-sm text-muted-foreground', className)}>
      {children}
    </p>
  )
}

// ── DialogFooter ───────────────────────────────────────────

export function DialogFooter({ children, className }: { children: ReactNode; className?: string }) {
  return (
    <div className={cn('flex flex-col-reverse sm:flex-row sm:justify-end sm:space-x-2 mt-4', className)}>
      {children}
    </div>
  )
}

// ── DialogClose ────────────────────────────────────────────

export function DialogClose({ children, className }: { children: ReactNode; className?: string }) {
  const { onOpenChange } = useDialogContext()
  return (
    <Button variant="outline" className={className} onClick={() => onOpenChange(false)}>
      {children}
    </Button>
  )
}
