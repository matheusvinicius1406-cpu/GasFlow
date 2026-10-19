/**
 * Classificação única de falha de request para os estados de UI (I1/P2).
 *
 * Regras:
 * - `403` → `permission` (inclusive o 403 de "senha pendente", que já levanta o gate).
 * - Qualquer outro status HTTP → `unknown` (o backend respondeu; é erro normal).
 * - Sem resposta HTTP (rede caiu, timeout de 10 s do `apiClient`, mock) → `offline`.
 * - `null`/`undefined` → `unknown` (sem informação, título genérico).
 */
export type RequestFailure = 'permission' | 'offline' | 'unknown'

interface AxiosLikeError {
  response?: { status?: number }
}

export const FAILURE_TITLES: Record<RequestFailure, string> = {
  permission: 'Sem permissão',
  offline: 'Sem conexão',
  unknown: 'Algo deu errado',
}

export function classifyRequestFailure(error: unknown): RequestFailure {
  if (error == null) return 'unknown'
  // Booleano (estado antigo `const [error, setError] = useState(false)`) não
  // carrega informação nenhuma — tratar como "sem falha classificada" evita
  // mentir "Sem conexão" durante a migração dos call sites.
  if (typeof error === 'boolean') return 'unknown'
  const status = (error as AxiosLikeError)?.response?.status
  if (typeof status !== 'number') return 'offline'
  return status === 403 ? 'permission' : 'unknown'
}

export function failureTitle(error: unknown): string {
  return FAILURE_TITLES[classifyRequestFailure(error)]
}
