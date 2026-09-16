import { X } from 'lucide-react'
import { Button } from '@/components/ui/Button'
import { BrandMark } from '@/components/brand/BrandLogo'
import { NavTree } from './nav'

interface MobileSidebarProps {
  isOpen: boolean
  onClose: () => void
}

/**
 * Sidebar mobile — mesma árvore de 8 grupos do desktop (reorg F2).
 */
export function MobileSidebar({ isOpen, onClose }: MobileSidebarProps) {
  if (!isOpen) return null

  return (
    <>
      {/* Backdrop */}
      <div
        className="fixed inset-0 z-40 bg-black/50 md:hidden"
        onClick={onClose}
      />

      {/* Sidebar */}
      <aside className="fixed inset-y-0 left-0 z-50 w-64 bg-card md:hidden overflow-y-auto">
        <div className="flex h-16 items-center justify-between border-b border-border px-6">
          <BrandMark />
          <Button variant="ghost" size="icon" onClick={onClose}>
            <X className="h-5 w-5" />
          </Button>
        </div>

        <NavTree onNavigate={onClose} />
      </aside>
    </>
  )
}
