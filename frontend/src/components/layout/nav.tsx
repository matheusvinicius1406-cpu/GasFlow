/**
 * Navegação em 7 grupos (reorg F2 + consolidação: Pedidos entra no grupo de
 * logística — pedido vira entrega).
 *
 * Fonte única da verdade usada por Sidebar (desktop) e MobileSidebar (mobile):
 * Dashboard é o único item direto; os demais são grupos colapsáveis.
 * A IA NÃO é item de menu — vive na bolinha flutuante (FloatingCopilot, F4).
 */

import { useState } from 'react'
import { NavLink, useLocation } from 'react-router-dom'
import {
  BarChart3,
  Brain,
  ChevronDown,
  Contact,
  DollarSign,
  Flame,
  FileText,
  Filter,
  LayoutDashboard,
  Megaphone,
  MessageSquare,
  Package,
  Repeat,
  Settings,
  ShieldCheck,
  ShoppingCart,
  Smartphone,
  Sparkles,
  Ticket,
  Truck,
  UserCog,
  Users,
  Warehouse,
  Zap,
} from 'lucide-react'
import { cn } from '@/lib/utils'

export interface NavLeaf {
  label: string
  href: string
  icon: React.ElementType
}

export interface NavEntry {
  label: string
  icon: React.ElementType
  /** Presente = item único (navega direto); ausente = grupo colapsável. */
  href?: string
  items?: NavLeaf[]
}

export const NAV_GROUPS: NavEntry[] = [
  { label: 'Dashboard', icon: LayoutDashboard, href: '/' },
  {
    label: 'WhatsApp',
    icon: MessageSquare,
    items: [
      { label: 'Conversas', href: '/whatsapp', icon: MessageSquare },
      { label: 'Contatos', href: '/whatsapp/contacts', icon: Contact },
      { label: 'Organizador', href: '/whatsapp/contacts/organizer', icon: Sparkles },
      { label: 'Campanhas', href: '/whatsapp/campaigns', icon: Megaphone },
      { label: 'Automações', href: '/whatsapp/automations', icon: Zap },
      { label: 'Contas & Conexão', href: '/whatsapp/accounts', icon: Smartphone },
    ],
  },
  {
    label: 'Pedidos & Entregas',
    icon: ShoppingCart,
    items: [
      { label: 'Pedidos', href: '/orders', icon: ShoppingCart },
      { label: 'Entregas', href: '/deliveries', icon: Truck },
      { label: 'Motoristas', href: '/drivers', icon: UserCog },
    ],
  },
  {
    label: 'Clientes',
    icon: Users,
    items: [
      { label: 'Lista', href: '/customers', icon: Users },
      { label: 'Segmentos', href: '/segments', icon: Filter },
      { label: 'Recompra', href: '/reorder', icon: Repeat },
      { label: 'Cupons', href: '/promotions', icon: Ticket },
    ],
  },
  {
    label: 'Produtos & Estoque',
    icon: Package,
    items: [
      { label: 'Produtos', href: '/products', icon: Package },
      { label: 'Estoque', href: '/inventory', icon: Warehouse },
      { label: 'Notas de Compra', href: '/purchase-notes', icon: FileText },
    ],
  },
  {
    label: 'Financeiro & Relatórios',
    icon: DollarSign,
    items: [
      { label: 'Financeiro', href: '/finance', icon: DollarSign },
      { label: 'Relatórios', href: '/reports', icon: BarChart3 },
      { label: 'Mapa de Calor', href: '/reports/heatmap', icon: Flame },
    ],
  },
  {
    label: 'Configurações',
    icon: Settings,
    items: [
      { label: 'Geral', href: '/settings', icon: Settings },
      { label: 'Usuários', href: '/admin/users', icon: UserCog },
      { label: 'Auditoria', href: '/admin/audit', icon: ShieldCheck },
      { label: 'IA', href: '/settings/ai', icon: Brain },
    ],
  },
]

const linkCls =
  'flex items-center gap-3 rounded-md px-3 py-2 text-sm font-medium transition-colors text-muted-foreground hover:bg-accent hover:text-accent-foreground'
const activeCls = 'bg-primary/10 text-primary'

/** Atividade por prefixo de rota ('/' é exato). */
function pathMatches(href: string, pathname: string): boolean {
  if (href === '/') return pathname === '/'
  return pathname === href || pathname.startsWith(`${href}/`)
}

interface NavTreeProps {
  /** Chamado ao navegar — fecha o drawer mobile. */
  onNavigate?: () => void
}

/**
 * Árvore de navegação renderizada igual no desktop e no mobile.
 * Grupos abrem sozinhos quando a rota atual pertence a eles;
 * o usuário pode abrir/fechar manualmente (override em memória).
 */
export function NavTree({ onNavigate }: NavTreeProps) {
  const { pathname } = useLocation()
  const [toggled, setToggled] = useState<Record<string, boolean>>({})

  return (
    <nav className="space-y-1 p-4">
      {NAV_GROUPS.map((entry) => {
        // Item único (Dashboard, Pedidos)
        if (entry.href) {
          return (
            <NavLink
              key={entry.label}
              to={entry.href}
              end={entry.href === '/'}
              onClick={onNavigate}
              className={({ isActive }) => cn(linkCls, isActive && activeCls)}
            >
              <entry.icon className="h-4 w-4" />
              {entry.label}
            </NavLink>
          )
        }

        // Grupo colapsável
        const items = entry.items ?? []
        const groupActive = items.some((item) => pathMatches(item.href, pathname))
        const open = toggled[entry.label] ?? groupActive

        return (
          <div key={entry.label} className="space-y-1">
            <button
              type="button"
              aria-expanded={open}
              onClick={() => setToggled((prev) => ({ ...prev, [entry.label]: !open }))}
              className={cn(linkCls, 'w-full cursor-pointer', groupActive && activeCls)}
            >
              <entry.icon className="h-4 w-4" />
              <span className="flex-1 text-left">{entry.label}</span>
              <ChevronDown
                className={cn('h-4 w-4 shrink-0 transition-transform duration-200', !open && '-rotate-90')}
              />
            </button>

            {open &&
              items.map((item) => (
                <NavLink
                  key={item.href}
                  to={item.href}
                  // Conversas é home do módulo: sem prefixo, senão ficaria ativa
                  // em todas as rotas /whatsapp/*.
                  end={item.href === '/whatsapp'}
                  onClick={onNavigate}
                  className={({ isActive }) =>
                    cn(linkCls, 'py-1.5 pl-9 text-[13px]', isActive && activeCls)
                  }
                >
                  <item.icon className="h-4 w-4" />
                  {item.label}
                </NavLink>
              ))}
          </div>
        )
      })}
    </nav>
  )
}
