import { ModulePlaceholder } from '@/components/layout/ModulePlaceholder'
import { DollarSign } from 'lucide-react'

export function FinancePage() {
  return (
    <ModulePlaceholder
      icon={DollarSign}
      title="Financeiro"
      description="Controle de receitas, despesas e pagamentos"
    />
  )
}
