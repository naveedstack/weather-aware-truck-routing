import { describe, expect, it } from 'vitest'
import { OTHER_ROUTE_COLORS, SELECTED_ROUTE_COLOR } from '../risk'
import { TRUCK_ICON_COLORS, truckIcon, truckIconId } from './truckIcon'

describe('truckIconId', () => {
  it('names one image per route colour, so each marker keeps its own', () => {
    expect(truckIconId(SELECTED_ROUTE_COLOR)).toBe('truck-0e7490')
    const ids = TRUCK_ICON_COLORS.map(truckIconId)
    expect(new Set(ids).size).toBe(ids.length)
    expect(TRUCK_ICON_COLORS).toEqual([SELECTED_ROUTE_COLOR, ...OTHER_ROUTE_COLORS])
  })
})

describe('truckIcon', () => {
  it('gives up rather than throwing where there is no 2D canvas, so the layer still draws text', () => {
    // jsdom has no canvas rendering context; in a browser this returns the drawn image.
    expect(truckIcon(SELECTED_ROUTE_COLOR)).toBeNull()
  })
})
