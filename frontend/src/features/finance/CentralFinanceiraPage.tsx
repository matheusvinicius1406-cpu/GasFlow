import { useMemo, type ReactNode } from 'react'
import {
  BarChart3,
  Boxes,
  Calculator,
  CalendarDays,
  CreditCard,
  FileDown,
  Landmark,
  LineChart,
  Target,
  Users,
  Wallet,
} from 'lucide-react'
import { Page, PageActions, PageHeader, PageTitle } from '@/components/layout/Page'
import { Button } from '@/components/ui/Button'
import { useAuth } from '@/features/auth'
import { toCsvDate } from './exportPeriodCsv'
import { SectionShell } from './SectionShell'
import { CalendarioSection } from './sections/CalendarioSection'
import { ClientesSection } from './sections/ClientesSection'
import { DreSection } from './sections/DreSection'
import { OrcamentoSection } from './sections/OrcamentoSection'
import { PagamentosSection } from './sections/PagamentosSection'
import { ProdutosSection } from './sections/ProdutosSection'
import { ProjecaoSection } from './sections/ProjecaoSection'
import { SimuladorSection } from './sections/SimuladorSection'
import { TendenciaSection } from './sections/TendenciaSection'
import { VisaoGeralSection } from './sections/VisaoGeralSection'
import { SECTIONS, findSection, usePeriodFilter } from './usePeriodFilter'
import {
  useCalendarioData,
  useClientesData,
  useDreData,
  useMethodsData,
  useOrcamentoData,
  useProductsData,
  useProjectionData,
  useSimuladorData,
  useTendenciaData,
} from './useAnalyticsData'
import { money, useVisaoGeralData } from './useVisaoGeralData'

/** Estados loading/error de uma seção a partir do estado de um hook. */
function sectionState(state: { data: unknown; error: boolean }) {
  return { loading: state.data === null && !state.error, error: state.data === null && state.error }
}

/**
 * Shell da Central Financeira (P4–P7): Page/PageHeader + filtros globais
 * (presets V1) + abas das 15 seções com deep-link `?secao=`.
 *
 * Reais até aqui: Visão Geral (P5), analíticas I (P6: DRE, Produtos,
 * Orçamento, Projeção) e analíticas II (P7: Clientes, Pagamentos,
 * Calendário, Tendência, Simulador). As demais seguem placeholder até P8.
 * O shell busca os dados e injeta na seção (§2.2) — os hooks só disparam o
 * GET da seção ativa.
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
  const clientes = useClientesData(secao === 'clientes')
  const pagamentos = useMethodsData(days, secao === 'pagamentos')
  const calendario = useCalendarioData(days, secao === 'calendario')
  const tendencia = useTendenciaData(days, secao === 'tendencia')
  const simulador = useSimuladorData(days, secao === 'simulador')
  const can = useMemo(
    () => ({
      write: hasPermission('finance.write'),
      receive: hasPermission('finance.receive'),
    }),
    [hasPermission]
  )

  function sectionContent(): ReactNode {
    switch (secao) {
      case 'visao-geral':
        return (
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

      case 'dre':
        return (
          <SectionShell
            title="DRE"
            {...sectionState(dre)}
            onRetry={() => void dre.reload()}
            empty={
              dre.data !== null &&
              money(dre.data.revenue) === 0 &&
              money(dre.data.expenses) === 0
            }
            emptyIcon={BarChart3}
            emptyTitle="Sem movimentações no período"
            emptyDescription="Não há receita nem despesa operacional no período escolhido."
          >
            {dre.data ? <DreSection data={dre.data} /> : null}
          </SectionShell>
        )

      case 'produtos':
        return (
          <SectionShell
            title="Produtos"
            {...sectionState(produtos)}
            onRetry={() => void produtos.reload()}
            empty={produtos.data !== null && produtos.data.items.length === 0}
            emptyIcon={Boxes}
            emptyTitle="Nenhum produto vendido"
            emptyDescription="Não há itens de pedido no período escolhido."
          >
            {produtos.data ? <ProdutosSection data={produtos.data} /> : null}
          </SectionShell>
        )

      case 'projecao':
        return (
          <SectionShell
            title="Projeção"
            {...sectionState(projecao)}
            onRetry={() => void projecao.reload()}
            empty={projecao.data !== null && projecao.data.daily.length === 0}
            emptyIcon={Wallet}
            emptyTitle="Projeção indisponível"
            emptyDescription="Sem série diária para projetar no horizonte escolhido."
          >
            {projecao.data ? <ProjecaoSection data={projecao.data} /> : null}
          </SectionShell>
        )

      case 'orcamento':
        return (
          <SectionShell
            title="Orçamento"
            {...sectionState(orcamento)}
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

      case 'clientes':
        return (
          <SectionShell
            title="Clientes"
            {...sectionState(clientes)}
            onRetry={() => void clientes.reload()}
            empty={
              clientes.data !== null &&
              clientes.data.summary.open_count === 0 &&
              clientes.data.overdue.length === 0
            }
            emptyIcon={Users}
            emptyTitle="Nenhum recebível em aberto"
            emptyDescription="Não há títulos a receber nem vencidos."
          >
            {clientes.data ? <ClientesSection data={clientes.data} /> : null}
          </SectionShell>
        )

      case 'pagamentos':
        return (
          <SectionShell
            title="Pagamentos"
            {...sectionState(pagamentos)}
            onRetry={() => void pagamentos.reload()}
            empty={pagamentos.data !== null && pagamentos.data.items.length === 0}
            emptyIcon={CreditCard}
            emptyTitle="Nenhum pagamento no período"
            emptyDescription="Não há recebimentos registrados no período escolhido."
          >
            {pagamentos.data ? <PagamentosSection data={pagamentos.data} /> : null}
          </SectionShell>
        )

      case 'calendario':
        return (
          <SectionShell
            title="Calendário"
            {...sectionState(calendario)}
            onRetry={() => void calendario.reload()}
            empty={calendario.data !== null && calendario.data.a.daily.length === 0}
            emptyIcon={CalendarDays}
            emptyTitle="Sem dias no período"
            emptyDescription="Não há fluxo diário para desenhar o calendário."
          >
            {calendario.data ? (
              <CalendarioSection data={{ period: calendario.data.a, hourly: calendario.data.b }} />
            ) : null}
          </SectionShell>
        )

      case 'tendencia':
        return (
          <SectionShell
            title="Tendência"
            {...sectionState(tendencia)}
            onRetry={() => void tendencia.reload()}
            empty={tendencia.data !== null && tendencia.data.daily.length === 0}
            emptyIcon={LineChart}
            emptyTitle="Sem série para analisar"
            emptyDescription="Não há fluxo diário no período escolhido."
          >
            {tendencia.data ? <TendenciaSection data={tendencia.data} /> : null}
          </SectionShell>
        )

      case 'simulador':
        return (
          <SectionShell
            title="Simulador"
            {...sectionState(simulador)}
            onRetry={() => void simulador.reload()}
            empty={simulador.data !== null && simulador.data.a.daily.length === 0}
            emptyIcon={Calculator}
            emptyTitle="Sem dados para simular"
            emptyDescription="Não há fluxo diário no período escolhido."
          >
            {simulador.data ? (
              <SimuladorSection data={{ period: simulador.data.a, receivables: simulador.data.b }} />
            ) : null}
          </SectionShell>
        )

      default:
        return (
          <SectionShell
            title={atual.label}
            empty
            emptyIcon={Landmark}
            emptyTitle={`${atual.label} — em construção`}
            emptyDescription={`Esta seção entra no PR ${atual.pr} da Central Financeira.`}
          />
        )
    }
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

      {sectionContent()}
    </Page>
  )
}
