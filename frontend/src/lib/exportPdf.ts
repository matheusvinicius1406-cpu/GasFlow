/**
 * Exportação da view atual como PDF — F10.9
 *
 * Dentro do app (Electron) usa o `printToPDF` do conteúdo JÁ renderizado: é o
 * único caminho que preserva o que está na tela (gráficos, tabela). O PDF do
 * backend (`/reports/daily.pdf`) só existe para o resumo de um dia.
 *
 * Fora do app (navegador/dev) cai no diálogo de impressão do sistema — o
 * usuário escolhe "Salvar como PDF" ali mesmo.
 *
 * Devolve o modo usado para quem chamou poder avisar o operador.
 */

export type ExportPdfMode = 'pdf' | 'print'

export async function exportCurrentViewPdf(): Promise<ExportPdfMode> {
  const bridge = (window as { gasflow?: { exportCurrentViewPdf?: () => Promise<unknown> } }).gasflow
  if (bridge?.exportCurrentViewPdf) {
    await bridge.exportCurrentViewPdf()
    return 'pdf'
  }
  window.print()
  return 'print'
}
