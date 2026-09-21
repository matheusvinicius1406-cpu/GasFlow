/**
 * Splash de entrada do app.
 *
 * O splash vive em `index.html` (markup + CSS inline) para pintar no primeiro
 * frame, antes do bundle chegar. Assim que o React monta, o app está na tela
 * atrás dele e este módulo dissolve o splash em vez de simplesmente apagá-lo —
 * é a animação de entrada do sistema.
 *
 * O id é o contrato com o HTML; o mesmo valor está documentado lá.
 */
export const BOOT_SPLASH_ID = 'gasflow-boot-splash'

/** Classe que dispara o fade-out (definida no `<style>` do index.html). */
const LEAVE_CLASS = 'gf-boot--leave'

/** Deve cobrir a transição de `opacity` do `.gf-boot` (0.34s no HTML). */
export const BOOT_SPLASH_FADE_MS = 400

/**
 * Dissolve e remove o splash de entrada. Idempotente e seguro fora do
 * navegador (sem o nó, é no-op — ex.: testes, mobile).
 */
export function dismissBootSplash(doc: Document = document): void {
  const splash = doc.getElementById(BOOT_SPLASH_ID)
  if (!splash) return

  // Marca como saindo uma única vez: chamadas repetidas não reiniciam o fade.
  if (splash.classList.contains(LEAVE_CLASS)) return
  splash.classList.add(LEAVE_CLASS)

  // Remove de fato ao fim do fade: o nó sai do DOM e deixa de interceptar
  // cliques, mesmo se o CSS não carregar.
  setTimeout(() => splash.remove(), BOOT_SPLASH_FADE_MS)
}
