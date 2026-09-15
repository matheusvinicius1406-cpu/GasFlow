import { useCallback, useRef } from 'react'

/**
 * Notification sound for incoming WhatsApp messages.
 *
 * Uses the Web Audio API against /notify.wav (a soft two-tone ding served
 * from public/). Browsers block audio until the first user gesture — we
 * retry with a synthesized beep fallback and keep track of play failures so
 * the first click anywhere in the app unlocks playback (standard autoplay
 * policy workaround).
 *
 * Rate-limited: at most one sound per second (batched message bursts don't
 * turn into a machine-gun).
 */
const SOUND_PATH = '/notify.wav'
const MIN_INTERVAL_MS = 1000

export function useNotifySound() {
  const lastPlayedRef = useRef(0)
  const audioCtxRef = useRef<AudioContext | null>(null)
  const unlockedRef = useRef(false)

  const ensureContext = useCallback((): AudioContext | null => {
    if (typeof window === 'undefined') return null
    if (!audioCtxRef.current) {
      const Ctx = window.AudioContext ?? (window as unknown as { webkitAudioContext?: typeof AudioContext }).webkitAudioContext
      if (!Ctx) return null
      audioCtxRef.current = new Ctx()
    }
    if (audioCtxRef.current.state === 'suspended') {
      void audioCtxRef.current.resume()
    }
    return audioCtxRef.current
  }, [])

  /** Synthesized fallback ding (same two-tone shape as the wav). */
  const playSynth = useCallback(() => {
    const ctx = ensureContext()
    if (!ctx) return
    const now = ctx.currentTime
    const notes: Array<[number, number, number]> = [
      [1318.51, 0.0, 0.09], // E6
      [1046.5, 0.09, 0.16], // C6
    ]
    for (const [freq, start, dur] of notes) {
      const osc = ctx.createOscillator()
      const gain = ctx.createGain()
      osc.type = 'sine'
      osc.frequency.value = freq
      gain.gain.setValueAtTime(0.0001, now + start)
      gain.gain.exponentialRampToValueAtTime(0.18, now + start + 0.012)
      gain.gain.exponentialRampToValueAtTime(0.0001, now + start + dur)
      osc.connect(gain).connect(ctx.destination)
      osc.start(now + start)
      osc.stop(now + start + dur + 0.02)
    }
  }, [ensureContext])

  /** Play the notification sound (rate-limited). Safe to call on any event. */
  const play = useCallback(() => {
    const now = Date.now()
    if (now - lastPlayedRef.current < MIN_INTERVAL_MS) return
    lastPlayedRef.current = now

    // Web Audio unlock: resume + fallback synth if the fetch/autoplay path fails.
    const ctx = ensureContext()
    try {
      const audio = new Audio(SOUND_PATH)
      audio.volume = 0.6
      audio.play().catch(() => {
        // Autoplay blocked or file missing — synth fallback.
        unlockedRef.current = false
        playSynth()
      })
    } catch {
      playSynth()
    }
    if (ctx?.state === 'running') unlockedRef.current = true
  }, [ensureContext, playSynth])

  /** Call once on the first user interaction to unlock audio autoplay. */
  const unlock = useCallback(() => {
    const ctx = ensureContext()
    if (ctx && ctx.state === 'suspended') void ctx.resume()
  }, [ensureContext])

  return { play, unlock }
}
