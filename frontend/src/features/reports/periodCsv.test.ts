import { describe, it, expect } from 'vitest'
import { buildPeriodCsv, periodCsvFilename, toCsvDate, toCsvMoney } from './periodCsv'

const relatorio = {
  from: '2026-09-04',
  to: '2026-09-06',
  days: 3,
  total_receipts: '150.00',
  total_expenses: '50.00',
  net_result: '100.00',
  daily: [
    { date: '2026-09-04', receipts: '50.00', expenses: '20.00', net_result: '30.00' },
    { date: '2026-09-05', receipts: '0.00', expenses: '0.00', net_result: '0.00' },
    { date: '2026-09-06', receipts: '100.00', expenses: '30.00', net_result: '70.00' },
  ],
}

describe('periodCsv (F10.9)', () => {
  it('formata dinheiro com vírgula e data em pt-BR', () => {
    expect(toCsvMoney('1234.5')).toBe('1234,50')
    expect(toCsvMoney(0)).toBe('0,00')
    expect(toCsvMoney('não é número')).toBe('0,00')
    expect(toCsvDate('2026-09-19')).toBe('19/09/2026')
    expect(toCsvDate('2026-09-19T12:00:00')).toBe('19/09/2026')
  })

  it('usa ponto e vírgula e BOM (Excel pt-BR abre certo e sem acento quebrado)', () => {
    const csv = buildPeriodCsv(relatorio)

    expect(csv.startsWith('\ufeff')).toBe(true)
    expect(csv).toContain('Data;Recebimentos;Despesas;Resultado')
    expect(csv.split('\r\n')[1]).toBe('04/09/2026;50,00;20,00;30,00')
  })

  it('inclui todos os dias do período, inclusive os zerados, e o TOTAL', () => {
    const linhas = buildPeriodCsv(relatorio).replace('\ufeff', '').split('\r\n')

    expect(linhas).toContain('05/09/2026;0,00;0,00;0,00')
    expect(linhas).toContain('TOTAL;150,00;50,00;100,00')
    expect(linhas).toContain('Período;04/09/2026;06/09/2026')
    expect(linhas).toContain('Dias;3')
  })

  it('nomeia o arquivo com o período exportado', () => {
    expect(periodCsvFilename(relatorio)).toBe('relatorio_2026-09-04_a_2026-09-06.csv')
  })
})
