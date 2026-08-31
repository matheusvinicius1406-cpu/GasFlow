import { useState, useRef, useEffect, type ReactNode } from 'react'
import { cn } from '@/lib/utils'

interface TooltipProps {
  children: ReactNode
  content: ReactNode
  side?: 'top' | 'bottom' | 'left' | 'right'
  className?: string
}

export function Tooltip({ children, content, side = 'top', className }: TooltipProps) {
  const [show, setShow] = useState(false)
  const timeoutRef = useRef<ReturnType<typeof setTimeout>>(undefined)

  const showTooltip = () => {
    timeoutRef.current = setTimeout(() => setShow(true), 300)
  }

  const hideTooltip = () => {
    clearTimeout(timeoutRef.current)
    setShow(false)
  }

  useEffect(() => {
    return () => clearTimeout(timeoutRef.current)
  }, [])

  const positionClasses = {
    top: 'bottom-full left-1/2 -translate-x-1/2 mb-2',
    bottom: 'top-full left-1/2 -translate-x-1/2 mt-2',
    left: 'right-full top-1/2 -translate-y-1/2 mr-2',
    right: 'left-full top-1/2 -translate-y-1/2 ml-2',
  }

  return (
    <div
      className="relative inline-flex"
      onMouseEnter={showTooltip}
      onMouseLeave={hideTooltip}
      onFocus={showTooltip}
      onBlur={hideTooltip}
    >
      {children}
      {show && (
        <div
          role="tooltip"
          className={cn(
            'absolute z-[var(--z-tooltip)] px-3 py-1.5 text-xs font-medium text-foreground',
            'bg-popover border border-border rounded-md shadow-md',
            'pointer-events-none whitespace-nowrap',
            'animate-in fade-in-0',
            positionClasses[side],
            className
          )}
        >
          {content}
        </div>
      )}
    </div>
  )
}
