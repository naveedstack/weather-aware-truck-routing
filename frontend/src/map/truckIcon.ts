// The truck marker's image. MapLibre can't recolour a plain raster image, so one is drawn per route
// colour and registered under its own id; the symbol layer then picks one with ['get', 'icon'].

import { OTHER_ROUTE_COLORS, SELECTED_ROUTE_COLOR } from '../risk'

export const TRUCK_ICON_RATIO = 2 // drawn at 2x, so the marker stays sharp on dense screens
const SIZE = 30 // the marker's size in CSS pixels

/** Every colour a route line can take, so all the images exist before any plan is drawn. */
export const TRUCK_ICON_COLORS: readonly string[] = [SELECTED_ROUTE_COLOR, ...OTHER_ROUTE_COLORS]

export function truckIconId(color: string): string {
  return `truck-${color.replace('#', '')}`
}

export interface IconImage {
  width: number
  height: number
  data: Uint8Array
}

/** A route-coloured disc with a white ring and a white truck silhouette.
 *
 * Returns null where there is no 2D canvas (jsdom in the tests); the layer then draws its text
 * label alone rather than failing.
 */
export function truckIcon(color: string): IconImage | null {
  const size = SIZE * TRUCK_ICON_RATIO
  const canvas = document.createElement('canvas')
  canvas.width = size
  canvas.height = size
  const context = canvas.getContext('2d')
  if (!context) return null

  const middle = size / 2
  const radius = middle - 2.5 * TRUCK_ICON_RATIO

  // The disc, with a white ring and a faint dark edge so it reads on a pale basemap.
  context.beginPath()
  context.arc(middle, middle, radius, 0, 2 * Math.PI)
  context.fillStyle = color
  context.fill()
  context.lineWidth = 2.5 * TRUCK_ICON_RATIO
  context.strokeStyle = '#ffffff'
  context.stroke()
  context.beginPath()
  context.arc(middle, middle, radius + 1.25 * TRUCK_ICON_RATIO, 0, 2 * Math.PI)
  context.lineWidth = TRUCK_ICON_RATIO
  context.strokeStyle = 'rgba(17, 24, 39, 0.22)'
  context.stroke()

  // A truck seen from above, pointing north. The layer rotates the icon to the road's bearing, and
  // an overhead shape reads correctly at every angle, where a side view would end up upside down
  // whenever the route runs west.
  const span = radius * 1.5
  const x = (u: number) => middle - span / 2 + u * span
  const y = (v: number) => middle - span / 2 + v * span
  context.fillStyle = '#ffffff'
  context.beginPath() // the cab, at the front
  context.rect(x(0.35), y(0.1), span * 0.3, span * 0.2)
  context.fill()
  context.beginPath() // the trailer behind it, a little wider
  context.rect(x(0.3), y(0.34), span * 0.4, span * 0.52)
  context.fill()
  return { width: size, height: size, data: new Uint8Array(context.getImageData(0, 0, size, size).data) }
}
