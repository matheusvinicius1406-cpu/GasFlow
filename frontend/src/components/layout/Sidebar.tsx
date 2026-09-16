import { NavTree } from './nav'
import { BrandMark } from '@/components/brand/BrandLogo'

/**
 * Sidebar desktop — 8 grupos (reorg F2). A árvore de navegação vive em
 * `nav.tsx` (fonte única compartilhada com o MobileSidebar).
 */
export function Sidebar() {
  return (
    <aside className="hidden w-64 border-r border-border bg-card md:block">
      <div className="flex h-16 items-center gap-2 border-b border-border px-6">
        <BrandMark />
      </div>

      <div className="h-[calc(100vh-4rem)] overflow-y-auto">
        <NavTree />
      </div>
    </aside>
  )
}
