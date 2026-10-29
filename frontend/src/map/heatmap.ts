// The risk heatmap: one square cell per grid square around the routes, with a level for each of
// the plan's forecast hours (README "Assumptions" 15-17). Pure functions, so they're easy to test.

import type { FeatureCollection, Polygon } from 'geojson'
import type { Plan, RiskLevel } from '../types'

export const NO_DATA = -1 // a cell's level when the forecast is missing ('-' in the API)

export interface CellProps {
  index: number // into plan.heatmap.cells, so a hover can read that cell's levels and causes
}

/** The level at one hour from a cell's level string ('0'-'4', or '-' for No data). */
export function levelAt(levels: string, hour: number): number {
  const code = levels.charCodeAt(hour) - 48 // '0' is 48
  return code >= 0 && code <= 4 ? code : NO_DATA
}

/** A cell's level at one hour as a risk level, or null for No data. */
export function riskAt(levels: string, hour: number): RiskLevel | null {
  const level = levelAt(levels, hour)
  return level === NO_DATA ? null : (level as RiskLevel)
}

/** The reading behind a cell's level at one hour, in the cause's own unit. Null where the API sent
 * none, which it does below Moderate: the UI says nothing about a Low cell. */
export function readingAt(values: string, hour: number): number | null {
  const slot = values.split(',')[hour]
  if (slot === undefined || slot === '') return null
  const value = Number(slot)
  return Number.isFinite(value) ? value : null
}

const CAUSES: Record<string, string> = { w: 'wind', r: 'rain', s: 'snow' }

/** What set a cell's level at one hour ("wind", "rain", "snow"), or null when nothing did. */
export function causeAt(causes: string, hour: number): string | null {
  return CAUSES[causes.charAt(hour)] ?? null
}

/** Every cell's level at one hour, in the plan's cell order. */
export function cellLevels(plan: Plan, hour: number): number[] {
  return plan.heatmap.cells.map((cell) => levelAt(cell.levels, hour))
}

/** The cells whose level differs between two hours, with the new level: moving the slider only
 * repaints these. A missing previous level counts as different. */
export function levelChanges(from: readonly number[], to: readonly number[]): [cell: number, level: number][] {
  const changes: [number, number][] = []
  to.forEach((level, cell) => {
    if (from[cell] !== level) changes.push([cell, level])
  })
  return changes
}

/** The cells as squares. Feature ids (for MapLibre's feature-state) are firstId + the cell's index:
 * each plan gets ids of its own, so its levels never land on another plan's cells. */
export function heatmapCells(plan: Plan, firstId = 0): FeatureCollection<Polygon, CellProps> {
  return {
    type: 'FeatureCollection',
    features: plan.heatmap.cells.map((cell, index) => {
      const [west, south, east, north] = cell.bounds
      return {
        type: 'Feature',
        id: firstId + index,
        geometry: {
          type: 'Polygon',
          coordinates: [
            [
              [west, south],
              [east, south],
              [east, north],
              [west, north],
              [west, south],
            ],
          ],
        },
        properties: { index },
      }
    }),
  }
}
