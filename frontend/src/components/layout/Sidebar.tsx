import { NavTree } from './nav'
import { BrandMark } from '@/components/brand/BrandLogo'

/**
 * Sidebar desktop — 8 grupos (reorg F2). A árvore de navegação vive em
 * `nav.tsx` (fonte única compartilhada com o MobileSidebar).
 */
export function Sidebar() {
  return (
    <aside className="hidden w-64 border-r border-border bg-card md:flex md:flex-col">
      <div className="flex h-16 shrink-0 items-center gap-2 border-b border-border px-6">
        <BrandMark />
      </div>

      <div className="flex-1 overflow-y-auto py-2">
        <NavTree />
      </div>
    </aside>
  )
}
