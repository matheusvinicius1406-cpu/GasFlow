/**
 * CSV do relatório por período — F10.9
 *
 * Separador `;` e vírgula decimal: é o que o Excel em português abre certo ao
 * dar duplo clique (com `,` ele joga tudo numa coluna só). O BOM (\ufeff) é o
 * que faz o Excel reconhecer o UTF-8 sem "Ã§" nos acentos.
 *
 * Função pura de propósito: o conteúdo exportado é conferível em teste, sem
 * tocar em DOM/arquivo.
 */

export interface PeriodDayPoint {
  date: string
  receipts: number | string
  expenses: number | string
  net_result: number | string
}

export interface PeriodReportCsvInput {
  from: string
  to: string
  days: number
  total_receipts: number | string
  total_expenses: number | string
  net_result: number | string
  daily: PeriodDayPoint[]
}

/** 1234.5 → "1234,50" (o formato que o Excel pt-BR entende como número). */
export function toCsvMoney(value: number | string): string {
  const n = Number(value)
  return Number.isFinite(n) ? n.toFixed(2).replace('.', ',') : '0,00'
}

/** "2026-09-19" → "19/09/2026" (data que o operador lê, não ISO). */
export function toCsvDate(iso: string): string {
  const [ano, mes, dia] = iso.slice(0, 10).split('-')
  return ano && mes && dia ? `${dia}/${mes}/${ano}` : iso
}

export function buildPeriodCsv(report: PeriodReportCsvInput): string {
  const linhas: string[] = []

  linhas.push('Data;Recebimentos;Despesas;Resultado')
  for (const dia of report.daily) {
    linhas.push(
      [
        toCsvDate(dia.date),
        toCsvMoney(dia.receipts),
        toCsvMoney(dia.expenses),
        toCsvMoney(dia.net_result),
      ].join(';')
    )
  }
  linhas.push(
    ['TOTAL', toCsvMoney(report.total_receipts), toCsvMoney(report.total_expenses), toCsvMoney(report.net_result)].join(';')
  )
  linhas.push('')
  linhas.push(`Período;${toCsvDate(report.from)};${toCsvDate(report.to)}`)
  linhas.push(`Dias;${report.days}`)

  return `\ufeff${linhas.join('\r\n')}\r\n`
}

export function periodCsvFilename(report: Pick<PeriodReportCsvInput, 'from' | 'to'>): string {
  return `relatorio_${report.from}_a_${report.to}.csv`
}

/** Dispara o download do CSV no navegador/app (Blob + link temporário). */
export function downloadPeriodCsv(report: PeriodReportCsvInput): void {
  const blob = new Blob([buildPeriodCsv(report)], { type: 'text/csv;charset=utf-8' })
  const url = URL.createObjectURL(blob)
  try {
    const link = document.createElement('a')
    link.href = url
    link.download = periodCsvFilename(report)
    document.body.appendChild(link)
    link.click()
    link.remove()
  } finally {
    // Sem revogar, o Blob fica preso na memória da janela.
    URL.revokeObjectURL(url)
  }
}
