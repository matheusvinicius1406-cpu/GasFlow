import { useState, useEffect } from 'react';
import { Link } from 'react-router-dom';
import { Page, PageHeader, PageTitle, PageActions } from '@/components/layout/Page';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/Card';
import { Button } from '@/components/ui/Button';

import { Input } from '@/components/ui/Input';
import { LoadingSpinner } from '@/components/ui/LoadingSpinner';
import { ErrorState } from '@/components/ui/ErrorState';
import { EmptyState } from '@/components/ui/EmptyState';
import { StatCard } from '@/components/ui/StatCard';
import { apiClient } from '@/lib/api/client';
import { Users, TrendingUp, Clock, AlertTriangle, Package, RefreshCw, Search } from 'lucide-react';

interface ReorderOpportunity {
  customer_codigo: string;
  customer_nome: string;
  total_orders: number;
  total_spent: number;
  average_ticket: number;
  days_since_last_order: number | null;
  last_order_date: string | null;
  expected_reorder_date: string | null;
  expected_interval_days: number | null;
  reorder_score: number;
  confidence: 'HIGH' | 'MEDIUM' | 'LOW';
  status: 'READY' | 'DUE' | 'OVERDUE' | 'DORMANT';
  recommended_product: string | null;
  days_overdue: number | null;
  avg_days_between_orders: number | null;
  order_dates: string[];
}

interface ReorderSummary {
  total_customers: number;
  ready_count: number;
  due_count: number;
  overdue_count: number;
  dormant_count: number;
  high_confidence_count: number;
  medium_confidence_count: number;
  low_confidence_count: number;
}

const STATUS_CONFIG: Record<string, { label: string; color: string }> = {
  READY: { label: 'Próximo', color: 'bg-emerald-100 text-emerald-800 dark:bg-emerald-900/30 dark:text-emerald-400' },
  DUE: { label: 'Na Janela', color: 'bg-blue-100 text-blue-800 dark:bg-blue-900/30 dark:text-blue-400' },
  OVERDUE: { label: 'Atrasado', color: 'bg-amber-100 text-amber-800 dark:bg-amber-900/30 dark:text-amber-400' },
  DORMANT: { label: 'Inativo', color: 'bg-red-100 text-red-800 dark:bg-red-900/30 dark:text-red-400' },
};

const CONFIDENCE_CONFIG: Record<string, { label: string; color: string }> = {
  HIGH: { label: 'Alta', color: 'bg-emerald-100 text-emerald-800 dark:bg-emerald-900/30 dark:text-emerald-400' },
  MEDIUM: { label: 'Média', color: 'bg-amber-100 text-amber-800 dark:bg-amber-900/30 dark:text-amber-400' },
  LOW: { label: 'Baixa', color: 'bg-gray-100 text-gray-800 dark:bg-gray-800 dark:text-gray-400' },
};

export function ReorderPage() {
  const [opportunities, setOpportunities] = useState<ReorderOpportunity[]>([]);
  const [summary, setSummary] = useState<ReorderSummary | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [search, setSearch] = useState('');
  const [statusFilter, setStatusFilter] = useState<string>('');
  const [confidenceFilter, setConfidenceFilter] = useState<string>('');

  const fetchData = async () => {
    setLoading(true);
    setError(null);
    try {
      const [summaryRes, oppsRes] = await Promise.all([
        apiClient.get('/reorder/summary'),
        apiClient.get('/reorder/opportunities'),
      ]);
      setSummary(summaryRes.data);
      setOpportunities(oppsRes.data.opportunities || []);
    } catch {
      setError('Erro ao carregar dados de recompra');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => { fetchData(); }, []);

  const filtered = opportunities.filter(opp => {
    if (search && !opp.customer_nome.toLowerCase().includes(search.toLowerCase()) && !opp.customer_codigo.includes(search)) return false;
    if (statusFilter && opp.status !== statusFilter) return false;
    if (confidenceFilter && opp.confidence !== confidenceFilter) return false;
    return true;
  });

  const formatDate = (d: string | null) => {
    if (!d) return '—';
    return new Date(d).toLocaleDateString('pt-BR');
  };

  const formatCurrency = (v: number) =>
    new Intl.NumberFormat('pt-BR', { style: 'currency', currency: 'BRL' }).format(v);

  if (loading) {
    return (
      <Page>
        <PageHeader>
          <PageTitle subtitle="Análise de oportunidades de recompra">Recompra Inteligente</PageTitle>
        </PageHeader>
        <div className="flex items-center justify-center py-20">
          <LoadingSpinner size="lg" />
        </div>
      </Page>
    );
  }

  if (error) {
    return (
      <Page>
        <PageHeader>
          <PageTitle subtitle="Análise de oportunidades de recompra">Recompra Inteligente</PageTitle>
        </PageHeader>
        <ErrorState message={error} onRetry={fetchData} />
      </Page>
    );
  }

  return (
    <Page>
      <PageHeader>
        <PageTitle subtitle="Clientes com potencial de recompra baseado em histórico real">Recompra Inteligente</PageTitle>
        <PageActions>
          <Button variant="outline" onClick={fetchData} className="gap-2">
            <RefreshCw className="w-4 h-4" />
            Atualizar
          </Button>
        </PageActions>
      </PageHeader>

      {/* Summary KPIs */}
      {summary && (
        <div className="grid grid-cols-2 md:grid-cols-4 gap-4 mb-6">
          <StatCard
            title="Próximos"
            value={summary.ready_count}
            icon={TrendingUp}
          />
          <StatCard
            title="Na Janela"
            value={summary.due_count}
            icon={Clock}
          />
          <StatCard
            title="Atrasados"
            value={summary.overdue_count}
            icon={AlertTriangle}
          />
          <StatCard
            title="Inativos"
            value={summary.dormant_count}
            icon={Users}
          />
        </div>
      )}

      {/* Filters */}
      <Card className="mb-6">
        <CardContent className="pt-6">
          <div className="flex flex-col sm:flex-row gap-3">
            <div className="flex-1 relative">
              <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-muted-foreground" />
              <Input
                placeholder="Buscar por nome ou código..."
                value={search}
                onChange={(e) => setSearch(e.target.value)}
                className="pl-10"
              />
            </div>
            <select
              value={statusFilter}
              onChange={(e) => setStatusFilter(e.target.value)}
              className="px-3 py-2 border rounded-md bg-background text-sm"
            >
              <option value="">Todos os status</option>
              <option value="READY">Próximos</option>
              <option value="DUE">Na Janela</option>
              <option value="OVERDUE">Atrasados</option>
              <option value="DORMANT">Inativos</option>
            </select>
            <select
              value={confidenceFilter}
              onChange={(e) => setConfidenceFilter(e.target.value)}
              className="px-3 py-2 border rounded-md bg-background text-sm"
            >
              <option value="">Todas as confianças</option>
              <option value="HIGH">Alta</option>
              <option value="MEDIUM">Média</option>
              <option value="LOW">Baixa</option>
            </select>
          </div>
        </CardContent>
      </Card>

      {/* Opportunities Table */}
      {filtered.length === 0 ? (
        <EmptyState
          title="Nenhuma oportunidade encontrada"
          description="Ajuste os filtros ou aguarde mais pedidos para gerar análises."
          icon={Package}
        />
      ) : (
        <Card>
          <CardHeader>
            <CardTitle>Oportunidades ({filtered.length})</CardTitle>
          </CardHeader>
          <CardContent>
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead>
                  <tr className="border-b">
                    <th className="text-left py-3 px-2 font-medium text-muted-foreground">Cliente</th>
                    <th className="text-center py-3 px-2 font-medium text-muted-foreground">Score</th>
                    <th className="text-center py-3 px-2 font-medium text-muted-foreground">Status</th>
                    <th className="text-center py-3 px-2 font-medium text-muted-foreground">Confiança</th>
                    <th className="text-right py-3 px-2 font-medium text-muted-foreground">Pedidos</th>
                    <th className="text-right py-3 px-2 font-medium text-muted-foreground">Ticket Médio</th>
                    <th className="text-center py-3 px-2 font-medium text-muted-foreground">Último Pedido</th>
                    <th className="text-center py-3 px-2 font-medium text-muted-foreground">Previsão</th>
                    <th className="text-left py-3 px-2 font-medium text-muted-foreground">Produto</th>
                  </tr>
                </thead>
                <tbody>
                  {filtered.map((opp) => (
                    <tr key={opp.customer_codigo} className="border-b hover:bg-muted/50">
                      <td className="py-3 px-2">
                        <Link to={`/customers/${opp.customer_codigo}`} className="font-medium text-foreground hover:underline">
                          {opp.customer_nome}
                        </Link>
                        <div className="text-xs text-muted-foreground">#{opp.customer_codigo}</div>
                      </td>
                      <td className="py-3 px-2 text-center">
                        <div className="inline-flex items-center gap-1.5">
                          <div className="w-10 h-1.5 bg-muted rounded-full overflow-hidden">
                            <div
                              className="h-full rounded-full bg-primary"
                              style={{ width: `${Math.min(100, opp.reorder_score)}%` }}
                            />
                          </div>
                          <span className="text-xs font-medium">{opp.reorder_score.toFixed(0)}</span>
                        </div>
                      </td>
                      <td className="py-3 px-2 text-center">
                        <span className={`inline-flex items-center px-2 py-0.5 rounded-full text-xs font-medium ${STATUS_CONFIG[opp.status]?.color || ''}`}>
                          {STATUS_CONFIG[opp.status]?.label || opp.status}
                        </span>
                      </td>
                      <td className="py-3 px-2 text-center">
                        <span className={`px-2 py-0.5 rounded-full text-xs font-medium ${CONFIDENCE_CONFIG[opp.confidence]?.color || ''}`}>
                          {CONFIDENCE_CONFIG[opp.confidence]?.label || opp.confidence}
                        </span>
                      </td>
                      <td className="py-3 px-2 text-right">{opp.total_orders}</td>
                      <td className="py-3 px-2 text-right">{formatCurrency(opp.average_ticket)}</td>
                      <td className="py-3 px-2 text-center text-xs">{formatDate(opp.last_order_date)}</td>
                      <td className="py-3 px-2 text-center text-xs">
                        {opp.expected_reorder_date ? (
                          <div>
                            <div>{formatDate(opp.expected_reorder_date)}</div>
                            {opp.days_overdue !== null && opp.days_overdue > 0 && (
                              <div className="text-amber-600 dark:text-amber-400 text-[10px]">
                                +{opp.days_overdue} dias
                              </div>
                            )}
                          </div>
                        ) : '—'}
                      </td>
                      <td className="py-3 px-2 text-xs">
                        {opp.recommended_product || '—'}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </CardContent>
        </Card>
      )}
    </Page>
  );
}
