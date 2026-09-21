import { useState } from 'react'
import { Outlet } from 'react-router-dom'
import { Sidebar } from './Sidebar'
import { Header } from './Header'
import { MobileSidebar } from './MobileSidebar'
import { RealtimeBridge } from '@/components/realtime/RealtimeBridge'
import { FloatingCopilot } from '@/components/copilot/FloatingCopilot'

/**
 * Sessão de entregador ativa no mesmo app (F1a): o motorista logado em
 * /driver não pode ver módulos admin. Se existe driver_token e NÃO há
 * token de operador, a sessão é exclusivamente de entregador — o layout
 * admin não deve renderizar navegação/canal de operador. (Com os dois
 * tokens, o operador apenas visitou /driver — layout admin intacto.)
 */
function isDriverOnlySession(): boolean {
  if (typeof window === 'undefined') return false
  return !!window.localStorage.getItem('driver_token') && !window.localStorage.getItem('gasflow_token')
}

export function DashboardLayout() {
  const [isMobileSidebarOpen, setIsMobileSidebarOpen] = useState(false)

  if (isDriverOnlySession()) {
    return <Outlet />
  }

  return (
    <div className="flex h-screen overflow-hidden bg-background">
      <RealtimeBridge />
      {/* Skip Link */}
      <a href="#main-content" className="skip-link">
        Pular para o conteúdo
      </a>

      {/* Desktop Sidebar */}
      <Sidebar />

      {/* Mobile Sidebar */}
      <MobileSidebar
        isOpen={isMobileSidebarOpen}
        onClose={() => setIsMobileSidebarOpen(false)}
      />

      {/* Main Content */}
      <div className="flex flex-1 flex-col overflow-hidden">
        <Header onMenuClick={() => setIsMobileSidebarOpen(true)} />

        <main id="main-content" className="flex-1 overflow-y-auto p-6">
          <Outlet />
        </main>
      </div>

      {/*
        Auto-update (Electron) não fica aqui: `UpdateScreen` e `UpdateNotifier`
        são montados na raiz do App (src/App.tsx) para valerem em toda rota.
      */}

      {/* IA — bolinha flutuante (reorg F4); não é item de menu */}
      <FloatingCopilot />
    </div>
  )
}
