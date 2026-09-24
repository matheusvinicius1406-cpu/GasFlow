import { useMemo } from 'react'
import { BarChart3, FileDown, Landmark } from 'lucide-react'
import { Page, PageActions, PageHeader, PageTitle } from '@/components/layout/Page'
import { Button } from '@/components/ui/Button'
import { useAuth } from '@/features/auth'
import { toCsvDate } from './exportPeriodCsv'
import { SectionShell } from './SectionShell'
import { VisaoGeralSection } from './sections/VisaoGeralSection'
import { SECTIONS, findSection, usePeriodFilter } from './usePeriodFilter'
import { useVisaoGeralData } from './useVisaoGeralData'

/**
 * Shell da Central Financeira (P4/P5): Page/PageHeader + filtros globais
 * (presets V1) + abas das 15 seções com deep-link `?secao=`.
 * A Visão Geral (P5) é a primeira seção real: o shell busca os dados e
 * injeta na seção (§2.2); as demais seguem placeholder até P6–P8.
 */
export function CentralFinanceiraPage() {
  const { days, setDays, presets, secao, setSecao } = usePeriodFilter()
  const atual = findSection(secao)
  const { hasPermission } = useAuth()
  const vg = useVisaoGeralData(days)
  const can = useMemo(
    () => ({
      write: hasPermission('finance.write'),
      receive: hasPermission('finance.receive'),
    }),
    [hasPermission]
  )
  const isVisao = secao === 'visao-geral'

  return (
    <Page>
      <PageHeader>
        <PageTitle
          subtitle={
            vg.period
              ? `${toCsvDate(vg.period.from)} a ${toCsvDate(vg.period.to)} · ${vg.period.days} dia${
                  vg.period.days > 1 ? 's' : ''
                }`
              : 'Financeiro e relatórios em uma tela só.'
          }
        >
          Central Financeira
        </PageTitle>
        <PageActions>
          {isVisao && (
            <Button
              type="button"
              size="sm"
              variant="outline"
              onClick={vg.actions.exportCsv}
              disabled={!vg.period}
            >
              <FileDown className="h-4 w-4" />
              Exportar CSV
            </Button>
          )}
          <div className="flex items-center gap-1" role="group" aria-label="Período da Central Financeira">
            {presets.map((p) => (
              <Button
                key={p.days}
                size="sm"
                variant={days === p.days ? 'default' : 'outline'}
                aria-pressed={days === p.days}
                onClick={() => setDays(p.days)}
              >
                {p.label}
              </Button>
            ))}
          </div>
        </PageActions>
      </PageHeader>

      <div
        className="flex gap-2 overflow-x-auto border-b pb-2"
        role="group"
        aria-label="Seções da Central Financeira"
      >
        {SECTIONS.map((s) => (
          <Button
            key={s.slug}
            size="sm"
            variant={s.slug === secao ? 'default' : 'ghost'}
            aria-pressed={s.slug === secao}
            onClick={() => setSecao(s.slug)}
          >
            {s.label}
          </Button>
        ))}
      </div>

      {isVisao ? (
        <SectionShell
          title="Visão Geral"
          loading={vg.loading && !vg.period}
          error={vg.error && !vg.period}
          onRetry={() => void vg.actions.reload()}
          empty={vg.empty}
          emptyIcon={BarChart3}
          emptyTitle="Sem movimentações neste período"
          emptyDescription="Nenhum recebimento ou despesa no período escolhido. Troque o filtro ou registre lançamentos."
        >
          {vg.period ? <VisaoGeralSection data={vg} can={can} /> : null}
        </SectionShell>
      ) : (
        <SectionShell
          title={atual.label}
          empty
          emptyIcon={Landmark}
          emptyTitle={`${atual.label} — em construção`}
          emptyDescription={`Esta seção entra no PR ${atual.pr} da Central Financeira.`}
        />
      )}
    </Page>
  )
}
