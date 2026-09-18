import { useCallback, useEffect, useState } from 'react'
import { Wand2, AlertTriangle, ListChecks, Hash, Loader2 } from 'lucide-react'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/Card'
import { Button } from '@/components/ui/Button'
import { Badge } from '@/components/ui/Badge'
import { LoadingSpinner } from '@/components/ui/LoadingSpinner'
import { ErrorState } from '@/components/ui/ErrorState'
import { EmptyState } from '@/components/ui/EmptyState'
import { Page, PageHeader, PageTitle, PageActions } from '@/components/layout/Page'
import { apiClient } from '@/lib/api/client'

interface RenameChange {
  codigo: string
  telefone: string
  before: string
  after: string
  bairro: string
}

interface PreviewResponse {
  changes: RenameChange[]
  total: number
}

interface ApplyResponse {
  renamed: number
  conflicts_skipped: number
  skipped_missing: number
}

interface ConflictItem {
  codigo: string
  nome: string
  telefone: string
  issues: string[]
  duplicates_with: string[]
}

interface ConflictsResponse {
  total: number
  items: ConflictItem[]
}

const ISSUE_LABELS: Record<string, string> = {
  duplicate_name: 'Nome duplicado',
  bad_phone: 'Telefone inválido',
}

export function ContactsOrganizerPage() {
  // Regras (espelham RenameRule do backend)
  const [stripPrefixes, setStripPrefixes] = useState(true)
  const [caseMode, setCaseMode] = useState<'title' | 'upper' | 'lower' | ''>('title')
  const [patternBairro, setPatternBairro] = useState(false)

  const [preview, setPreview] = useState<PreviewResponse | null>(null)
  const [conflicts, setConflicts] = useState<ConflictsResponse | null>(null)
  const [busy, setBusy] = useState('')
  const [notice, setNotice] = useState('')
  const [error, setError] = useState(false)
  const [applied, setApplied] = useState<Set<string>>(new Set())

  const buildRule = useCallback(
    () => ({
      trim: true,
      strip_prefixes: stripPrefixes,
      case: caseMode || null,
      pattern_bairro: patternBairro,
    }),
    [stripPrefixes, caseMode, patternBairro],
  )

  const fetchConflicts = useCallback(async () => {
    try {
      const res = await apiClient.get('/whatsapp/contacts/organizer/conflicts')
      setConflicts(res.data)
    } catch {
      /* lista de conflitos é secundária — falha não bloqueia a página */
    }
  }, [])

  useEffect(() => {
    fetchConflicts()
  }, [fetchConflicts])

  const handlePreview = async () => {
    setBusy('preview')
    setNotice('')
    setError(false)
    try {
      const res = await apiClient.post('/whatsapp/contacts/organizer/rename-preview', buildRule())
      setPreview(res.data)
      setApplied(new Set())
    } catch {
      setError(true)
    } finally {
      setBusy('')
    }
  }

  const handleApply = async () => {
    if (!preview || applied.size === 0) return
    setBusy('apply')
    setNotice('')
    try {
      const codes = preview.changes.map((c) => c.codigo)
      const res = await apiClient.post('/whatsapp/contacts/organizer/rename-apply', {
        rule: buildRule(),
        codes,
      })
      const body: ApplyResponse = res.data
      setNotice(
        `Renomeação aplicada: ${body.renamed} contato(s). ` +
          (body.conflicts_skipped > 0 ? `${body.conflicts_skipped} em conflito foram preservados. ` : '') +
          (body.skipped_missing > 0 ? `${body.skipped_missing} não encontrados.` : ''),
      )
      setPreview(null)
      setApplied(new Set())
      fetchConflicts()
    } catch {
      setNotice('Falha ao aplicar a renomeação.')
    } finally {
      setBusy('')
    }
  }

  const handleBackfill = async () => {
    setBusy('backfill')
    setNotice('')
    try {
      const res = await apiClient.post('/whatsapp/contacts/organizer/backfill-codes')
      setNotice(`Backfill concluído: ${res.data.fixed} código(s) atribuído(s).`)
      fetchConflicts()
    } catch {
      setNotice('Falha no backfill de códigos.')
    } finally {
      setBusy('')
    }
  }

  const toggleAll = (checked: boolean) => {
    if (!preview) return
    setApplied(checked ? new Set(preview.changes.map((c) => c.codigo)) : new Set())
  }

  return (
    <Page>
      <PageHeader>
        <PageTitle>Organizador de Contatos</PageTitle>
        <PageActions>
          <Button variant="outline" onClick={handleBackfill} disabled={busy === 'backfill'}>
            {busy === 'backfill' ? <Loader2 className="h-4 w-4 animate-spin" /> : <Hash className="h-4 w-4" />}
            Backfill de códigos
          </Button>
        </PageActions>
      </PageHeader>

      {notice && (
        <div className="rounded-md border border-green-200 bg-green-50 px-4 py-2 text-sm text-green-800" role="status">
          {notice}
        </div>
      )}

      <div className="grid gap-4 lg:grid-cols-2">
        {/* ── Renomeador em lote ── */}
        <Card>
          <CardHeader>
            <CardTitle className="text-base">Renomeador em lote</CardTitle>
          </CardHeader>
          <CardContent className="space-y-3">
            <p className="text-sm text-muted-foreground">
              Nada é gravado sem o preview. Confira as mudanças antes de aplicar.
            </p>

            <label className="flex items-center gap-2 text-sm">
              <input
                type="checkbox"
                checked={stripPrefixes}
                onChange={(e) => setStripPrefixes(e.target.checked)}
              />
              Remover prefixos (WA-, WPP-, +…)
            </label>

            <label className="flex items-center gap-2 text-sm">
              <input
                type="checkbox"
                checked={patternBairro}
                onChange={(e) => setPatternBairro(e.target.checked)}
              />
              Padrão &quot;Nome — Bairro&quot;
            </label>

            <div className="flex items-center gap-2 text-sm">
              <span>Capitalização:</span>
              <select
                className="rounded-md border px-2 py-1 text-sm"
                value={caseMode}
                onChange={(e) => setCaseMode(e.target.value as typeof caseMode)}
              >
                <option value="">Manter</option>
                <option value="title">Title Case</option>
                <option value="upper">MAIÚSCULAS</option>
                <option value="lower">minúsculas</option>
              </select>
            </div>

            <Button onClick={handlePreview} disabled={busy === 'preview'}>
              {busy === 'preview' ? <Loader2 className="h-4 w-4 animate-spin" /> : <Wand2 className="h-4 w-4" />}
              Gerar preview
            </Button>
          </CardContent>
        </Card>

        {/* ── Lista Revisar (conflitos) ── */}
        <Card>
          <CardHeader>
            <CardTitle className="flex items-center gap-2 text-base">
              <AlertTriangle className="h-4 w-4 text-amber-500" />
              Revisar
              {conflicts && conflicts.total > 0 && <Badge variant="destructive">{conflicts.total}</Badge>}
            </CardTitle>
          </CardHeader>
          <CardContent>
            {!conflicts ? (
              <LoadingSpinner />
            ) : conflicts.total === 0 ? (
              <EmptyState
                icon={ListChecks}
                title="Sem conflitos"
                description="Nenhum nome duplicado ou telefone inválido."
              />
            ) : (
              <ul className="max-h-72 space-y-2 overflow-y-auto text-sm">
                {conflicts.items.map((item) => (
                  <li key={item.codigo} className="rounded-md border px-3 py-2">
                    <div className="flex items-center justify-between gap-2">
                      <span className="font-medium">{item.nome}</span>
                      <span className="flex gap-1">
                        {item.issues.map((issue) => (
                          <Badge key={issue} variant="secondary">
                            {ISSUE_LABELS[issue] ?? issue}
                          </Badge>
                        ))}
                      </span>
                    </div>
                    <div className="text-xs text-muted-foreground">
                      {item.codigo} · {item.telefone}
                    </div>
                  </li>
                ))}
              </ul>
            )}
          </CardContent>
        </Card>
      </div>

      {/* ── Preview das mudanças ── */}
      {error && <ErrorState message="Não foi possível gerar o preview." onRetry={handlePreview} />}

      {preview && !error && (
        <Card>
          <CardHeader>
            <CardTitle className="flex items-center justify-between text-base">
              <span className="flex items-center gap-2">
                <ListChecks className="h-4 w-4" />
                Preview — {preview.total} mudança(s)
              </span>
              <label className="flex items-center gap-2 text-sm font-normal">
                <input
                  type="checkbox"
                  checked={preview.total > 0 && applied.size === preview.total}
                  onChange={(e) => toggleAll(e.target.checked)}
                />
                Selecionar todas
              </label>
            </CardTitle>
          </CardHeader>
          <CardContent className="space-y-3">
            {preview.total === 0 ? (
              <EmptyState
                icon={ListChecks}
                title="Nada a mudar"
                description="Nenhum contato seria alterado com essas regras."
              />
            ) : (
              <>
                <div className="max-h-80 overflow-y-auto rounded-md border">
                  <table className="w-full text-sm">
                    <thead className="bg-muted/50 text-left">
                      <tr>
                        <th className="p-2"></th>
                        <th className="p-2">Antes</th>
                        <th className="p-2">Depois</th>
                        <th className="p-2">Código</th>
                      </tr>
                    </thead>
                    <tbody>
                      {preview.changes.map((c) => (
                        <tr key={c.codigo} className="border-t">
                          <td className="p-2">
                            <input
                              type="checkbox"
                              checked={applied.has(c.codigo)}
                              onChange={(e) => {
                                const next = new Set(applied)
                                if (e.target.checked) next.add(c.codigo)
                                else next.delete(c.codigo)
                                setApplied(next)
                              }}
                            />
                          </td>
                          <td className="p-2 text-muted-foreground line-through">{c.before}</td>
                          <td className="p-2 font-medium">{c.after}</td>
                          <td className="p-2 text-xs">{c.codigo}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
                <Button onClick={handleApply} disabled={busy === 'apply' || applied.size === 0}>
                  {busy === 'apply' ? <Loader2 className="h-4 w-4 animate-spin" /> : null}
                  Aplicar {applied.size > 0 ? `(${applied.size} selecionada(s))` : ''}
                </Button>
              </>
            )}
          </CardContent>
        </Card>
      )}
    </Page>
  )
}
