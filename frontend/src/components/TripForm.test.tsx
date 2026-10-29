import { fireEvent, render, screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { TripForm } from './TripForm'

// Only Date is faked, so user-event's timers still run. The tests run in America/Chicago.
beforeEach(() => {
  vi.useFakeTimers({ toFake: ['Date'] })
  vi.setSystemTime(new Date('2026-10-24T14:20:00Z')) // Sat 9:20 AM CDT
})

afterEach(() => {
  vi.useRealTimers()
  vi.unstubAllGlobals()
})

function input(label: string): HTMLInputElement {
  return screen.getByLabelText(label)
}

/** The label of the chosen interval. */
function checkedInterval(): string | undefined {
  const checked = screen.getAllByRole<HTMLInputElement>('radio').find((radio) => radio.checked)
  return checked?.closest('label')?.textContent ?? undefined
}

/** The text a screen reader reads after the field's name. */
function description(element: HTMLElement): string {
  const ids = element.getAttribute('aria-describedby')?.split(' ') ?? []
  return ids.map((id) => document.getElementById(id)?.textContent).join(' ')
}

describe('TripForm', () => {
  it('starts at the next full hour and allows departures up to the end of the forecast', () => {
    render(<TripForm busy={false} errors={{}} onSubmit={vi.fn()} />)

    expect(input('Departure').value).toBe('2026-10-24T10:00')
    expect(input('Departure').min).toBe('2026-10-24T09:05') // 15 minutes of grace, like the server
    expect(input('Departure').max).toBe('2026-11-08T17:00') // Nov 8, 23:00 UTC
    expect(description(input('Departure'))).toBe('Your time zone: America/Chicago')
    expect(input('Load (lb)').value).toBe('35000')
    expect(input('Load (lb)').step).toBe('1') // whole pounds
    expect(checkedInterval()).toBe('25 mi')
  })

  it('offers the intervals as one group with a single choice', async () => {
    const user = userEvent.setup()
    render(<TripForm busy={false} errors={{}} onSubmit={vi.fn()} />)

    const group = screen.getByRole('radiogroup', { name: 'Checkpoints every' })
    expect(within(group).getAllByRole('radio').map((radio) => radio.getAttribute('value'))).toEqual(['10', '25', '50'])
    await user.click(screen.getByRole('radio', { name: '50 mi' }))

    expect(checkedInterval()).toBe('50 mi')
  })

  it('starts from the given trip', () => {
    const trip = { origin: 'Dallas, TX', destination: 'Denver, CO', departure: '2026-10-25T14:00:00.000Z', load_lb: 42000, interval_mi: 10 as const }
    render(<TripForm initial={trip} busy={false} errors={{}} onSubmit={vi.fn()} />)

    expect(input('From').value).toBe('Dallas, TX')
    expect(input('To').value).toBe('Denver, CO')
    expect(input('Departure').value).toBe('2026-10-25T09:00') // 14:00 UTC in Chicago (CDT)
    expect(input('Load (lb)').value).toBe('42000')
    expect(checkedInterval()).toBe('10 mi')
  })

  it('offers Cancel only when there is a trip to go back to', async () => {
    const user = userEvent.setup()
    const onCancel = vi.fn()
    const view = render(<TripForm busy={false} errors={{}} onSubmit={vi.fn()} />)
    expect(screen.queryByRole('button', { name: 'Cancel' })).toBeNull()

    view.rerender(<TripForm busy={false} errors={{}} onSubmit={vi.fn()} onCancel={onCancel} />)
    await user.click(screen.getByRole('button', { name: 'Cancel' }))

    expect(onCancel).toHaveBeenCalledOnce()
  })

  it('moves the departure limits forward when the field gets focus', () => {
    render(<TripForm busy={false} errors={{}} onSubmit={vi.fn()} />)

    vi.setSystemTime(new Date('2026-10-25T05:30:00Z')) // the page stayed open past midnight UTC
    fireEvent.focus(input('Departure'))

    expect(input('Departure').min).toBe('2026-10-25T00:15')
    expect(input('Departure').max).toBe('2026-11-09T17:00')
  })

  it('sends the trip, with the local departure as a UTC time', async () => {
    const user = userEvent.setup()
    const onSubmit = vi.fn()
    render(<TripForm busy={false} errors={{}} onSubmit={onSubmit} />)

    await user.type(input('From'), '  Dallas, TX ')
    await user.type(input('To'), 'Denver, CO')
    fireEvent.change(input('Departure'), { target: { value: '2026-10-25T09:00' } })
    await user.clear(input('Load (lb)'))
    await user.type(input('Load (lb)'), '42000')
    await user.click(screen.getByRole('radio', { name: '10 mi' }))
    await user.click(screen.getByRole('button', { name: 'Plan trip' }))

    expect(onSubmit).toHaveBeenCalledExactlyOnceWith({
      origin: 'Dallas, TX',
      destination: 'Denver, CO',
      departure: '2026-10-25T14:00:00.000Z',
      load_lb: 42000,
      interval_mi: 10,
    })
  })

  it('suggests cities as a place is typed, and fills in the one chosen', async () => {
    const places = { places: [{ name: 'Denver, CO' }, { name: 'Denver, NC' }] }
    const fetch = vi.fn(async (_url: string) => new Response(JSON.stringify(places), { headers: { 'Content-Type': 'application/json' } }))
    vi.stubGlobal('fetch', fetch)
    const user = userEvent.setup()
    render(<TripForm busy={false} errors={{}} onSubmit={vi.fn()} />)

    await user.type(input('To'), 'Denv')
    await user.click(await screen.findByRole('option', { name: 'Denver, CO' })) // after the pause in typing

    expect(input('To').value).toBe('Denver, CO')
    expect(document.activeElement).toBe(input('To'))
    expect(screen.queryByRole('listbox')).toBeNull()
    expect(fetch).toHaveBeenCalledOnce()
    expect(fetch.mock.calls[0][0]).toBe('/api/places/?q=Denv')
  })

  it("shows the server's message under the field it is about", () => {
    const message = "Couldn't find a place called “Dalas”."
    render(<TripForm busy={false} errors={{ origin: message }} onSubmit={vi.fn()} />)

    const origin = input('From')
    expect(origin.getAttribute('aria-invalid')).toBe('true')
    expect(description(origin)).toBe(message)
    expect(input('To').hasAttribute('aria-invalid')).toBe(false)
  })

  it('keeps the time zone hint with a departure error', () => {
    render(<TripForm busy={false} errors={{ departure: 'Departure is in the past.' }} onSubmit={vi.fn()} />)

    expect(description(input('Departure'))).toBe('Your time zone: America/Chicago Departure is in the past.')
  })

  it('disables the button and shows a spinner while a plan loads', () => {
    render(<TripForm busy errors={{}} onSubmit={vi.fn()} />)

    const button = screen.getByRole('button', { name: 'Planning…' }) as HTMLButtonElement
    expect(button.disabled).toBe(true)
    expect(button.querySelector('.spinner')).not.toBeNull()
  })
})
