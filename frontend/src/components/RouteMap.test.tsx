import { render, screen } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { makePlan } from '../testing/fixtures'
import { RouteMap } from './RouteMap'

// MapLibre needs WebGL, which jsdom lacks; this checks how the component drives the map.
type Mock = ReturnType<typeof vi.fn>
const maps = vi.hoisted(() => ({
  created: [] as { showPlan: Mock; selectRoute: Mock; highlightRoute: Mock; showHeatmapHour: Mock; destroy: Mock }[],
  failToStart: false,
}))

vi.mock('../map/MapController', () => ({
  MapController: class {
    showPlan = vi.fn()
    selectRoute = vi.fn()
    highlightRoute = vi.fn()
    showHeatmapHour = vi.fn()
    destroy = vi.fn()
    constructor() {
      if (maps.failToStart) throw new Error('Failed to initialize WebGL')
      maps.created.push(this)
    }
  },
}))

afterEach(() => {
  maps.created.length = 0
  maps.failToStart = false
  vi.restoreAllMocks()
})

const props = { selectedRoute: null, highlightedRoute: null, heatmapHour: 0, status: null, failed: false, onFailure: () => {} }

describe('RouteMap', () => {
  it('keeps one map and passes it each plan, selected and highlighted route, and heatmap hour', () => {
    const first = makePlan()
    const second = makePlan({ load_lb: 42000 })

    const view = render(<RouteMap {...props} plan={first} />)
    view.rerender(<RouteMap {...props} plan={second} highlightedRoute="B" heatmapHour={30} />)
    view.rerender(<RouteMap {...props} plan={second} highlightedRoute="B" heatmapHour={12} />) // only the hour
    view.rerender(<RouteMap {...props} plan={second} highlightedRoute="B" heatmapHour={12} selectedRoute="C" />)
    view.unmount()

    expect(maps.created).toHaveLength(1)
    const [map] = maps.created
    expect(map.showPlan.mock.calls).toEqual([[first], [second]])
    expect(map.highlightRoute.mock.calls).toEqual([[null], ['B']])
    expect(map.showHeatmapHour.mock.calls).toEqual([[0], [30], [12]])
    expect(map.selectRoute.mock.calls).toEqual([[null], ['C']])
    expect(map.destroy).toHaveBeenCalledOnce()
  })

  it('shows the planning step on the map while a plan is computed', () => {
    const view = render(<RouteMap {...props} plan={null} status="Getting truck routes from TomTom…" />)
    expect(screen.getByText('Getting truck routes from TomTom…')).toBeTruthy()

    view.rerender(<RouteMap {...props} plan={makePlan()} />)
    expect(screen.queryByText('Getting truck routes from TomTom…')).toBeNull()
  })

  it('says so when the map can\'t be shown, and makes no map', () => {
    render(<RouteMap {...props} plan={null} status="Getting truck routes from TomTom…" failed />)

    expect(screen.getByText(/doesn't support WebGL 2/)).toBeTruthy()
    expect(screen.queryByText('Getting truck routes from TomTom…')).toBeNull() // no map to show it on
    expect(maps.created).toHaveLength(0)
  })

  it('reports a map that fails to start', () => {
    maps.failToStart = true
    vi.spyOn(console, 'error').mockImplementation(() => {})
    const onFailure = vi.fn()

    render(<RouteMap {...props} plan={null} onFailure={onFailure} />)

    expect(onFailure).toHaveBeenCalledExactlyOnceWith(true)
  })
})
