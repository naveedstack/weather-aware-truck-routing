import { useEffect, useRef } from 'react'
import { MapController } from '../map/MapController'
import type { Plan } from '../types'

interface Props {
  plan: Plan | null
  selectedRoute: string | null
  highlightedRoute: string | null
  heatmapHour: number // of plan.heatmap.hours
  status: string | null // the planning step to show while a plan is computed
  failed: boolean // the map can't be shown (no WebGL 2, or MapLibre failed to start)
  onFailure: (failed: boolean) => void // called with true when MapLibre fails to start
}

const FAILURE = "The map can't be shown because this browser doesn't support WebGL 2. The route details are still listed."

/** Hosts the one map. The map is created once; later prop changes only update its data. */
export function RouteMap({ plan, selectedRoute, highlightedRoute, heatmapHour, status, failed, onFailure }: Props) {
  const container = useRef<HTMLDivElement>(null)
  const controller = useRef<MapController | null>(null)

  useEffect(() => {
    if (failed || !container.current) return
    try {
      controller.current = new MapController(container.current)
    } catch (error) {
      console.error(error) // the trip panel keeps working without the map
      onFailure(true)
      return
    }
    return () => {
      controller.current?.destroy()
      controller.current = null
    }
  }, [failed, onFailure])

  // showPlan selects the plan's recommended route; App's selection then follows it.
  useEffect(() => controller.current?.showPlan(plan), [plan])
  useEffect(() => controller.current?.selectRoute(selectedRoute), [selectedRoute])
  useEffect(() => controller.current?.highlightRoute(highlightedRoute), [highlightedRoute])
  useEffect(() => controller.current?.showHeatmapHour(heatmapHour), [heatmapHour])

  return (
    <div className="map-area">
      <div ref={container} className="map" />
      {status && !failed && (
        // Screen readers hear the progress from the panel's live region.
        <div className="map-status" aria-hidden="true">
          <span className="spinner" />
          {/* A new key per step, so each message fades in. */}
          <span key={status} className="status-text">
            {status}
          </span>
        </div>
      )}
      {failed && <p className="map-failure">{FAILURE}</p>}
    </div>
  )
}
