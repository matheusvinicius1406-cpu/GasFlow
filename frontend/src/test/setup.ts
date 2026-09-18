import '@testing-library/jest-dom'

// window.print é usado como fallback de export PDF (F9) — jsdom não o
// implementa; stub global para os testes poderem verificar a chamada.
window.print = window.print || (() => undefined)
