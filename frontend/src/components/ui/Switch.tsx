import { forwardRef, type InputHTMLAttributes } from 'react'
import { cn } from '@/lib/utils'

export interface SwitchProps extends Omit<InputHTMLAttributes<HTMLInputElement>, 'type' | 'size'> {
  checked?: boolean
}

const Switch = forwardRef<HTMLInputElement, SwitchProps>(
  ({ className, checked, ...props }, ref) => (
    <label className={cn('relative inline-flex items-center cursor-pointer', className)}>
      <input
        ref={ref}
        type="checkbox"
        className="sr-only peer"
        checked={checked}
        {...props}
      />
      <div className={cn(
        'w-9 h-5 rounded-full transition-colors',
        'bg-muted peer-checked:bg-primary',
        'after:content-[""] after:absolute after:top-0.5 after:left-[2px]',
        'after:bg-white after:rounded-full after:h-4 after:w-4 after:transition-all',
        'peer-checked:after:translate-x-full',
        'peer-focus-visible:ring-2 peer-focus-visible:ring-ring peer-focus-visible:ring-offset-2',
        'peer-disabled:cursor-not-allowed peer-disabled:opacity-50'
      )} />
    </label>
  )
)
Switch.displayName = 'Switch'

export { Switch }
