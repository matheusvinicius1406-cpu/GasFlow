/**
 * Fila local do cadastro por convite (F10.5).
 *
 * Se a API central estiver fora do ar quando o cliente enviar o formulário,
 * os dados ficam guardados neste aparelho e a página reenvia sozinha:
 * ao voltar a internet, ao reabrir o link e, com a página aberta, com
 * backoff crescente.
 *
 * Reenviar é seguro porque o backend é idempotente por (token + telefone):
 * se a resposta se perdeu depois do commit, ele devolve o MESMO cupom em vez
 * de "convite já utilizado".
 *
 * Tudo aqui é best-effort: navegador com armazenamento bloqueado (aba
 * anônima/privacidade rígida) apenas não guarda nada — a página segue
 * mostrando o erro do envio normalmente.
 */

/** Corpo enviado ao endpoint público (mesmos nomes da API). */
export interface SignupPayload {
  inviteToken: string
  name: string
  phone: string
  rua: string
  numero: string
  bairro: string
  complemento?: string
  lgpdConsent: boolean
}

export interface PendingSignup {
  token: string
  payload: SignupPayload
  savedAt: string
  attempts: number
}

const STORAGE_KEY = 'gasflow_invite_pending'

/** Cadastro guardado muito tempo depois quase sempre já foi resolvido na
 *  loja por outro caminho — descartamos para não acumular lixo no aparelho. */
export const MAX_AGE_MS = 7 * 24 * 60 * 60 * 1000

/** Backoff do reenvio automático (ms) — teto no último valor. */
export const RETRY_DELAYS_MS: readonly number[] = [3_000, 8_000, 20_000, 60_000]
const RETRY_DELAY_MAX_MS = 60_000

function readAll(): Record<string, PendingSignup> {
  try {
    const raw = localStorage.getItem(STORAGE_KEY)
    if (!raw) return {}
    const parsed = JSON.parse(raw)
    return parsed && typeof parsed === 'object' ? (parsed as Record<string, PendingSignup>) : {}
  } catch {
    // JSON corrompido ou armazenamento indisponível → começa limpo
    return {}
  }
}

function writeAll(all: Record<string, PendingSignup>): void {
  try {
    if (Object.keys(all).length === 0) localStorage.removeItem(STORAGE_KEY)
    else localStorage.setItem(STORAGE_KEY, JSON.stringify(all))
  } catch {
    /* sem armazenamento → não persiste (a página continua funcionando) */
  }
}

/** Cadastro guardado para este convite, se ainda for recente. */
export function loadPending(token: string): PendingSignup | null {
  if (!token) return null
  const record = readAll()[token]
  if (!record) return null
  const savedAt = Date.parse(record.savedAt || '')
  if (!Number.isFinite(savedAt) || Date.now() - savedAt > MAX_AGE_MS) {
    clearPending(token)
    return null
  }
  return record
}

export function savePending(token: string, payload: SignupPayload, attempts = 0): PendingSignup {
  const record: PendingSignup = {
    token,
    payload,
    savedAt: new Date().toISOString(),
    attempts,
  }
  const all = readAll()
  all[token] = record
  writeAll(all)
  return record
}

export function clearPending(token: string): void {
  const all = readAll()
  if (!(token in all)) return
  delete all[token]
  writeAll(all)
}

/** Marca mais uma tentativa de reenvio (para o cálculo do backoff). */
export function bumpAttempts(token: string): PendingSignup | null {
  const record = loadPending(token)
  if (!record) return null
  return savePending(token, record.payload, record.attempts + 1)
}

/** Usado pelos testes/limpeza manual. */
export function clearAllPending(): void {
  try {
    localStorage.removeItem(STORAGE_KEY)
  } catch {
    /* best-effort */
  }
}

/**
 * Falha que vale a pena reenviar?
 *
 * - sem `response` (rede fora, túnel caído, timeout) → sim
 * - 5xx / 408 / 425 / 429 → sim (servidor ou limite temporário)
 * - demais 4xx (token inválido/expirado, já usado, validação) → não: reenviar
 *   daria o mesmo resultado e só irritaria o cliente.
 */
export function isTransientFailure(error: unknown): boolean {
  const status = (error as { response?: { status?: number } } | null)?.response?.status
  if (typeof status !== 'number') return true
  if (status >= 500) return true
  return status === 408 || status === 425 || status === 429
}

/** Espera antes do próximo reenvio (teto no último valor da tabela). */
export function retryDelayMs(attempts: number): number {
  const index = Math.min(Math.max(attempts, 0), RETRY_DELAYS_MS.length - 1)
  return RETRY_DELAYS_MS[index] ?? RETRY_DELAY_MAX_MS
}
