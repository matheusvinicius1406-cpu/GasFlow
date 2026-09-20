import { useCallback, useEffect, useRef, useState, type FormEvent } from 'react'
import { useSearchParams, Link } from 'react-router-dom'
import { apiClient } from '@/lib/api/client'
import { Button } from '@/components/ui/Button'
import { Input } from '@/components/ui/Input'
import { LoadingSpinner } from '@/components/ui/LoadingSpinner'
import {
  bumpAttempts,
  clearPending,
  isTransientFailure,
  loadPending,
  retryDelayMs,
  savePending,
  type PendingSignup,
  type SignupPayload,
} from './pendingSignup'

interface SignupResult {
  status: string
  referred_codigo?: string | null
  coupon_code?: string | null
  coupon_value?: number | null
  coupon_valid_until?: string | null
  message: string
}

/** Situação do convite antes do formulário (GET público, sem PII de terceiros). */
interface PeekResult {
  valid: boolean
  reason: 'ok' | 'already_used' | 'not_found' | 'malformed'
  coupon_value?: number | null
  coupon_type?: string | null
  validity_days?: number | null
}

function friendlyError(detail: string | undefined, status?: number): string {
  // Só falhas definitivas chegam aqui; as transitórias (rede/5xx/limite) viram
  // fila local e são mostradas no painel de "dados salvos".
  if (status === 409) return 'Este convite já foi utilizado. Peça um novo link a quem te convidou.'
  if (status === 404) return 'Convite não encontrado. Confira o link ou peça um novo.'
  if (status === 401) return 'Convite inválido ou expirado.'
  return detail || 'Não foi possível completar o cadastro. Tente novamente.'
}

export function InviteSignupPage() {
  const [params] = useSearchParams()
  const token = (params.get('token') || '').trim()
  const tokenValido = token.startsWith('GF-INV-') && token.length > 10

  const [name, setName] = useState('')
  const [phone, setPhone] = useState('')
  const [rua, setRua] = useState('')
  const [numero, setNumero] = useState('')
  const [bairro, setBairro] = useState('')
  const [complemento, setComplemento] = useState('')
  const [consent, setConsent] = useState(false)
  const [submitting, setSubmitting] = useState(false)
  const [retrying, setRetrying] = useState(false)
  const [error, setError] = useState('')
  const [result, setResult] = useState<SignupResult | null>(null)
  // Fila local (F10.5): cadastro guardado no aparelho enquanto a loja não responde
  const [queued, setQueued] = useState<{ record: PendingSignup; status?: number } | null>(null)
  const [peek, setPeek] = useState<PeekResult | null>(null)
  // Já nasce conferindo quando a consulta vai acontecer: sem isso o formulário
  // pisca na tela antes do aviso de "link já usado".
  const [checking, setChecking] = useState(() => tokenValido && !loadPending(token))
  const [forceForm, setForceForm] = useState(false)

  const busyRef = useRef(false)
  const timerRef = useRef<ReturnType<typeof setTimeout> | null>(null)

  /**
   * Envia o cadastro. Falha de rede/5xx/limite (transitória) guarda os dados
   * no aparelho e devolve false para o reenvio automático assumir; falha
   * definitiva (convite inválido/já usado/validação) limpa a fila e mostra erro.
   */
  const send = useCallback(async (data: SignupPayload, auto = false): Promise<boolean> => {
    if (busyRef.current) return false
    busyRef.current = true
    if (auto) setRetrying(true)
    else setSubmitting(true)
    try {
      const { data: body } = await apiClient.post<SignupResult>('/public/referral/signup', data)
      clearPending(data.inviteToken)
      setQueued(null)
      setError('')
      setResult(body)
      return true
    } catch (err: unknown) {
      const detail = (err as { response?: { data?: { detail?: string } } })?.response?.data?.detail
      const status = (err as { response?: { status?: number } })?.response?.status
      if (isTransientFailure(err)) {
        // Guarda (ou atualiza) o pendente. Reenvio é idempotente no backend:
        // se a resposta se perdeu depois do commit, ele devolve o mesmo cupom.
        const record = auto
          ? bumpAttempts(data.inviteToken) ?? savePending(data.inviteToken, data)
          : savePending(data.inviteToken, data)
        setQueued({ record, status })
        setError('')
        return false
      }
      clearPending(data.inviteToken)
      setQueued(null)
      setError(friendlyError(detail, status))
      return false
    } finally {
      busyRef.current = false
      if (auto) setRetrying(false)
      else setSubmitting(false)
    }
  }, [])

  // Reabriu o link com cadastro pendente: devolve o que a pessoa digitou e
  // reenvia na hora (o caso mais comum é a loja ter voltado).
  useEffect(() => {
    if (!tokenValido) return
    const record = loadPending(token)
    if (!record) return
    setName(record.payload.name)
    setPhone(record.payload.phone)
    setRua(record.payload.rua)
    setNumero(record.payload.numero)
    setBairro(record.payload.bairro)
    setComplemento(record.payload.complemento || '')
    setConsent(record.payload.lgpdConsent)
    setQueued({ record })
    void send(record.payload, true)
  }, [token, tokenValido, send])

  // Reenvio automático com backoff enquanto a página estiver aberta.
  useEffect(() => {
    if (!queued || result) return
    timerRef.current = setTimeout(() => {
      void send(queued.record.payload, true)
    }, retryDelayMs(queued.record.attempts))
    return () => {
      if (timerRef.current) clearTimeout(timerRef.current)
    }
  }, [queued, result, send])

  // Consulta o convite antes de mostrar o formulário: evita preencher tudo
  // para só então descobrir que o link já foi usado. Falha de rede NÃO
  // bloqueia (otimista) — o cliente continua podendo preencher e enviar, e a
  // fila local (F10.5) assume se a loja estiver fora do ar.
  //
  // Com cadastro pendente a consulta é pulada de propósito: aquele token pode
  // ter sido consumido pelo próprio reenvio, e "já usado" esconderia a
  // recuperação do cupom.
  useEffect(() => {
    if (!tokenValido) return
    if (loadPending(token)) return

    let cancelled = false
    setChecking(true)
    void (async () => {
      try {
        const { data } = await apiClient.get<PeekResult>(`/public/referral/invite/${encodeURIComponent(token)}`)
        if (!cancelled) setPeek(data ?? null)
      } catch {
        if (!cancelled) setPeek(null) // sem resposta da loja → segue para o formulário
      } finally {
        if (!cancelled) setChecking(false)
      }
    })()
    return () => {
      cancelled = true
    }
  }, [token, tokenValido])

  // Internet voltou → tenta na hora, sem esperar o backoff.
  useEffect(() => {
    if (!queued || result) return
    const onOnline = () => {
      void send(queued.record.payload, true)
    }
    window.addEventListener('online', onOnline)
    return () => window.removeEventListener('online', onOnline)
  }, [queued, result, send])

  async function handleSubmit(e: FormEvent) {
    e.preventDefault()
    if (!consent) {
      setError('É preciso aceitar o uso dos seus dados para concluir o cadastro.')
      return
    }
    await send({
      inviteToken: token,
      name,
      phone,
      rua,
      numero,
      bairro,
      complemento: complemento || undefined,
      lgpdConsent: consent,
    })
  }

  if (!tokenValido) {
    return (
      <main className="flex min-h-screen items-center justify-center bg-gray-50 px-4 dark:bg-gray-950">
        <div className="w-full max-w-md rounded-xl border border-gray-200 bg-white p-8 text-center shadow-sm dark:border-gray-800 dark:bg-gray-900">
          <h1 className="text-xl font-semibold text-gray-900 dark:text-gray-100">Convite inválido</h1>
          <p className="mt-2 text-sm text-gray-600 dark:text-gray-400">
            Este link de convite parece incompleto. Ele começa com <span className="font-mono">GF-INV-</span> seguido de
            um código. Peça o link completo a quem te convidou.
          </p>
        </div>
      </main>
    )
  }

  if (checking && !peek) {
    return (
      <main className="flex min-h-screen items-center justify-center bg-gray-50 px-4 dark:bg-gray-950">
        <div className="flex items-center gap-3 text-sm text-gray-600 dark:text-gray-400">
          <LoadingSpinner size="sm" /> Conferindo o convite…
        </div>
      </main>
    )
  }

  // Convite morto: avisa ANTES de pedir qualquer dado.
  if (peek && !peek.valid && !forceForm) {
    const jaUsado = peek.reason === 'already_used'
    return (
      <main className="flex min-h-screen items-center justify-center bg-gray-50 px-4 dark:bg-gray-950">
        <div className="w-full max-w-md rounded-xl border border-gray-200 bg-white p-8 text-center shadow-sm dark:border-gray-800 dark:bg-gray-900">
          <h1 className="text-xl font-semibold text-gray-900 dark:text-gray-100">
            {jaUsado ? 'Este convite já foi usado' : 'Convite não encontrado'}
          </h1>
          <p className="mt-2 text-sm text-gray-600 dark:text-gray-400">
            {jaUsado
              ? 'Cada link vale um cadastro só. Peça um link novo a quem te convidou — leva um minuto.'
              : 'Confira o link ou peça um novo a quem te convidou.'}
          </p>
          {jaUsado && (
            <>
              <Button variant="secondary" className="mt-5 w-full" onClick={() => setForceForm(true)}>
                Já preenchi meus dados — quero ver meu cupom
              </Button>
              <p className="mt-3 text-xs text-gray-500 dark:text-gray-500">
                Se você já se cadastrou por este link, informe o mesmo WhatsApp para receber o cupom de novo.
              </p>
            </>
          )}
        </div>
      </main>
    )
  }

  if (result) {
    return (
      <main className="flex min-h-screen items-center justify-center bg-gray-50 px-4 dark:bg-gray-950">
        <div className="w-full max-w-md rounded-xl border border-gray-200 bg-white p-8 text-center shadow-sm dark:border-gray-800 dark:bg-gray-900">
          <div className="mx-auto mb-4 flex h-12 w-12 items-center justify-center rounded-full bg-green-100 text-2xl dark:bg-green-900/40">
            🎉
          </div>
          <h1 className="text-xl font-semibold text-gray-900 dark:text-gray-100">Cadastro realizado!</h1>
          <p className="mt-2 text-sm text-gray-600 dark:text-gray-400">{result.message}</p>
          {result.coupon_code && (
            <div className="mt-4 rounded-lg bg-green-50 p-4 dark:bg-green-900/20">
              <p className="text-xs uppercase tracking-wide text-green-700 dark:text-green-400">Seu cupom</p>
              <p className="mt-1 font-mono text-lg font-bold text-green-800 dark:text-green-300">{result.coupon_code}</p>
              {result.coupon_value != null && (
                <p className="mt-1 text-sm text-green-700 dark:text-green-400">
                  R$ {result.coupon_value.toFixed(2)} de desconto
                  {result.coupon_valid_until ? ` — válido até ${new Date(result.coupon_valid_until).toLocaleDateString('pt-BR')}` : ''}
                </p>
              )}
            </div>
          )}
          <p className="mt-4 text-xs text-gray-500 dark:text-gray-500">
            Anote o código! No próximo contato com a loja, é só pedir para usar o cupom.
          </p>
        </div>
      </main>
    )
  }

  return (
    <main className="flex min-h-screen items-center justify-center bg-gray-50 px-4 py-10 dark:bg-gray-950">
      <div className="w-full max-w-md">
        <div className="rounded-xl border border-gray-200 bg-white p-8 shadow-sm dark:border-gray-800 dark:bg-gray-900">
          <h1 className="text-xl font-semibold text-gray-900 dark:text-gray-100">Cadastro por convite</h1>
          <p className="mt-1 text-sm text-gray-600 dark:text-gray-400">
            Você foi convidado por um cliente da loja. Complete o cadastro e{' '}
            <strong className="text-gray-900 dark:text-gray-100">
              {peek?.coupon_value ? `você ganha R$ ${peek.coupon_value.toFixed(2)} em cupom` : 'vocês dois ganham um cupom de desconto'}
            </strong>
            .
          </p>
          {peek && peek.valid === false && (
            <p className="mt-3 rounded-lg bg-amber-50 p-3 text-xs text-amber-800 dark:bg-amber-900/20 dark:text-amber-300">
              Este link já foi usado. Se foi você, informe o mesmo WhatsApp do cadastro para receber o cupom de novo.
            </p>
          )}

          <form onSubmit={handleSubmit} className="mt-6 space-y-4">
            <div>
              <label htmlFor="name" className="mb-1 block text-sm font-medium text-gray-700 dark:text-gray-300">Nome completo</label>
              <Input id="name" value={name} onChange={(e) => setName(e.target.value)} required minLength={3} maxLength={120} placeholder="Maria Souza" autoComplete="name" />
            </div>
            <div>
              <label htmlFor="phone" className="mb-1 block text-sm font-medium text-gray-700 dark:text-gray-300">WhatsApp</label>
              <Input id="phone" value={phone} onChange={(e) => setPhone(e.target.value)} required placeholder="(11) 98888-7777" autoComplete="tel" inputMode="tel" />
            </div>
            <div className="grid grid-cols-[1fr_auto] gap-3">
              <div>
                <label htmlFor="rua" className="mb-1 block text-sm font-medium text-gray-700 dark:text-gray-300">Rua</label>
                <Input id="rua" value={rua} onChange={(e) => setRua(e.target.value)} required placeholder="Rua das Flores" autoComplete="address-line1" />
              </div>
              <div className="w-24">
                <label htmlFor="numero" className="mb-1 block text-sm font-medium text-gray-700 dark:text-gray-300">Número</label>
                <Input id="numero" value={numero} onChange={(e) => setNumero(e.target.value)} required placeholder="120" inputMode="numeric" />
              </div>
            </div>
            <div>
              <label htmlFor="bairro" className="mb-1 block text-sm font-medium text-gray-700 dark:text-gray-300">Bairro</label>
              <Input id="bairro" value={bairro} onChange={(e) => setBairro(e.target.value)} required placeholder="Jardim América" autoComplete="address-level2" />
            </div>
            <div>
              <label htmlFor="complemento" className="mb-1 block text-sm font-medium text-gray-700 dark:text-gray-300">Complemento (opcional)</label>
              <Input id="complemento" value={complemento} onChange={(e) => setComplemento(e.target.value)} placeholder="Apto 42 / Bloco B" />
            </div>

            <label className="flex items-start gap-3 rounded-lg bg-gray-50 p-3 text-xs leading-relaxed text-gray-600 dark:bg-gray-800/60 dark:text-gray-400">
              <input type="checkbox" checked={consent} onChange={(e) => setConsent(e.target.checked)} className="mt-0.5 h-4 w-4 shrink-0" required />
              <span>
                Autorizo a loja a usar meus dados (nome, WhatsApp e endereço) para entregas e comunicação. Dados
                armazenados com segurança; você pode pedir a exclusão quando quiser.
              </span>
            </label>

            {queued && !result && (
              <div role="status" className="rounded-lg bg-amber-50 p-3 text-sm text-amber-800 dark:bg-amber-900/20 dark:text-amber-300">
                <p className="font-medium">
                  {queued.status === 429 ? 'Muitas tentativas deste número' : 'A loja não respondeu agora'}
                </p>
                <p className="mt-1 text-xs leading-relaxed">
                  Seus dados estão salvos neste aparelho e vamos tentar enviar de novo automaticamente — o cupom
                  aparece aqui assim que a loja responder.
                  {queued.status === 429
                    ? ' O limite costuma liberar em cerca de 1 hora; se preferir, fale com a loja.'
                    : ''}
                </p>
                {retrying && (
                  <div className="mt-2 flex items-center gap-2 text-xs">
                    <LoadingSpinner size="sm" /> Reenviando…
                  </div>
                )}
              </div>
            )}

            {error && (
              <p role="alert" className="rounded-lg bg-red-50 p-3 text-sm text-red-700 dark:bg-red-900/30 dark:text-red-400">
                {error}
              </p>
            )}

            <Button type="submit" disabled={submitting || retrying || !name || !phone || !rua || !numero || !bairro || !consent} className="w-full">
              {submitting ? <LoadingSpinner size="sm" /> : queued ? 'Tentar enviar de novo' : 'Criar conta e ganhar cupom'}
            </Button>
          </form>
        </div>
        <p className="mt-4 text-center text-xs text-gray-500 dark:text-gray-500">
          Já é cliente? <Link to="/login" className="underline hover:text-gray-700 dark:hover:text-gray-300">Entrar no sistema</Link>
        </p>
      </div>
    </main>
  )
}
