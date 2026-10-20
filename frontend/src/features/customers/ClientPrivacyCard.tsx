import { useState } from 'react'
import { Download, ShieldCheck, ShieldOff } from 'lucide-react'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/Card'
import { Button } from '@/components/ui/Button'
import { useAuth } from '@/features/auth'
import { useToast } from '@/components/ui/Toast'
import { api } from '@/lib/api/client'

interface ClientPrivacyCardProps {
  customerCodigo: string
  customerNome: string
  /** Chamado depois da anonimização — a tela decide refetch/redirect. */
  onErased?: () => void
}

function statusOf(err: unknown): number | undefined {
  return (err as { response?: { status?: number } })?.response?.status
}

/**
 * LGPD (D8) na ficha do cliente.
 *
 * - **Exportar** (customer.write): baixa um JSON com a PII do titular para
 *   portabilidade (art. 18, V). O backend audita a operação.
 * - **Anonimizar** (customer.*): remove nome/telefone/endereço/e-mail e
 *   preserva pedidos e valores fiscais (art. 18, VI). Irreversível — por isso
 *   exige digitar o código do cliente, não um `confirm()` de um clique.
 */
export function ClientPrivacyCard({ customerCodigo, customerNome, onErased }: ClientPrivacyCardProps) {
  const { hasPermission } = useAuth()
  const toast = useToast()
  const [busy, setBusy] = useState<'export' | 'erase' | null>(null)

  const canExport = hasPermission('customer.write')
  const canErase = hasPermission('customer.*')
  if (!canExport && !canErase) return null

  async function handleExport() {
    setBusy('export')
    try {
      const { data } = await api.clients.exportData(customerCodigo)
      const blob = new Blob([JSON.stringify(data, null, 2)], { type: 'application/json' })
      const url = URL.createObjectURL(blob)
      const link = document.createElement('a')
      link.href = url
      link.download = `cliente-${customerCodigo}-lgpd.json`
      document.body.appendChild(link)
      link.click()
      link.remove()
      URL.revokeObjectURL(url)
      toast.success('Dados exportados', `Pacote LGPD de ${customerNome} baixado.`)
    } catch (err) {
      if (statusOf(err) === 403) {
        toast.error('Sem permissão', 'Seu usuário não pode exportar dados de cliente.')
      } else {
        toast.error('Não foi possível exportar', 'Nada foi baixado. Tente novamente.')
      }
    } finally {
      setBusy(null)
    }
  }

  async function handleErase() {
    const typed = window.prompt(
      `Anonimizar os dados de ${customerNome}?\n\n` +
        'Pedidos, pagamentos e valores fiscais são preservados; nome, telefone, endereço e e-mail são removidos. ' +
        'Esta ação é irreversível.\n\n' +
        `Digite o código do cliente (${customerCodigo}) para confirmar:`,
    )
    if (typed === null) return
    if (typed.trim() !== customerCodigo) {
      toast.error('Confirmação inválida', 'O código digitado não confere — nada foi alterado.')
      return
    }

    setBusy('erase')
    try {
      await api.clients.eraseData(customerCodigo)
      toast.success('Dados anonimizados', 'A PII foi removida; pedidos e fiscal foram preservados.')
      onErased?.()
    } catch (err) {
      if (statusOf(err) === 403) {
        toast.error('Sem permissão', 'Apenas administradores/gerentes podem anonimizar dados.')
      } else if (statusOf(err) === 404) {
        toast.error('Cliente não encontrado', 'A ficha pode ter sido removida — recarregue a lista.')
      } else {
        toast.error('Não foi possível anonimizar', 'Nada foi alterado. Tente novamente.')
      }
    } finally {
      setBusy(null)
    }
  }

  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex items-center gap-2">
          <ShieldCheck className="h-5 w-5" /> Privacidade e LGPD
        </CardTitle>
      </CardHeader>
      <CardContent className="space-y-4">
        <p className="text-sm text-muted-foreground">
          Direitos do titular: exporte os dados cadastrais ou anonimize a PII. O histórico de pedidos e os
          valores fiscais são preservados.
        </p>
        <div className="flex flex-wrap gap-2">
          {canExport && (
            <Button variant="outline" onClick={handleExport} disabled={busy !== null}>
              <Download className="h-4 w-4 mr-1" />
              {busy === 'export' ? 'Exportando...' : 'Exportar dados'}
            </Button>
          )}
          {canErase && (
            <Button
              variant="destructive"
              onClick={handleErase}
              disabled={busy !== null}
              aria-label={`Anonimizar dados de ${customerNome}`}
            >
              <ShieldOff className="h-4 w-4 mr-1" />
              {busy === 'erase' ? 'Anonimizando...' : 'Anonimizar dados'}
            </Button>
          )}
        </div>
      </CardContent>
    </Card>
  )
}
