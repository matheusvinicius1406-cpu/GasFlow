import { X } from 'lucide-react'
import { NavLink } from 'react-router-dom'
import {
  LayoutDashboard,
  ShoppingCart,
  Users,
  MessageSquare,
  Truck,
  UserCog,
  Package,
  Warehouse,
  DollarSign,
  BarChart3,
  Brain,
  Settings,
  Filter,
} from 'lucide-react'
import { cn } from '@/lib/utils'
import { Button } from '@/components/ui/Button'
import { BrandMark } from '@/components/brand/BrandLogo'

interface MobileSidebarProps {
  isOpen: boolean
  onClose: () => void
}

const navItems = [
  { label: 'Dashboard', href: '/', icon: LayoutDashboard },
  { label: 'Pedidos', href: '/orders', icon: ShoppingCart },
  { label: 'Clientes', href: '/customers', icon: Users },
  { label: 'Segmentos', href: '/segments', icon: Filter },
  { label: 'WhatsApp', href: '/whatsapp', icon: MessageSquare },
  { label: 'Entregas', href: '/deliveries', icon: Truck },
  { label: 'Motoristas', href: '/drivers', icon: UserCog },
  { label: 'Produtos', href: '/products', icon: Package },
  { label: 'Estoque', href: '/inventory', icon: Warehouse },
  { label: 'Financeiro', href: '/finance', icon: DollarSign },
  { label: 'Relatórios', href: '/reports', icon: BarChart3 },
  { label: 'Inteligência', href: '/intelligence', icon: Brain },
  { label: 'Configurações', href: '/settings', icon: Settings },
]

export function MobileSidebar({ isOpen, onClose }: MobileSidebarProps) {
  if (!isOpen) return null

  return (
    <>
      {/* Backdrop */}
      <div
        className="fixed inset-0 z-40 bg-black/50 lg:hidden"
        onClick={onClose}
      />

      {/* Sidebar */}
      <aside className="fixed inset-y-0 left-0 z-50 w-64 bg-card lg:hidden overflow-y-auto">
        <div className="flex h-16 items-center justify-between border-b border-border px-6">
          <BrandMark />
          <Button variant="ghost" size="icon" onClick={onClose}>
            <X className="h-5 w-5" />
          </Button>
        </div>

        <nav className="space-y-1 p-4">
          {navItems.map((item) => (
            <NavLink
              key={item.href}
              to={item.href}
              end={item.href === '/'}
              onClick={onClose}
              className={({ isActive }) =>
                cn(
                  'flex items-center gap-3 rounded-md px-3 py-2 text-sm font-medium transition-colors',
                  isActive
                    ? 'bg-primary/10 text-primary'
                    : 'text-muted-foreground hover:bg-accent hover:text-accent-foreground'
                )
              }
            >
              <item.icon className="h-4 w-4" />
              {item.label}
            </NavLink>
          ))}
        </nav>
      </aside>
    </>
  )
}
