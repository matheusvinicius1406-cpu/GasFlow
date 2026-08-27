/**
 * WhatsApp Conversations — FASE 10
 *
 * Operator console for monitoring and managing WhatsApp AI conversations.
 * Shows conversation list, detail with messages, and takeover/release.
 */

import { useState, useEffect, useCallback } from 'react'
import { MessageSquare, User, Bot, Headphones, ArrowLeft, Send, RefreshCw } from 'lucide-react'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/Card'
import { Button } from '@/components/ui/Button'
import { Badge } from '@/components/ui/Badge'
import { Input } from '@/components/ui/Input'
import { LoadingSpinner } from '@/components/ui/LoadingSpinner'

const API_BASE = import.meta.env.VITE_API_URL || 'http://localhost:8000'

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
                  <div className="min-w-0">
                    <div className="flex items-center gap-2">
                      <span className="font-medium text-sm truncate">
                        {conv.customer_codigo || conv.customer_phone}
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
}: {
  detail: ConversationDetail
  onBack: () => void
  onTakeover: () => void
  onRelease: () => void
  onSendReply: (text: string) => void
}) {
  const [replyText, setReplyText] = useState('')
  const isHumanActive = detail.state === 'HUMAN_ACTIVE'
  const isHumanPending = detail.state === 'HUMAN_PENDING'

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
              {detail.customer_codigo || detail.customer_phone}
            </h3>
            <p className="text-xs text-muted-foreground">
              {detail.customer_phone} • {detail.account_id}
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

      {/* Messages */}
      <Card>
        <CardContent className="p-4 max-h-96 overflow-y-auto">
          <div className="space-y-3">
            {detail.messages.map((msg) => (
              <div
                key={msg.id}
                className={`flex ${msg.direction === 'OUTGOING' ? 'justify-end' : 'justify-start'}`}
              >
                <div
                  className={`max-w-[80%] rounded-lg px-3 py-2 text-sm ${
                    msg.direction === 'OUTGOING'
                      ? 'bg-primary text-primary-foreground'
                      : 'bg-muted'
                  }`}
                >
                  <div className="flex items-center gap-1 mb-1">
                    {msg.sender === 'customer' && <User className="h-3 w-3" />}
                    {msg.sender === 'assistant' && <Bot className="h-3 w-3" />}
                    {msg.sender === 'human' && <Headphones className="h-3 w-3" />}
                    <span className="text-xs opacity-70">{msg.sender}</span>
                  </div>
                  <p className="whitespace-pre-wrap">{msg.content}</p>
                  <p className="text-xs opacity-50 mt-1">{formatTime(msg.created_at)}</p>
                </div>
              </div>
            ))}
          </div>
        </CardContent>
      </Card>

      {/* Reply (only when human active) */}
      {isHumanActive && (
        <div className="flex gap-2">
          <Input
            value={replyText}
            onChange={(e) => setReplyText(e.target.value)}
            placeholder="Digite sua resposta..."
            onKeyDown={(e) => e.key === 'Enter' && handleSend()}
          />
          <Button onClick={handleSend} disabled={!replyText.trim()}>
            <Send className="h-4 w-4" />
          </Button>
        </div>
      )}
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

  const fetchConversations = useCallback(async () => {
    try {
      const res = await fetch(`${API_BASE}/api/whatsapp/conversations`)
      if (res.ok) {
        const data = await res.json()
        setConversations(data.conversations || [])
      }
    } catch {
      // silent
    } finally {
      setLoading(false)
    }
  }, [])

  const fetchDetail = useCallback(async (id: number) => {
    setDetailLoading(true)
    try {
      const res = await fetch(`${API_BASE}/api/whatsapp/conversations/${id}`)
      if (res.ok) {
        setDetail(await res.json())
      }
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

  const handleTakeover = async () => {
    if (!selectedId) return
    try {
      await fetch(`${API_BASE}/api/whatsapp/conversations/${selectedId}/takeover`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ operator: 'Operador' }),
      })
      fetchDetail(selectedId)
    } catch {
      // silent
    }
  }

  const handleRelease = async () => {
    if (!selectedId) return
    try {
      await fetch(`${API_BASE}/api/whatsapp/conversations/${selectedId}/release`, {
        method: 'POST',
      })
      fetchDetail(selectedId)
    } catch {
      // silent
    }
  }

  const handleSendReply = async (text: string) => {
    if (!selectedId) return
    try {
      await fetch(`${API_BASE}/api/whatsapp/conversations/${selectedId}/reply`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ text }),
      })
      fetchDetail(selectedId)
    } catch {
      // silent
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
          />
        )}
      </div>
    </div>
  )
}
