import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, vi } from 'vitest'
import { TripBar } from './TripBar'

const TRIP = {
  origin: 'Dallas, TX',
  destination: 'Denver, CO',
  departure: '2026-10-24T20:00:00Z',
  load_lb: 35000,
  interval_mi: 25,
}

describe('TripBar', () => {
  it('names the trip, its departure with the date, the load and the interval', () => {
    render(<TripBar trip={TRIP} busy={false} onChange={vi.fn()} />)

    expect(screen.getByText('Dallas, TX → Denver, CO')).toBeTruthy()
    // The tests run in America/Chicago (see vite.config.ts).
    expect(screen.getByText(/^Departs Sat, Oct 24, 3:00\sPM CDT · 35,000 lb · checkpoints every 25 mi$/)).toBeTruthy()
  })

  it('opens the form again with "Change trip"', async () => {
    const user = userEvent.setup()
    const onChange = vi.fn()
    render(<TripBar trip={TRIP} busy={false} onChange={onChange} />)

    await user.click(screen.getByRole('button', { name: 'Change trip' }))

    expect(onChange).toHaveBeenCalledOnce()
  })

  it('shows progress instead of the button while the trip is planned', () => {
    render(<TripBar trip={TRIP} busy onChange={vi.fn()} />)

    expect(screen.getByText('Planning…')).toBeTruthy()
    expect(screen.queryByRole('button', { name: 'Change trip' })).toBeNull()
  })
})
