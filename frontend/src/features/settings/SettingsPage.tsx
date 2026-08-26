import { ModulePlaceholder } from '@/components/layout/ModulePlaceholder'
import { Settings } from 'lucide-react'

export function SettingsPage() {
  return (
    <ModulePlaceholder
      icon={Settings}
      title="Configurações"
      description="Configurações gerais do sistema"
    />
  )
}
