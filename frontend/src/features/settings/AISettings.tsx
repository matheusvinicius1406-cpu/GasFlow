import { useCallback, useEffect, useState } from 'react'
import { Brain, RefreshCw, Send, ChevronDown, ChevronUp } from 'lucide-react'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/Card'
import { Button } from '@/components/ui/Button'
import { Badge } from '@/components/ui/Badge'
import { LoadingSpinner } from '@/components/ui/LoadingSpinner'
import { ErrorState } from '@/components/ui/ErrorState'
import { api } from '@/lib/api/client'

/**
 * AISettings — Item 3 (3.3): tela admin da IA.
 *
 * Regras de UX obrigatórias: NUNCA expor "Ollama", "qwen3", "provider" ou
 * outro jargão técnico na UI principal. Estados: ready (verde) /
 * preparing (âmbar, com progresso) / unavailable ou disabled (cinza).
 * O fallback externo NÃO existe (cenário B da Fase 4.2) — não há toggle.
 */

interface AiStatus {
  state: 'ready' | 'preparing' | 'unavailable' | 'disabled'
  message: string
  progress: number | null
}

interface AiSettings {
  enabled: boolean
  model: string
  timeout_seconds: number
}

const STATUS_STYLES: Record<AiStatus['state'], { badge: 'success' | 'warning' | 'secondary'; label: string }> = {
  ready: { badge: 'success', label: 'IA pronta' },
  preparing: { badge: 'warning', label: 'Preparando IA…' },
  unavailable: { badge: 'secondary', label: 'IA local indisponível' },
  disabled: { badge: 'secondary', label: 'IA desativada' },
}

export function AISettingsPage() {
  const [status, setStatus] = useState<AiStatus | null>(null)
  const [settings, setSettings] = useState<AiSettings | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(false)
  const [saving, setSaving] = useState(false)
  const [showAdvanced, setShowAdvanced] = useState(false)
  const [testPrompt, setTestPrompt] = useState('')
  const [testResult, setTestResult] = useState<{ response: string; provider: string; error: string | null } | null>(null)
  const [testing, setTesting] = useState(false)

  const load = useCallback(async () => {
    setLoading(true)
    setError(false)
    try {
      const [statusRes, settingsRes] = await Promise.all([api.ai.status(), api.ai.settings()])
      setStatus(statusRes.data as AiStatus)
      setSettings(settingsRes.data as AiSettings)
    } catch {
      setError(true)
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    load()
  }, [load])

  const toggleEnabled = async () => {
    if (!settings) return
    setSaving(true)
    try {
      const { data } = await api.ai.updateSettings({ enabled: !settings.enabled })
      setSettings(data as AiSettings)
      await load()
    } finally {
      setSaving(false)
    }
  }

  const runTest = async () => {
    if (!testPrompt.trim() || testing) return
    setTesting(true)
    setTestResult(null)
    try {
      const { data } = await api.ai.test(testPrompt)
      setTestResult(data as { response: string; provider: string; error: string | null })
    } catch {
      setTestResult({ response: '', provider: 'none', error: 'IA temporariamente indisponível.' })
    } finally {
      setTesting(false)
    }
  }

  if (loading) {
    return (
      <div className="flex items-center justify-center py-16">
        <LoadingSpinner size="lg" />
      </div>
    )
  }

  if (error || !status || !settings) {
    return <ErrorState message="Não foi possível carregar as configurações de IA." onRetry={load} />
  }

  const style = STATUS_STYLES[status.state] ?? STATUS_STYLES.unavailable

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold text-foreground">Inteligência</h1>
        <p className="text-sm text-muted-foreground">
          Assistente inteligente do GasFlow — funciona localmente, no seu computador.
        </p>
      </div>

      {/* 1. Status */}
      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2">
            <Brain className="h-5 w-5" aria-hidden />
            Status
          </CardTitle>
        </CardHeader>
        <CardContent className="space-y-3">
          <div className="flex items-center gap-3">
            <Badge variant={style.badge}>{style.label}</Badge>
            {status.state === 'preparing' && status.progress != null && (
              <span className="text-sm text-muted-foreground">{status.progress}%</span>
            )}
          </div>
          <p className="text-sm text-muted-foreground">{status.message}</p>
          {(status.state === 'unavailable' || status.state === 'disabled') && (
            <Button variant="outline" size="sm" onClick={load}>
              <RefreshCw className="mr-2 h-4 w-4" aria-hidden />
              Tentar novamente
            </Button>
          )}
        </CardContent>
      </Card>

      {/* 2. Preferências */}
      <Card>
        <CardHeader>
          <CardTitle>Preferências</CardTitle>
        </CardHeader>
        <CardContent className="space-y-4">
          <label className="flex items-center justify-between gap-4">
            <span>
              <span className="block text-sm font-medium text-foreground">Ativar Inteligência</span>
              <span className="block text-xs text-muted-foreground">
                Desativar aqui derruba toda a IA imediatamente, sem reiniciar o sistema.
              </span>
            </span>
            <input
              type="checkbox"
              role="switch"
              aria-label="Ativar Inteligência"
              checked={settings.enabled}
              disabled={saving}
              onChange={toggleEnabled}
              className="h-5 w-5"
            />
          </label>
          <p className="rounded-md bg-muted p-3 text-xs text-muted-foreground">
            A IA roda inteiramente neste computador. Nenhuma informação sai da sua máquina.
          </p>
        </CardContent>
      </Card>

      {/* 3. Avançado (colapsável, escondido por default) */}
      <Card>
        <CardHeader>
          <button
            type="button"
            onClick={() => setShowAdvanced((v) => !v)}
            className="flex w-full items-center justify-between text-left"
            aria-expanded={showAdvanced}
          >
            <CardTitle>Avançado</CardTitle>
            {showAdvanced ? (
              <ChevronUp className="h-4 w-4" aria-hidden />
            ) : (
              <ChevronDown className="h-4 w-4" aria-hidden />
            )}
          </button>
        </CardHeader>
        {showAdvanced && (
          <CardContent className="space-y-2 text-sm text-muted-foreground">
            <div className="flex justify-between gap-4">
              <span>Serviço local</span>
              <span className="font-mono text-foreground">localhost:11434</span>
            </div>
            <div className="flex justify-between gap-4">
              <span>Modelo</span>
              <span className="font-mono text-foreground">{settings.model}</span>
            </div>
            <div className="flex justify-between gap-4">
              <span>Tempo limite de resposta</span>
              <span className="font-mono text-foreground">{settings.timeout_seconds}s</span>
            </div>
            <p className="text-xs">
              Serviço externo alternativo: não disponível nesta versão (decisão de privacidade).
            </p>
          </CardContent>
        )}
      </Card>

      {/* 4. Teste rápido */}
      <Card>
        <CardHeader>
          <CardTitle>Teste rápido</CardTitle>
        </CardHeader>
        <CardContent className="space-y-3">
          <div className="flex gap-2">
            <input
              type="text"
              value={testPrompt}
              onChange={(e) => setTestPrompt(e.target.value)}
              placeholder="Escreva uma pergunta para testar a IA…"
              aria-label="Pergunta de teste"
              className="flex-1 rounded-md border border-input bg-background px-3 py-2 text-sm"
              maxLength={500}
            />
            <Button size="sm" onClick={runTest} disabled={testing || !testPrompt.trim()}>
              <Send className="mr-2 h-4 w-4" aria-hidden />
              Testar
            </Button>
          </div>
          {testResult && (
            <div className="rounded-md bg-muted p-3 text-sm" data-testid="ai-test-result">
              {testResult.error ? (
                <p className="text-destructive">{testResult.error}</p>
              ) : (
                <p className="whitespace-pre-wrap">{testResult.response}</p>
              )}
              <p className="mt-2 text-xs text-muted-foreground">
                {testResult.provider === 'local' ? 'Respondido pela IA local.' : 'IA indisponível.'}
              </p>
            </div>
          )}
        </CardContent>
      </Card>
    </div>
  )
}
