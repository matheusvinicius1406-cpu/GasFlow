import { act, renderHook, waitFor } from '@testing-library/react'
import { describe, it, expect, vi, afterEach } from 'vitest'
import { INITIAL_UPDATE_STATE, useUpdaterState, type UpdateState } from './updater'

/** Substitui a ponte do Electron por uma dublê controlável. */
function stubUpdater(initial: UpdateState) {
  const listeners = new Set<(state: UpdateState) => void>()
  let unsubscribed = 0

  const api = {
    check: vi.fn(async () => ({ ok: true })),
    install: vi.fn(async () => ({ ok: true })),
    getState: vi.fn(async () => initial),
    onStateChange: vi.fn((cb: (state: UpdateState) => void) => {
      listeners.add(cb)
      return () => {
        unsubscribed += 1
        listeners.delete(cb)
      }
    }),
  }

  window.gasflowUpdater = api

  return {
    api,
    getUnsubscribed: () => unsubscribed,
    emit: (state: UpdateState) =>
      act(() => {
        listeners.forEach((cb) => cb(state))
      }),
  }
}

afterEach(() => {
  delete window.gasflowUpdater
})

describe('useUpdaterState', () => {
  it('fica em idle quando não há ponte (navegador/web)', () => {
    const { result } = renderHook(() => useUpdaterState())
    expect(result.current).toEqual(INITIAL_UPDATE_STATE)
  })

  it('lê o estado atual da ponte ao montar', async () => {
    const ready: UpdateState = { status: 'ready', version: '1.1.7', progress: 100, error: null }
    const { api } = stubUpdater(ready)

    const { result } = renderHook(() => useUpdaterState())

    await waitFor(() => expect(result.current).toEqual(ready))
    expect(api.getState).toHaveBeenCalledTimes(1)
  })

  it('acompanha as atualizações emitidas pelo processo main', async () => {
    const { api, emit } = stubUpdater(INITIAL_UPDATE_STATE)

    const { result } = renderHook(() => useUpdaterState())
    await waitFor(() => expect(api.onStateChange).toHaveBeenCalled())

    emit({ status: 'downloading', version: '1.1.7', progress: 42, error: null })
    expect(result.current.status).toBe('downloading')
    expect(result.current.progress).toBe(42)
  })

  it('cancela a assinatura ao desmontar', async () => {
    const { api, getUnsubscribed } = stubUpdater(INITIAL_UPDATE_STATE)

    const { unmount } = renderHook(() => useUpdaterState())
    await waitFor(() => expect(api.onStateChange).toHaveBeenCalled())

    unmount()
    expect(getUnsubscribed()).toBe(1)
  })
})
