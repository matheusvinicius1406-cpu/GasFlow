import { useState } from 'react'
import { Package, Loader2, AlertTriangle } from 'lucide-react'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/Card'
import { LoadingSpinner } from '@/components/ui/LoadingSpinner'
import { EmptyState } from '@/components/ui/EmptyState'
import { Badge } from '@/components/ui/Badge'
import { Button } from '@/components/ui/Button'
import { Input } from '@/components/ui/Input'
import { useDriverStock, driverStockApi } from '@/lib/api/driverStock'

interface DriverStockCardProps {
  driverId: string
  driverName?: string
}

/**
 * Card F7 — estoque carregado pelo entregador: carga confirmada, avaria
 * com motivo obrigatório e reconciliação de fim de turno. Divergência
 * fora da tolerância bloqueia novas cargas (mostrado no card).
 */
export function DriverStockCard({ driverId, driverName }: DriverStockCardProps) {
  const { data: stock = [], isLoading, refetch } = useDriverStock(driverId)
  const [busy, setBusy] = useState('')
  const [notice, setNotice] = useState('')
  const [loadQty, setLoadQty] = useState('10')
  const [damageQty, setDamageQty] = useState('1')
  const [damageReason, setDamageReason] = useState('')
  const [counted, setCounted] = useState('')

  const run = async (action: string, fn: () => Promise<unknown>) => {
    setBusy(action)
    setNotice('')
    try {
      await fn()
      refetch()
      setNotice('Operação registrada.')
    } catch (e: unknown) {
      const detail = (e as { response?: { data?: { detail?: string } } })?.response?.data?.detail
      setNotice(detail || 'Falha na operação.')
    } finally {
      setBusy('')
    }
  }

  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex items-center gap-2 text-base">
          <Package className="h-4 w-4" />
          Estoque do Entregador
          {driverName ? <span className="text-muted-foreground font-normal">— {driverName}</span> : null}
        </CardTitle>
      </CardHeader>
      <CardContent className="space-y-4">
        {isLoading ? (
          <LoadingSpinner />
        ) : stock.length === 0 ? (
          <EmptyState
            icon={Package}
            title="Sem carga registrada"
            description="Registre a carga de cilindros que o entregador levou."
          />
        ) : (
          <div className="space-y-2">
            {stock.map((row) => (
              <div key={row.product_codigo} className="flex items-center justify-between rounded-md border px-3 py-2 text-sm">
                <span className="font-medium">{row.product_codigo}</span>
                <span className="flex items-center gap-3">
                  <span>
                    Cheios: <strong>{row.full_tanks_loaded}</strong>
                  </span>
                  <span className="text-muted-foreground">Vazios devolvidos: {row.empty_tanks_returned}</span>
                  {row.blocked && (
                    <Badge variant="destructive">
                      <AlertTriangle className="h-3 w-3 mr-1" /> Bloqueado
                    </Badge>
                  )}
                </span>
              </div>
            ))}
            {stock.some((r) => r.blocked) && (
              <p className="text-xs text-destructive">
                Divergência pendente: cargas bloqueadas até reconciliação manual.
              </p>
            )}
          </div>
        )}

        <div className="grid gap-2 sm:grid-cols-3">
          <div className="space-y-1">
            <label className="text-xs text-muted-foreground">Carga (cheios levados)</label>
            <div className="flex gap-1">
              <Input
                type="number"
                min="1"
                value={loadQty}
                onChange={(e) => setLoadQty(e.target.value)}
                aria-label="Quantidade de cheios carregados"
              />
              <Button
                size="sm"
                disabled={busy === 'load' || !loadQty}
                onClick={() =>
                  run('load', () => driverStockApi.load(driverId, stock[0]?.product_codigo ?? 'P13', Number(loadQty)))
                }
              >
                {busy === 'load' ? <Loader2 className="h-4 w-4 animate-spin" /> : 'Carregar'}
              </Button>
            </div>
          </div>

          <div className="space-y-1">
            <label className="text-xs text-muted-foreground">Avaria (motivo obrigatório)</label>
            <Input
              value={damageReason}
              onChange={(e) => setDamageReason(e.target.value)}
              placeholder="Motivo"
              aria-label="Motivo da avaria"
            />
            <div className="flex gap-1">
              <Input
                type="number"
                min="1"
                value={damageQty}
                onChange={(e) => setDamageQty(e.target.value)}
                aria-label="Quantidade avariada"
              />
              <Button
                size="sm"
                variant="destructive"
                disabled={busy === 'damage' || !damageReason.trim()}
                onClick={() =>
                  run('damage', () =>
                    driverStockApi.damage(driverId, stock[0]?.product_codigo ?? 'P13', Number(damageQty), damageReason),
                  )
                }
              >
                {busy === 'damage' ? <Loader2 className="h-4 w-4 animate-spin" /> : 'Avaria'}
              </Button>
            </div>
          </div>

          <div className="space-y-1">
            <label className="text-xs text-muted-foreground">Reconciliação (contagem física)</label>
            <div className="flex gap-1">
              <Input
                type="number"
                min="0"
                value={counted}
                onChange={(e) => setCounted(e.target.value)}
                aria-label="Cheios contados fisicamente"
              />
              <Button
                size="sm"
                variant="outline"
                disabled={busy === 'reconcile' || counted === ''}
                onClick={() =>
                  run('reconcile', () =>
                    driverStockApi.reconcile(driverId, { [stock[0]?.product_codigo ?? 'P13']: Number(counted) }),
                  )
                }
              >
                {busy === 'reconcile' ? <Loader2 className="h-4 w-4 animate-spin" /> : 'Conferir'}
              </Button>
            </div>
          </div>
        </div>

        {notice && (
          <p className="text-sm text-muted-foreground" role="status">
            {notice}
          </p>
        )}
      </CardContent>
    </Card>
  )
}
