import { useQueryClient } from '@tanstack/react-query'
import { useRealtime } from '@/lib/hooks/useRealtime'
import { isRelevantEvent, realtimeQueryKeys } from '@/lib/realtime'

const TOKEN_KEY = 'gasflow_token'

/**
 * Mounted once inside DashboardLayout. Opens the tenant WebSocket channel
 * with the operator token and invalidates React Query caches when the
 * backend publishes delivery and driver lifecycle events — so Deliveries
 * and the Dashboard react within seconds to driver/assignment changes instead
 * of waiting for the next poll/refetch.
 *
 * Renders nothing.
 */
export function RealtimeBridge() {
  const queryClient = useQueryClient()

  useRealtime({
    token: typeof window !== 'undefined' ? window.localStorage.getItem(TOKEN_KEY) : null,
    onEvent: (message) => {
      if (!isRelevantEvent(message) || !message.event?.type) return
      const keys = realtimeQueryKeys(message.event.type)
      for (const key of keys) {
        void queryClient.invalidateQueries({ queryKey: key })
      }
    },
  })

  return null
}
