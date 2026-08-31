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
} from 'lucide-react'
import { cn } from '@/lib/utils'
import { BrandMark } from '@/components/brand/BrandLogo'

interface NavItem {
  label: string
  href: string
  icon: React.ElementType
  disabled?: boolean
}

const navItems: NavItem[] = [
  { label: 'Dashboard', href: '/', icon: LayoutDashboard },
  { label: 'Pedidos', href: '/orders', icon: ShoppingCart },
  { label: 'Clientes', href: '/customers', icon: Users },
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

export function Sidebar() {
  return (
    <aside className="hidden w-64 border-r border-border bg-card lg:block">
      <div className="flex h-16 items-center gap-2 border-b border-border px-6">
        <BrandMark />
      </div>

      <nav className="space-y-1 p-4">
        {navItems.map((item) => (
          <NavLink
            key={item.href}
            to={item.href}
            end={item.href === '/'}
            className={({ isActive }) =>
              cn(
                'flex items-center gap-3 rounded-md px-3 py-2 text-sm font-medium transition-colors',
                isActive
                  ? 'bg-primary/10 text-primary'
                  : 'text-muted-foreground hover:bg-accent hover:text-accent-foreground',
                item.disabled && 'pointer-events-none opacity-50'
              )
            }
          >
            <item.icon className="h-4 w-4" />
            {item.label}
            {item.disabled && (
              <span className="ml-auto text-xs text-muted-foreground">Em breve</span>
            )}
          </NavLink>
        ))}
      </nav>
    </aside>
  )
}
