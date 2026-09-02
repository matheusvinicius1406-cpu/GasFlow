import { useState, useEffect } from 'react';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/Card';
import { Button } from '@/components/ui/Button';
import { Input } from '@/components/ui/Input';
import { Badge } from '@/components/ui/Badge';
import { LoadingSpinner } from '@/components/ui/LoadingSpinner';
import { ErrorState } from '@/components/ui/ErrorState';
import { EmptyState } from '@/components/ui/EmptyState';
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/Table';
import { DollarSign, TrendingUp, TrendingDown, Plus, Wallet } from 'lucide-react';
import { apiClient } from '@/lib/api/client';

interface Payment {
  id: number;
  order_codigo: string;
  amount: number;
  method: string;
  status: string;
  paid_at: string | null;
  created_at: string;
}

interface Expense {
  id: number;
  description: string;
  amount: number;
  category: string;
  date: string;
  status: string;
}

interface CashMovement {
  id: number;
  type: string;
  amount: number;
  description: string;
  balance_after: number;
  created_at: string;
}

const METHOD_LABELS: Record<string, string> = {
  CASH: 'Dinheiro', PIX: 'PIX', CARD: 'Cartão', TRANSFER: 'Transferência', OTHER: 'Outro',
};
const CATEGORY_LABELS: Record<string, string> = {
  FUEL: 'Combustível', MAINTENANCE: 'Manutenção', SUPPLIES: 'Suprimentos',
  UTILITIES: 'Utilidades', SALARY: 'Salário', TAX: 'Imposto', OTHER: 'Outro',
};
const STATUS_COLORS: Record<string, string> = {
  PAID: 'bg-green-100 text-green-800', PENDING: 'bg-yellow-100 text-yellow-800',
  PARTIAL: 'bg-blue-100 text-blue-800', REFUNDED: 'bg-purple-100 text-purple-800',
  ACTIVE: 'bg-green-100 text-green-800', CANCELLED: 'bg-gray-100 text-gray-800',
  RECEIPT: 'bg-green-100 text-green-800', EXPENSE: 'bg-red-100 text-red-800',
  REFUND: 'bg-orange-100 text-orange-800',
};

function formatMoney(v: number) { return `R$ ${Number(v).toFixed(2).replace('.', ',')}`; }

export function FinancePage() {
  const [payments, setPayments] = useState<Payment[]>([]);
  const [expenses, setExpenses] = useState<Expense[]>([]);
  const [cashMovements, setCashMovements] = useState<CashMovement[]>([]);
  const [balance, setBalance] = useState(0);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(false);
  const [activeTab, setActiveTab] = useState<'payments' | 'expenses' | 'cash'>('payments');
  const [expenseOpen, setExpenseOpen] = useState(false);
  const [newExpense, setNewExpense] = useState({ description: '', amount: '', category: 'OTHER' });

  useEffect(() => { fetchData(); }, []);

  async function fetchData() {
    setLoading(true);
    setError(false);
    try {
      const [payRes, expRes, cashRes, balRes] = await Promise.all([
        apiClient.get('/finance/payments'),
        apiClient.get('/finance/expenses'),
        apiClient.get('/finance/cash'),
        apiClient.get('/finance/cash/balance'),
      ]);
      setPayments(payRes.data.items || []);
      setExpenses(expRes.data.items || []);
      setCashMovements(cashRes.data.items || []);
      setBalance(Number(balRes.data.balance) || 0);
    } catch {
      setError(true);
    } finally {
      setLoading(false);
    }
  }

  async function handleCreateExpense() {
    if (!newExpense.description || !newExpense.amount) return;
    try {
      await apiClient.post('/finance/expenses', {
        description: newExpense.description,
        amount: parseFloat(newExpense.amount),
        category: newExpense.category,
      });
      setExpenseOpen(false);
      setNewExpense({ description: '', amount: '', category: 'OTHER' });
      fetchData();
    } catch {
      // error handled silently
    }
  }

  const totalPayments = payments.reduce((s, p) => s + Number(p.amount), 0);
  const totalExpenses = expenses.filter(e => e.status === 'ACTIVE').reduce((s, e) => s + Number(e.amount), 0);

  if (loading) {
    return (
      <div className="flex items-center justify-center py-16">
        <LoadingSpinner size="lg" />
      </div>
    );
  }

  if (error) {
    return (
      <ErrorState
        message="Não foi possível carregar os dados financeiros."
        onRetry={() => fetchData()}
      />
    );
  }

  return (
    <div className="space-y-6">
      <h1 className="text-2xl font-bold text-foreground">Financeiro</h1>

      {/* Summary Cards */}
      <div className="grid grid-cols-1 md:grid-cols-4 gap-4">
        <Card><CardContent className="p-4">
          <div className="flex items-center gap-3">
            <div className="p-2 bg-green-100 rounded-lg"><Wallet className="h-5 w-5 text-green-600" /></div>
            <div><p className="text-sm text-muted-foreground">Saldo em Caixa</p><p className="text-xl font-bold">{formatMoney(balance)}</p></div>
          </div>
        </CardContent></Card>
        <Card><CardContent className="p-4">
          <div className="flex items-center gap-3">
            <div className="p-2 bg-blue-100 rounded-lg"><TrendingUp className="h-5 w-5 text-blue-600" /></div>
            <div><p className="text-sm text-muted-foreground">Total Recebido</p><p className="text-xl font-bold">{formatMoney(totalPayments)}</p></div>
          </div>
        </CardContent></Card>
        <Card><CardContent className="p-4">
          <div className="flex items-center gap-3">
            <div className="p-2 bg-red-100 rounded-lg"><TrendingDown className="h-5 w-5 text-red-600" /></div>
            <div><p className="text-sm text-muted-foreground">Total Despesas</p><p className="text-xl font-bold">{formatMoney(totalExpenses)}</p></div>
          </div>
        </CardContent></Card>
        <Card><CardContent className="p-4">
          <div className="flex items-center gap-3">
            <div className="p-2 bg-purple-100 rounded-lg"><DollarSign className="h-5 w-5 text-purple-600" /></div>
            <div><p className="text-sm text-muted-foreground">Resultado</p><p className="text-xl font-bold">{formatMoney(totalPayments - totalExpenses)}</p></div>
          </div>
        </CardContent></Card>
      </div>

      {/* Tab Buttons */}
      <div className="flex gap-2 border-b pb-2">
        {(['payments', 'expenses', 'cash'] as const).map(tab => (
          <Button key={tab} variant={activeTab === tab ? 'default' : 'ghost'} onClick={() => setActiveTab(tab)}>
            {tab === 'payments' ? '💳 Pagamentos' : tab === 'expenses' ? '📋 Despesas' : '💰 Movimentações'}
          </Button>
        ))}
      </div>

      {/* Payments */}
      {activeTab === 'payments' && (
        <Card>
          <CardHeader><CardTitle>Pagamentos</CardTitle></CardHeader>
          <CardContent>
            {payments.length === 0 ? (
              <EmptyState
                icon={DollarSign}
                title="Nenhum pagamento registrado"
                description="Os pagamentos aparecerão aqui quando forem registrados."
              />
            ) : (
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead>Pedido</TableHead>
                    <TableHead>Valor</TableHead>
                    <TableHead>Método</TableHead>
                    <TableHead>Status</TableHead>
                    <TableHead>Data</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {payments.map(p => (
                    <TableRow key={p.id}>
                      <TableCell className="font-mono">#{p.order_codigo}</TableCell>
                      <TableCell className="font-semibold">{formatMoney(p.amount)}</TableCell>
                      <TableCell>{METHOD_LABELS[p.method] || p.method}</TableCell>
                      <TableCell><Badge className={STATUS_COLORS[p.status] || ''}>{p.status}</Badge></TableCell>
                      <TableCell>{p.paid_at ? new Date(p.paid_at).toLocaleDateString('pt-BR') : '-'}</TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            )}
          </CardContent>
        </Card>
      )}

      {/* Expenses */}
      {activeTab === 'expenses' && (
        <Card>
          <CardHeader>
            <div className="flex items-center justify-between">
              <CardTitle>Despesas</CardTitle>
              <Button onClick={() => setExpenseOpen(!expenseOpen)}><Plus className="h-4 w-4 mr-1" /> Nova</Button>
            </div>
          </CardHeader>
          <CardContent>
            {expenseOpen && (
              <div className="bg-accent/50 p-4 rounded-lg mb-4 space-y-3">
                <Input placeholder="Descrição" value={newExpense.description} onChange={e => setNewExpense({ ...newExpense, description: e.target.value })} />
                <Input type="number" step="0.01" placeholder="Valor (R$)" value={newExpense.amount} onChange={e => setNewExpense({ ...newExpense, amount: e.target.value })} />
                <select className="w-full rounded-md border border-border bg-background px-3 py-2 text-sm" value={newExpense.category} onChange={e => setNewExpense({ ...newExpense, category: e.target.value })}>
                  {Object.entries(CATEGORY_LABELS).map(([k, v]) => <option key={k} value={k}>{v}</option>)}
                </select>
                <div className="flex gap-2">
                  <Button onClick={handleCreateExpense}>Registrar</Button>
                  <Button variant="ghost" onClick={() => setExpenseOpen(false)}>Cancelar</Button>
                </div>
              </div>
            )}
            {expenses.length === 0 ? (
              <EmptyState
                icon={DollarSign}
                title="Nenhuma despesa registrada"
                description="As despesas aparecerão aqui quando forem registradas."
              />
            ) : (
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead>Descrição</TableHead>
                    <TableHead>Valor</TableHead>
                    <TableHead>Categoria</TableHead>
                    <TableHead>Status</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {expenses.map(e => (
                    <TableRow key={e.id}>
                      <TableCell>{e.description}</TableCell>
                      <TableCell className="font-semibold text-destructive">{formatMoney(e.amount)}</TableCell>
                      <TableCell>{CATEGORY_LABELS[e.category] || e.category}</TableCell>
                      <TableCell><Badge className={STATUS_COLORS[e.status] || ''}>{e.status}</Badge></TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            )}
          </CardContent>
        </Card>
      )}

      {/* Cash Movements */}
      {activeTab === 'cash' && (
        <Card>
          <CardHeader><CardTitle>Movimentações de Caixa</CardTitle></CardHeader>
          <CardContent>
            {cashMovements.length === 0 ? (
              <EmptyState
                icon={Wallet}
                title="Nenhuma movimentação"
                description="As movimentações de caixa aparecerão aqui."
              />
            ) : (
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead>Tipo</TableHead>
                    <TableHead>Descrição</TableHead>
                    <TableHead>Valor</TableHead>
                    <TableHead>Saldo</TableHead>
                    <TableHead>Data</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {cashMovements.map(m => (
                    <TableRow key={m.id}>
                      <TableCell><Badge className={STATUS_COLORS[m.type] || ''}>{m.type === 'RECEIPT' ? 'Recebimento' : m.type === 'EXPENSE' ? 'Despesa' : m.type === 'REFUND' ? 'Estorno' : 'Ajuste'}</Badge></TableCell>
                      <TableCell>{m.description}</TableCell>
                      <TableCell className={`font-semibold ${m.type === 'EXPENSE' || m.type === 'REFUND' ? 'text-destructive' : 'text-green-600'}`}>{m.type === 'EXPENSE' || m.type === 'REFUND' ? '-' : '+'}{formatMoney(m.amount)}</TableCell>
                      <TableCell className="font-mono">{formatMoney(m.balance_after)}</TableCell>
                      <TableCell>{new Date(m.created_at).toLocaleDateString('pt-BR')}</TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            )}
          </CardContent>
        </Card>
      )}
    </div>
  );
}
