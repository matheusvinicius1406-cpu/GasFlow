import { useState, useEffect } from 'react';
import { Page, PageHeader, PageTitle, PageActions } from '@/components/layout/Page';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/Card';
import { Button } from '@/components/ui/Button';
import { Input } from '@/components/ui/Input';

import { LoadingSpinner } from '@/components/ui/LoadingSpinner';
import { ErrorState } from '@/components/ui/ErrorState';
import { EmptyState } from '@/components/ui/EmptyState';
import { StatCard } from '@/components/ui/StatCard';
import { apiClient } from '@/lib/api/client';
import { Zap, Play, Pause, Trash2, Plus, Send, CheckCircle, Clock } from 'lucide-react';

interface AutomationRule {
  id: number;
  name: string;
  description: string;
  trigger_type: string;
  status: string;
  segment_id: number | null;
  min_score: number | null;
  confidence_filter: string | null;
  message_template: string;
  account_id: string;
  max_messages_per_day: number;
  cooldown_days: number;
  requires_approval: boolean;
  total_executions: number;
  successful_sends: number;
  failed_sends: number;
  opted_out_count: number;
  created_at: string;
  updated_at: string;
}

interface AutomationExecution {
  id: number;
  rule_id: number;
  customer_codigo: string;
  customer_nome: string;
  customer_phone: string;
  message_text: string;
  status: string;
  error_message: string | null;
  triggered_at: string;
  sent_at: string | null;
}

interface AutomationMetrics {
  total_rules: number;
  active_rules: number;
  total_executions: number;
  pending: number;
  sent: number;
  delivered: number;
  failed: number;
  opted_out: number;
  success_rate: number;
}

const STATUS_COLORS: Record<string, string> = {
  DRAFT: 'bg-gray-100 text-gray-800 dark:bg-gray-800 dark:text-gray-400',
  ACTIVE: 'bg-emerald-100 text-emerald-800 dark:bg-emerald-900/30 dark:text-emerald-400',
  PAUSED: 'bg-amber-100 text-amber-800 dark:bg-amber-900/30 dark:text-amber-400',
  ARCHIVED: 'bg-red-100 text-red-800 dark:bg-red-900/30 dark:text-red-400',
};

const EXEC_STATUS_COLORS: Record<string, string> = {
  PENDING: 'bg-amber-100 text-amber-800 dark:bg-amber-900/30 dark:text-amber-400',
  APPROVED: 'bg-blue-100 text-blue-800 dark:bg-blue-900/30 dark:text-blue-400',
  SENT: 'bg-emerald-100 text-emerald-800 dark:bg-emerald-900/30 dark:text-emerald-400',
  DELIVERED: 'bg-emerald-100 text-emerald-800 dark:bg-emerald-900/30 dark:text-emerald-400',
  FAILED: 'bg-red-100 text-red-800 dark:bg-red-900/30 dark:text-red-400',
  CANCELLED: 'bg-gray-100 text-gray-800 dark:bg-gray-800 dark:text-gray-400',
  OPTED_OUT: 'bg-orange-100 text-orange-800 dark:bg-orange-900/30 dark:text-orange-400',
};

const TRIGGER_LABELS: Record<string, string> = {
  REORDER_OPPORTUNITY: 'Recompra',
  SEGMENT_MEMBERSHIP: 'Segmento',
  MANUAL: 'Manual',
  SCHEDULED: 'Agendado',
};

export function AutomationsPage() {
  const [rules, setRules] = useState<AutomationRule[]>([]);
  const [executions, setExecutions] = useState<AutomationExecution[]>([]);
  const [metrics, setMetrics] = useState<AutomationMetrics | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [activeTab, setActiveTab] = useState<'rules' | 'executions'>('rules');
  const [showCreate, setShowCreate] = useState(false);
  const [newRule, setNewRule] = useState({
    name: '',
    description: '',
    trigger_type: 'MANUAL',
    message_template: '',
    cooldown_days: 7,
    requires_approval: true,
  });
  const [previewResult, setPreviewResult] = useState<{ message: string; customer: string } | null>(null);
  const [previewCustomer, setPreviewCustomer] = useState('');

  const fetchData = async () => {
    setLoading(true);
    setError(null);
    try {
      const [rulesRes, execsRes, metricsRes] = await Promise.all([
        apiClient.get('/automation/whatsapp/rules'),
        apiClient.get('/automation/whatsapp/executions?limit=50'),
        apiClient.get('/automation/whatsapp/metrics'),
      ]);
      setRules(rulesRes.data.rules || []);
      setExecutions(execsRes.data.executions || []);
      setMetrics(metricsRes.data);
    } catch {
      setError('Erro ao carregar automações');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => { fetchData(); }, []);

  const handleCreate = async () => {
    if (!newRule.name || !newRule.message_template) return;
    try {
      await apiClient.post('/automation/whatsapp/rules', newRule);
      setShowCreate(false);
      setNewRule({ name: '', description: '', trigger_type: 'MANUAL', message_template: '', cooldown_days: 7, requires_approval: true });
      fetchData();
    } catch { /* ignore */ }
  };

  const handleActivate = async (id: number) => {
    await apiClient.post(`/automation/whatsapp/rules/${id}/activate`);
    fetchData();
  };

  const handlePause = async (id: number) => {
    await apiClient.post(`/automation/whatsapp/rules/${id}/pause`);
    fetchData();
  };

  const handleDelete = async (id: number) => {
    if (!confirm('Excluir esta regra de automação?')) return;
    await apiClient.delete(`/automation/whatsapp/rules/${id}`);
    fetchData();
  };

  const handleExecute = async (id: number) => {
    if (!confirm('Executar esta regra? Clientes elegíveis receberão mensagens.')) return;
    await apiClient.post(`/automation/whatsapp/rules/${id}/execute`);
    fetchData();
  };

  const handlePreview = async () => {
    if (!previewCustomer || !newRule.message_template) return;
    try {
      const res = await apiClient.post('/automation/whatsapp/preview', {
        template: newRule.message_template,
        customer_codigo: previewCustomer,
      });
      setPreviewResult({ message: res.data.rendered_message, customer: previewCustomer });
    } catch { setPreviewResult(null); }
  };



  if (loading) {
    return (
      <Page>
        <PageHeader><PageTitle subtitle="Automações WhatsApp">Automações</PageTitle></PageHeader>
        <div className="flex items-center justify-center py-20"><LoadingSpinner size="lg" /></div>
      </Page>
    );
  }

  if (error) {
    return (
      <Page>
        <PageHeader><PageTitle subtitle="Automações WhatsApp">Automações</PageTitle></PageHeader>
        <ErrorState message={error} onRetry={fetchData} />
      </Page>
    );
  }

  return (
    <Page>
      <PageHeader>
        <PageTitle subtitle="Automações WhatsApp — CRM → Mensagem → Conversa">Automações</PageTitle>
        <PageActions>
          <Button variant="outline" onClick={fetchData} className="gap-2">
            <Zap className="w-4 h-4" /> Atualizar
          </Button>
          <Button onClick={() => setShowCreate(!showCreate)} className="gap-2">
            <Plus className="w-4 h-4" /> Nova Regra
          </Button>
        </PageActions>
      </PageHeader>

      {/* Metrics */}
      {metrics && (
        <div className="grid grid-cols-2 md:grid-cols-4 gap-4 mb-6">
          <StatCard title="Regras Ativas" value={metrics.active_rules} icon={Zap} />
          <StatCard title="Enviados" value={metrics.sent} icon={Send} />
          <StatCard title="Pendentes" value={metrics.pending} icon={Clock} />
          <StatCard title="Taxa de Sucesso" value={`${metrics.success_rate}%`} icon={CheckCircle} />
        </div>
      )}

      {/* Create Form */}
      {showCreate && (
        <Card className="mb-6">
          <CardHeader><CardTitle>Nova Regra de Automação</CardTitle></CardHeader>
          <CardContent className="space-y-4">
            <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
              <div>
                <label className="text-sm font-medium">Nome</label>
                <Input value={newRule.name} onChange={e => setNewRule({ ...newRule, name: e.target.value })} placeholder="Ex: Recompra P13" />
              </div>
              <div>
                <label className="text-sm font-medium">Tipo de Trigger</label>
                <select value={newRule.trigger_type} onChange={e => setNewRule({ ...newRule, trigger_type: e.target.value })} className="w-full px-3 py-2 border rounded-md bg-background text-sm">
                  <option value="MANUAL">Manual</option>
                  <option value="REORDER_OPPORTUNITY">Oportunidade de Recompra</option>
                  <option value="SEGMENT_MEMBERSHIP">Membro de Segmento</option>
                </select>
              </div>
            </div>
            <div>
              <label className="text-sm font-medium">Descrição</label>
              <Input value={newRule.description} onChange={e => setNewRule({ ...newRule, description: e.target.value })} placeholder="Descrição da automação" />
            </div>
            <div>
              <label className="text-sm font-medium">Template da Mensagem</label>
              <textarea
                value={newRule.message_template}
                onChange={e => setNewRule({ ...newRule, message_template: e.target.value })}
                placeholder="Olá {{customer_name}}! Notamos que você costuma comprar {{product}}. Quer fazer um novo pedido?"
                className="w-full px-3 py-2 border rounded-md bg-background text-sm min-h-[80px]"
              />
              <p className="text-xs text-muted-foreground mt-1">
                Variáveis: {'{{customer_name}}'} {'{{product}}'} {'{{last_order_date}}'} {'{{total_orders}}'} {'{{average_ticket}}'}
              </p>
            </div>
            <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
              <div>
                <label className="text-sm font-medium">Cooldown (dias)</label>
                <Input type="number" value={newRule.cooldown_days} onChange={e => setNewRule({ ...newRule, cooldown_days: parseInt(e.target.value) || 7 })} />
              </div>
              <div className="flex items-center gap-2 pt-6">
                <input type="checkbox" checked={newRule.requires_approval} onChange={e => setNewRule({ ...newRule, requires_approval: e.target.checked })} className="rounded" />
                <label className="text-sm">Requer aprovação</label>
              </div>
            </div>

            {/* Preview */}
            <div className="border-t pt-4">
              <label className="text-sm font-medium">Preview</label>
              <div className="flex gap-2 mt-1">
                <Input value={previewCustomer} onChange={e => setPreviewCustomer(e.target.value)} placeholder="Código do cliente" className="flex-1" />
                <Button variant="outline" onClick={handlePreview}>Preview</Button>
              </div>
              {previewResult && (
                <div className="mt-2 p-3 bg-emerald-50 dark:bg-emerald-900/20 rounded-md text-sm">
                  <div className="font-medium text-emerald-700 dark:text-emerald-400 mb-1">Preview para #{previewResult.customer}:</div>
                  <div className="whitespace-pre-wrap">{previewResult.message}</div>
                </div>
              )}
            </div>

            <div className="flex justify-end gap-2">
              <Button variant="outline" onClick={() => setShowCreate(false)}>Cancelar</Button>
              <Button onClick={handleCreate}>Criar Regra</Button>
            </div>
          </CardContent>
        </Card>
      )}

      {/* Tabs */}
      <div className="flex gap-2 mb-6">
        <Button variant={activeTab === 'rules' ? 'default' : 'outline'} onClick={() => setActiveTab('rules')}>
          Regras ({rules.length})
        </Button>
        <Button variant={activeTab === 'executions' ? 'default' : 'outline'} onClick={() => setActiveTab('executions')}>
          Execuções ({executions.length})
        </Button>
      </div>

      {/* Rules Tab */}
      {activeTab === 'rules' && (
        <>
          {rules.length === 0 ? (
            <EmptyState
              title="Nenhuma regra de automação"
              description="Crie regras para automatizar mensagens WhatsApp baseadas em recompra ou segmentação."
              icon={Zap}
            />
          ) : (
            <div className="space-y-4">
              {rules.map(rule => (
                <Card key={rule.id}>
                  <CardContent className="pt-6">
                    <div className="flex items-start justify-between">
                      <div className="flex-1">
                        <div className="flex items-center gap-2 mb-1">
                          <h3 className="font-semibold">{rule.name}</h3>
                          <span className={`px-2 py-0.5 rounded-full text-xs font-medium ${STATUS_COLORS[rule.status] || ''}`}>
                            {rule.status}
                          </span>
                          <span className="px-2 py-0.5 rounded-full text-xs font-medium bg-blue-100 text-blue-800 dark:bg-blue-900/30 dark:text-blue-400">
                            {TRIGGER_LABELS[rule.trigger_type] || rule.trigger_type}
                          </span>
                        </div>
                        {rule.description && <p className="text-sm text-muted-foreground mb-2">{rule.description}</p>}
                        <div className="text-xs text-muted-foreground space-x-4">
                          <span>Cooldown: {rule.cooldown_days}d</span>
                          <span>Max/dia: {rule.max_messages_per_day}</span>
                          <span>Aprovação: {rule.requires_approval ? 'Sim' : 'Não'}</span>
                          <span>Execuções: {rule.total_executions}</span>
                          <span>Sucesso: {rule.successful_sends}</span>
                          <span>Falhas: {rule.failed_sends}</span>
                        </div>
                        {rule.message_template && (
                          <div className="mt-2 p-2 bg-muted rounded text-xs max-w-xl truncate">
                            {rule.message_template}
                          </div>
                        )}
                      </div>
                      <div className="flex items-center gap-1 ml-4">
                        {rule.status === 'DRAFT' || rule.status === 'PAUSED' ? (
                          <Button variant="ghost" size="icon" onClick={() => handleActivate(rule.id)} title="Ativar">
                            <Play className="w-4 h-4 text-emerald-600" />
                          </Button>
                        ) : (
                          <Button variant="ghost" size="icon" onClick={() => handlePause(rule.id)} title="Pausar">
                            <Pause className="w-4 h-4 text-amber-600" />
                          </Button>
                        )}
                        <Button variant="ghost" size="icon" onClick={() => handleExecute(rule.id)} title="Executar agora">
                          <Send className="w-4 h-4 text-blue-600" />
                        </Button>
                        <Button variant="ghost" size="icon" onClick={() => handleDelete(rule.id)} title="Excluir">
                          <Trash2 className="w-4 h-4 text-red-600" />
                        </Button>
                      </div>
                    </div>
                  </CardContent>
                </Card>
              ))}
            </div>
          )}
        </>
      )}

      {/* Executions Tab */}
      {activeTab === 'executions' && (
        <>
          {executions.length === 0 ? (
            <EmptyState
              title="Nenhuma execução"
              description="Execute uma regra para gerar envios de mensagens."
              icon={Send}
            />
          ) : (
            <Card>
              <CardContent className="pt-6">
                <div className="overflow-x-auto">
                  <table className="w-full text-sm">
                    <thead>
                      <tr className="border-b">
                        <th className="text-left py-2 px-2 font-medium text-muted-foreground">Cliente</th>
                        <th className="text-left py-2 px-2 font-medium text-muted-foreground">Mensagem</th>
                        <th className="text-center py-2 px-2 font-medium text-muted-foreground">Status</th>
                        <th className="text-center py-2 px-2 font-medium text-muted-foreground">Trigger</th>
                        <th className="text-center py-2 px-2 font-medium text-muted-foreground">Enviado</th>
                      </tr>
                    </thead>
                    <tbody>
                      {executions.map(exec => (
                        <tr key={exec.id} className="border-b hover:bg-muted/50">
                          <td className="py-2 px-2">
                            <div className="font-medium">{exec.customer_nome || exec.customer_codigo}</div>
                            <div className="text-xs text-muted-foreground">#{exec.customer_codigo}</div>
                          </td>
                          <td className="py-2 px-2 text-xs max-w-xs truncate">{exec.message_text}</td>
                          <td className="py-2 px-2 text-center">
                            <span className={`px-2 py-0.5 rounded-full text-xs font-medium ${EXEC_STATUS_COLORS[exec.status] || ''}`}>
                              {exec.status}
                            </span>
                          </td>
                          <td className="py-2 px-2 text-center text-xs">
                            {exec.triggered_at ? new Date(exec.triggered_at).toLocaleDateString('pt-BR') : '—'}
                          </td>
                          <td className="py-2 px-2 text-center text-xs">
                            {exec.sent_at ? new Date(exec.sent_at).toLocaleString('pt-BR') : '—'}
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </CardContent>
            </Card>
          )}
        </>
      )}
    </Page>
  );
}
