/**
 * WhatsApp Conversations — FASE 10
 *
 * Operator console for monitoring and managing WhatsApp AI conversations.
 * Shows conversation list, detail with messages, and takeover/release.
 */

import { useState, useEffect, useCallback, useRef } from 'react'
import { MessageSquare, User, Bot, Headphones, ArrowLeft, Send, RefreshCw } from 'lucide-react'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/Card'
import { Button } from '@/components/ui/Button'
import { Badge } from '@/components/ui/Badge'
import { Input } from '@/components/ui/Input'
import { LoadingSpinner } from '@/components/ui/LoadingSpinner'
import { apiClient } from '@/lib/api/client'

interface ConversationMessage {
  id: number
  direction: string
  sender: string
  content: string
  message_type: string
  created_at: string | null
}

interface ConversationInfo {
  id: number
  account_id: string
  customer_phone: string
  customer_codigo: string | null
  contact_name: string | null
  state: string
  human_operator: string | null
  message_count: number
  last_message: string | null
  created_at: string | null
  updated_at: string | null
}

interface ConversationDetail extends ConversationInfo {
  draft: Record<string, unknown> | null
  messages: ConversationMessage[]
}

function getStateColor(state: string): 'success' | 'warning' | 'destructive' | 'secondary' | 'default' {
  switch (state) {
    case 'IDLE': return 'secondary'
    case 'BROWSING': return 'default'
    case 'BUILDING_ORDER': return 'warning'
    case 'AWAITING_CONFIRMATION': return 'warning'
    case 'ORDER_CREATED': return 'success'
    case 'HUMAN_PENDING': return 'destructive'
    case 'HUMAN_ACTIVE': return 'destructive'
    case 'CLOSED': return 'secondary'
    default: return 'secondary'
  }
}

function getStateLabel(state: string): string {
  switch (state) {
    case 'IDLE': return 'Ociosa'
    case 'BROWSING': return 'Navegando'
    case 'BUILDING_ORDER': return 'Montando Pedido'
    case 'AWAITING_CONFIRMATION': return 'Aguardando Confirmação'
    case 'ORDER_CREATED': return 'Pedido Criado'
    case 'HUMAN_PENDING': return 'Aguardando Atendente'
    case 'HUMAN_ACTIVE': return 'Atendente Ativo'
    case 'CLOSED': return 'Fechada'
    default: return state
  }
}

function formatTime(iso: string | null): string {
  if (!iso) return '—'
  const d = new Date(iso)
  return d.toLocaleTimeString('pt-BR', { hour: '2-digit', minute: '2-digit' })
}

/** (91) 8137-6879 | +55 91 8137-6879 — tolerant a tamanhos variados. */
function formatPhone(phone: string): string {
  const d = phone.replace(/\D/g, '')
  if (d.length === 13 && d.startsWith('55')) {
    return `+${d.slice(0, 2)} (${d.slice(2, 4)}) ${d.slice(4, 9)}-${d.slice(9)}`
  }
  if (d.length === 12 && d.startsWith('55')) {
    return `+${d.slice(0, 2)} (${d.slice(2, 4)}) ${d.slice(4, 8)}-${d.slice(8)}`
  }
  if (d.length === 11) return `(${d.slice(0, 2)}) ${d.slice(2, 7)}-${d.slice(7)}`
  if (d.length === 10) return `(${d.slice(0, 2)}) ${d.slice(2, 6)}-${d.slice(6)}`
  return phone
}

/** Nome de exibição: contato do celular > nome do cadastro > telefone formatado. */
function displayName(conv: Pick<ConversationInfo, 'contact_name' | 'customer_codigo' | 'customer_phone'>): string {
  return conv.contact_name || conv.customer_codigo || formatPhone(conv.customer_phone)
}

function senderLabel(sender: string): string {
  switch (sender) {
    case 'customer': return 'Cliente'
    case 'assistant': return 'IA'
    case 'human': return 'Você'
    default: return sender
  }
}


// ── Conversation List ──────────────────────────────────

function ConversationList({
  conversations,
  selectedId,
  onSelect,
  loading,
  onRefresh,
}: {
  conversations: ConversationInfo[]
  selectedId: number | null
  onSelect: (id: number) => void
  loading: boolean
  onRefresh: () => void
}) {
  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <h3 className="text-lg font-semibold">Conversas Ativas</h3>
        <Button onClick={onRefresh} variant="outline" size="sm">
          <RefreshCw className="h-4 w-4" />
        </Button>
      </div>

      {loading && <LoadingSpinner />}

      {!loading && conversations.length === 0 && (
        <Card>
          <CardContent className="flex flex-col items-center justify-center py-8">
            <MessageSquare className="h-8 w-8 text-muted-foreground mb-2" />
            <p className="text-sm text-muted-foreground">Nenhuma conversa ativa</p>
          </CardContent>
        </Card>
      )}

      <div className="space-y-2">
        {conversations.map((conv) => (
          <Card
            key={conv.id}
            className={`cursor-pointer transition-colors hover:bg-accent ${
              selectedId === conv.id ? 'border-primary' : ''
            }`}
            onClick={() => onSelect(conv.id)}
          >
            <CardContent className="p-3">
              <div className="flex items-center justify-between">
                <div className="flex items-center gap-3 min-w-0">
                  <div className="h-8 w-8 rounded-full bg-primary/10 flex items-center justify-center flex-shrink-0">
                    <User className="h-4 w-4 text-primary" />
                  </div>
                  <div className="min-w-0 flex-1">
                    <div className="flex items-center gap-2">
                      <span className="font-medium text-sm truncate">
                        {displayName(conv)}
                      </span>
                      <Badge variant={getStateColor(conv.state)} className="text-xs flex-shrink-0">
                        {getStateLabel(conv.state)}
                      </Badge>
                    </div>
                    <p className="text-xs text-muted-foreground truncate mt-0.5">
                      {conv.last_message || 'Sem mensagens'}
                    </p>
                  </div>
                </div>
                <div className="text-xs text-muted-foreground flex-shrink-0 ml-2">
                  {formatTime(conv.updated_at)}
                </div>
              </div>
            </CardContent>
          </Card>
        ))}
      </div>
    </div>
  )
}

// ── Conversation Detail ────────────────────────────────

function ConversationDetailPanel({
  detail,
  onBack,
  onTakeover,
  onRelease,
  onSendReply,
  replyError,
}: {
  detail: ConversationDetail
  onBack: () => void
  onTakeover: () => void
  onRelease: () => void
  onSendReply: (text: string) => void
  replyError?: string | null
}) {
  const [replyText, setReplyText] = useState('')
  const scrollRef = useRef<HTMLDivElement | null>(null)
  const isHumanActive = detail.state === 'HUMAN_ACTIVE'
  const isHumanPending = detail.state === 'HUMAN_PENDING'

  // Auto-scroll para a última mensagem
  useEffect(() => {
    const el = scrollRef.current
    if (el) el.scrollTop = el.scrollHeight
  }, [detail.messages])

  const handleSend = () => {
    if (!replyText.trim()) return
    onSendReply(replyText.trim())
    setReplyText('')
  }

  return (
    <div className="space-y-4">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2">
          <Button onClick={onBack} variant="ghost" size="sm">
            <ArrowLeft className="h-4 w-4" />
          </Button>
          <div>
            <h3 className="font-semibold">
              {displayName(detail)}
            </h3>
            <p className="text-xs text-muted-foreground">
              {formatPhone(detail.customer_phone)} • conta {detail.account_id}
            </p>
          </div>
        </div>
        <div className="flex items-center gap-2">
          <Badge variant={getStateColor(detail.state)}>
            {getStateLabel(detail.state)}
          </Badge>
          {!isHumanActive && !isHumanPending && (
            <Button onClick={onTakeover} variant="destructive" size="sm">
              <Headphones className="h-4 w-4" />
              Assumir
            </Button>
          )}
          {isHumanActive && (
            <Button onClick={onRelease} variant="outline" size="sm">
              <Bot className="h-4 w-4" />
              Devolver à IA
            </Button>
          )}
        </div>
      </div>

      {/* Draft */}
      {detail.draft && (
        <Card>
          <CardHeader>
            <CardTitle className="text-sm">Draft do Pedido</CardTitle>
          </CardHeader>
          <CardContent>
              {(() => {
                const d = detail.draft as Record<string, unknown>
                const items = d.items as Array<Record<string, unknown>> | undefined
                return (
                  <>
                    <p className="text-xs text-muted-foreground">
                      Cliente: {String(d.customer_name || d.customer_codigo || '')}
                    </p>
                    {items?.map((it, i) => (
                      <p key={i} className="text-sm">
                        {String(it.product_nome || it.product_codigo)} × {String(it.quantity)} = R$ {String(it.subtotal)}
                      </p>
                    ))}
                    <p className="text-sm font-bold mt-2">
                      Total: R$ {String(d.total)}
                    </p>
                  </>
                )
              })()}
          </CardContent>
        </Card>
      )}

      {/* Messages — estilo WhatsApp: bolhas alinhadas, auto-scroll no fim */}
      <Card>
        <CardContent className="p-4">
          <div ref={scrollRef} className="max-h-96 overflow-y-auto">
            <div className="space-y-3">
              {detail.messages.map((msg) => (
                <div
                  key={msg.id}
                  className={`flex ${msg.direction === 'OUTGOING' ? 'justify-end' : 'justify-start'}`}
                >
                  <div
                    className={`max-w-[80%] rounded-2xl px-3 py-2 text-sm ${
                      msg.direction === 'OUTGOING'
                        ? 'bg-primary text-primary-foreground rounded-br-sm'
                        : 'bg-muted rounded-bl-sm'
                    }`}
                  >
                    <div className="flex items-center gap-1 mb-1">
                      {msg.sender === 'customer' && <User className="h-3 w-3" />}
                      {msg.sender === 'assistant' && <Bot className="h-3 w-3" />}
                      {msg.sender === 'human' && <Headphones className="h-3 w-3" />}
                      <span className="text-xs opacity-70">{senderLabel(msg.sender)}</span>
                    </div>
                    <p className="whitespace-pre-wrap break-words">{msg.content}</p>
                    <p className="text-xs opacity-50 mt-1 text-right">{formatTime(msg.created_at)}</p>
                  </div>
                </div>
              ))}
            </div>
          </div>
        </CardContent>
      </Card>

      {/* Reply — sempre disponível (auto-assume ao responder) */}
      {replyError && (
        <p className="text-xs text-destructive">{replyError}</p>
      )}
      <div className="flex gap-2">
        <Input
          value={replyText}
          onChange={(e) => setReplyText(e.target.value)}
          placeholder="Digite sua resposta... (envia pelo WhatsApp e assume a conversa)"
          onKeyDown={(e) => e.key === 'Enter' && handleSend()}
        />
        <Button onClick={handleSend} disabled={!replyText.trim()}>
          <Send className="h-4 w-4" />
        </Button>
      </div>
    </div>
  )
}

// ── Main Page ──────────────────────────────────────────

export function ConversationsPage() {
  const [conversations, setConversations] = useState<ConversationInfo[]>([])
  const [selectedId, setSelectedId] = useState<number | null>(null)
  const [detail, setDetail] = useState<ConversationDetail | null>(null)
  const [loading, setLoading] = useState(true)
  const [detailLoading, setDetailLoading] = useState(false)
  const [replyError, setReplyError] = useState<string | null>(null)

  const fetchConversations = useCallback(async () => {
    try {
      const { data } = await apiClient.get('/whatsapp/conversations')
      setConversations(data.conversations || [])
    } catch {
      // silent
    } finally {
      setLoading(false)
    }
  }, [])

  const fetchDetail = useCallback(async (id: number) => {
    setDetailLoading(true)
    try {
      const { data } = await apiClient.get(`/whatsapp/conversations/${id}`)
      setDetail(data)
    } catch {
      // silent
    } finally {
      setDetailLoading(false)
    }
  }, [])

  useEffect(() => {
    fetchConversations()
    const interval = setInterval(fetchConversations, 10000)
    return () => clearInterval(interval)
  }, [fetchConversations])

  useEffect(() => {
    if (selectedId) fetchDetail(selectedId)
  }, [selectedId, fetchDetail])

  // Polling do thread aberto: mensagens novas aparecem ao vivo (estilo WhatsApp)
  useEffect(() => {
    if (!selectedId) return
    const interval = setInterval(() => fetchDetail(selectedId), 5000)
    return () => clearInterval(interval)
  }, [selectedId, fetchDetail])

  const handleTakeover = async () => {
    if (!selectedId) return
    try {
      await apiClient.post(`/whatsapp/conversations/${selectedId}/takeover`, { operator: 'Operador' })
      fetchDetail(selectedId)
    } catch {
      // silent
    }
  }

  const handleRelease = async () => {
    if (!selectedId) return
    try {
      await apiClient.post(`/whatsapp/conversations/${selectedId}/release`)
      fetchDetail(selectedId)
    } catch {
      // silent
    }
  }

  const handleSendReply = async (text: string) => {
    if (!selectedId) return
    setReplyError(null)
    try {
      await apiClient.post(`/whatsapp/conversations/${selectedId}/reply`, { text })
      fetchDetail(selectedId)
    } catch (err) {
      const detailMsg =
        (err as { response?: { data?: { detail?: string } } })?.response?.data?.detail ||
        'Falha ao enviar a resposta. Tente novamente.'
      setReplyError(detailMsg)
    }
  }

  return (
    <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
      {/* List */}
      <div className={selectedId ? 'hidden md:block' : ''}>
        <ConversationList
          conversations={conversations}
          selectedId={selectedId}
          onSelect={setSelectedId}
          loading={loading}
          onRefresh={fetchConversations}
        />
      </div>

      {/* Detail */}
      <div className="md:col-span-2">
        {!selectedId && !detailLoading && (
          <Card>
            <CardContent className="flex flex-col items-center justify-center py-16">
              <MessageSquare className="h-12 w-12 text-muted-foreground mb-4" />
              <h3 className="text-lg font-semibold">Selecione uma conversa</h3>
              <p className="text-sm text-muted-foreground mt-2">
                Clique em uma conversa para ver detalhes
              </p>
            </CardContent>
          </Card>
        )}

        {detailLoading && (
          <div className="flex items-center justify-center py-16">
            <LoadingSpinner size="lg" />
          </div>
        )}

        {!detailLoading && detail && (
          <ConversationDetailPanel
            detail={detail}
            onBack={() => { setSelectedId(null); setDetail(null) }}
            onTakeover={handleTakeover}
            onRelease={handleRelease}
            onSendReply={handleSendReply}
            replyError={replyError}
          />
        )}
      </div>
    </div>
  )
}
