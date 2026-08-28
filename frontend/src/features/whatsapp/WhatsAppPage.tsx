/**
 * WhatsApp Page — Multi-Account Management
 *
 * FASE 4.1 — Architecture Boundary:
 * This page talks ONLY to the FastAPI backend.
 * The backend proxies to the WhatsApp Service.
 * Frontend NEVER knows about the Node.js service.
 */

import { useState, useEffect, useCallback } from 'react'
import { Wifi, WifiOff, RefreshCw, LogOut, Smartphone, MessageSquare } from 'lucide-react'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/Card'
import { Button } from '@/components/ui/Button'
import { Badge } from '@/components/ui/Badge'
import { LoadingSpinner } from '@/components/ui/LoadingSpinner'
import { Tabs, TabsList, TabsTrigger, TabsContent } from '@/components/ui/Tabs'
import { ConversationsPage } from './ConversationsPage'
import { apiClient } from '@/lib/api/client'

interface WhatsAppAccount {
  id: string
  name: string
  status: {
    state: 'disconnected' | 'connecting' | 'qr_pending' | 'connected'
    connected: boolean
    hasQr: boolean
  }
  phone: string | null
  lastConnectedAt: string | null
}

interface QRData {
  qr: string
  dataUrl: string
  svg: string
  generatedAt: string
  expiresAt: string
  expiresIn: number
}

function getStatusColor(state: string): 'success' | 'warning' | 'destructive' | 'secondary' {
  switch (state) {
    case 'connected': return 'success'
    case 'connecting':
    case 'qr_pending': return 'warning'
    case 'disconnected': return 'destructive'
    default: return 'secondary'
  }
}

function getStatusLabel(state: string): string {
  switch (state) {
    case 'connected': return 'Conectado'
    case 'connecting': return 'Conectando...'
    case 'qr_pending': return 'Aguardando QR'
    case 'disconnected': return 'Desconectado'
    default: return state
  }
}

function AccountCard({ account, onRefresh }: { account: WhatsAppAccount; onRefresh: () => void }) {
  const [qr, setQr] = useState<QRData | null>(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const fetchQR = useCallback(async () => {
    try {
      const { data } = await apiClient.get(`/whatsapp/accounts/${account.id}/qr`)
      setQr(data)
      setError(null)
    } catch {
      setQr(null)
    }
  }, [account.id])

  useEffect(() => {
    if (account.status.hasQr) fetchQR()
    else setQr(null)
  }, [account.status.hasQr, fetchQR])

  const handleStart = async () => {
    setLoading(true)
    setError(null)
    try {
      await apiClient.post(`/whatsapp/accounts/${account.id}/start`)
      onRefresh()
    } catch (err: unknown) {
      const msg = (err as { response?: { data?: { detail?: string } } })?.response?.data?.detail
      setError(msg || 'Falha ao iniciar conexão')
    } finally {
      setLoading(false)
    }
  }

  const handleStop = async () => {
    setLoading(true)
    setError(null)
    try {
      await apiClient.post(`/whatsapp/accounts/${account.id}/stop`)
      onRefresh()
    } catch {
      setError('Falha ao parar conexão')
    } finally {
      setLoading(false)
    }
  }

  const handleLogout = async () => {
    if (!confirm(`Desconectar ${account.name}? Isso invalidará a sessão.`)) return
    setLoading(true)
    setError(null)
    try {
      await apiClient.post(`/whatsapp/accounts/${account.id}/logout`)
      setQr(null)
      onRefresh()
    } catch {
      setError('Falha ao desconectar')
    } finally {
      setLoading(false)
    }
  }

  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex items-center justify-between">
          <div className="flex items-center gap-2">
            <Smartphone className="h-5 w-5" />
            <span>{account.name}</span>
          </div>
          <Badge variant={getStatusColor(account.status.state)}>
            {getStatusLabel(account.status.state)}
          </Badge>
        </CardTitle>
      </CardHeader>
      <CardContent className="space-y-4">
        {/* Account Info */}
        <div className="grid grid-cols-2 gap-4 text-sm">
          <div>
            <p className="text-muted-foreground">Conta</p>
            <p className="font-medium">{account.id}</p>
          </div>
          <div>
            <p className="text-muted-foreground">Telefone</p>
            <p className="font-medium">{account.phone || '—'}</p>
          </div>
          <div>
            <p className="text-muted-foreground">Última conexão</p>
            <p className="font-medium">
              {account.lastConnectedAt
                ? new Date(account.lastConnectedAt).toLocaleString('pt-BR')
                : '—'}
            </p>
          </div>
          <div>
            <p className="text-muted-foreground">Status</p>
            <div className="flex items-center gap-1">
              {account.status.connected ? (
                <Wifi className="h-4 w-4 text-green-500" />
              ) : (
                <WifiOff className="h-4 w-4 text-red-500" />
              )}
              <span className="font-medium">{getStatusLabel(account.status.state)}</span>
            </div>
          </div>
        </div>

        {/* QR Code */}
        {qr && (
          <div className="flex flex-col items-center gap-2 rounded-lg border border-border p-4">
            <p className="text-sm text-muted-foreground">Escaneie com o WhatsApp</p>
            <div
              className="h-64 w-64"
              dangerouslySetInnerHTML={{ __html: qr.svg }}
            />
            <p className="text-xs text-muted-foreground">
              Expira em {qr.expiresIn}s
            </p>
          </div>
        )}

        {/* Error */}
        {error && (
          <p className="text-sm text-destructive">{error}</p>
        )}

        {/* Actions */}
        <div className="flex gap-2">
          {!account.status.connected ? (
            <Button onClick={handleStart} disabled={loading} className="flex-1">
              {loading ? <LoadingSpinner size="sm" /> : <Wifi className="h-4 w-4" />}
              Conectar
            </Button>
          ) : (
            <Button onClick={handleStop} variant="outline" disabled={loading} className="flex-1">
              {loading ? <LoadingSpinner size="sm" /> : <WifiOff className="h-4 w-4" />}
              Desconectar
            </Button>
          )}
          <Button onClick={onRefresh} variant="ghost" size="icon">
            <RefreshCw className="h-4 w-4" />
          </Button>
          {account.status.connected && (
            <Button onClick={handleLogout} variant="destructive" size="icon">
              <LogOut className="h-4 w-4" />
            </Button>
          )}
        </div>
      </CardContent>
    </Card>
  )
}

function WhatsAppAccountsView() {
  const [accounts, setAccounts] = useState<WhatsAppAccount[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  const fetchAccounts = useCallback(async () => {
    try {
      const { data } = await apiClient.get('/whatsapp/accounts')
      setAccounts(data.accounts || [])
      setError(null)
    } catch {
      setError('Serviço indisponível')
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    fetchAccounts()
    const interval = setInterval(fetchAccounts, 15000)
    return () => clearInterval(interval)
  }, [fetchAccounts])

  if (loading) {
    return (
      <div className="flex items-center justify-center py-16">
        <LoadingSpinner size="lg" />
      </div>
    )
  }

  if (error) {
    return (
      <div className="space-y-6">
        <h1 className="text-2xl font-bold text-foreground">WhatsApp</h1>
        <Card>
          <CardContent className="flex flex-col items-center justify-center py-12">
            <WifiOff className="h-12 w-12 text-destructive mb-4" />
            <h3 className="text-lg font-semibold">Serviço Indisponível</h3>
            <p className="text-sm text-muted-foreground mt-2">{error}</p>
            <Button onClick={fetchAccounts} className="mt-4">
              <RefreshCw className="h-4 w-4" />
              Tentar novamente
            </Button>
          </CardContent>
        </Card>
      </div>
    )
  }

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-foreground">WhatsApp</h1>
          <p className="text-sm text-muted-foreground">
            Gerencie as contas WhatsApp do GasFlow
          </p>
        </div>
        <Button onClick={fetchAccounts} variant="outline">
          <RefreshCw className="h-4 w-4" />
          Atualizar
        </Button>
      </div>

      {/* Stats */}
      <div className="grid gap-4 md:grid-cols-3">
        <Card>
          <CardContent className="p-4">
            <div className="flex items-center gap-2">
              <Smartphone className="h-5 w-5 text-primary" />
              <div>
                <p className="text-sm text-muted-foreground">Total</p>
                <p className="text-xl font-bold">{accounts.length}</p>
              </div>
            </div>
          </CardContent>
        </Card>
        <Card>
          <CardContent className="p-4">
            <div className="flex items-center gap-2">
              <Wifi className="h-5 w-5 text-green-500" />
              <div>
                <p className="text-sm text-muted-foreground">Conectadas</p>
                <p className="text-xl font-bold">
                  {accounts.filter((a) => a.status.connected).length}
                </p>
              </div>
            </div>
          </CardContent>
        </Card>
        <Card>
          <CardContent className="p-4">
            <div className="flex items-center gap-2">
              <MessageSquare className="h-5 w-5 text-blue-500" />
              <div>
                <p className="text-sm text-muted-foreground">Aguardando QR</p>
                <p className="text-xl font-bold">
                  {accounts.filter((a) => a.status.state === 'qr_pending').length}
                </p>
              </div>
            </div>
          </CardContent>
        </Card>
      </div>

      {/* Account Cards */}
      <div className="grid gap-6 md:grid-cols-2">
        {accounts.map((account) => (
          <AccountCard key={account.id} account={account} onRefresh={fetchAccounts} />
        ))}
      </div>

      {accounts.length === 0 && (
        <Card>
          <CardContent className="flex flex-col items-center justify-center py-12">
            <Smartphone className="h-12 w-12 text-muted-foreground mb-4" />
            <h3 className="text-lg font-semibold">Nenhuma conta configurada</h3>
            <p className="text-sm text-muted-foreground mt-2">
              Configure as contas WhatsApp no arquivo .env do serviço
            </p>
          </CardContent>
        </Card>
      )}
    </div>
  )
}

// ── Main Export with Tabs ──────────────────────────────

export function WhatsAppPage() {
  return (
    <div className="space-y-6">
      <h1 className="text-2xl font-bold text-foreground">WhatsApp</h1>
      <Tabs defaultValue="accounts">
        <TabsList>
          <TabsTrigger value="accounts">Contas</TabsTrigger>
          <TabsTrigger value="conversations">Conversas</TabsTrigger>
        </TabsList>
        <TabsContent value="accounts">
          <WhatsAppAccountsView />
        </TabsContent>
        <TabsContent value="conversations">
          <ConversationsPage />
        </TabsContent>
      </Tabs>
    </div>
  )
}
