import { describe, expect, it } from 'vitest'
import {
  formatDateTime,
  formatDuration,
  formatMiles,
  formatMph,
  formatNumber,
  formatPounds,
  formatRate,
  formatSpan,
  formatTime,
  fromDeparture,
  lastForecastHour,
  nextFullHour,
  toLocalInputValue,
} from './format'

// The tests run in America/Chicago (see vite.config.ts). `\s` also matches the narrow no-break space
// some ICU versions put before "PM".

describe('times', () => {
  it('shows a time with its weekday and time zone', () => {
    expect(formatTime('2026-10-24T20:00:00Z')).toMatch(/^Sat, 3:00\sPM CDT$/)
    expect(formatTime('2026-11-02T20:00:00Z')).toMatch(/^Mon, 2:00\sPM CST$/) // after DST ends
  })

  it('shows a date and time', () => {
    expect(formatDateTime('2026-10-24T20:00:00Z')).toMatch(/^Sat, Oct 24, 3:00\sPM CDT$/)
  })
})

describe('formatDuration', () => {
  it('shows hours and minutes', () => {
    expect(formatDuration(712)).toBe('11 h 52 min')
    expect(formatDuration(605)).toBe('10 h 5 min')
  })

  it('shows only minutes under an hour', () => {
    expect(formatDuration(45)).toBe('45 min')
  })

  it('rounds before splitting, so it never shows 60 minutes', () => {
    expect(formatDuration(119.6)).toBe('2 h 0 min')
  })
})

describe('spans of time', () => {
  it('writes hours and minutes, leaving out a zero part', () => {
    expect([formatSpan(60), formatSpan(80), formatSpan(40), formatSpan(0)]).toEqual(['1 h', '1 h 20 min', '40 min', '0 min'])
  })

  it('says how far a forecast hour is from the departure, either way', () => {
    expect(fromDeparture('2026-10-24T20:00:00Z', '2026-10-24T20:00:00Z')).toBe('at departure')
    expect(fromDeparture('2026-10-24T21:00:00Z', '2026-10-24T19:40:00Z')).toBe('1 h 20 min after departure')
    expect(fromDeparture('2026-10-24T20:00:00Z', '2026-10-24T20:25:00Z')).toBe('25 min before departure')
  })
})

describe('numbers', () => {
  it('keeps exactly the given decimals', () => {
    expect(formatNumber(1234.5, 1)).toBe('1,234.5')
    expect(formatNumber(2, 2)).toBe('2.00')
  })

  it('formats miles, speeds, rates and weights', () => {
    expect(formatMiles(882.7)).toBe('882.7 mi')
    expect(formatMiles(0)).toBe('0.0 mi')
    expect(formatMph(34.9)).toBe('34.9 mph')
    expect(formatRate(0.1)).toBe('0.100 in/hr')
    expect(formatRate(0.004)).toBe('0.004 in/hr')
    expect(formatPounds(35000)).toBe('35,000 lb')
  })

  it('says "No data" for a missing value', () => {
    expect(formatMph(null)).toBe('No data')
    expect(formatRate(null)).toBe('No data')
  })
})

describe('departure helpers', () => {
  it('writes the local value a datetime-local input uses', () => {
    expect(toLocalInputValue(new Date(2026, 9, 24, 9, 5))).toBe('2026-10-24T09:05')
  })

  it('finds the next full hour', () => {
    expect(nextFullHour(new Date(2026, 9, 24, 9, 5, 30))).toEqual(new Date(2026, 9, 24, 10, 0, 0))
    expect(nextFullHour(new Date(2026, 9, 24, 23, 40))).toEqual(new Date(2026, 9, 25, 0, 0, 0))
  })

  it('ends the departure window where the server does: 16 days from the start of the UTC day, minus an hour', () => {
    expect(lastForecastHour(new Date('2026-10-24T23:30:00Z')).toISOString()).toBe('2026-11-08T23:00:00.000Z')
    expect(lastForecastHour(new Date('2026-10-25T00:30:00Z')).toISOString()).toBe('2026-11-09T23:00:00.000Z')
  })
})
