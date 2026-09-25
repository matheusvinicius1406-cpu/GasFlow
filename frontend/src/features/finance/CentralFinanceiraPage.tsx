import { useMemo, type ReactNode } from 'react'
import {
  BarChart3,
  Boxes,
  Calculator,
  CalendarDays,
  CreditCard,
  FileDown,
  History,
  Landmark,
  LineChart,
  Link2,
  Target,
  Users,
  Wallet,
} from 'lucide-react'
import { Page, PageActions, PageHeader, PageTitle } from '@/components/layout/Page'
import { Button } from '@/components/ui/Button'
import { useAuth } from '@/features/auth'
import { toCsvDate } from './exportPeriodCsv'
import { SectionShell } from './SectionShell'
import { AuditoriaSection } from './sections/AuditoriaSection'
import { CalendarioSection } from './sections/CalendarioSection'
import { ClientesSection } from './sections/ClientesSection'
import { ConciliacaoSection } from './sections/ConciliacaoSection'
import { DreSection } from './sections/DreSection'
import { EquipeSection } from './sections/EquipeSection'
import { MapaCalorSection } from './sections/MapaCalorSection'
import { OrcamentoSection } from './sections/OrcamentoSection'
import { PagamentosSection } from './sections/PagamentosSection'
import { ProdutosSection } from './sections/ProdutosSection'
import { ProjecaoSection } from './sections/ProjecaoSection'
import { SalvosSection } from './sections/SalvosSection'
import { SimuladorSection } from './sections/SimuladorSection'
import { TendenciaSection } from './sections/TendenciaSection'
import { VisaoGeralSection } from './sections/VisaoGeralSection'
import { SECTIONS, findSection, usePeriodFilter } from './usePeriodFilter'
import {
  useAuditoriaData,
  useCalendarioData,
  useClientesData,
  useConciliacaoData,
  useDreData,
  useEquipeData,
  useMethodsData,
  useOrcamentoData,
  useProductsData,
  useProjectionData,
  useSalvosData,
  useSimuladorData,
  useTendenciaData,
} from './useAnalyticsData'
import { money, useVisaoGeralData } from './useVisaoGeralData'

/** Estados loading/error de uma seção a partir do estado de um hook. */
function sectionState(state: { data: unknown; error: boolean }) {
  return { loading: state.data === null && !state.error, error: state.data === null && state.error }
}

/**
 * Shell da Central Financeira (P4–P8): Page/PageHeader + filtros globais
 * (presets V1) + abas das 15 seções com deep-link `?secao=`.
 *
 * Todas as 15 seções estão reais: Visão Geral (P5), analíticas I (P6:
 * DRE, Produtos, Orçamento, Projeção), II (P7: Clientes, Pagamentos,
 * Calendário, Tendência, Simulador) e III (P8: Conciliação, Auditoria,
 * Relatórios Salvos, Equipe, Mapa de Calor). O shell busca os dados e
 * injeta na seção (§2.2) — os hooks só disparam o GET da seção ativa.
 */
export function CentralFinanceiraPage() {
  const { days, setDays, presets, secao, setSecao } = usePeriodFilter()
  const atual = findSection(secao)
  const { hasPermission } = useAuth()
  const can = useMemo(
    () => ({
      write: hasPermission('finance.write'),
      receive: hasPermission('finance.receive'),
      audit: hasPermission('audit.view'),
    }),
    [hasPermission]
  )

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
  const conciliacao = useConciliacaoData(days, secao === 'conciliacao')
  const auditoria = useAuditoriaData(days, secao === 'auditoria' && can.audit)
  const salvos = useSalvosData(secao === 'salvos')
  const equipe = useEquipeData(days, secao === 'equipe')

  // A seção de Auditoria fica oculta sem `audit.view` (o backend também exige).
  const secoes = can.audit ? SECTIONS : SECTIONS.filter((s) => s.slug !== 'auditoria')

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
              dre.data !== null && money(dre.data.revenue) === 0 && money(dre.data.expenses) === 0
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

      case 'conciliacao':
        return (
          <SectionShell
            title="Conciliação"
            {...sectionState(conciliacao)}
            onRetry={() => void conciliacao.reload()}
            empty={
              conciliacao.data !== null &&
              conciliacao.data.checked === 0 &&
              conciliacao.data.items.length === 0
            }
            emptyIcon={Link2}
            emptyTitle="Nada a conciliar no período"
            emptyDescription="Não há pagamentos registrados no período escolhido."
          >
            {conciliacao.data ? <ConciliacaoSection data={conciliacao.data} /> : null}
          </SectionShell>
        )

      case 'auditoria':
        if (!can.audit) {
          return (
            <SectionShell
              title="Auditoria"
              empty
              emptyIcon={Landmark}
              emptyTitle="Sem permissão"
              emptyDescription="Você precisa da permissão audit.view para ver a trilha de auditoria."
            />
          )
        }
        return (
          <SectionShell
            title="Auditoria"
            {...sectionState(auditoria)}
            onRetry={() => void auditoria.reload()}
            empty={auditoria.data !== null && auditoria.data.items.length === 0}
            emptyIcon={History}
            emptyTitle="Nenhum evento no período"
            emptyDescription="A trilha registra só eventos a partir do deploy da Central Financeira."
          >
            {auditoria.data ? <AuditoriaSection data={auditoria.data} /> : null}
          </SectionShell>
        )

      case 'salvos':
        return (
          <SectionShell title="Relatórios Salvos" {...sectionState(salvos)} onRetry={() => void salvos.reload()}>
            {salvos.data ? (
              <SalvosSection
                data={salvos.data}
                canWrite={can.write}
                saving={salvos.saving}
                onCreate={salvos.create}
                onDelete={(report) => salvos.remove(report.id)}
              />
            ) : null}
          </SectionShell>
        )

      case 'equipe':
        return (
          <SectionShell title="Equipe" {...sectionState(equipe)} onRetry={() => void equipe.reload()}>
            {equipe.data ? <EquipeSection data={equipe.data} /> : null}
          </SectionShell>
        )

      case 'mapa-de-calor':
        return (
          <SectionShell title="Mapa de Calor">
            <MapaCalorSection />
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
        {secoes.map((s) => (
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
