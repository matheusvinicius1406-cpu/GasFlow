import { useState } from 'react'
import { Outlet } from 'react-router-dom'
import { Sidebar } from './Sidebar'
import { Header } from './Header'
import { MobileSidebar } from './MobileSidebar'
import { RealtimeBridge } from '@/components/realtime/RealtimeBridge'
import { UpdateNotifier } from '@/components/UpdateNotifier'
import { FloatingCopilot } from '@/components/copilot/FloatingCopilot'

export function DashboardLayout() {
  const [isMobileSidebarOpen, setIsMobileSidebarOpen] = useState(false)

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

      {/* Auto-update (Electron) — canto inferior direito */}
      <UpdateNotifier />

      {/* IA — bolinha flutuante (reorg F4); não é item de menu */}
      <FloatingCopilot />
    </div>
  )
}
