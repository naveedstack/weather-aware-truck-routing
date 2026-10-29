import { fireEvent, render, screen } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'
import { heatmapHours } from '../testing/fixtures'
import { HeatmapSlider } from './HeatmapSlider'

// The tests run in America/Chicago (see vite.config.ts): 20:00 UTC is 3 PM CDT.
const HOURS = heatmapHours('2026-10-24T20:00:00Z')

function slider(): HTMLInputElement {
  return screen.getByRole('slider', { name: 'Weather heatmap' })
}

describe('HeatmapSlider', () => {
  it('covers 0 to 48 hours, with the hour shown in words', () => {
    render(<HeatmapSlider hours={HOURS} departure="2026-10-24T20:00:00Z" hour={0} onChange={vi.fn()} />)

    expect([slider().min, slider().max, slider().step]).toEqual(['0', '48', '1'])
    expect(screen.getByText(/^Sat, Oct 24, 3:00\sPM CDT$/)).toBeTruthy()
    expect(screen.getByText('at departure')).toBeTruthy()
    expect(slider().getAttribute('aria-valuetext')).toMatch(/^Sat, Oct 24, 3:00\sPM CDT, at departure$/)
  })

  it('counts from the real departure, not from the forecast hour nearest it', () => {
    // A 2:40 PM departure: hour 0 is 3 PM, 20 minutes later.
    const view = render(<HeatmapSlider hours={HOURS} departure="2026-10-24T19:40:00Z" hour={0} onChange={vi.fn()} />)
    expect(screen.getByText('20 min after departure')).toBeTruthy()

    view.rerender(<HeatmapSlider hours={HOURS} departure="2026-10-24T19:40:00Z" hour={30} onChange={vi.fn()} />)
    expect(screen.getByText(/^Sun, Oct 25, 9:00\sPM CDT$/)).toBeTruthy() // 02:00 UTC on Oct 26
    expect(screen.getByText('30 h 20 min after departure')).toBeTruthy()

    view.rerender(<HeatmapSlider hours={HOURS} departure="2026-10-24T20:25:00Z" hour={0} onChange={vi.fn()} />)
    expect(screen.getByText('25 min before departure')).toBeTruthy()
  })

  it('reports the hour chosen', () => {
    // jsdom doesn't move range inputs with the arrow keys; browsers do, and that is checked in Chrome.
    const onChange = vi.fn()
    render(<HeatmapSlider hours={HOURS} departure="2026-10-24T20:00:00Z" hour={5} onChange={onChange} />)

    fireEvent.change(slider(), { target: { value: '24' } })

    expect(onChange).toHaveBeenCalledExactlyOnceWith(24)
  })

  it('puts each tick at its hour along the track', () => {
    const { container } = render(<HeatmapSlider hours={HOURS} departure="2026-10-24T20:00:00Z" hour={0} onChange={vi.fn()} />)

    const ticks = [...container.querySelectorAll<HTMLElement>('.heatmap-ticks span')]
    expect(ticks.map((tick) => tick.textContent)).toEqual(['0 h', '+12 h', '+24 h', '+36 h', '+48 h'])
    expect(ticks.map((tick) => tick.style.getPropertyValue('--at'))).toEqual(['0', '0.25', '0.5', '0.75', '1'])
  })
})
