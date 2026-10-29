// Small plans for tests, shaped like the API's JSON. Override only what a test cares about.

import type { Checkpoint, Plan, Route } from '../types'

const HOUR_MS = 3600 * 1000

/** The API's 49 heatmap hours (slider positions 0-48), from a departure's forecast hour. */
export function heatmapHours(first: string): string[] {
  return Array.from({ length: 49 }, (_, hour) =>
    new Date(Date.parse(first) + hour * HOUR_MS).toISOString().replace('.000Z', 'Z'),
  )
}

export function makeCheckpoint(overrides: Partial<Checkpoint> = {}): Checkpoint {
  return {
    mile: 0,
    lat: 32.7767,
    lon: -96.797,
    covers_mi: 12.5,
    eta: '2026-10-24T20:00:00Z',
    forecast_hour: '2026-10-24T20:00:00Z',
    wind_mph: 12.3,
    gust_mph: 21.4,
    rain_in_per_hr: 0,
    snow_in_per_hr: 0,
    risk: 0,
    wind_risk: 0,
    rain_risk: 0,
    snow_risk: 0,
    load_rule: null,
    ...overrides,
  }
}

export function makeRoute(overrides: Partial<Route> = {}): Route {
  return {
    id: 'A',
    via: false,
    recommended: true,
    unsafe: false,
    distance_mi: 790.4,
    travel_time_min: 712,
    arrival: '2026-10-25T07:52:00Z',
    average_risk: 0.13,
    miles: { no_travel: 0, severe: 0, high: 0, moderate: 100, low: 690.4, no_data: 0 },
    line: [
      [-96.797, 32.7767],
      [-101.8313, 35.222],
      [-104.9903, 39.7392],
    ],
    checkpoints: [
      makeCheckpoint(),
      makeCheckpoint({ mile: 395.2, lat: 35.222, lon: -101.8313, covers_mi: 25, eta: '2026-10-25T02:00:00Z' }),
      makeCheckpoint({ mile: 790.4, lat: 39.7392, lon: -104.9903, eta: '2026-10-25T07:52:00Z' }),
    ],
    ...overrides,
  }
}

export function makePlan(overrides: Partial<Plan> = {}): Plan {
  return {
    origin: { query: 'Dallas, TX', name: 'Dallas, TX', lat: 32.7767, lon: -96.797 },
    destination: { query: 'Denver, CO', name: 'Denver, CO', lat: 39.7392, lon: -104.9903 },
    departure: '2026-10-24T20:00:00Z',
    load_lb: 35000,
    interval_mi: 25,
    routes: [
      makeRoute(),
      makeRoute({
        id: 'B',
        recommended: false,
        distance_mi: 812.9,
        travel_time_min: 745,
        average_risk: 0.4,
        miles: { no_travel: 0, severe: 0, high: 25, moderate: 150, low: 637.9, no_data: 0 },
        line: [
          [-96.797, 32.7767],
          [-100.4, 37.1],
          [-104.9903, 39.7392],
        ],
      }),
    ],
    recommendation: { route_id: 'A', reason: 'Route A has the lowest average risk.', warnings: [] },
    notices: [],
    heatmap: {
      cell_size_deg: 0.5,
      hours: heatmapHours('2026-10-24T20:00:00Z'),
      cells: [
        {
          bounds: [-97, 32.5, -96.5, 33],
          levels: '0'.repeat(49),
          causes: 'w'.repeat(49),
          values: ','.repeat(48), // all Low, so no readings
        },
        {
          bounds: [-102, 35, -101.5, 35.5],
          levels: '0'.repeat(24) + '3'.repeat(10) + '-'.repeat(15),
          causes: 'w'.repeat(24) + 'r'.repeat(10) + '-'.repeat(15),
          // Severe for hours 24-33, so those ten carry the rain rate behind them.
          values: [...Array(24).fill(''), ...Array(10).fill('0.6'), ...Array(15).fill('')].join(','),
        },
      ],
    },
    weather_locations: 120,
    ...overrides,
  }
}
