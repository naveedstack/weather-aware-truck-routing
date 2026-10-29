import { act, fireEvent, render, screen, within } from '@testing-library/react'
import { useState } from 'react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { looseText, SUGGEST_DELAY_MS } from '../places'
import { PlaceInput } from './PlaceInput'

// These tests control the clock, to check the pause before suggestions are asked for, so they use
// fireEvent: user-event waits on timers between steps, which a stopped clock never fires.
// TripForm.test.tsx goes through the same steps with user-event and the real clock.

// The server's stand-in: cities that start with the text, like TomTom's typeahead search, and for
// "Dallas, TX" nearby cities too, as TomTom gives.
const CITIES = ['Dallas, TX', 'Dallas, GA', 'Dalton, GA', 'Denver, CO']
const NEARBY: Record<string, string[]> = { 'dallas tx': ['Dallas, TX', 'Lake Dallas, TX', 'Irving, TX'] }

const mocks = vi.hoisted(() => ({ suggest: vi.fn<(text: string, signal?: AbortSignal) => Promise<string[]>>() }))
vi.mock('../api', () => ({ suggestPlaces: mocks.suggest }))

beforeEach(() => {
  vi.useFakeTimers()
  mocks.suggest.mockImplementation(async (text) => {
    const typed = looseText(text)
    return NEARBY[typed] ?? CITIES.filter((city) => looseText(city).startsWith(typed))
  })
})

afterEach(() => {
  vi.useRealTimers()
  mocks.suggest.mockReset()
})

function Field() {
  const [value, setValue] = useState('')
  return (
    <>
      <label htmlFor="origin">From</label>
      <PlaceInput id="origin" value={value} onChange={setValue} />
    </>
  )
}

function setup(): HTMLInputElement {
  render(<Field />)
  return screen.getByRole('combobox', { name: 'From' }) as HTMLInputElement
}

/** Types at the end of the field, one character at a time, with no pause in between. */
function type(field: HTMLInputElement, text: string) {
  for (const character of text) fireEvent.change(field, { target: { value: field.value + character } })
}

function backspace(field: HTMLInputElement) {
  fireEvent.change(field, { target: { value: field.value.slice(0, -1) } })
}

/** Presses a key in the field. True when the browser may go on with the key's usual action, which
 * for Enter is sending the form. */
function press(field: HTMLInputElement, key: string, init: KeyboardEventInit = {}): boolean {
  return fireEvent.keyDown(field, { key, ...init })
}

/** Lets time pass with no typing, and the server's answers arrive. */
async function pause(ms = SUGGEST_DELAY_MS) {
  await act(() => vi.advanceTimersByTimeAsync(ms))
}

/** The suggestions listed under the field. */
function listed(): string[] {
  return screen.queryAllByRole('option').map((option) => option.textContent ?? '')
}

function activeOption(field: HTMLInputElement): string | undefined {
  const id = field.getAttribute('aria-activedescendant')
  return id ? (document.getElementById(id)?.textContent ?? undefined) : undefined
}

describe('PlaceInput', () => {
  it('asks for suggestions once typing pauses for 300 ms, from three letters or digits', async () => {
    const field = setup()

    type(field, 'D a')
    await pause(1000)
    expect(mocks.suggest).not.toHaveBeenCalled() // two letters

    type(field, 'l')
    await pause(299)
    expect(mocks.suggest).not.toHaveBeenCalled()
    await pause(1)
    expect(mocks.suggest).toHaveBeenCalledExactlyOnceWith('D al', expect.any(AbortSignal))
  })

  it('asks once while the typing goes on, for the text typed by then', async () => {
    const field = setup()

    for (const character of 'Denver') {
      type(field, character)
      await pause(SUGGEST_DELAY_MS - 50)
    }
    expect(mocks.suggest).not.toHaveBeenCalled()
    await pause(50)

    expect(mocks.suggest).toHaveBeenCalledExactlyOnceWith('Denver', expect.any(AbortSignal))
  })

  it('lists the cities found as a listbox, with the typed part in bold', async () => {
    const field = setup()
    expect(field.getAttribute('aria-expanded')).toBe('false')

    type(field, 'dal')
    await pause()

    const list = screen.getByRole('listbox', { name: 'Suggestions' })
    expect(field.getAttribute('aria-controls')).toBe(list.id)
    expect(field.getAttribute('aria-expanded')).toBe('true')
    expect(listed()).toEqual(['Dallas, TX', 'Dallas, GA', 'Dalton, GA'])
    expect(within(list).getAllByRole('option')[0].querySelector('strong')?.textContent).toBe('Dal')
    expect(screen.getByRole('status').textContent).toBe('3 suggestions')
  })

  it('narrows the list while typing goes on, and lists only the city once it is typed in full', async () => {
    const field = setup()
    type(field, 'Dal')
    await pause()

    type(field, 'las')
    expect(listed()).toEqual(['Dallas, TX', 'Dallas, GA']) // at once, before the next answer
    type(field, ', tx')
    expect(listed()).toEqual(['Dallas, TX'])

    await pause() // the server suggests nearby cities for "Dallas, tx" too
    expect(mocks.suggest).toHaveBeenLastCalledWith('Dallas, tx', expect.any(AbortSignal))
    expect(listed()).toEqual(['Dallas, TX'])
    expect(screen.getByRole('status').textContent).toBe('1 suggestion')
  })

  it('keeps a place typed in full that it has no suggestion for, and leaves Enter to send the form', async () => {
    const field = setup()

    type(field, 'Dalhart, TX')
    await pause()

    expect(listed()).toEqual([])
    expect(press(field, 'Enter')).toBe(true)
    expect(field.value).toBe('Dalhart, TX')
  })

  it('fills the field in with the arrow keys and Enter, and keeps that Enter from sending the form', async () => {
    const field = setup()
    type(field, 'Dal')
    await pause()

    expect(press(field, 'ArrowDown')).toBe(false) // the caret stays where it is
    expect(activeOption(field)).toBe('Dallas, TX')
    expect(screen.getByRole('option', { name: 'Dallas, TX' }).getAttribute('aria-selected')).toBe('true')
    press(field, 'ArrowDown')
    press(field, 'ArrowDown')
    press(field, 'ArrowDown')
    expect(activeOption(field)).toBe('Dallas, TX') // round again
    press(field, 'ArrowUp')
    expect(activeOption(field)).toBe('Dalton, GA')
    expect(press(field, 'Enter')).toBe(false)

    expect(field.value).toBe('Dalton, GA')
    expect(listed()).toEqual([])
    expect(field.getAttribute('aria-expanded')).toBe('false')
    expect(field.hasAttribute('aria-activedescendant')).toBe(false)
    expect(press(field, 'Enter')).toBe(true) // the next Enter sends the form
    await pause(1000)
    expect(mocks.suggest).toHaveBeenCalledOnce() // choosing asks for nothing more
  })

  it('keeps the suggestion picked with the arrow keys when a later answer would arrive', async () => {
    const field = setup()
    type(field, 'Dal')
    await pause()

    type(field, 'l') // the list narrows at once, and "Dall" would be asked for after the pause
    await pause(150)
    press(field, 'ArrowDown')
    press(field, 'ArrowDown')
    await pause(1000)

    expect(activeOption(field)).toBe('Dallas, GA')
    expect(press(field, 'Enter')).toBe(false) // picks it, rather than sending the form with "Dall"
    expect(field.value).toBe('Dallas, GA')
    expect(mocks.suggest).toHaveBeenCalledOnce() // choosing from the list stopped the next question
  })

  it('leaves the keys alone while a character is being composed (IME)', async () => {
    const field = setup()
    type(field, 'Dal')
    await pause()
    press(field, 'ArrowDown')

    expect(press(field, 'Enter', { isComposing: true })).toBe(true)
    expect(field.value).toBe('Dal')
  })

  it('fills the field in with a click, without taking the focus from it', async () => {
    const field = setup()
    type(field, 'Dal')
    await pause()

    const option = screen.getByRole('option', { name: 'Dallas, GA' })
    expect(fireEvent.mouseDown(option)).toBe(false) // a press on the list keeps the focus in the field
    fireEvent.click(option)

    expect(field.value).toBe('Dallas, GA')
    expect(listed()).toEqual([])
  })

  it('closes with Escape, opens again with the arrow keys, and closes when the field is left', async () => {
    const field = setup()
    type(field, 'Dal')
    await pause()

    press(field, 'Escape')
    expect(listed()).toEqual([])
    expect(field.value).toBe('Dal') // the text stays
    press(field, 'ArrowDown')
    expect(listed()).toEqual(['Dallas, TX', 'Dallas, GA', 'Dalton, GA'])

    type(field, 'l')
    fireEvent.blur(field) // before the pause is over
    await pause(1000)
    expect(listed()).toEqual([])
    expect(mocks.suggest).toHaveBeenCalledOnce() // "Dall" was never asked for
  })

  it('keeps the list closed when Escape is pressed before the suggestions arrive', async () => {
    const field = setup()

    type(field, 'Dal')
    press(field, 'Escape')
    await pause(1000)

    expect(listed()).toEqual([])
    expect(mocks.suggest).not.toHaveBeenCalled() // the pause was cut short, so nothing was asked
  })

  it('lists the suggestions for the latest text when answers arrive out of order', async () => {
    const answers: ((names: string[]) => void)[] = []
    mocks.suggest.mockImplementation(() => new Promise((resolve) => answers.push(resolve)))
    const field = setup()

    type(field, 'Dal')
    await pause()
    type(field, 'l')
    await pause()
    expect(mocks.suggest.mock.calls[0][1]?.aborted).toBe(true) // "Dal" is cancelled by "Dall"
    await act(async () => answers[1](['Dallas, TX']))
    await act(async () => answers[0](['Dale, VA'])) // too late to be listed

    expect(listed()).toEqual(['Dallas, TX'])
  })

  it('asks nothing again for text it already has suggestions for', async () => {
    const field = setup()
    type(field, 'Dal')
    await pause()
    type(field, 'l')
    await pause()

    backspace(field)
    expect(listed()).toEqual(['Dallas, TX', 'Dallas, GA', 'Dalton, GA']) // at once
    await pause(1000)

    expect(mocks.suggest).toHaveBeenCalledTimes(2)
  })

  it('asks once for text that differs only in punctuation, even when typed before the answer', async () => {
    const answers: ((names: string[]) => void)[] = []
    mocks.suggest.mockImplementation(() => new Promise((resolve) => answers.push(resolve)))
    const field = setup()
    type(field, 'Dallas')
    await pause()

    type(field, ',') // "Dallas," is "Dallas" to the server, and its answer is still on its way
    await act(async () => answers[0](['Dallas, TX', 'Dallas, GA']))
    await pause(1000)

    expect(mocks.suggest).toHaveBeenCalledOnce()
    expect(listed()).toEqual(['Dallas, TX', 'Dallas, GA'])
  })

  it('hides the list below three letters or digits', async () => {
    const field = setup()
    type(field, 'Dal')
    await pause()

    backspace(field)

    expect(listed()).toEqual([])
    expect(field.getAttribute('aria-expanded')).toBe('false')
  })

  it('goes without suggestions when the server has none to give', async () => {
    mocks.suggest.mockRejectedValue(new Error("The server couldn't suggest places (error 502)."))
    const field = setup()

    type(field, 'Dal')
    await pause()
    type(field, 'las')

    expect(listed()).toEqual([])
    expect(field.value).toBe('Dallas')
  })
})
