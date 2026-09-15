import { useEffect } from 'react'
import { useQueryClient } from '@tanstack/react-query'
import { useRealtime } from '@/lib/hooks/useRealtime'
import { useNotifySound } from '@/lib/hooks/useNotifySound'
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
  const { play, unlock } = useNotifySound()

  // Desbloqueia o áudio no primeiro clique (política de autoplay dos browsers).
  useEffect(() => {
    const handler = () => unlock()
    window.addEventListener('pointerdown', handler, { once: true })
    window.addEventListener('keydown', handler, { once: true })
    return () => {
      window.removeEventListener('pointerdown', handler)
      window.removeEventListener('keydown', handler)
    }
  }, [unlock])

  useRealtime({
    token: typeof window !== 'undefined' ? window.localStorage.getItem(TOKEN_KEY) : null,
    onEvent: (message) => {
      if (!isRelevantEvent(message) || !message.event?.type) return
      // Som de notificação para mensagens de clientes no WhatsApp.
      if (message.event.type === 'whatsapp.message_received') {
        play()
      }
      const keys = realtimeQueryKeys(message.event.type)
      for (const key of keys) {
        void queryClient.invalidateQueries({ queryKey: key })
      }
    },
  })

  return null
}
