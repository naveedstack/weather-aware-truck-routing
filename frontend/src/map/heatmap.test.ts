import { describe, expect, it } from 'vitest'
import { makePlan } from '../testing/fixtures'
import {
  NO_DATA,
  causeAt,
  cellLevels,
  heatmapCells,
  levelAt,
  levelChanges,
  readingAt,
  riskAt,
} from './heatmap'

describe('levelAt', () => {
  it("reads one hour's level from a cell's level string", () => {
    expect(levelAt('01234', 0)).toBe(0)
    expect(levelAt('01234', 4)).toBe(4)
  })

  it('reads "-", and hours past the end, as No data', () => {
    expect(levelAt('0-2', 1)).toBe(NO_DATA)
    expect(levelAt('012', 3)).toBe(NO_DATA)
  })
})

describe('cellLevels', () => {
  it("lists every cell's level at an hour, in the plan's cell order", () => {
    const plan = makePlan()
    expect(cellLevels(plan, 0)).toEqual([0, 0])
    expect(cellLevels(plan, 30)).toEqual([0, 3])
    expect(cellLevels(plan, 48)).toEqual([0, NO_DATA])
  })
})

describe('levelChanges', () => {
  it('lists only the cells whose level changes, so the slider repaints only those', () => {
    expect(levelChanges([0, 1, 2, NO_DATA], [0, 2, 2, 0])).toEqual([
      [1, 2],
      [3, 0],
    ])
    expect(levelChanges([0, 1], [0, 1])).toEqual([])
  })

  it('treats every cell as changed when nothing is shown yet', () => {
    expect(levelChanges([], [0, NO_DATA])).toEqual([
      [0, 0],
      [1, NO_DATA],
    ])
  })
})

describe('heatmapCells', () => {
  it('draws each cell as a closed square, with the given first id plus its index as the feature id', () => {
    const features = heatmapCells(makePlan(), 2_000_000).features

    expect(features.map((feature) => feature.id)).toEqual([2_000_000, 2_000_001])
    expect(features[0].geometry.coordinates).toEqual([
      [
        [-97, 32.5],
        [-96.5, 32.5],
        [-96.5, 33],
        [-97, 33],
        [-97, 32.5],
      ],
    ])
  })
})

describe('riskAt', () => {
  it('reads a level as a risk level, and No data as null', () => {
    expect(riskAt('0-234', 0)).toBe(0)
    expect(riskAt('0-234', 4)).toBe(4)
    expect(riskAt('0-234', 1)).toBeNull()
    expect(riskAt('012', 9)).toBeNull() // past the end
  })
})

describe('causeAt', () => {
  it("names the condition that set an hour's level", () => {
    expect(causeAt('wrs', 0)).toBe('wind')
    expect(causeAt('wrs', 1)).toBe('rain')
    expect(causeAt('wrs', 2)).toBe('snow')
  })

  it('reads "-", and hours past the end, as nothing to blame', () => {
    expect(causeAt('w-s', 1)).toBeNull()
    expect(causeAt('w', 5)).toBeNull()
  })
})

describe('heatmapCells', () => {
  it('gives each cell its index, so a hover can look its levels up', () => {
    expect(heatmapCells(makePlan()).features.map((feature) => feature.properties.index)).toEqual([0, 1])
  })
})

describe('readingAt', () => {
  it("reads the cause's value for an hour", () => {
    expect(readingAt('38.3,44,0.12', 0)).toBe(38.3)
    expect(readingAt('38.3,44,0.12', 1)).toBe(44)
    expect(readingAt('38.3,44,0.12', 2)).toBe(0.12)
  })

  it('reads an empty slot, and hours past the end, as no reading', () => {
    expect(readingAt(',44,', 0)).toBeNull() // Low hours carry none
    expect(readingAt(',44,', 2)).toBeNull()
    expect(readingAt(',44,', 7)).toBeNull()
  })
})
