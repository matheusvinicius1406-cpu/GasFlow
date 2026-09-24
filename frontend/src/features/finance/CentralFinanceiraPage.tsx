import { Landmark } from 'lucide-react'
import { Page, PageActions, PageHeader, PageTitle } from '@/components/layout/Page'
import { Button } from '@/components/ui/Button'
import { SectionShell } from './SectionShell'
import { SECTIONS, findSection, usePeriodFilter } from './usePeriodFilter'

/**
 * Shell da Central Financeira (P4): Page/PageHeader + filtros globais
 * (presets V1) + abas das 15 seções com deep-link `?secao=`.
 * As seções chegam nos PRs P5–P8; por ora cada aba mostra placeholder.
 */
export function CentralFinanceiraPage() {
  const { days, setDays, presets, secao, setSecao } = usePeriodFilter()
  const atual = findSection(secao)

  return (
    <Page>
      <PageHeader>
        <PageTitle subtitle="Financeiro e relatórios em uma tela só.">Central Financeira</PageTitle>
        <PageActions>
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

      <SectionShell
        title={atual.label}
        empty
        emptyIcon={Landmark}
        emptyTitle={`${atual.label} — em construção`}
        emptyDescription={`Esta seção entra no PR ${atual.pr} da Central Financeira.`}
      />
    </Page>
  )
}
