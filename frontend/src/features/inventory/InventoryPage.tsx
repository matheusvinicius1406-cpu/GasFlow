import { ModulePlaceholder } from '@/components/layout/ModulePlaceholder'
import { Warehouse } from 'lucide-react'

export function InventoryPage() {
  return (
    <ModulePlaceholder
      icon={Warehouse}
      title="Estoque"
      description="Controle de entradas, saídas e movimentações de estoque"
    />
  )
}
