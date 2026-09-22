import axios from 'axios'

import {
  ACCESS_TOKEN_KEY,
  PASSWORD_CHANGE_REQUIRED_EVENT,
  REFRESH_TOKEN_KEY,
  SESSION_REFRESHED_EVENT,
} from './session'

const API_BASE_URL = import.meta.env?.VITE_API_URL || '/api'

// As chaves de sessão vivem em `./session` (módulo sem axios) e são
// reexportadas aqui para quem já importa do client.
export {
  ACCESS_TOKEN_KEY,
  PASSWORD_CHANGE_REQUIRED_EVENT,
  REFRESH_TOKEN_KEY,
  SESSION_REFRESHED_EVENT,
} from './session'

function clearSession() {
  localStorage.removeItem(ACCESS_TOKEN_KEY)
  localStorage.removeItem(REFRESH_TOKEN_KEY)
}

/**
 * Renovação *single-flight*.
 *
 * Várias requests simultâneas que recebem 401 compartilham **uma** chamada de
 * refresh. Isso não é otimização: a rotação no backend guarda o refresh
 * anterior para detectar vazamento, então N trocas concorrentes com o mesmo
 * refresh seriam lidas como reuso e **revogariam a sessão do próprio usuário**.
 */
let refreshInFlight: Promise<string | null> | null = null

async function refreshAccessToken(): Promise<string | null> {
  const refresh = localStorage.getItem(REFRESH_TOKEN_KEY)
  if (!refresh) return null
  if (!refreshInFlight) {
    refreshInFlight = api.auth
      .refresh(refresh)
      .then((res) => {
        const access = res.data?.access_token as string | undefined
        if (!access) return null
        localStorage.setItem(ACCESS_TOKEN_KEY, access)
        // O refresh também gira; guardar o novo é o que mantém a sessão viva.
        if (res.data?.refresh_token) {
          localStorage.setItem(REFRESH_TOKEN_KEY, res.data.refresh_token)
        }
        try {
          window.dispatchEvent(new CustomEvent(SESSION_REFRESHED_EVENT, { detail: access }))
        } catch {
          // Ambiente sem CustomEvent (SSR/teste) — irrelevante para o fluxo.
        }
        return access
      })
      .catch(() => null)
      .finally(() => {
        refreshInFlight = null
      })
  }
  return refreshInFlight
}

export const apiClient = axios.create({
  baseURL: API_BASE_URL,
  timeout: 10000,
  headers: {
    'Content-Type': 'application/json',
  },
})

// Request interceptor - attach auth token
apiClient.interceptors.request.use(
  (config) => {
    const token = localStorage.getItem('gasflow_token')
    if (token) {
      config.headers.Authorization = `Bearer ${token}`
    }
    return config
  },
  (error) => Promise.reject(error)
)

// Response interceptor - handle errors
apiClient.interceptors.response.use(
  (response) => response,
  async (error) => {
    const status = error.response?.status
    const url: string = error.config?.url || ''
    // Endpoints de sessão não entram na renovação: um 401 no login é
    // credencial errada, e no refresh é sessão morta (não há o que renovar).
    const isSessionEndpoint = url.includes('/auth/login') || url.includes('/auth/refresh')
    const original = error.config as (typeof error.config & { __gfRetried?: boolean }) | undefined

    // B5: access expirado (15 min) → renova e repete **uma** vez. Sem isso o
    // usuário seria deslogado no meio do dia sem motivo visível.
    if (status === 401 && !isSessionEndpoint && original && !original.__gfRetried) {
      const access = await refreshAccessToken()
      if (access) {
        original.__gfRetried = true
        original.headers = { ...original.headers, Authorization: `Bearer ${access}` }
        return apiClient(original)
      }
    }

    if (status === 401 && !isSessionEndpoint) {
      clearSession()
      window.location.href = '/login'
    }

    // P0 (3.8 reforçado): o backend recusa rotas fora de /auth enquanto a troca
    // de senha está pendente. Levanta o gate em vez de deixar um 403 mudo.
    if (status === 403 && error.response?.data?.detail === 'Password change required') {
      window.dispatchEvent(new Event(PASSWORD_CHANGE_REQUIRED_EVENT))
    }
    return Promise.reject(error)
  }
)

// API endpoints
export const api = {
  // Dashboard
  dashboard: () => apiClient.get('/dashboard'),

  // Health
  health: () => apiClient.get('/health'),

  // Auth — FASE 13
  auth: {
    login: (username: string, password: string) =>
      apiClient.post('/auth/login', { username, password }),
    // B5: troca o refresh por um par novo (rotação com detecção de reuso).
    refresh: (refreshToken: string) =>
      apiClient.post('/auth/refresh', { refresh_token: refreshToken }),
    // P0 (3.8): troca obrigatória/self-service pós-reset
    changePassword: (currentPassword: string, newPassword: string) =>
      apiClient.post('/auth/change-password', {
        current_password: currentPassword,
        new_password: newPassword,
      }),
    logout: () => apiClient.post('/auth/logout'),
    me: () => apiClient.get('/auth/me'),
    users: () => apiClient.get('/auth/users'),
    createUser: (data: unknown) => apiClient.post('/auth/users', data),
    roles: () => apiClient.get('/auth/roles'),
    audit: (limit?: number) => apiClient.get('/auth/audit', { params: { limit } }),
  },

  // Admin — P0 3.3 (RBAC persistido + auditoria)
  admin: {
    users: (params?: { search?: string; role_id?: string; status?: string }) =>
      apiClient.get('/admin/users', { params }),
    createUser: (data: {
      username: string
      email: string
      password: string
      display_name?: string
      role_id?: string | null
    }) => apiClient.post('/admin/users', data),
    updateUser: (
      id: string,
      data: { username?: string; email?: string; display_name?: string; role_id?: string | null }
    ) => apiClient.patch(`/admin/users/${id}`, data),
    resetPassword: (id: string) => apiClient.post(`/admin/users/${id}/reset-password`),
    deactivate: (id: string) => apiClient.post(`/admin/users/${id}/deactivate`),
    activate: (id: string) => apiClient.post(`/admin/users/${id}/activate`),
    roles: () => apiClient.get('/admin/roles'),
    updateRolePermissions: (id: string, permissions: string[]) =>
      apiClient.patch(`/admin/roles/${id}/permissions`, { permissions }),
    audit: (params?: {
      actor_id?: string
      action?: string
      resource?: string
      from_ts?: string
      to_ts?: string
      offset?: number
      limit?: number
    }) => apiClient.get('/admin/audit', { params }),
  },

  // Clients — FASE 6: search, pagination, 360
  clients: {
    list: (params?: { q?: string; tipo?: string; ativo?: boolean; page?: number; page_size?: number }) =>
      apiClient.get('/clients/', { params }),
    listLegacy: () => apiClient.get('/clients/legacy'),
    get: (codigo: string) => apiClient.get(`/clients/${codigo}`),
    get360: (codigo: string) => apiClient.get(`/clients/${codigo}/360`),
    getOrders: (codigo: string) => apiClient.get(`/clients/${codigo}/orders`),
    create: (data: unknown) => apiClient.post('/clients/', data),
    update: (codigo: string, data: unknown) => apiClient.put(`/clients/${codigo}`, data),
    disable: (codigo: string) => apiClient.patch(`/clients/${codigo}/disable`),
  },

  // Orders
  orders: {
    list: (status?: string) => apiClient.get('/orders/', { params: { status } }),
    get: (codigo: string) => apiClient.get(`/orders/${codigo}`),
    create: (data: unknown) => apiClient.post('/orders/', data),
    updateStatus: (codigo: string, status: string) =>
      apiClient.patch(`/orders/${codigo}/status`, { status }),
    assignDriver: (codigo: string, driverCodigo: string) =>
      apiClient.patch(`/orders/${codigo}/assign-driver`, {
        delivery_driver_codigo: driverCodigo,
      }),
  },

  // Products
  products: {
    list: () => apiClient.get('/products/'),
    get: (codigo: string) => apiClient.get(`/products/${codigo}`),
    create: (data: unknown) => apiClient.post('/products/', data),
    update: (codigo: string, data: unknown) => apiClient.put(`/products/${codigo}`, data),
    disable: (codigo: string) => apiClient.patch(`/products/${codigo}/disable`),
  },

  // Inventory — FASE 7
  inventory: {
    list: (params?: { stock_status?: string; product_type?: string }) =>
      apiClient.get('/inventory/', { params }),
    get: (productCodigo: string) => apiClient.get(`/inventory/${productCodigo}`),
    getMovements: (productCodigo: string, params?: { page?: number; page_size?: number }) =>
      apiClient.get(`/inventory/${productCodigo}/movements`, { params }),
    addStock: (productCodigo: string, data: { quantity: number; reason?: string }) =>
      apiClient.post(`/inventory/${productCodigo}/entries`, data),
    adjust: (productCodigo: string, data: { new_quantity: number; reason?: string }) =>
      apiClient.post(`/inventory/${productCodigo}/adjustments`, data),
    recordLoss: (productCodigo: string, data: { quantity: number; reason: string }) =>
      apiClient.post(`/inventory/${productCodigo}/losses`, data),
    setMinimum: (productCodigo: string, data: { minimum_quantity: number }) =>
      apiClient.patch(`/inventory/${productCodigo}/minimum`, data),
    reconciliation: () => apiClient.get('/inventory/reconciliation/check'),
  },

  // Delivery Drivers
  drivers: {
    list: () => apiClient.get('/delivery-drivers/'),
    get: (codigo: string) => apiClient.get(`/delivery-drivers/${codigo}`),
    create: (data: unknown) => apiClient.post('/delivery-drivers/', data),
    disable: (codigo: string) => apiClient.patch(`/delivery-drivers/${codigo}/disable`),
  },

  // Delivery Operations — FASE 14
  deliveryOps: {
    listDeliveries: (params?: { status?: string; driver_id?: string }) =>
      apiClient.get('/delivery/deliveries', { params }),
    getDelivery: (id: string) => apiClient.get(`/delivery/deliveries/${id}`),
    createDelivery: (data: {
      order_id: string;
      customer_codigo: string;
      customer_name: string;
      address?: { street: string; number: string; complement?: string; neighborhood: string; city?: string; state?: string; zip_code?: string; reference?: string };
      scheduled_at?: string;
      notes?: string;
    }) => apiClient.post('/delivery/deliveries', data),
    assignDelivery: (id: string, data: { driver_id: string; vehicle_id?: string }) =>
      apiClient.patch(`/delivery/deliveries/${id}/assign`, data),
    updateStatus: (id: string, data: {
      status: string;
      failure_reason?: string;
      failure_notes?: string;
      proof_type?: string;
    }) => apiClient.patch(`/delivery/deliveries/${id}/status`, data),
    listDrivers: (params?: { status?: string }) =>
      apiClient.get('/delivery/drivers', { params }),
    getDriver: (id: string) => apiClient.get(`/delivery/drivers/${id}`),
    dispatchSummary: () => apiClient.get('/delivery/dispatch/summary'),
    listVehicles: () => apiClient.get('/delivery/vehicles'),
    listRoutes: () => apiClient.get('/delivery/routes'),
  },

  // Finance — payments, receivables, expenses, cash
  finance: {
    // Payments
    listPayments: (params?: { status?: string; order_codigo?: string; page?: number; page_size?: number }) =>
      apiClient.get('/finance/payments', { params }),
    registerPayment: (orderCodigo: string, data: {
      amount: number;
      method: string;
      reference?: string;
      idempotency_key?: string;
      notes?: string;
    }) => apiClient.post(`/finance/orders/${orderCodigo}/payments`, data),
    refundPayment: (paymentId: number, reason?: string) =>
      apiClient.post(`/finance/payments/${paymentId}/refund`, null, { params: { reason: reason || '' } }),

    // Receivables
    listReceivables: (params?: { status?: string; order_codigo?: string; page?: number; page_size?: number }) =>
      apiClient.get('/finance/receivables', { params }),

    // Expenses
    listExpenses: (params?: { status?: string; page?: number; page_size?: number }) =>
      apiClient.get('/finance/expenses', { params }),
    createExpense: (data: { description: string; amount: number; category?: string; date?: string; payment_method?: string; notes?: string }) =>
      apiClient.post('/finance/expenses', data),
    cancelExpense: (expenseId: number) =>
      apiClient.post(`/finance/expenses/${expenseId}/cancel`),

    // Cash
    listCash: (params?: { type_filter?: string; page?: number; page_size?: number }) =>
      apiClient.get('/finance/cash', { params }),
    cashBalance: () => apiClient.get('/finance/cash/balance'),

    // Reports
    daily: (date?: string) => apiClient.get('/finance/reports/daily', { params: { date } }),
    // F10.8: período (totais + série diária + comparação com o anterior)
    periodReport: (params: { days?: number; from?: string; to?: string }) =>
      apiClient.get('/finance/reports/period', { params }),
  },

  // Finance Reports (backward compat)
  financeReports: {
    daily: (date?: string) => apiClient.get('/finance/reports/daily', { params: { date } }),
    cashBalance: () => apiClient.get('/finance/cash/balance'),
  },

  // Payments
  payments: {
    listMethods: () => apiClient.get('/payments/methods'),
    createMethod: (data: unknown) => apiClient.post('/payments/methods', data),
    updateMethod: (id: string, data: unknown) => apiClient.patch(`/payments/methods/${id}`, data),
    deleteMethod: (id: string) => apiClient.delete(`/payments/methods/${id}`),
    toggleMethod: (id: string) => apiClient.patch(`/payments/methods/${id}/toggle`),
    getPix: () => apiClient.get('/payments/pix'),
    createPix: (data: unknown) => apiClient.post('/payments/pix', data),
    updatePix: (id: string, data: unknown) => apiClient.patch(`/payments/pix/${id}`, data),
    deletePix: (id: string) => apiClient.delete(`/payments/pix/${id}`),
    generatePix: (data: unknown) => apiClient.post('/payments/pix/payload', data),
    pixStatus: (txid: string) => apiClient.get(`/payments/pix/${txid}/status`),
    list: (params?: { status?: string }) => apiClient.get('/payments/', { params }),
    create: (data: unknown) => apiClient.post('/payments/', data),
    get: (id: string) => apiClient.get(`/payments/${id}`),
    confirm: (id: string, notes?: string) => apiClient.post(`/payments/${id}/confirm`, { notes: notes || '' }),
    cancel: (id: string) => apiClient.post(`/payments/${id}/cancel`),
    refund: (id: string) => apiClient.post(`/payments/${id}/refund`),
    summary: () => apiClient.get('/payments/summary'),
  },

  // Printer
  printer: {
    print: (data: { order_id: string; is_reprint?: boolean }) => apiClient.post('/printer/print', data),
    status: () => apiClient.get('/printer/status'),
    jobs: (limit?: number) => apiClient.get('/printer/jobs', { params: { limit } }),
    retry: (jobId: string) => apiClient.post(`/printer/jobs/${jobId}/retry`),
  },

  // Reports
  reports: {
    daily: (date?: string) => apiClient.get('/reports/daily', { params: { date } }),
    dailyPdf: (date?: string) => apiClient.get('/reports/daily.pdf', { params: { date }, responseType: 'blob' }),
    summary: () => apiClient.get('/reports/summary'),
  },

  // WhatsApp
  whatsapp: {
    status: () => apiClient.get('/whatsapp/status'),
    qr: () => apiClient.get('/whatsapp/qr'),
    start: () => apiClient.post('/whatsapp/start'),
    logout: () => apiClient.post('/whatsapp/logout'),
    contacts: (limit = 50, offset = 0) =>
      apiClient.get('/whatsapp/contacts', { params: { limit, offset } }),
    syncContacts: () => apiClient.post('/whatsapp/contacts/sync'),
    customers: (limit = 50, offset = 0) =>
      apiClient.get('/whatsapp/customers', { params: { limit, offset } }),
    lists: () => apiClient.get('/whatsapp/lists'),
    campaigns: () => apiClient.get('/whatsapp/campaigns'),
  },

  // Purchase Notes — Item 2 (notas de compra internas, sem SEFAZ)
  purchaseNotes: {
    list: (params?: { supplier?: string; status?: string; from?: string; to?: string }) =>
      apiClient.get('/purchase-notes', { params }),
    get: (id: string) => apiClient.get(`/purchase-notes/${id}`),
    create: (data: {
      supplier_name: string
      supplier_cnpj?: string
      issue_date?: string
      observations?: string
      items: { product_codigo: string; quantity: number; unit_price: number }[]
    }) => apiClient.post('/purchase-notes', data),
    update: (
      id: string,
      data: {
        supplier_name?: string
        supplier_cnpj?: string
        issue_date?: string
        observations?: string
        items?: { product_codigo: string; quantity: number; unit_price: number }[]
      }
    ) => apiClient.patch(`/purchase-notes/${id}`, data),
    confirm: (id: string) => apiClient.post(`/purchase-notes/${id}/confirm`),
    cancel: (id: string) => apiClient.post(`/purchase-notes/${id}/cancel`),
    pdfUrl: (id: string) => `/purchase-notes/${id}/pdf`,
  },

  // AI — Item 3 (IA no boot, toggle admin, sem jargão na UI)
  ai: {
    status: () => apiClient.get('/ai/status'),
    test: (prompt: string) => apiClient.post('/ai/test', { prompt }),
    settings: () => apiClient.get('/ai/settings'),
    updateSettings: (data: { enabled?: boolean }) => apiClient.patch('/ai/settings', data),
    downloadModel: () => apiClient.post('/ai/model/download'),
    downloadProgress: () => apiClient.get('/ai/model/download-progress'),
  },
}
