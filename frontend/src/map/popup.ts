// The checkpoint popup, built from DOM nodes with textContent only: the route ids and load-rule texts
// come from the server, so nothing is ever parsed as HTML.

import { formatDateTime, formatMiles, formatMph, formatNumber, formatRate, formatTime } from '../format'
import { riskLabel, riskStyle } from '../risk'
import type { Checkpoint, RiskLevel, Route } from '../types'

export interface PopupEntry {
  route: Route
  checkpointIndex: number
}

function element(tag: string, className?: string, text?: string): HTMLElement {
  const node = document.createElement(tag)
  if (className) node.className = className
  if (text !== undefined) node.textContent = text
  return node
}

/** A term and its value, with the value's risk level when it has one. */
function row(list: HTMLElement, term: string, value: string, level?: RiskLevel | null): void {
  list.append(element('dt', undefined, term))
  const description = element('dd', undefined, value)
  if (level !== undefined && level !== null) {
    const tag = element('span', 'popup-level', riskLabel(level))
    tag.style.setProperty('--level-color', riskStyle(level).color)
    description.append(' ', tag)
  }
  list.append(description)
}

export function checkpointTitle(routeId: string, index: number, count: number): string {
  if (index === 0) return `Route ${routeId} · start`
  if (index === count - 1) return `Route ${routeId} · destination`
  return `Route ${routeId} · checkpoint ${index}`
}

function missingNote(checkpoint: Checkpoint): string {
  const known = [checkpoint.wind_mph, checkpoint.rain_in_per_hr, checkpoint.snow_in_per_hr].some((value) => value !== null)
  return known
    ? 'Part of the forecast is missing, so this checkpoint has no overall level.'
    : 'No forecast is available for this place and time.'
}

/** One checkpoint: its level, where it is, and the weather at its ETA. */
export function checkpointPopup(route: Route, checkpointIndex: number): HTMLElement {
  const checkpoint = route.checkpoints[checkpointIndex]
  const style = riskStyle(checkpoint.risk)
  const section = element('section', 'popup-section')

  const header = element('div', 'popup-header')
  header.append(element('span', 'popup-title', checkpointTitle(route.id, checkpointIndex, route.checkpoints.length)))
  const badge = element('span', 'popup-risk', style.label)
  badge.style.background = style.color
  badge.style.color = style.text
  header.append(badge)
  section.append(header)
  const where = `Mile ${formatNumber(checkpoint.mile, 1)} · stands for ${formatMiles(checkpoint.covers_mi)} of road`
  section.append(element('div', 'popup-subtitle', where))

  const list = element('dl', 'popup-values')
  row(list, 'ETA', formatDateTime(checkpoint.eta))
  row(list, 'Forecast for', formatTime(checkpoint.forecast_hour))
  row(list, 'Wind', formatMph(checkpoint.wind_mph), checkpoint.wind_risk)
  row(list, 'Gusts', checkpoint.gust_mph === null ? 'No data' : `${formatMph(checkpoint.gust_mph)} (info only)`)
  row(list, 'Rain', formatRate(checkpoint.rain_in_per_hr), checkpoint.rain_risk)
  row(list, 'Snow', formatRate(checkpoint.snow_in_per_hr), checkpoint.snow_risk)
  section.append(list)

  if (checkpoint.load_rule) section.append(element('p', 'popup-note', checkpoint.load_rule))
  if (checkpoint.risk === null) section.append(element('p', 'popup-note', missingNote(checkpoint)))
  return section
}

/** The one condition that set the checkpoint's level, with its value: what to blame at a glance. */
function leadingCondition(checkpoint: Checkpoint): string | null {
  if (checkpoint.risk === null) return null
  const conditions: [RiskLevel | null, string][] = [
    [checkpoint.wind_risk, `Wind ${formatMph(checkpoint.wind_mph)}`],
    [checkpoint.rain_risk, `Rain ${formatRate(checkpoint.rain_in_per_hr)}`],
    [checkpoint.snow_risk, `Snow ${formatRate(checkpoint.snow_in_per_hr)}`],
  ]
  return conditions.find(([level]) => level === checkpoint.risk)?.[1] ?? null
}

/** The hover tip: which checkpoint, its level, its ETA and the condition behind it. The full
 * weather, the per-condition levels and any load rule come from the click popup instead. */
export function checkpointTip(route: Route, checkpointIndex: number): HTMLElement {
  const checkpoint = route.checkpoints[checkpointIndex]
  const style = riskStyle(checkpoint.risk)
  const root = element('div', 'tip')
  root.append(element('span', 'tip-title', checkpointTitle(route.id, checkpointIndex, route.checkpoints.length)))

  const line = element('div', 'tip-line')
  const badge = element('span', 'tip-risk', style.label)
  badge.style.background = style.color
  badge.style.color = style.text
  line.append(badge, element('span', 'tip-eta', formatTime(checkpoint.eta)))
  root.append(line)

  const leading = leadingCondition(checkpoint)
  if (leading) root.append(element('div', 'tip-lead', leading))
  root.append(element('div', 'tip-hint', 'Click for details'))
  return root
}

/** How a heatmap cell's cause reads, with its value in that condition's own unit. */
function causeReading(cause: string, value: number | null): string {
  if (value === null) return `Set by the ${cause}`
  return cause === 'wind' ? `Wind ${formatMph(value)}` : `${cause === 'rain' ? 'Rain' : 'Snow'} ${formatRate(value)}`
}

/** The hover tip for a heatmap cell: how bad it is at the slider's hour, and which condition put it
 * there, with the reading. Low cells get no tip at all, so none is built for them. */
export function heatmapTip(
  level: RiskLevel | null,
  cause: string | null,
  value: number | null,
  hour: string,
): HTMLElement {
  const style = riskStyle(level)
  const root = element('div', 'tip')
  root.append(element('span', 'tip-title', 'Weather here'))

  const line = element('div', 'tip-line')
  const badge = element('span', 'tip-risk', style.label)
  badge.style.background = style.color
  badge.style.color = style.text
  line.append(badge, element('span', 'tip-eta', formatTime(hour)))
  root.append(line)

  root.append(
    element(
      'div',
      'tip-lead',
      cause === null ? 'No forecast for this place and hour' : causeReading(cause, value),
    ),
  )
  root.append(element('div', 'tip-hint', "At the slider's hour, not the truck's ETA"))
  return root
}

/** The popup for a click: one section per route with a checkpoint there (routes share points such
 * as the destination, where each has its own ETA and weather), and a close button. */
export function checkpointsPopup(entries: PopupEntry[], onClose: () => void): HTMLElement {
  const root = element('div', 'popup')
  root.tabIndex = -1 // a click on its text keeps focus in the map, where Escape closes it
  const close = document.createElement('button')
  close.type = 'button'
  close.className = 'popup-close'
  close.textContent = '×'
  close.setAttribute('aria-label', 'Close')
  close.addEventListener('click', onClose)
  const body = element('div', 'popup-body') // scrolls when a spot has several routes
  for (const { route, checkpointIndex } of entries) body.append(checkpointPopup(route, checkpointIndex))
  root.append(close, body)
  return root
}
