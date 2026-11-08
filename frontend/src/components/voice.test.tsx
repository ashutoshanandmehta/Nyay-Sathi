import { act, cleanup, fireEvent, render, screen } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

const voice = vi.hoisted(() => ({
  prewarm: vi.fn(async () => null),
  stop: vi.fn(async () => 'Police stopped my brother near Patna'),
  cancel: vi.fn(),
  handlers: null as null | { onText: (f: string, p: string) => void; onState?: (s: string) => void },
  start: vi.fn(),
}))
vi.mock('../voice', () => ({
  prewarm: voice.prewarm,
  startLiveTranscription: voice.start,
}))
import Composer, { HOLD_MS } from './Composer'

const mic = () => screen.getByRole('button', { name: 'Hold to talk, or hold Space' })
const box = () => screen.getByLabelText('Message') as HTMLTextAreaElement
const flush = () => act(async () => { await Promise.resolve(); await Promise.resolve() })

function renderComposer(initial = '') {
  const onSend = vi.fn(async () => true)
  render(<Composer disabled={false} initial={initial} onSend={onSend} onUpload={() => {}} />)
  return onSend
}

beforeEach(() => {
  vi.useFakeTimers()
  Object.values(voice).forEach(v => typeof v === 'function' && 'mockClear' in v && v.mockClear())
  voice.start.mockImplementation(async (handlers: typeof voice.handlers) => {
    voice.handlers = handlers
    handlers?.onState?.('listening')
    return { stop: voice.stop, cancel: voice.cancel }
  })
  vi.stubGlobal('requestAnimationFrame', (cb: FrameRequestCallback) => { cb(0); return 1 })
})
afterEach(() => { cleanup(); vi.useRealTimers(); vi.unstubAllGlobals() })

describe('hold to talk', () => {
  it('ignores a quick tap: nothing starts, nothing is spent', async () => {
    renderComposer()
    fireEvent.pointerDown(mic(), { pointerId: 1 })
    act(() => { vi.advanceTimersByTime(HOLD_MS - 50) })
    fireEvent.pointerUp(mic(), { pointerId: 1 })
    act(() => { vi.advanceTimersByTime(500) })
    expect(voice.start).not.toHaveBeenCalled()
    expect(screen.getByRole('status')).toHaveTextContent('Hold to talk, or hold Space')
  })

  it('records while held, shows live text, and fills the textbox on release', async () => {
    const onSend = renderComposer('Earlier note')
    fireEvent.pointerDown(mic(), { pointerId: 1 })
    act(() => { vi.advanceTimersByTime(HOLD_MS) })
    await flush()
    expect(voice.start).toHaveBeenCalledOnce()
    act(() => voice.handlers!.onText('Police stopped', 'my brother'))
    expect(screen.getByText('Police stopped')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Send message' })).toBeDisabled()

    fireEvent.pointerUp(mic(), { pointerId: 1 })
    await flush(); await flush()
    expect(voice.stop).toHaveBeenCalledOnce()
    expect(box().value).toBe('Earlier note\nPolice stopped my brother near Patna')
    expect(onSend).not.toHaveBeenCalled() // the user still presses Send
    expect(screen.getByRole('button', { name: 'Send message' })).toBeEnabled()
  })

  it('Space talks when nothing is focused but types a space in the textbox', async () => {
    renderComposer()
    box().focus()
    fireEvent.keyDown(box(), { code: 'Space', key: ' ' })
    act(() => { vi.advanceTimersByTime(HOLD_MS + 50) })
    expect(voice.start).not.toHaveBeenCalled()

    box().blur()
    fireEvent.keyDown(document.body, { code: 'Space', key: ' ' })
    fireEvent.keyDown(document.body, { code: 'Space', key: ' ', repeat: true })
    act(() => { vi.advanceTimersByTime(HOLD_MS) })
    await flush()
    expect(voice.start).toHaveBeenCalledOnce()
    fireEvent.keyUp(document.body, { code: 'Space', key: ' ' })
    await flush(); await flush()
    expect(voice.stop).toHaveBeenCalledOnce()
    expect(box().value).toBe('Police stopped my brother near Patna')
  })

  it('Esc discards, and leaving the window finishes and keeps the text', async () => {
    renderComposer()
    fireEvent.pointerDown(mic(), { pointerId: 1 })
    act(() => { vi.advanceTimersByTime(HOLD_MS) })
    await flush()
    fireEvent.keyDown(window, { key: 'Escape' })
    await flush()
    expect(voice.cancel).toHaveBeenCalledOnce()
    expect(voice.stop).not.toHaveBeenCalled()
    expect(box().value).toBe('')

    fireEvent.pointerDown(mic(), { pointerId: 2 })
    act(() => { vi.advanceTimersByTime(HOLD_MS) })
    await flush()
    fireEvent.blur(window)
    await flush(); await flush()
    expect(voice.stop).toHaveBeenCalledOnce()
    expect(box().value).toBe('Police stopped my brother near Patna')
  })
})
