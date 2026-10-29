import { describe, expect, it, vi } from 'vitest'
import { makeCheckpoint, makeRoute } from '../testing/fixtures'
import { checkpointPopup, checkpointTip, checkpointTitle, checkpointsPopup, heatmapTip } from './popup'

/** The popup's rows as "term: value" text. */
function rows(popup: HTMLElement): Record<string, string> {
  const terms = [...popup.querySelectorAll('dt')]
  return Object.fromEntries(terms.map((term) => [term.textContent, term.nextElementSibling?.textContent ?? '']))
}

describe('checkpointTitle', () => {
  it('names the start, the destination and the checkpoints between', () => {
    expect(checkpointTitle('A', 0, 5)).toBe('Route A · start')
    expect(checkpointTitle('A', 2, 5)).toBe('Route A · checkpoint 2')
    expect(checkpointTitle('A', 4, 5)).toBe('Route A · destination')
  })
})

describe('checkpointPopup', () => {
  it("shows the checkpoint's weather, each value with its level", () => {
    const route = makeRoute({
      id: 'B',
      checkpoints: [
        makeCheckpoint(),
        makeCheckpoint({
          mile: 395.2,
          covers_mi: 25,
          eta: '2026-10-25T02:10:00Z',
          forecast_hour: '2026-10-25T02:00:00Z',
          wind_mph: 38.2,
          gust_mph: 51.6,
          rain_in_per_hr: 0.12,
          snow_in_per_hr: 0,
          risk: 2,
          wind_risk: 2,
          rain_risk: 1,
          snow_risk: 0,
        }),
        makeCheckpoint(),
      ],
    })

    const popup = checkpointPopup(route, 1)

    expect(popup.querySelector('.popup-title')?.textContent).toBe('Route B · checkpoint 1')
    expect(popup.querySelector('.popup-risk')?.textContent).toBe('High')
    expect(popup.querySelector('.popup-subtitle')?.textContent).toBe('Mile 395.2 · stands for 25.0 mi of road')
    const values = rows(popup)
    expect(values.ETA).toMatch(/^Sat, Oct 24, 9:10\sPM CDT$/)
    expect(values['Forecast for']).toMatch(/^Sat, 9:00\sPM CDT$/)
    expect(values.Wind).toBe('38.2 mph High')
    expect(values.Gusts).toBe('51.6 mph (info only)')
    expect(values.Rain).toBe('0.120 in/hr Moderate')
    expect(values.Snow).toBe('0.000 in/hr Low')
    expect(popup.querySelector('.popup-note')).toBeNull()
  })

  it('explains a load rule', () => {
    const rule = 'Wind of 45 up to 55 mph with a load over 30,000 lb is No Travel.'
    const route = makeRoute({ checkpoints: [makeCheckpoint({ wind_mph: 47, risk: 4, wind_risk: 4, load_rule: rule })] })

    const popup = checkpointPopup(route, 0)

    expect(popup.querySelector('.popup-note')?.textContent).toBe(rule)
    expect(rows(popup).Wind).toBe('47.0 mph No Travel')
  })

  it('says "No data" when the forecast is missing', () => {
    const missing = { wind_mph: null, gust_mph: null, rain_in_per_hr: null, snow_in_per_hr: null }
    const levels = { risk: null, wind_risk: null, rain_risk: null, snow_risk: null }
    const route = makeRoute({ checkpoints: [makeCheckpoint({ ...missing, ...levels })] })

    const popup = checkpointPopup(route, 0)

    expect(popup.querySelector('.popup-risk')?.textContent).toBe('No data')
    expect(rows(popup)).toMatchObject({ Wind: 'No data', Gusts: 'No data', Rain: 'No data', Snow: 'No data' })
    expect(popup.querySelector('.popup-note')?.textContent).toBe('No forecast is available for this place and time.')
  })

  it('explains a checkpoint with part of its forecast missing', () => {
    const partial = { wind_mph: 5, rain_in_per_hr: null, risk: null, wind_risk: 0, rain_risk: null } as const
    const route = makeRoute({ checkpoints: [makeCheckpoint(partial)] })

    const popup = checkpointPopup(route, 0)

    expect(rows(popup)).toMatchObject({ Wind: '5.0 mph Low', Rain: 'No data', Snow: '0.000 in/hr Low' })
    expect(popup.querySelector('.popup-note')?.textContent).toBe(
      'Part of the forecast is missing, so this checkpoint has no overall level.',
    )
  })

  it('shows every route with a checkpoint at the clicked spot, in the order given', () => {
    const a = makeRoute({ id: 'A', checkpoints: [makeCheckpoint(), makeCheckpoint({ risk: 3, wind_risk: 3 })] })
    const b = makeRoute({ id: 'B', checkpoints: [makeCheckpoint(), makeCheckpoint({ risk: 0 })] })

    const popup = checkpointsPopup(
      [
        { route: b, checkpointIndex: 1 },
        { route: a, checkpointIndex: 1 },
      ],
      () => {},
    )

    const titles = [...popup.querySelectorAll('.popup-title')].map((title) => title.textContent)
    expect(titles).toEqual(['Route B · destination', 'Route A · destination'])
    expect([...popup.querySelectorAll('.popup-risk')].map((badge) => badge.textContent)).toEqual(['Low', 'Severe'])
  })

  it('closes with its button, and keeps focus in the map when its text is clicked', () => {
    const onClose = vi.fn()
    const popup = checkpointsPopup([{ route: makeRoute(), checkpointIndex: 0 }], onClose)

    const close = popup.querySelector<HTMLButtonElement>('button.popup-close')
    expect(close?.getAttribute('aria-label')).toBe('Close')
    close?.click()

    expect(onClose).toHaveBeenCalledOnce()
    expect(popup.tabIndex).toBe(-1) // focusable, so Escape (handled by the map) still reaches it
  })

  it('shows text as text, never as HTML', () => {
    const route = makeRoute({ id: '<img src=x onerror=alert(1)>', checkpoints: [makeCheckpoint()] })

    const popup = checkpointPopup(route, 0)

    expect(popup.querySelector('img')).toBeNull()
    expect(popup.querySelector('.popup-title')?.textContent).toContain('<img')
  })
})

describe('checkpointTip', () => {
  const tip = (overrides = {}) =>
    checkpointTip(makeRoute({ id: 'A', checkpoints: [makeCheckpoint(overrides)] }), 0)

  it('summarises the checkpoint: which one, its level, its ETA and the condition behind it', () => {
    const node = tip({
      eta: '2026-10-25T02:10:00Z',
      wind_mph: 38.2, rain_in_per_hr: 0.12, snow_in_per_hr: 0,
      risk: 2, wind_risk: 2, rain_risk: 1, snow_risk: 0,
    })

    expect(node.querySelector('.tip-title')?.textContent).toBe('Route A · start')
    expect(node.querySelector('.tip-risk')?.textContent).toBe('High')
    expect(node.querySelector('.tip-eta')?.textContent).toMatch(/9:10\sPM CDT$/)
    expect(node.querySelector('.tip-lead')?.textContent).toBe('Wind 38.2 mph') // the level's cause
    expect(node.querySelector('.tip-hint')?.textContent).toBe('Click for details')
  })

  it('names rain when rain is the worst condition', () => {
    const node = tip({ wind_mph: 5, rain_in_per_hr: 0.6, risk: 3, wind_risk: 0, rain_risk: 3, snow_risk: 0 })

    expect(node.querySelector('.tip-lead')?.textContent).toBe('Rain 0.600 in/hr')
  })

  it('leaves the cause out when there is no overall level', () => {
    const node = tip({ wind_mph: null, risk: null, wind_risk: null, rain_risk: null, snow_risk: null })

    expect(node.querySelector('.tip-risk')?.textContent).toBe('No data')
    expect(node.querySelector('.tip-lead')).toBeNull()
  })
})

describe('heatmapTip', () => {
  it('says how bad a cell is, when, and which condition put it there, with the reading', () => {
    const node = heatmapTip(1, 'wind', 27.4, '2026-10-25T02:00:00Z')

    expect(node.querySelector('.tip-title')?.textContent).toBe('Weather here')
    expect(node.querySelector('.tip-risk')?.textContent).toBe('Moderate')
    expect(node.querySelector('.tip-eta')?.textContent).toMatch(/9:00\sPM CDT$/)
    expect(node.querySelector('.tip-lead')?.textContent).toBe('Wind 27.4 mph')
    expect(node.querySelector('.tip-hint')?.textContent).toBe("At the slider's hour, not the truck's ETA")
  })

  it('gives rain and snow their own unit', () => {
    expect(heatmapTip(2, 'rain', 0.3, '2026-10-25T02:00:00Z').querySelector('.tip-lead')?.textContent).toBe(
      'Rain 0.300 in/hr',
    )
    expect(heatmapTip(3, 'snow', 2.5, '2026-10-25T02:00:00Z').querySelector('.tip-lead')?.textContent).toBe(
      'Snow 2.500 in/hr',
    )
  })

  it('names the condition without a reading when the API sent none', () => {
    const node = heatmapTip(1, 'wind', null, '2026-10-25T02:00:00Z')

    expect(node.querySelector('.tip-lead')?.textContent).toBe('Set by the wind')
  })

  it('says so when the cell has no forecast', () => {
    const node = heatmapTip(null, null, null, '2026-10-25T02:00:00Z')

    expect(node.querySelector('.tip-risk')?.textContent).toBe('No data')
    expect(node.querySelector('.tip-lead')?.textContent).toBe('No forecast for this place and hour')
  })
})
