import type { RiskLevel } from './types'

interface LevelStyle {
  label: string
  color: string // fill
  text: string // text on the fill, at least 4.5:1 contrast (WCAG AA for small text)
}

// Green to purple, the usual order for weather risk. Every level is also written out in words,
// so color is never the only cue.
export const RISK_STYLES: Record<RiskLevel, LevelStyle> = {
  0: { label: 'Low', color: '#43a047', text: '#111827' },
  1: { label: 'Moderate', color: '#fdd835', text: '#3b3200' },
  2: { label: 'High', color: '#fb8c00', text: '#111827' },
  3: { label: 'Severe', color: '#e53935', text: '#000000' },
  4: { label: 'No Travel', color: '#6a1b9a', text: '#ffffff' },
}
export const NO_DATA_STYLE: LevelStyle = { label: 'No data', color: '#9e9e9e', text: '#111827' }

export const RISK_LEVELS: RiskLevel[] = [0, 1, 2, 3, 4]

export function riskStyle(level: RiskLevel | null): LevelStyle {
  return level === null ? NO_DATA_STYLE : RISK_STYLES[level]
}

export function riskLabel(level: RiskLevel | null): string {
  return riskStyle(level).label
}

// Route lines are dark cyan, blue and gray, so they never look like a risk level. The selected route
// (at first the recommended one) is dark cyan, the same as the app's accent; the others are muted, so
// it stands out on the map, in the cards and in the legend.
export const SELECTED_ROUTE_COLOR = '#0e7490'
export const OTHER_ROUTE_COLORS = ['#1d4ed8', '#64748b'] as const

/** Each route's color, in the plan's order: dark cyan for the selected route. */
export function routeColors(routes: readonly { id: string }[], selectedId: string | null): string[] {
  let others = 0
  return routes.map((route) =>
    route.id === selectedId ? SELECTED_ROUTE_COLOR : OTHER_ROUTE_COLORS[others++ % OTHER_ROUTE_COLORS.length],
  )
}
