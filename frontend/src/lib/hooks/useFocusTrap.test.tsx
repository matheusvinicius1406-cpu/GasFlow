import { render, fireEvent, screen, act } from '@testing-library/react'
import { describe, it, expect } from 'vitest'
import { useRef } from 'react'
import { useFocusTrap } from './useFocusTrap'

function flushFrame(): Promise<void> {
  // jsdom dispara requestAnimationFrame ~16ms depois — esperar além disso.
  return act(async () => {
    await new Promise((resolve) => setTimeout(resolve, 32))
  })
}

function TrapHarness({
  active,
  focusContainer = false,
  withTrigger = true,
}: {
  active: boolean
  focusContainer?: boolean
  withTrigger?: boolean
}) {
  const ref = useRef<HTMLDivElement>(null)
  useFocusTrap(ref, active, { focusContainer })

  return (
    <div>
      {withTrigger && <button>Gatilho externo</button>}
      <div ref={ref} data-testid="trap" tabIndex={-1}>
        <button>Primeiro</button>
        <button>Meio</button>
        <button>Último</button>
      </div>
    </div>
  )
}

describe('useFocusTrap', () => {
  it('moves focus to the first focusable element when activated', async () => {
    render(<TrapHarness active />)
    await flushFrame()
    expect(screen.getByText('Primeiro')).toHaveFocus()
  })

  it('focuses the container itself with focusContainer: true', async () => {
    render(<TrapHarness active focusContainer />)
    await flushFrame()
    expect(screen.getByTestId('trap')).toHaveFocus()
  })

  it('wraps Tab from the last element back to the first', async () => {
    render(<TrapHarness active />)
    await flushFrame()

    screen.getByText('Último').focus()
    fireEvent.keyDown(document, { key: 'Tab' })
    expect(screen.getByText('Primeiro')).toHaveFocus()
  })

  it('wraps Shift+Tab from the first element back to the last', async () => {
    render(<TrapHarness active />)
    await flushFrame()

    screen.getByText('Primeiro').focus()
    fireEvent.keyDown(document, { key: 'Tab', shiftKey: true })
    expect(screen.getByText('Último')).toHaveFocus()
  })

  it('moves forward with Tab from the container (focusContainer mode)', async () => {
    render(<TrapHarness active focusContainer />)
    await flushFrame()

    const trap = screen.getByTestId('trap')
    trap.focus()
    fireEvent.keyDown(document, { key: 'Tab' })
    expect(screen.getByText('Primeiro')).toHaveFocus()
  })

  it('restores focus to the previously focused element on deactivation', async () => {
    const { rerender } = render(<TrapHarness active />)
    await flushFrame()

    const trigger = screen.getByText('Gatilho externo')
    trigger.focus()

    rerender(<TrapHarness active={false} />)
    expect(trigger).toHaveFocus()
  })
})
