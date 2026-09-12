import { useCallback, useEffect, useMemo, useState } from 'react'
import { Download, ScrollText } from 'lucide-react'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/Card'
import { Badge } from '@/components/ui/Badge'
import { Button } from '@/components/ui/Button'
import { Input } from '@/components/ui/Input'
import { Select } from '@/components/ui/Select'
import { LoadingSpinner } from '@/components/ui/LoadingSpinner'
import { ErrorState } from '@/components/ui/ErrorState'
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/Table'
import { apiClient } from '@/lib/api/client'

interface AuditRecord {
  id: string
  actor_id: string
  action: string
  resource: string
  resource_id: string
  result: string
  timestamp: string
  before_json: Record<string, unknown> | null
  after_json: Record<string, unknown> | null
  platform: string
}

interface AuditResponse {
  records: AuditRecord[]
}

const PAGE_SIZE = 50

const ACTION_OPTIONS = [
  'USER_CREATED',
  'USER_DISABLED',
  'PASSWORD_CHANGED',
  'ROLE_CHANGED',
  'RESOURCE_MODIFIED',
  'AUTH_SUCCESS',
  'AUTH_FAILURE',
]

export function AuditPage() {
  const [records, setRecords] = useState<AuditRecord[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(false)
  const [actorId, setActorId] = useState('')
  const [action, setAction] = useState('')
  const [resource, setResource] = useState('')
  const [fromDate, setFromDate] = useState('')
  const [toDate, setToDate] = useState('')
  const [offset, setOffset] = useState(0)

  const fetchAudit = useCallback(
    async (currentOffset: number) => {
      setLoading(true)
      setError(false)
      try {
        const { data } = await apiClient.get<AuditResponse>('/admin/audit', {
          params: {
            actor_id: actorId || undefined,
            action: action || undefined,
            resource: resource || undefined,
            from_ts: fromDate ? `${fromDate}T00:00:00` : undefined,
            to_ts: toDate ? `${toDate}T23:59:59` : undefined,
            offset: currentOffset,
            limit: PAGE_SIZE,
          },
        })
        setRecords(data.records)
      } catch {
        setError(true)
      } finally {
        setLoading(false)
      }
    },
    [actorId, action, resource, fromDate, toDate]
  )

  useEffect(() => {
    fetchAudit(offset)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [offset])

  const applyFilters = () => {
    setOffset(0)
    fetchAudit(0)
  }

  // Opções de ator/recurso derivadas dos registros carregados (sem exigir user.read).
  const actorOptions = useMemo(
    () => Array.from(new Set(records.map((r) => r.actor_id).filter(Boolean))).sort(),
    [records]
  )
  const resourceOptions = useMemo(
    () => Array.from(new Set(records.map((r) => r.resource).filter(Boolean))).sort(),
    [records]
  )

  const exportCsv = () => {
    const header = ['id', 'timestamp', 'actor_id', 'action', 'resource', 'resource_id', 'result', 'platform']
    const escape = (value: unknown) => {
      const str = value === null || value === undefined ? '' : String(value)
      return /[",\n]/.test(str) ? `"${str.replace(/"/g, '""')}"` : str
    }
    const lines = [header.join(',')]
    for (const r of records) {
      lines.push(
        [r.id, r.timestamp, r.actor_id, r.action, r.resource, r.resource_id, r.result, r.platform]
          .map(escape)
          .join(',')
      )
    }
    const blob = new Blob([lines.join('\n')], { type: 'text/csv;charset=utf-8' })
    const url = URL.createObjectURL(blob)
    const link = document.createElement('a')
    link.href = url
    link.download = `gasflow-audit-${new Date().toISOString().slice(0, 10)}.csv`
    document.body.appendChild(link)
    link.click()
    document.body.removeChild(link)
    URL.revokeObjectURL(url)
  }

  if (loading && records.length === 0) {
    return (
      <div className="flex items-center justify-center py-16">
        <LoadingSpinner size="lg" />
      </div>
    )
  }

  if (error && records.length === 0) {
    return <ErrorState message="Não foi possível carregar a auditoria." onRetry={() => fetchAudit(offset)} />
  }

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h1 className="flex items-center gap-2 text-xl font-semibold">
            <ScrollText className="h-6 w-6" /> Auditoria
          </h1>
          <p className="text-sm text-muted-foreground">
            Quem fez o quê, quando e sobre o quê (trilha imutável).
          </p>
        </div>
        <Button variant="outline" onClick={exportCsv} disabled={records.length === 0}>
          <Download className="h-4 w-4" /> Exportar CSV
        </Button>
      </div>

      {/* Filtros */}
      <div className="grid gap-2 md:grid-cols-6">
        <Input
          placeholder="Ator (user id)"
          value={actorId}
          onChange={(e) => setActorId(e.target.value)}
          aria-label="Filtrar por ator"
          className="md:col-span-2"
        />
        <Select value={action} onChange={(e) => setAction(e.target.value)} aria-label="Filtrar por ação">
          <option value="">Todas as ações</option>
          {Array.from(new Set([...ACTION_OPTIONS, ...records.map((r) => r.action)])).map((a) => (
            <option key={a} value={a}>
              {a}
            </option>
          ))}
        </Select>
        <Select value={resource} onChange={(e) => setResource(e.target.value)} aria-label="Filtrar por módulo">
          <option value="">Todos os módulos</option>
          {resourceOptions.map((r) => (
            <option key={r} value={r}>
              {r}
            </option>
          ))}
        </Select>
        <Input
          type="date"
          value={fromDate}
          onChange={(e) => setFromDate(e.target.value)}
          aria-label="Data inicial"
        />
        <Input
          type="date"
          value={toDate}
          onChange={(e) => setToDate(e.target.value)}
          aria-label="Data final"
        />
      </div>
      <div className="flex gap-2">
        <Button size="sm" onClick={applyFilters}>
          Aplicar filtros
        </Button>
        <Button
          size="sm"
          variant="ghost"
          onClick={() => {
            setActorId('')
            setAction('')
            setResource('')
            setFromDate('')
            setToDate('')
            setOffset(0)
            fetchAudit(0)
          }}
        >
          Limpar
        </Button>
      </div>

      <Card>
        <CardHeader>
          <CardTitle className="text-base">{records.length} registros</CardTitle>
        </CardHeader>
        <CardContent>
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Quando</TableHead>
                <TableHead>Ator</TableHead>
                <TableHead>Ação</TableHead>
                <TableHead>Alvo</TableHead>
                <TableHead>Plataforma</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {records.map((r) => (
                <TableRow key={r.id}>
                  <TableCell className="whitespace-nowrap text-xs text-muted-foreground">
                    {new Date(r.timestamp).toLocaleString('pt-BR')}
                  </TableCell>
                  <TableCell className="font-mono text-xs">{r.actor_id || '—'}</TableCell>
                  <TableCell>
                    <Badge
                      variant={
                        r.result === 'DENIED'
                          ? 'destructive'
                          : r.action === 'USER_DISABLED' || r.action === 'PASSWORD_CHANGED'
                            ? 'warning'
                            : 'secondary'
                      }
                      className="font-mono text-[10px]"
                    >
                      {r.action}
                    </Badge>
                  </TableCell>
                  <TableCell className="text-xs">
                    {r.resource}
                    {r.resource_id ? (
                      <span className="text-muted-foreground"> · {r.resource_id.slice(0, 8)}…</span>
                    ) : null}
                  </TableCell>
                  <TableCell className="text-xs text-muted-foreground">{r.platform || '—'}</TableCell>
                </TableRow>
              ))}
              {records.length === 0 && (
                <TableRow>
                  <TableCell colSpan={5} className="py-8 text-center text-muted-foreground">
                    Nenhum registro para os filtros atuais.
                  </TableCell>
                </TableRow>
              )}
            </TableBody>
          </Table>

          {/* Paginação */}
          <div className="mt-3 flex items-center justify-end gap-2">
            <Button variant="outline" size="sm" disabled={offset === 0} onClick={() => setOffset(Math.max(0, offset - PAGE_SIZE))}>
              Anterior
            </Button>
            <Button
              variant="outline"
              size="sm"
              disabled={records.length < PAGE_SIZE}
              onClick={() => setOffset(offset + PAGE_SIZE)}
            >
              Próxima
            </Button>
          </div>
        </CardContent>
      </Card>
    </div>
  )
}
