import { Bell, Menu, LogOut, Sun, Moon } from 'lucide-react'
import { useAuth } from '@/features/auth'
import { useTheme } from '@/lib/theme'
import { Button } from '@/components/ui/Button'
import { Avatar, AvatarFallback } from '@/components/ui/Avatar'
import { Separator } from '@/components/ui/Separator'

interface HeaderProps {
  onMenuClick?: () => void
}

export function Header({ onMenuClick }: HeaderProps) {
  const { user, logout } = useAuth()
  const { theme, toggleTheme } = useTheme()

  return (
    <header className="flex h-16 items-center justify-between border-b border-border bg-card px-6">
      <div className="flex items-center gap-4">
        <Button
          variant="ghost"
          size="icon"
          className="lg:hidden"
          onClick={onMenuClick}
          aria-label="Abrir menu"
        >
          <Menu className="h-5 w-5" />
        </Button>
      </div>

      <div className="flex items-center gap-2">
        {/* Theme Toggle */}
        <Button
          variant="ghost"
          size="icon"
          onClick={toggleTheme}
          aria-label={theme === 'dark' ? 'Mudar para tema claro' : 'Mudar para tema escuro'}
        >
          {theme === 'dark' ? (
            <Sun className="h-5 w-5" />
          ) : (
            <Moon className="h-5 w-5" />
          )}
        </Button>

        <Separator orientation="vertical" className="h-6" />

        {/* Notifications */}
        <Button variant="ghost" size="icon" className="relative" aria-label="Notificações">
          <Bell className="h-5 w-5" />
          <span className="absolute right-1 top-1 h-2 w-2 rounded-full bg-primary" />
        </Button>

        <Separator orientation="vertical" className="h-6" />

        {/* User */}
        <div className="flex items-center gap-3">
          <Avatar>
            <AvatarFallback>
              {user?.name?.charAt(0) ?? 'U'}
            </AvatarFallback>
          </Avatar>
          <div className="hidden text-sm md:block">
            <p className="font-medium text-foreground">{user?.name}</p>
            <p className="text-xs text-muted-foreground">{user?.role}</p>
          </div>
        </div>

        <Separator orientation="vertical" className="h-6" />

        {/* Logout */}
        <Button variant="ghost" size="icon" onClick={logout} aria-label="Sair da conta">
          <LogOut className="h-5 w-5" />
        </Button>
      </div>
    </header>
  )
}
