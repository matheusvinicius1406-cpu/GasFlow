import { useState, useCallback, createContext, useContext, type ReactNode } from 'react'
import { X, CheckCircle, AlertTriangle, Info, AlertCircle } from 'lucide-react'
import { cn } from '@/lib/utils'

// ── Types ──────────────────────────────────────────────────

type ToastType = 'success' | 'info' | 'warning' | 'error'

interface Toast {
  id: string
  type: ToastType
  title: string
  description?: string
  duration?: number
}

interface ToastContextType {
  toasts: Toast[]
  addToast: (toast: Omit<Toast, 'id'>) => void
  removeToast: (id: string) => void
}

// ── Context ────────────────────────────────────────────────

const ToastContext = createContext<ToastContextType | null>(null)

let toastCounter = 0

export function ToastProvider({ children }: { children: ReactNode }) {
  const [toasts, setToasts] = useState<Toast[]>([])

  const addToast = useCallback((toast: Omit<Toast, 'id'>) => {
    const id = `toast-${++toastCounter}`
    const newToast = { ...toast, id }
    setToasts((prev) => [...prev, newToast])

    // Auto-remove after duration
    const duration = toast.duration ?? 5000
    if (duration > 0) {
      setTimeout(() => {
        setToasts((prev) => prev.filter((t) => t.id !== id))
      }, duration)
    }
  }, [])

  const removeToast = useCallback((id: string) => {
    setToasts((prev) => prev.filter((t) => t.id !== id))
  }, [])

  return (
    <ToastContext.Provider value={{ toasts, addToast, removeToast }}>
      {children}
      <ToastContainer toasts={toasts} removeToast={removeToast} />
    </ToastContext.Provider>
  )
}

export function useToast() {
  const ctx = useContext(ToastContext)
  if (!ctx) throw new Error('useToast must be used within a ToastProvider')

  return {
    toast: ctx.addToast,
    success: (title: string, description?: string) => ctx.addToast({ type: 'success', title, description }),
    info: (title: string, description?: string) => ctx.addToast({ type: 'info', title, description }),
    warning: (title: string, description?: string) => ctx.addToast({ type: 'warning', title, description }),
    error: (title: string, description?: string) => ctx.addToast({ type: 'error', title, description }),
    dismiss: ctx.removeToast,
  }
}

// ── Icons ──────────────────────────────────────────────────

const TOAST_ICONS: Record<ToastType, typeof CheckCircle> = {
  success: CheckCircle,
  info: Info,
  warning: AlertTriangle,
  error: AlertCircle,
}

const TOAST_STYLES: Record<ToastType, string> = {
  success: 'border-success/20 bg-success/10 text-success',
  info: 'border-info/20 bg-info/10 text-info',
  warning: 'border-warning/20 bg-warning/10 text-warning',
  error: 'border-destructive/20 bg-destructive/10 text-destructive',
}

// ── Container ──────────────────────────────────────────────

function ToastContainer({
  toasts,
  removeToast,
}: {
  toasts: Toast[]
  removeToast: (id: string) => void
}) {
  if (toasts.length === 0) return null

  return (
    <div className="fixed bottom-4 right-4 z-[var(--z-toast)] flex flex-col gap-2 max-w-sm w-full pointer-events-none">
      {toasts.map((toast) => (
        <ToastItem key={toast.id} toast={toast} onDismiss={() => removeToast(toast.id)} />
      ))}
    </div>
  )
}

// ── Toast Item ─────────────────────────────────────────────

function ToastItem({ toast, onDismiss }: { toast: Toast; onDismiss: () => void }) {
  const Icon = TOAST_ICONS[toast.type]

  return (
    <div
      className={cn(
        'pointer-events-auto w-full rounded-lg border p-4 shadow-lg',
        'transition-all duration-200',
        TOAST_STYLES[toast.type]
      )}
      role="alert"
      aria-live="assertive"
    >
      <div className="flex items-start gap-3">
        <Icon className="h-5 w-5 mt-0.5 flex-shrink-0" />
        <div className="flex-1 min-w-0">
          <p className="text-sm font-medium text-foreground">{toast.title}</p>
          {toast.description && (
            <p className="mt-1 text-sm text-muted-foreground">{toast.description}</p>
          )}
        </div>
        <button
          onClick={onDismiss}
          className="flex-shrink-0 rounded-sm opacity-70 hover:opacity-100"
          aria-label="Fechar notificação"
        >
          <X className="h-4 w-4" />
        </button>
      </div>
    </div>
  )
}
