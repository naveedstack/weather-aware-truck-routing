// Map features built from a plan. Pure functions, so they're easy to test.
// Features carry small numeric ids (for MapLibre's feature-state) and indexes back into the plan;
// popups read the full checkpoint from the plan, not from feature properties.

import type { Feature, FeatureCollection, LineString, Point } from 'geojson'
import { riskStyle, routeColors } from '../risk'
import { truckIconId } from './truckIcon'
import type { Plan, RiskLevel, Route } from '../types'

export type LngLat = [number, number]

export interface RouteProps {
  color: string
  selected: boolean
  sortKey: number // the selected route is drawn on top
}

export interface CheckpointProps {
  routeIndex: number
  checkpointIndex: number
  color: string
  selected: boolean
  sortKey: number
}

/** Where checkpoints of several routes meet (the start, the destination, shared roads), the
 * riskiest is drawn on top (No data lowest), then the selected route's. */
export function checkpointSortKey(risk: RiskLevel | null, selected: boolean): number {
  return ((risk ?? -1) + 1) * 2 + (selected ? 1 : 0)
}

export interface LabelProps {
  label: string
  color: string
}

export const EMPTY: FeatureCollection = { type: 'FeatureCollection', features: [] }

export function routeLines(plan: Plan, selectedId: string | null): FeatureCollection<LineString, RouteProps> {
  const colors = routeColors(plan.routes, selectedId)
  return {
    type: 'FeatureCollection',
    features: plan.routes.map((route, routeIndex) => ({
      type: 'Feature',
      id: routeIndex,
      geometry: { type: 'LineString', coordinates: route.line },
      properties: {
        color: colors[routeIndex],
        selected: route.id === selectedId,
        sortKey: route.id === selectedId ? 1 : 0,
      },
    })),
  }
}

export function checkpointPoints(plan: Plan, selectedId: string | null): FeatureCollection<Point, CheckpointProps> {
  const features: Feature<Point, CheckpointProps>[] = []
  plan.routes.forEach((route, routeIndex) => {
    route.checkpoints.forEach((checkpoint, checkpointIndex) => {
      features.push({
        type: 'Feature',
        id: features.length,
        geometry: { type: 'Point', coordinates: [checkpoint.lon, checkpoint.lat] },
        properties: {
          routeIndex,
          checkpointIndex,
          color: riskStyle(checkpoint.risk).color,
          selected: route.id === selectedId,
          sortKey: checkpointSortKey(checkpoint.risk, route.id === selectedId),
        },
      })
    })
  })
  return { type: 'FeatureCollection', features }
}

/** The point a given share of the way along a line (distances in a flat local projection). */
export function pointAlong(line: LngLat[], share: number): LngLat {
  if (line.length === 1) return line[0]
  const scale = Math.cos((line[Math.floor(line.length / 2)][1] * Math.PI) / 180)
  const lengths = line.slice(1).map(([lon, lat], i) => Math.hypot((lon - line[i][0]) * scale, lat - line[i][1]))
  let remaining = lengths.reduce((sum, length) => sum + length, 0) * share
  for (let i = 0; i < lengths.length; i++) {
    if (remaining <= lengths[i] && lengths[i] > 0) {
      const t = remaining / lengths[i]
      return [line[i][0] + (line[i + 1][0] - line[i][0]) * t, line[i][1] + (line[i + 1][1] - line[i][1]) * t]
    }
    remaining -= lengths[i]
  }
  return line[line.length - 1]
}

/** The compass bearing along a line at a share of its length, in degrees clockwise from north.
 * Read over a short step either side, so the heading is the road's and not one polyline joint's. */
export function bearingAlong(line: LngLat[], share: number): number {
  const step = 0.004 // about 0.4% of the route
  const start = Math.max(0, Math.min(1 - step, share - step / 2))
  const [fromLon, fromLat] = pointAlong(line, start)
  const [toLon, toLat] = pointAlong(line, start + step)
  const scale = Math.cos((fromLat * Math.PI) / 180)
  const bearing = (Math.atan2((toLon - fromLon) * scale, toLat - fromLat) * 180) / Math.PI
  return (bearing + 360) % 360
}

/** Distance from a point to a line, in degrees, flattened at the point's latitude. */
export function distanceToLine([lon, lat]: LngLat, line: LngLat[]): number {
  const scale = Math.cos((lat * Math.PI) / 180)
  const flat = line.map(([x, y]): LngLat => [(x - lon) * scale, y - lat]) // relative to the point
  if (flat.length === 1) return Math.hypot(flat[0][0], flat[0][1])
  let nearest = Infinity
  for (let i = 1; i < flat.length; i++) {
    const [ax, ay] = flat[i - 1]
    const [dx, dy] = [flat[i][0] - ax, flat[i][1] - ay]
    const lengthSq = dx * dx + dy * dy
    const t = lengthSq === 0 ? 0 : Math.min(1, Math.max(0, -(ax * dx + ay * dy) / lengthSq))
    nearest = Math.min(nearest, Math.hypot(ax + t * dx, ay + t * dy))
  }
  return nearest
}

// Where a route's letter may go, as shares of its length: the middle first, then further out.
const LABEL_SHARES = [0.5, 0.42, 0.58, 0.35, 0.65, 0.3, 0.7]

/** The spot for a route's letter: the one farthest from the other routes, so that no letter sits
 * on a road it shares with another route, where the two letters would hide each other. */
export function labelPoint(line: LngLat[], others: LngLat[][]): LngLat {
  let best = pointAlong(line, LABEL_SHARES[0])
  let bestGap = -Infinity
  for (const share of LABEL_SHARES) {
    const point = pointAlong(line, share)
    const gap = Math.min(Infinity, ...others.map((other) => distanceToLine(point, other)))
    if (gap > bestGap) {
      best = point
      bestGap = gap
    }
  }
  return best
}

// The letters' spots depend only on the plan, and finding them takes a few milliseconds on a long
// trip, so they're found once per plan rather than each time the selection changes.
const labelPoints = new WeakMap<Plan, LngLat[]>()

function labelPointsOf(plan: Plan): LngLat[] {
  let points = labelPoints.get(plan)
  if (!points) {
    points = plan.routes.map((route, routeIndex) => {
      const others = plan.routes.filter((_, index) => index !== routeIndex).map((other) => other.line)
      return labelPoint(route.line, others)
    })
    labelPoints.set(plan, points)
  }
  return points
}

export function routeLabels(plan: Plan, selectedId: string | null): FeatureCollection<Point, LabelProps> {
  const colors = routeColors(plan.routes, selectedId)
  const points = labelPointsOf(plan)
  return {
    type: 'FeatureCollection',
    features: plan.routes.map((route, routeIndex) => ({
      type: 'Feature',
      geometry: { type: 'Point', coordinates: points[routeIndex] },
      properties: { label: route.id, color: colors[routeIndex] },
    })),
  }
}

export interface TruckProps {
  label: string // the route's letter, shown beside the marker
  icon: string // the registered image for this route's colour
  color: string
  bearing: number // the road's heading here, so the icon points the way it is driving
  selected: boolean
  sortKey: number
}

/** The mile a route's truck has reached at a moment, from its checkpoint ETAs.
 *
 * 0 before the departure (hour 0 can fall up to half an hour before it, when the truck is still at
 * the origin), and null once the route has arrived, so no marker is drawn for a finished trip.
 */
export function mileAtTime(route: Route, atMs: number): number | null {
  const checkpoints = route.checkpoints
  if (checkpoints.length === 0) return null
  if (atMs <= Date.parse(checkpoints[0].eta)) return 0
  if (atMs > Date.parse(checkpoints[checkpoints.length - 1].eta)) return null
  for (let index = 1; index < checkpoints.length; index++) {
    const previous = checkpoints[index - 1]
    const current = checkpoints[index]
    const end = Date.parse(current.eta)
    if (atMs <= end) {
      const start = Date.parse(previous.eta)
      const share = end > start ? (atMs - start) / (end - start) : 0
      return previous.mile + (current.mile - previous.mile) * share
    }
  }
  return null
}

/** The mile each route's truck has reached at one of the heatmap's hours, in the plan's route
 * order. Null for a route that has already arrived. */
export function truckMiles(plan: Plan, hour: number): (number | null)[] {
  const at = Date.parse(plan.heatmap.hours[hour] ?? plan.departure)
  return plan.routes.map((route) => mileAtTime(route, at))
}

/** The truck markers at the given miles, one per route. Each is placed along the route line the map
 * draws, by share of the route's length, so the marker stays on the road at any mile; and it carries
 * the bearing of the road there, so the icon can point the way it is driving. Passing miles in
 * rather than an hour is what lets the markers be animated between hours. */
export function truckPositions(
  plan: Plan,
  miles: readonly (number | null)[],
  selectedId: string | null,
): FeatureCollection<Point, TruckProps> {
  const colors = routeColors(plan.routes, selectedId)
  const features: Feature<Point, TruckProps>[] = []
  plan.routes.forEach((route, routeIndex) => {
    const mile = miles[routeIndex]
    if (mile === null || mile === undefined) return // arrived, or no mile for it yet
    const share = route.distance_mi > 0 ? Math.min(1, mile / route.distance_mi) : 0
    features.push({
      type: 'Feature',
      geometry: { type: 'Point', coordinates: pointAlong(route.line, share) },
      properties: {
        label: route.id,
        icon: truckIconId(colors[routeIndex]),
        color: colors[routeIndex],
        bearing: Math.round(bearingAlong(route.line, share)),
        selected: route.id === selectedId,
        sortKey: route.id === selectedId ? 1 : 0,
      },
    })
  })
  return { type: 'FeatureCollection', features }
}

export function endpoints(plan: Plan): FeatureCollection<Point> {
  return {
    type: 'FeatureCollection',
    features: [plan.origin, plan.destination].map((place) => ({
      type: 'Feature',
      geometry: { type: 'Point', coordinates: [place.lon, place.lat] },
      properties: {},
    })),
  }
}

/** [[west, south], [east, north]] around every route. */
export function planBounds(plan: Plan): [LngLat, LngLat] {
  let west = Infinity
  let south = Infinity
  let east = -Infinity
  let north = -Infinity
  for (const route of plan.routes) {
    for (const [lon, lat] of route.line) {
      west = Math.min(west, lon)
      east = Math.max(east, lon)
      south = Math.min(south, lat)
      north = Math.max(north, lat)
    }
  }
  return [
    [west, south],
    [east, north],
  ]
}
