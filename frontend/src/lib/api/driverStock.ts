import { useQuery, useQueryClient } from '@tanstack/react-query'
import { apiClient } from '@/lib/api/client'

export interface DriverStockRow {
  product_codigo: string
  full_tanks_loaded: number
  empty_tanks_returned: number
  blocked: boolean
  blocked_reason: string | null
}

export interface ReconcileResult {
  product_codigo: string
  expected_full: number
  informed_full: number
  divergence_full: number
  expected_empty: number
  informed_empty: number
  divergence_empty: number
  blocked: boolean
}

export interface DispatchRecommendation {
  driver_id: string
  driver_name: string
  score: number
  distance_km: number
  explanation: string[]
  capacity_fit: Record<string, { product: string; needed: number; available: number; fits: boolean }>
}

export interface DispatchSuggestionResponse {
  success: boolean
  error?: string
  recommendations: DispatchRecommendation[]
  rejected: { driver_id: string; driver_name: string; reason: string; details: string }[]
}

export const driverStockApi = {
  getStock: (driverId: string) =>
    apiClient.get(`/delivery/drivers/${driverId}/stock`),
  load: (driverId: string, product_codigo: string, quantity: number) =>
    apiClient.post(`/delivery/drivers/${driverId}/stock/load`, { driver_id: driverId, product_codigo, quantity }),
  damage: (driverId: string, product_codigo: string, quantity: number, reason: string) =>
    apiClient.post(`/delivery/drivers/${driverId}/stock/damage`, { driver_id: driverId, product_codigo, quantity, reason }),
  reconcile: (driverId: string, counts: Record<string, number>, empty_returned: Record<string, number> = {}) =>
    apiClient.post(`/delivery/drivers/${driverId}/stock/reconcile`, { driver_id: driverId, counts, empty_returned }),
  unblock: (driverId: string) =>
    apiClient.post(`/delivery/drivers/${driverId}/stock/unblock`),
  suggest: (deliveryId: string) =>
    apiClient.post('/delivery/dispatch/suggest', { delivery_id: deliveryId }),
}

export function useDriverStock(driverId: string | null) {
  return useQuery({
    queryKey: ['driver-stock', driverId],
    queryFn: async () => {
      const { data } = await driverStockApi.getStock(driverId!)
      return (data?.stock ?? []) as DriverStockRow[]
    },
    enabled: !!driverId,
  })
}

export function useInvalidateDriverStock() {
  const queryClient = useQueryClient()
  return (driverId?: string) => {
    queryClient.invalidateQueries({ queryKey: ['driver-stock', driverId] })
    queryClient.invalidateQueries({ queryKey: ['driver-stock'] })
  }
}
