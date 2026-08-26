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
      localStorage.removeItem('gasflow_token')
      window.location.href = '/login'
    }
    return Promise.reject(error)
  }
)

// API endpoints
export const api = {
  // Health
  health: () => apiClient.get('/health'),

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

  // Delivery Drivers
  drivers: {
    list: () => apiClient.get('/delivery-drivers/'),
    get: (codigo: string) => apiClient.get(`/delivery-drivers/${codigo}`),
    create: (data: unknown) => apiClient.post('/delivery-drivers/', data),
    disable: (codigo: string) => apiClient.patch(`/delivery-drivers/${codigo}/disable`),
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
