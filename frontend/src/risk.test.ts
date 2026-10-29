import { describe, expect, it } from 'vitest'
import {
  NO_DATA_STYLE,
  OTHER_ROUTE_COLORS,
  RISK_LEVELS,
  RISK_STYLES,
  riskLabel,
  riskStyle,
  routeColors,
  SELECTED_ROUTE_COLOR,
} from './risk'

describe('risk styles', () => {
  it('names every level, and "No data" for a missing one', () => {
    expect(RISK_LEVELS.map(riskLabel)).toEqual(['Low', 'Moderate', 'High', 'Severe', 'No Travel'])
    expect(riskLabel(null)).toBe('No data')
    expect(riskStyle(null)).toBe(NO_DATA_STYLE)
  })

  it('gives each level its own color', () => {
    const colors = [...RISK_LEVELS.map((level) => RISK_STYLES[level].color), NO_DATA_STYLE.color]
    expect(new Set(colors).size).toBe(colors.length)
  })
})

describe('routeColors', () => {
  it('makes the selected route blue wherever it is, and the others muted', () => {
    const colors = routeColors([{ id: 'A' }, { id: 'B' }, { id: 'C' }], 'B')
    expect(colors).toEqual([OTHER_ROUTE_COLORS[0], SELECTED_ROUTE_COLOR, OTHER_ROUTE_COLORS[1]])
  })

  it('gives three routes different colors that are never a risk color', () => {
    const colors = routeColors([{ id: 'A' }, { id: 'B' }, { id: 'C' }], 'A')
    expect(new Set(colors).size).toBe(3)
    const riskColors = new Set([...RISK_LEVELS.map((level) => RISK_STYLES[level].color), NO_DATA_STYLE.color])
    expect(colors.some((color) => riskColors.has(color))).toBe(false)
  })
})
