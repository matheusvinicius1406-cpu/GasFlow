import { ModulePlaceholder } from '@/components/layout/ModulePlaceholder'
import { Truck } from 'lucide-react'

export function DeliveriesPage() {
  return (
    <ModulePlaceholder
      icon={Truck}
      title="Entregas"
      description="Gerenciar entregas e status de entrega dos pedidos"
    />
  )
}
