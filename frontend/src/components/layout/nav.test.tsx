import { describe, expect, it } from 'vitest'
import { NAV_GROUPS } from './nav'

function hrefs(): string[] {
  return NAV_GROUPS.flatMap((entry) =>
    entry.href ? [entry.href] : (entry.items ?? []).map((item) => item.href),
  )
}

describe('NAV_GROUPS', () => {
  it('não deixa telas internas fora do menu (Automações e Integrações)', () => {
    // Regressão: as duas rotas existiam em App.tsx e não tinham link em
    // lugar nenhum — o gate antigo não acusava porque "/" mascarava o check.
    expect(hrefs()).toContain('/automation')
    expect(hrefs()).toContain('/settings/integrations')
  })

  it('não repete destinos no menu', () => {
    const all = hrefs()
    expect(new Set(all).size).toBe(all.length)
  })
})
