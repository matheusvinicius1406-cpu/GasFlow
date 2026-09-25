import { useMemo, type ReactNode } from 'react'
import { BarChart3, Boxes, FileDown, Landmark, Target, Wallet } from 'lucide-react'
import { Page, PageActions, PageHeader, PageTitle } from '@/components/layout/Page'
import { Button } from '@/components/ui/Button'
import { useAuth } from '@/features/auth'
import { toCsvDate } from './exportPeriodCsv'
import { SectionShell } from './SectionShell'
import { DreSection } from './sections/DreSection'
import { OrcamentoSection } from './sections/OrcamentoSection'
import { ProdutosSection } from './sections/ProdutosSection'
import { ProjecaoSection } from './sections/ProjecaoSection'
import { VisaoGeralSection } from './sections/VisaoGeralSection'
import { SECTIONS, findSection, usePeriodFilter } from './usePeriodFilter'
import {
  useDreData,
  useOrcamentoData,
  useProductsData,
  useProjectionData,
} from './useAnalyticsData'
import { money, useVisaoGeralData } from './useVisaoGeralData'

/**
 * Shell da Central Financeira (P4/P5/P6): Page/PageHeader + filtros globais
 * (presets V1) + abas das 15 seções com deep-link `?secao=`.
 *
 * Visão Geral (P5) e as analíticas I (P6: DRE, Produtos, Orçamento,
 * Projeção) são reais; as demais seguem placeholder até P7–P8. O shell
 * busca os dados e injeta na seção (§2.2) — os hooks só disparam o GET da
 * seção ativa.
 */
export function CentralFinanceiraPage() {
  const { days, setDays, presets, secao, setSecao } = usePeriodFilter()
  const atual = findSection(secao)
  const { hasPermission } = useAuth()
  const vg = useVisaoGeralData(days)
  const dre = useDreData(days, secao === 'dre')
  const produtos = useProductsData(days, secao === 'produtos')
  const projecao = useProjectionData(days, secao === 'projecao')
  const orcamento = useOrcamentoData(days, secao === 'orcamento')
  const can = useMemo(
    () => ({
      write: hasPermission('finance.write'),
      receive: hasPermission('finance.receive'),
    }),
    [hasPermission]
  )

  let content: ReactNode
  if (secao === 'visao-geral') {
    content = (
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
    )
  } else if (secao === 'dre') {
    content = (
      <SectionShell
        title="DRE"
        loading={dre.data === null && !dre.error}
        error={dre.data === null && dre.error}
        onRetry={() => void dre.reload()}
        empty={dre.data !== null && money(dre.data.revenue) === 0 && money(dre.data.expenses) === 0}
        emptyIcon={BarChart3}
        emptyTitle="Sem movimentações no período"
        emptyDescription="Não há receita nem despesa operacional no período escolhido."
      >
        {dre.data ? <DreSection data={dre.data} /> : null}
      </SectionShell>
    )
  } else if (secao === 'produtos') {
    content = (
      <SectionShell
        title="Produtos"
        loading={produtos.data === null && !produtos.error}
        error={produtos.data === null && produtos.error}
        onRetry={() => void produtos.reload()}
        empty={produtos.data !== null && produtos.data.items.length === 0}
        emptyIcon={Boxes}
        emptyTitle="Nenhum produto vendido"
        emptyDescription="Não há itens de pedido no período escolhido."
      >
        {produtos.data ? <ProdutosSection data={produtos.data} /> : null}
      </SectionShell>
    )
  } else if (secao === 'projecao') {
    content = (
      <SectionShell
        title="Projeção"
        loading={projecao.data === null && !projecao.error}
        error={projecao.data === null && projecao.error}
        onRetry={() => void projecao.reload()}
        empty={projecao.data !== null && projecao.data.daily.length === 0}
        emptyIcon={Wallet}
        emptyTitle="Projeção indisponível"
        emptyDescription="Sem série diária para projetar no horizonte escolhido."
      >
        {projecao.data ? <ProjecaoSection data={projecao.data} /> : null}
      </SectionShell>
    )
  } else if (secao === 'orcamento') {
    content = (
      <SectionShell
        title="Orçamento"
        loading={orcamento.data === null && !orcamento.error}
        error={orcamento.data === null && orcamento.error}
        onRetry={() => void orcamento.reload()}
        empty={
          orcamento.data !== null &&
          orcamento.data.budget.items.length === 0 &&
          orcamento.data.realized.items.length === 0
        }
        emptyIcon={Target}
        emptyTitle="Sem orçamento nem despesas"
        emptyDescription="Defina as metas do mês ou registre despesas para comparar."
      >
        {orcamento.data ? (
          <OrcamentoSection
            data={orcamento.data}
            days={days}
            canWrite={can.write}
            saving={orcamento.saving}
            onSave={orcamento.save}
          />
        ) : null}
      </SectionShell>
    )
  } else {
    content = (
      <SectionShell
        title={atual.label}
        empty
        emptyIcon={Landmark}
        emptyTitle={`${atual.label} — em construção`}
        emptyDescription={`Esta seção entra no PR ${atual.pr} da Central Financeira.`}
      />
    )
  }

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
          {secao === 'visao-geral' && (
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

      {content}
    </Page>
  )
}
