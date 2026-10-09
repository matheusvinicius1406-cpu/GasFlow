import { useCallback, useState } from 'react'
import { useSearchParams } from 'react-router-dom'

/** Presets de período da Central Financeira (V1): Hoje / 7 / 30 / 90 / 180. */
export interface PeriodPreset {
  days: number
  label: string
}

export const PERIOD_PRESETS: PeriodPreset[] = [
  { days: 1, label: 'Hoje' },
  { days: 7, label: '7 dias' },
  { days: 30, label: '30 dias' },
  { days: 90, label: '90 dias' },
  { days: 180, label: '180 dias' },
]

export const DEFAULT_DAYS = 30
export const DEFAULT_SECAO = 'visao-geral'

/**
 * As 15 seções da Central Financeira. `pr` = PR que entrega a seção
 * (docs/auditoria/central-financeira-fase2.md §4) — o shell usa no
 * placeholder até a seção existir de verdade.
 */
export interface SectionDef {
  slug: string
  label: string
  pr: string
}

const VISAO_GERAL: SectionDef = { slug: 'visao-geral', label: 'Visão Geral', pr: 'P5' }

export const SECTIONS: SectionDef[] = [
  VISAO_GERAL,
  { slug: 'dre', label: 'DRE', pr: 'P6' },
  { slug: 'projecao', label: 'Projeção', pr: 'P6' },
  { slug: 'orcamento', label: 'Orçamento', pr: 'P6' },
  { slug: 'produtos', label: 'Produtos', pr: 'P6' },
  { slug: 'clientes', label: 'Clientes', pr: 'P7' },
  { slug: 'pagamentos', label: 'Pagamentos', pr: 'P7' },
  { slug: 'calendario', label: 'Calendário', pr: 'P7' },
  { slug: 'tendencia', label: 'Tendência', pr: 'P7' },
  { slug: 'simulador', label: 'Simulador', pr: 'P7' },
  { slug: 'conciliacao', label: 'Conciliação', pr: 'P8' },
  { slug: 'auditoria', label: 'Auditoria', pr: 'P8' },
  { slug: 'salvos', label: 'Relatórios Salvos', pr: 'P8' },
  { slug: 'equipe', label: 'Equipe', pr: 'P8' },
  { slug: 'mapa-de-calor', label: 'Mapa de Calor', pr: 'P8' },
]

/** Seção a partir do slug (URL desconhecida cai na Visão Geral). */
export function findSection(slug: string): SectionDef {
  return SECTIONS.find((s) => s.slug === slug) ?? VISAO_GERAL
}

/**
 * Estado global do shell: período (presets V1), busca e seção ativa.
 * A seção vive em `?secao=<slug>` (deep-link; padrão `visao-geral`) —
 * §2.1 do plano da Fase 2.
 */
export function usePeriodFilter() {
  const [searchParams, setSearchParams] = useSearchParams()
  const [days, setDays] = useState<number>(DEFAULT_DAYS)

  const secaoParam = searchParams.get('secao')
  const secao = secaoParam && SECTIONS.some((s) => s.slug === secaoParam) ? secaoParam : DEFAULT_SECAO

  const setSecao = useCallback(
    (slug: string) => {
      const next = new URLSearchParams(searchParams)
      next.set('secao', slug)
      setSearchParams(next, { replace: true })
    },
    [searchParams, setSearchParams]
  )

  return { days, setDays, presets: PERIOD_PRESETS, secao, setSecao }
}
