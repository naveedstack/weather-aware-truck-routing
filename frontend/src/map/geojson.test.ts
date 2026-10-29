import { describe, expect, it } from 'vitest'
import { NO_DATA_STYLE, OTHER_ROUTE_COLORS, RISK_STYLES, SELECTED_ROUTE_COLOR } from '../risk'
import { makeCheckpoint, makePlan, makeRoute } from '../testing/fixtures'
import type { Plan } from '../types'
import {
  checkpointPoints,
  checkpointSortKey,
  distanceToLine,
  endpoints,
  labelPoint,
  type LngLat,
  bearingAlong,
  mileAtTime,
  planBounds,
  pointAlong,
  routeLabels,
  routeLines,
  truckMiles,
  truckPositions,
} from './geojson'

describe('routeLines', () => {
  it('gives each route a numeric id and its color, and draws the selected one blue and on top', () => {
    const plan = makePlan()

    const features = routeLines(plan, 'B').features

    expect(features.map((feature) => feature.id)).toEqual([0, 1])
    expect(features.map((feature) => feature.properties.color)).toEqual([OTHER_ROUTE_COLORS[0], SELECTED_ROUTE_COLOR])
    expect(features.map((feature) => feature.properties.selected)).toEqual([false, true])
    expect(features.map((feature) => feature.properties.sortKey)).toEqual([0, 1])
    expect(features[1].geometry.coordinates).toEqual(plan.routes[1].line)
  })
})

describe('checkpointPoints', () => {
  it('numbers checkpoints across routes, colors them by risk, and points back into the plan', () => {
    const plan = makePlan({
      routes: [
        makeRoute({ checkpoints: [makeCheckpoint({ risk: 4 }), makeCheckpoint({ risk: null })] }),
        makeRoute({ id: 'B', recommended: false, checkpoints: [makeCheckpoint({ risk: 1, lat: 35, lon: -100 })] }),
      ],
    })

    const features = checkpointPoints(plan, 'A').features

    expect(features.map((feature) => feature.id)).toEqual([0, 1, 2])
    expect(features.map((feature) => feature.properties.color)).toEqual([
      RISK_STYLES[4].color,
      NO_DATA_STYLE.color,
      RISK_STYLES[1].color,
    ])
    expect(features[2].properties).toMatchObject({ routeIndex: 1, checkpointIndex: 0, selected: false })
    expect(features[2].geometry.coordinates).toEqual([-100, 35])
  })

  it('marks the selected route, wherever it is in the list', () => {
    const features = checkpointPoints(makePlan(), 'B').features

    expect(features.filter((feature) => feature.properties.selected).map((feature) => feature.properties.routeIndex)).toEqual([1, 1, 1])
    expect(features[3].properties.sortKey).toBeGreaterThan(features[0].properties.sortKey) // same risk
  })
})

describe('checkpointSortKey', () => {
  it("draws the riskiest dot on top where routes meet, then the selected route's", () => {
    expect(checkpointSortKey(4, false)).toBeGreaterThan(checkpointSortKey(3, true))
    expect(checkpointSortKey(1, false)).toBeGreaterThan(checkpointSortKey(0, true))
    expect(checkpointSortKey(0, true)).toBeGreaterThan(checkpointSortKey(0, false))
    expect(checkpointSortKey(0, false)).toBeGreaterThan(checkpointSortKey(null, true))
    expect(checkpointSortKey(null, false)).toBeGreaterThanOrEqual(0)
  })
})

describe('pointAlong', () => {
  it('finds the point a share of the way along a line', () => {
    const line: [number, number][] = [
      [0, 0],
      [1, 0],
      [1, 3],
    ]
    expect(pointAlong(line, 0)).toEqual([0, 0])
    expect(pointAlong(line, 0.5)).toEqual([1, 1])
    expect(pointAlong(line, 1)).toEqual([1, 3])
  })

  it('measures east-west distance shorter away from the equator', () => {
    // At 60° north a degree of longitude is half as long, so both segments are about 1 unit long.
    const line: [number, number][] = [
      [0, 60],
      [2, 60],
      [2, 61],
    ]
    const [lon, lat] = pointAlong(line, 0.25)
    expect(lon).toBeCloseTo(1, 9)
    expect(lat).toBeCloseTo(60, 9)
  })

  it('skips repeated points and handles a one-point line', () => {
    const line: [number, number][] = [
      [0, 0],
      [0, 0],
      [2, 0],
    ]
    expect(pointAlong(line, 0.25)).toEqual([0.5, 0])
    expect(pointAlong([[5, 5]], 0.5)).toEqual([5, 5])
  })
})

describe('route letters', () => {
  it('labels each route with its letter in the color of its line', () => {
    const plan = makePlan()

    const labels = routeLabels(plan, 'B').features
    const lines = routeLines(plan, 'B').features

    expect(labels.map((label) => label.properties.label)).toEqual(['A', 'B'])
    expect(labels.map((label) => label.properties.color)).toEqual(lines.map((line) => line.properties.color))
  })

  it('keeps the letters in place when the selection changes, and places each new plan anew', () => {
    const spots = (plan: Plan, selectedId: string) =>
      routeLabels(plan, selectedId).features.map((label) => label.geometry.coordinates)
    const plan = makePlan()
    const moved = makePlan({
      routes: plan.routes.map((route) => ({ ...route, line: route.line.map(([lon, lat]): LngLat => [lon + 1, lat]) })),
    })

    expect(spots(plan, 'B')).toEqual(spots(plan, 'A'))
    expect(spots(moved, 'A')).not.toEqual(spots(plan, 'A')) // not the first plan's spots
  })

  it("puts a route's letter where it runs apart from the other routes, not on a shared road", () => {
    // B shares A's road for its first 5 units, then turns north.
    const a: [number, number][] = [
      [0, 0],
      [10, 0],
    ]
    const b: [number, number][] = [
      [0, 0],
      [5, 0],
      [10, 4],
    ]

    const forA = labelPoint(a, [b])
    const forB = labelPoint(b, [a])

    expect(forA).toEqual([7, 0]) // 70% along A, the farthest candidate from B
    expect(distanceToLine(forB, a)).toBeGreaterThan(1.5) // up the part B doesn't share
  })

  it('keeps the middle for a route with no others', () => {
    const line: [number, number][] = [
      [0, 0],
      [4, 0],
    ]
    expect(labelPoint(line, [])).toEqual([2, 0])
  })

  it('measures the distance from a point to a line', () => {
    const line: [number, number][] = [
      [0, 0],
      [4, 0],
    ]
    expect(distanceToLine([2, 3], line)).toBeCloseTo(3, 9) // to the segment's middle
    expect(distanceToLine([7, 0], line)).toBeCloseTo(3, 9) // to its end
    // A degree of longitude is shorter away from the equator: at 60° north, half as long.
    expect(distanceToLine([6, 60], [[0, 60], [4, 60]])).toBeCloseTo(1, 2)
  })
})

describe('endpoints and bounds', () => {
  it('marks the origin and destination', () => {
    const coordinates = endpoints(makePlan()).features.map((feature) => feature.geometry.coordinates)
    expect(coordinates).toEqual([
      [-96.797, 32.7767],
      [-104.9903, 39.7392],
    ])
  })

  it('fits every route', () => {
    const plan = makePlan({
      routes: [
        makeRoute({ line: [[-97, 33], [-105, 40]] }),
        makeRoute({ id: 'B', line: [[-97, 33], [-109, 36], [-105, 41]] }),
      ],
    })
    expect(planBounds(plan)).toEqual([
      [-109, 33],
      [-97, 41],
    ])
  })
})

// The fixture's checkpoints: mile 0 at 20:00, mile 395.2 at 02:00, mile 790.4 (arrival) at 07:52.
describe('mileAtTime', () => {
  const route = makeRoute()
  const at = (iso: string) => mileAtTime(route, Date.parse(iso))

  it('puts the truck at the origin at the departure, and before it', () => {
    expect(at('2026-10-24T20:00:00Z')).toBe(0)
    expect(at('2026-10-24T19:30:00Z')).toBe(0) // hour 0 can fall before the departure
  })

  it('interpolates between checkpoint ETAs', () => {
    expect(at('2026-10-24T23:00:00Z')).toBeCloseTo(197.6, 1) // halfway to the 02:00 checkpoint
    expect(at('2026-10-25T02:00:00Z')).toBeCloseTo(395.2, 1) // exactly on it
  })

  it('returns null once the route has arrived, so no marker is drawn', () => {
    expect(at('2026-10-25T07:52:00Z')).toBeCloseTo(790.4, 1) // still arriving
    expect(at('2026-10-25T08:00:00Z')).toBeNull()
  })
})

describe('truckMiles', () => {
  it('gives the mile each route has reached at an hour, and null once it has arrived', () => {
    const plan = makePlan()

    expect(truckMiles(plan, 0)).toEqual([0, 0]) // both at the origin at the departure hour
    expect(truckMiles(plan, 3)[0]).toBeCloseTo(197.6, 1)
    expect(truckMiles(plan, 12)).toEqual([null, null]) // hour 12 is 08:00, past the 07:52 arrival
  })
})

describe('bearingAlong', () => {
  it('reads the road\'s heading, so the marker can point along it', () => {
    const north: LngLat[] = [
      [-100, 30],
      [-100, 40],
    ]
    const east: LngLat[] = [
      [-100, 30],
      [-90, 30],
    ]
    expect(bearingAlong(north, 0.5)).toBeCloseTo(0, 0)
    expect(bearingAlong(east, 0.5)).toBeCloseTo(90, 0)
    expect(bearingAlong([...north].reverse(), 0.5)).toBeCloseTo(180, 0)
  })

  it('is always in [0, 360)', () => {
    const west: LngLat[] = [
      [-90, 30],
      [-100, 30],
    ]
    expect(bearingAlong(west, 0.5)).toBeCloseTo(270, 0)
  })
})

describe('truckPositions', () => {
  it('places one marker per route at the given mile, on the route line, coloured by route', () => {
    const plan = makePlan()

    const features = truckPositions(plan, [197.6, 197.6], 'A').features

    expect(features.map((feature) => feature.properties.label)).toEqual(['A', 'B'])
    expect(features[0].properties.color).toBe(SELECTED_ROUTE_COLOR)
    expect(features[0].properties.icon).toBe('truck-0e7490') // its colour's registered image
    expect(features[1].properties.color).toBe(OTHER_ROUTE_COLORS[0])
    // On route A's line, which runs Dallas -> Amarillo -> Denver.
    const [lon, lat] = features[0].geometry.coordinates
    expect(lon).toBeLessThan(-96.797)
    expect(lon).toBeGreaterThan(-101.8313)
    expect(lat).toBeGreaterThan(32.7767)
  })

  it('carries the road\'s bearing, so the icon points the way it is driving', () => {
    // Dallas -> Denver runs north west, so the heading sits between north and west.
    const bearing = truckPositions(makePlan(), [197.6, 197.6], 'A').features[0].properties.bearing
    expect(bearing).toBeGreaterThan(270)
    expect(bearing).toBeLessThan(360)
  })

  it('accepts a fractional mile, which is how the markers are animated between hours', () => {
    const near = truckPositions(makePlan(), [100, 100], 'A').features[0].geometry.coordinates
    const far = truckPositions(makePlan(), [100.5, 100.5], 'A').features[0].geometry.coordinates
    expect(far).not.toEqual(near) // half a mile moves it, so a tween is smooth
  })

  it('draws no marker for a route with no mile, which is one that has arrived', () => {
    expect(truckPositions(makePlan(), [null, null], 'A').features).toEqual([])
  })

  it('starts a truck at the origin at mile 0', () => {
    const features = truckPositions(makePlan(), [0, 0], 'A').features

    for (const feature of features) {
      expect(feature.geometry.coordinates[0]).toBeCloseTo(-96.797, 3)
      expect(feature.geometry.coordinates[1]).toBeCloseTo(32.7767, 3)
    }
  })

  it("draws the selected route's truck on top", () => {
    const features = truckPositions(makePlan(), [100, 100], 'B').features

    expect(features.map((feature) => feature.properties.sortKey)).toEqual([0, 1])
  })
})
