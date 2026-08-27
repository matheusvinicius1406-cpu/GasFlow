import { useState, useEffect } from 'react';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/Card';
import { Button } from '@/components/ui/Button';
import { Input } from '@/components/ui/Input';
import { Badge } from '@/components/ui/Badge';
import { DollarSign, TrendingUp, TrendingDown, Plus, Wallet } from 'lucide-react';

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

export default function FinancePage() {
  const [payments, setPayments] = useState<Payment[]>([]);
  const [expenses, setExpenses] = useState<Expense[]>([]);
  const [cashMovements, setCashMovements] = useState<CashMovement[]>([]);
  const [balance, setBalance] = useState(0);
  const [loading, setLoading] = useState(true);
  const [activeTab, setActiveTab] = useState<'payments' | 'expenses' | 'cash'>('payments');
  const [expenseOpen, setExpenseOpen] = useState(false);
  const [newExpense, setNewExpense] = useState({ description: '', amount: '', category: 'OTHER' });

  useEffect(() => { fetchData(); }, []);

  async function fetchData() {
    setLoading(true);
    try {
      const [payRes, expRes, cashRes, balRes] = await Promise.all([
        fetch('/api/finance/payments').then(r => r.json()),
        fetch('/api/finance/expenses').then(r => r.json()),
        fetch('/api/finance/cash').then(r => r.json()),
        fetch('/api/finance/cash/balance').then(r => r.json()),
      ]);
      setPayments(payRes.items || []);
      setExpenses(expRes.items || []);
      setCashMovements(cashRes.items || []);
      setBalance(Number(balRes.balance) || 0);
    } catch { /* ignore */ }
    finally { setLoading(false); }
  }

  async function handleCreateExpense() {
    if (!newExpense.description || !newExpense.amount) return;
    await fetch('/api/finance/expenses', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ description: newExpense.description, amount: parseFloat(newExpense.amount), category: newExpense.category }),
    });
    setExpenseOpen(false);
    setNewExpense({ description: '', amount: '', category: 'OTHER' });
    fetchData();
  }

  const totalPayments = payments.reduce((s, p) => s + Number(p.amount), 0);
  const totalExpenses = expenses.filter(e => e.status === 'ACTIVE').reduce((s, e) => s + Number(e.amount), 0);

  if (loading) return <div className="flex items-center justify-center h-64"><div className="text-gray-500">Carregando...</div></div>;

  return (
    <div className="space-y-6">
      <h1 className="text-3xl font-bold">Financeiro</h1>

      {/* Summary Cards */}
      <div className="grid grid-cols-1 md:grid-cols-4 gap-4">
        <Card><CardContent className="p-4">
          <div className="flex items-center gap-3">
            <div className="p-2 bg-green-100 rounded-lg"><Wallet className="h-5 w-5 text-green-600" /></div>
            <div><p className="text-sm text-gray-500">Saldo em Caixa</p><p className="text-xl font-bold">{formatMoney(balance)}</p></div>
          </div>
        </CardContent></Card>
        <Card><CardContent className="p-4">
          <div className="flex items-center gap-3">
            <div className="p-2 bg-blue-100 rounded-lg"><TrendingUp className="h-5 w-5 text-blue-600" /></div>
            <div><p className="text-sm text-gray-500">Total Recebido</p><p className="text-xl font-bold">{formatMoney(totalPayments)}</p></div>
          </div>
        </CardContent></Card>
        <Card><CardContent className="p-4">
          <div className="flex items-center gap-3">
            <div className="p-2 bg-red-100 rounded-lg"><TrendingDown className="h-5 w-5 text-red-600" /></div>
            <div><p className="text-sm text-gray-500">Total Despesas</p><p className="text-xl font-bold">{formatMoney(totalExpenses)}</p></div>
          </div>
        </CardContent></Card>
        <Card><CardContent className="p-4">
          <div className="flex items-center gap-3">
            <div className="p-2 bg-purple-100 rounded-lg"><DollarSign className="h-5 w-5 text-purple-600" /></div>
            <div><p className="text-sm text-gray-500">Resultado</p><p className="text-xl font-bold">{formatMoney(totalPayments - totalExpenses)}</p></div>
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
            {payments.length === 0 ? <p className="text-center text-gray-500 py-4">Nenhum pagamento</p> : (
              <table className="w-full text-sm">
                <thead><tr className="border-b"><th className="text-left p-2">Pedido</th><th className="text-left p-2">Valor</th><th className="text-left p-2">Método</th><th className="text-left p-2">Status</th><th className="text-left p-2">Data</th></tr></thead>
                <tbody>
                  {payments.map(p => (
                    <tr key={p.id} className="border-b hover:bg-gray-50">
                      <td className="p-2 font-mono">#{p.order_codigo}</td>
                      <td className="p-2 font-semibold">{formatMoney(p.amount)}</td>
                      <td className="p-2">{METHOD_LABELS[p.method] || p.method}</td>
                      <td className="p-2"><Badge className={STATUS_COLORS[p.status] || ''}>{p.status}</Badge></td>
                      <td className="p-2">{p.paid_at ? new Date(p.paid_at).toLocaleDateString('pt-BR') : '-'}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
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
              <div className="bg-gray-50 p-4 rounded-lg mb-4 space-y-3">
                <Input placeholder="Descrição" value={newExpense.description} onChange={e => setNewExpense({ ...newExpense, description: e.target.value })} />
                <Input type="number" step="0.01" placeholder="Valor (R$)" value={newExpense.amount} onChange={e => setNewExpense({ ...newExpense, amount: e.target.value })} />
                <select className="w-full border rounded p-2" value={newExpense.category} onChange={e => setNewExpense({ ...newExpense, category: e.target.value })}>
                  {Object.entries(CATEGORY_LABELS).map(([k, v]) => <option key={k} value={k}>{v}</option>)}
                </select>
                <div className="flex gap-2">
                  <Button onClick={handleCreateExpense}>Registrar</Button>
                  <Button variant="ghost" onClick={() => setExpenseOpen(false)}>Cancelar</Button>
                </div>
              </div>
            )}
            {expenses.length === 0 ? <p className="text-center text-gray-500 py-4">Nenhuma despesa</p> : (
              <table className="w-full text-sm">
                <thead><tr className="border-b"><th className="text-left p-2">Descrição</th><th className="text-left p-2">Valor</th><th className="text-left p-2">Categoria</th><th className="text-left p-2">Status</th></tr></thead>
                <tbody>
                  {expenses.map(e => (
                    <tr key={e.id} className="border-b hover:bg-gray-50">
                      <td className="p-2">{e.description}</td>
                      <td className="p-2 font-semibold text-red-600">{formatMoney(e.amount)}</td>
                      <td className="p-2">{CATEGORY_LABELS[e.category] || e.category}</td>
                      <td className="p-2"><Badge className={STATUS_COLORS[e.status] || ''}>{e.status}</Badge></td>
                    </tr>
                  ))}
                </tbody>
              </table>
            )}
          </CardContent>
        </Card>
      )}

      {/* Cash Movements */}
      {activeTab === 'cash' && (
        <Card>
          <CardHeader><CardTitle>Movimentações de Caixa</CardTitle></CardHeader>
          <CardContent>
            {cashMovements.length === 0 ? <p className="text-center text-gray-500 py-4">Nenhuma movimentação</p> : (
              <table className="w-full text-sm">
                <thead><tr className="border-b"><th className="text-left p-2">Tipo</th><th className="text-left p-2">Descrição</th><th className="text-left p-2">Valor</th><th className="text-left p-2">Saldo</th><th className="text-left p-2">Data</th></tr></thead>
                <tbody>
                  {cashMovements.map(m => (
                    <tr key={m.id} className="border-b hover:bg-gray-50">
                      <td className="p-2"><Badge className={STATUS_COLORS[m.type] || ''}>{m.type === 'RECEIPT' ? 'Recebimento' : m.type === 'EXPENSE' ? 'Despesa' : m.type === 'REFUND' ? 'Estorno' : 'Ajuste'}</Badge></td>
                      <td className="p-2">{m.description}</td>
                      <td className={`p-2 font-semibold ${m.type === 'EXPENSE' || m.type === 'REFUND' ? 'text-red-600' : 'text-green-600'}`}>{m.type === 'EXPENSE' || m.type === 'REFUND' ? '-' : '+'}{formatMoney(m.amount)}</td>
                      <td className="p-2 font-mono">{formatMoney(m.balance_after)}</td>
                      <td className="p-2">{new Date(m.created_at).toLocaleDateString('pt-BR')}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            )}
          </CardContent>
        </Card>
      )}
    </div>
  );
}
