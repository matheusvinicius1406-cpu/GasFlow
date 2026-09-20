import '@testing-library/jest-dom'

// window.print é usado como fallback de export PDF (F9) — jsdom não o
// implementa; stub global para os testes poderem verificar a chamada.
window.print = window.print || (() => undefined)

// URL.createObjectURL/revokeObjectURL também não existem no jsdom e são o
// caminho do download de CSV (F10.9) — sem eles, exportar quebraria só nos
// testes, escondendo o comportamento real.
if (!URL.createObjectURL) {
  URL.createObjectURL = () => 'blob:gasflow-test'
}
if (!URL.revokeObjectURL) {
  URL.revokeObjectURL = () => undefined
}
