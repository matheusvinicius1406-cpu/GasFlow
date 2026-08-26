import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { api } from './client'
import type { Client, Product, Order, OrderDetail, OrderCreateInput, Customer360, PaginatedResponse } from '@/types'

// ── Customer Hooks ───────────────────────────────────────

export interface CustomerSearchParams {
  q?: string
  tipo?: string
  ativo?: boolean
  page?: number
  page_size?: number
}

export function useCustomers(params?: CustomerSearchParams) {
  return useQuery({
    queryKey: ['customers', params],
    queryFn: async () => {
      const { data } = await api.clients.list(params)
      return data as PaginatedResponse<Client>
    },
  })
}

export function useCustomersLegacy() {
  return useQuery({
    queryKey: ['customers', 'legacy'],
    queryFn: async () => {
      const { data } = await api.clients.listLegacy()
      return data as Client[]
    },
  })
}

export function useCustomer(codigo: string) {
  return useQuery({
    queryKey: ['customers', codigo],
    queryFn: async () => {
      const { data } = await api.clients.get(codigo)
      return data as Client
    },
    enabled: !!codigo,
  })
}

export function useCustomer360(codigo: string) {
  return useQuery({
    queryKey: ['customers', codigo, '360'],
    queryFn: async () => {
      const { data } = await api.clients.get360(codigo)
      return data as Customer360
    },
    enabled: !!codigo,
  })
}

export function useCustomerOrders(codigo: string) {
  return useQuery({
    queryKey: ['customers', codigo, 'orders'],
    queryFn: async () => {
      const { data } = await api.clients.getOrders(codigo)
      return data as Order[]
    },
    enabled: !!codigo,
  })
}

export function useCreateCustomer() {
  const queryClient = useQueryClient()

  return useMutation({
    mutationFn: async (data: Omit<Client, 'codigo' | 'ativo' | 'created_at' | 'updated_at'>) => {
      const { data: created } = await api.clients.create(data)
      return created as Client
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['customers'] })
    },
  })
}

export function useUpdateCustomer() {
  const queryClient = useQueryClient()

  return useMutation({
    mutationFn: async ({ codigo, data }: { codigo: string; data: Partial<Client> }) => {
      const { data: updated } = await api.clients.update(codigo, data)
      return updated as Client
    },
    onSuccess: (_, variables) => {
      queryClient.invalidateQueries({ queryKey: ['customers'] })
      queryClient.invalidateQueries({ queryKey: ['customers', variables.codigo] })
    },
  })
}

export function useDisableCustomer() {
  const queryClient = useQueryClient()

  return useMutation({
    mutationFn: async (codigo: string) => {
      const { data } = await api.clients.disable(codigo)
      return data as Client
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['customers'] })
    },
  })
}

// ── Product Hooks ────────────────────────────────────────

export function useProducts() {
  return useQuery({
    queryKey: ['products'],
    queryFn: async () => {
      const { data } = await api.products.list()
      return data as Product[]
    },
  })
}

export function useProduct(codigo: string) {
  return useQuery({
    queryKey: ['products', codigo],
    queryFn: async () => {
      const { data } = await api.products.get(codigo)
      return data as Product
    },
    enabled: !!codigo,
  })
}

export function useCreateProduct() {
  const queryClient = useQueryClient()

  return useMutation({
    mutationFn: async (data: Omit<Product, 'codigo' | 'ativo' | 'created_at' | 'updated_at'>) => {
      const { data: created } = await api.products.create(data)
      return created as Product
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['products'] })
    },
  })
}

export function useUpdateProduct() {
  const queryClient = useQueryClient()

  return useMutation({
    mutationFn: async ({ codigo, data }: { codigo: string; data: Partial<Product> }) => {
      const { data: updated } = await api.products.update(codigo, data)
      return updated as Product
    },
    onSuccess: (_, variables) => {
      queryClient.invalidateQueries({ queryKey: ['products'] })
      queryClient.invalidateQueries({ queryKey: ['products', variables.codigo] })
    },
  })
}

export function useDisableProduct() {
  const queryClient = useQueryClient()

  return useMutation({
    mutationFn: async (codigo: string) => {
      const { data } = await api.products.disable(codigo)
      return data as Product
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['products'] })
    },
  })
}

// ── Order Hooks ──────────────────────────────────────────

export function useOrders(status?: string) {
  return useQuery({
    queryKey: ['orders', status],
    queryFn: async () => {
      const { data } = await api.orders.list(status)
      return data as Order[]
    },
  })
}

export function useOrder(codigo: string) {
  return useQuery({
    queryKey: ['orders', codigo],
    queryFn: async () => {
      const { data } = await api.orders.get(codigo)
      return data as OrderDetail
    },
    enabled: !!codigo,
  })
}

export function useCreateOrder() {
  const queryClient = useQueryClient()

  return useMutation({
    mutationFn: async (data: OrderCreateInput) => {
      const { data: created } = await api.orders.create(data)
      return created as Order
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['orders'] })
    },
  })
}

export function useUpdateOrderStatus() {
  const queryClient = useQueryClient()

  return useMutation({
    mutationFn: async ({ codigo, status }: { codigo: string; status: string }) => {
      const { data: updated } = await api.orders.updateStatus(codigo, status)
      return updated as Order
    },
    onSuccess: (_, variables) => {
      queryClient.invalidateQueries({ queryKey: ['orders'] })
      queryClient.invalidateQueries({ queryKey: ['orders', variables.codigo] })
    },
  })
}

export function useAssignDriver() {
  const queryClient = useQueryClient()

  return useMutation({
    mutationFn: async ({ codigo, driverCodigo }: { codigo: string; driverCodigo: string }) => {
      const { data: updated } = await api.orders.assignDriver(codigo, driverCodigo)
      return updated as Order
    },
    onSuccess: (_, variables) => {
      queryClient.invalidateQueries({ queryKey: ['orders'] })
      queryClient.invalidateQueries({ queryKey: ['orders', variables.codigo] })
    },
  })
}
