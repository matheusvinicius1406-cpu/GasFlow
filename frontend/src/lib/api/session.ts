/**
 * Chaves da sessão (B5) — módulo próprio de propósito.
 *
 * O cliente de API (`client.ts`) é mockado inteiro em vários testes
 * (`vi.mock('@/lib/api/client')`). Constantes que todo o app lê não podem
 * morar lá: quem mocka o módulo passaria a precisar reexportá-las, e um
 * `AuthProvider` montado em teste quebraria sem motivo. Aqui elas são apenas
 * dados, sem dependência de axios.
 */

/** Access JWT curto — vai no header `Authorization` de cada request. */
export const ACCESS_TOKEN_KEY = 'gasflow_token'

/**
 * Refresh opaco e rotativo. **Nunca** vai no header de request do dia a dia:
 * só na chamada de `/auth/refresh`. Deixá-lo vazar é entregar a sessão.
 *
 * As strings são literais (não `import.meta`/prefixo) porque o gate IPC do
 * desktop e o bridge de realtime leem `gasflow_token` direto do localStorage.
 */
export const REFRESH_TOKEN_KEY = 'gasflow_refresh'

/** Emitido quando o access é renovado — o desktop re-registra o token no main. */
export const SESSION_REFRESHED_EVENT = 'gasflow:session-refreshed'

/**
 * Emitido quando o backend recusa uma rota por troca de senha pendente
 * (`403` + `detail: "Password change required"`). O `AuthProvider` ouve e
 * levanta o gate — sem isso um reset em pleno uso viraria um 403 mudo.
 */
export const PASSWORD_CHANGE_REQUIRED_EVENT = 'gasflow:password-change-required'
