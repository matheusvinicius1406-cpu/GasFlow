import axios from 'axios'

const API_BASE_URL = import.meta.env.VITE_API_URL || '/api'

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
  (error) => {
    if (error.response?.status === 401) {
      // Don't redirect on login endpoint (let caller handle it)
      const url = error.config?.url || ''
      if (!url.includes('/auth/login')) {
        localStorage.removeItem('gasflow_token')
        window.location.href = '/login'
      }
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
    logout: () => apiClient.post('/auth/logout'),
    me: () => apiClient.get('/auth/me'),
    users: () => apiClient.get('/auth/users'),
    createUser: (data: unknown) => apiClient.post('/auth/users', data),
    roles: () => apiClient.get('/auth/roles'),
    audit: (limit?: number) => apiClient.get('/auth/audit', { params: { limit } }),
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
    createDelivery: (data: unknown) => apiClient.post('/delivery/deliveries', data),
    assignDelivery: (id: string, data: unknown) => apiClient.patch(`/delivery/deliveries/${id}/assign`, data),
    updateStatus: (id: string, data: unknown) => apiClient.patch(`/delivery/deliveries/${id}/status`, data),
    listDrivers: (params?: { status?: string }) =>
      apiClient.get('/delivery/drivers', { params }),
    getDriver: (id: string) => apiClient.get(`/delivery/drivers/${id}`),
    dispatchSummary: () => apiClient.get('/delivery/dispatch/summary'),
    listVehicles: () => apiClient.get('/delivery/vehicles'),
    listRoutes: () => apiClient.get('/delivery/routes'),
  },

  // Finance Reports
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
}
