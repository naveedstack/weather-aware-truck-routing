// The one MapLibre map. React hands it data; it keeps its sources and layers and only updates them
// (setData, feature-state), never rebuilding layers.

import 'maplibre-gl/dist/maplibre-gl.css'

import {
  type ExpressionSpecification,
  type GeoJSONSource,
  type LayerSpecification,
  type MapGeoJSONFeature,
  type MapMouseEvent,
  Map as MapLibreMap,
  NavigationControl,
  type PaddingOptions,
  Popup,
  setWorkerUrl,
} from 'maplibre-gl'
import workerUrl from 'maplibre-gl/dist/maplibre-gl-worker.mjs?worker&url'
import type { FeatureCollection } from 'geojson'
import { NO_DATA_STYLE, RISK_STYLES } from '../risk'
import type { Plan } from '../types'
import { type PopupEntry, checkpointTip, checkpointsPopup, heatmapTip } from './popup'
import { EMPTY, type LngLat, checkpointPoints, endpoints, planBounds, routeLabels, routeLines, truckMiles, truckPositions } from './geojson'
import { NO_DATA, causeAt, cellLevels, heatmapCells, levelChanges, readingAt, riskAt } from './heatmap'
import { TRUCK_ICON_COLORS, TRUCK_ICON_RATIO, truckIcon, truckIconId } from './truckIcon'

setWorkerUrl(workerUrl) // a bundler can't find MapLibre's worker by itself

const STYLE_URL = 'https://tiles.openfreemap.org/styles/positron'
const REDUCED_MOTION = '(prefers-reduced-motion: reduce)'
const CAN_HOVER = '(hover: hover)' // touch devices get the click popup only
const LOW_RISK = 0 // RiskLevel.Low; a Low heatmap cell gets no hover tip
const TRUCK_MOVE_MS = 500 // one slider step is an hour of driving; long enough to read as motion
const POPUP_OPEN_MS = 220 // popup-in in index.css
const POPUP_CLOSE_MS = 160 // popup-out in index.css
const HEATMAP_ID_RANGE = 1_000_000 // feature ids per plan's heatmap; a plan has a few hundred cells
const MAP_TITLE = 'Map of the routes and checkpoints'
const WEATHER_CREDIT = '<a href="https://open-meteo.com/" target="_blank" rel="noreferrer">Weather data by Open-Meteo.com</a>'
const CONTIGUOUS_US: [LngLat, LngLat] = [
  [-124.8, 24.5],
  [-66.9, 49.4],
]

// On wide screens the trip panel (left) and the legend (bottom right) float over the map; see
// index.css. Routes and popups stay clear of the panel, and of the legend too: beside it when the
// map is wide enough, otherwise above it when the map is tall enough. On narrow screens the panel and
// legend are below the map, and only the zoom buttons (top right) and the attribution (bottom) cover it.
const NARROW_SCREEN = '(max-width: 899px)' // the same query as index.css, so the two always agree
const PANEL_SPACE = 460 // 16 px margin + 400 px panel + a gap
const LEGEND_WIDTH_SPACE = 288 // 228 px legend + 16 px margin + a gap
const LEGEND_HEIGHT_SPACE = 300 // about 245 px legend + 36 px offset + a gap
const MIN_ROUTE_SPACE = 360

function mapPadding(container: HTMLElement): PaddingOptions {
  if (window.matchMedia(NARROW_SCREEN).matches) return { top: 50, bottom: 70, left: 40, right: 50 }
  const { clientWidth: width, clientHeight: height } = container
  if (width - PANEL_SPACE - LEGEND_WIDTH_SPACE >= MIN_ROUTE_SPACE) {
    return { top: 60, bottom: 60, left: PANEL_SPACE, right: LEGEND_WIDTH_SPACE }
  }
  if (height - 60 - LEGEND_HEIGHT_SPACE >= MIN_ROUTE_SPACE) {
    return { top: 60, bottom: LEGEND_HEIGHT_SPACE, left: PANEL_SPACE, right: 60 }
  }
  return { top: 60, bottom: 60, left: PANEL_SPACE, right: 60 }
}

/** Popups keep clear of the panel and the legend on wide screens, and may open above their point
 * (top 0). On narrow screens any padding leaves MapLibre too little room to place them. */
function popupPadding(container: HTMLElement): PaddingOptions | undefined {
  return window.matchMedia(NARROW_SCREEN).matches ? undefined : { ...mapPadding(container), top: 0 }
}

const SOURCES = ['heatmap', 'routes', 'checkpoints', 'route-labels', 'endpoints', 'trucks'] as const
type SourceId = (typeof SOURCES)[number]

const selected: ExpressionSpecification = ['==', ['get', 'selected'], true]
const highlighted: ExpressionSpecification = ['boolean', ['feature-state', 'highlight'], false]
// A heatmap cell's level at the slider's hour, set as feature-state so the slider never rebuilds data.
const cellLevel: ExpressionSpecification = ['number', ['feature-state', 'level'], NO_DATA]

// Drawn below the basemap's labels (in this order), so place names stay readable.
const LAYERS_BELOW_LABELS: LayerSpecification[] = [
  {
    // Under the routes. Low cells are faint and riskier ones stronger, so danger stands out.
    id: 'heatmap',
    type: 'fill',
    source: 'heatmap',
    paint: {
      'fill-color': [
        'match',
        cellLevel,
        0,
        RISK_STYLES[0].color,
        1,
        RISK_STYLES[1].color,
        2,
        RISK_STYLES[2].color,
        3,
        RISK_STYLES[3].color,
        4,
        RISK_STYLES[4].color,
        NO_DATA_STYLE.color,
      ],
      'fill-opacity': ['match', cellLevel, 0, 0.14, 1, 0.32, 2, 0.4, 3, 0.46, 4, 0.52, 0.22],
      'fill-antialias': false, // antialiased edges of neighbouring cells would draw a faint grid
    },
  },
  {
    id: 'route-casing',
    type: 'line',
    source: 'routes',
    layout: { 'line-join': 'round', 'line-cap': 'round', 'line-sort-key': ['get', 'sortKey'] },
    paint: {
      'line-color': '#ffffff',
      'line-width': ['interpolate', ['linear'], ['zoom'], 3, ['case', selected, 7, 5], 10, ['case', selected, 12, 9]],
    },
  },
  {
    id: 'route-lines',
    type: 'line',
    source: 'routes',
    layout: { 'line-join': 'round', 'line-cap': 'round', 'line-sort-key': ['get', 'sortKey'] },
    paint: {
      'line-color': ['get', 'color'],
      'line-width': ['interpolate', ['linear'], ['zoom'], 3, ['case', selected, 4.5, 2.5], 10, ['case', selected, 8, 5]],
      'line-opacity': ['case', selected, 1, 0.75],
    },
  },
  {
    // The route whose card is hovered, drawn again over the others so all of it shows, even where
    // it shares a road with the selected route. Hovering only changes feature-state.
    id: 'route-highlight',
    type: 'line',
    source: 'routes',
    layout: { 'line-join': 'round', 'line-cap': 'round' },
    paint: {
      'line-color': ['get', 'color'],
      'line-width': ['interpolate', ['linear'], ['zoom'], 3, 6, 10, 10],
      'line-opacity': ['case', highlighted, 1, 0],
    },
  },
]

// Drawn above everything. The start and destination are rings around their checkpoint dots, so the
// dots' risk colors show; each ring stays just outside the largest dot (radius + 1.5 px stroke).
const LAYERS_ON_TOP: LayerSpecification[] = [
  {
    id: 'checkpoints',
    type: 'circle',
    source: 'checkpoints',
    layout: { 'circle-sort-key': ['get', 'sortKey'] },
    paint: {
      'circle-color': ['get', 'color'],
      'circle-radius': ['interpolate', ['linear'], ['zoom'], 3, ['case', selected, 4, 3], 8, ['case', selected, 6.5, 5], 12, ['case', selected, 8, 6.5]],
      'circle-stroke-color': '#ffffff',
      'circle-stroke-width': 1.5,
    },
  },
  {
    id: 'endpoints',
    type: 'circle',
    source: 'endpoints',
    paint: {
      'circle-radius': ['interpolate', ['linear'], ['zoom'], 3, 7, 8, 9.5, 12, 11],
      'circle-opacity': 0,
      'circle-stroke-color': '#111827',
      'circle-stroke-width': 3,
    },
  },
  {
    id: 'route-labels',
    type: 'symbol',
    source: 'route-labels',
    layout: {
      'text-field': ['get', 'label'],
      'text-font': ['Noto Sans Bold'], // OpenFreeMap serves single fonts, not font stacks
      'text-size': 18,
      'text-padding': 6,
      'text-allow-overlap': true, // always shown; labelPoint keeps the letters apart
    },
    paint: { 'text-color': ['get', 'color'], 'text-halo-color': '#ffffff', 'text-halo-width': 3 },
  },
  {
    // Where each truck is at the slider's hour: a truck marker in the route's own colour, so it is
    // never mistaken for a risk-coloured checkpoint, with the route's letter beside it. Drawn above
    // everything else. Overlap is allowed so trucks sharing a spot (the origin at hour 0) all show.
    id: 'trucks',
    type: 'symbol',
    source: 'trucks',
    layout: {
      'icon-image': ['get', 'icon'],
      'icon-size': ['interpolate', ['linear'], ['zoom'], 3, ['case', selected, 0.9, 0.78], 10, ['case', selected, 1.15, 1]],
      'icon-allow-overlap': true,
      'icon-ignore-placement': true,
      'icon-rotate': ['get', 'bearing'], // the overhead truck points the way it is driving
      'icon-rotation-alignment': 'map',
      'symbol-sort-key': ['get', 'sortKey'], // the selected route's truck is placed last, on top
      'text-field': ['get', 'label'],
      'text-font': ['Noto Sans Bold'],
      'text-size': 12,
      'text-anchor': 'left',
      'text-offset': [1, -1], // up and to the right of the marker, clear of the road
      'text-allow-overlap': true,
      'text-ignore-placement': true,
    },
    paint: { 'text-color': ['get', 'color'], 'text-halo-color': '#ffffff', 'text-halo-width': 2.5 },
  },
]

export class MapController {
  private readonly map: MapLibreMap
  private popup: Popup | null = null
  private popupKey: string | null = null // which checkpoints the open popup shows
  private popupOpenedAt = 0
  private tip: Popup | null = null // the hover tip: a short summary, not the full popup
  private tipKey: string | null = null
  private plan: Plan | null = null
  private styleReady = false
  private fitPending = false
  private highlightedRoute: number | null = null
  private selectedRoute: string | null = null // drawn blue and on top; at first the recommended one
  private heatmapHour = 0
  private truckMiles: (number | null)[] = [] // the miles the markers are drawn at, animated
  private truckFrom: (number | null)[] = []
  private truckTargets: (number | null)[] = []
  private truckFrame = 0 // requestAnimationFrame handle, 0 when still
  private truckStarted = 0
  private heatmapFirstId = 0 // the current cells' feature ids start here
  private heatmapShown: number[] = [] // each cell's level as last set on the map

  constructor(container: HTMLElement) {
    // RouteMap checks for WebGL 2 first and shows a message instead when it's missing.
    this.map = new MapLibreMap({
      container,
      style: STYLE_URL,
      bounds: CONTIGUOUS_US,
      fitBoundsOptions: { padding: mapPadding(container) },
      attributionControl: { customAttribution: WEATHER_CREDIT },
      locale: { 'Map.Title': MAP_TITLE },
      // North up and flat: there is no compass to undo a rotation or tilt.
      dragRotate: false,
      pitchWithRotate: false,
      touchPitch: false,
    })
    this.map.touchZoomRotate.disableRotation()
    this.map.keyboard.disableRotation()
    this.map.addControl(new NavigationControl({ showCompass: false }), 'top-right')
    // 'style.load' fires once the basemap is ready, and again after a lost WebGL context is restored.
    // MapLibre restores our sources and layers itself then, but not their feature-state, so redraw.
    this.map.on('style.load', () => {
      this.addLayers()
      this.styleReady = true
      this.draw()
    })
    // While the context is lost there is no style, so updates wait for the next 'style.load'.
    this.map.on('webglcontextlost', () => {
      this.styleReady = false
    })
    // A click on a checkpoint (or a start or destination ring) opens its popup; a click anywhere
    // else closes it, and so does Escape anywhere in the map, popup included.
    this.map.on('click', (event) => this.onClick(event))
    this.map.on('mousemove', (event) => this.onHover(event))
    this.map.on('mouseout', () => this.closeTip())
    this.map.getContainer().addEventListener('keydown', this.onKeyDown)
  }

  showPlan(plan: Plan | null): void {
    this.plan = plan
    this.selectedRoute = plan?.recommendation.route_id ?? null
    this.highlightedRoute = null
    this.heatmapHour = 0
    this.closePopup()
    this.closeTip()
    this.stopTrucks()
    this.truckMiles = [] // a new plan places its trucks rather than driving them from the old ones
    this.fitPending = plan !== null
    if (this.styleReady) this.draw()
  }

  /** Make one route the selected one: blue, thicker and on top, with its checkpoints larger. */
  selectRoute(routeId: string | null): void {
    if (routeId === this.selectedRoute) return
    this.selectedRoute = routeId
    if (this.styleReady) this.drawRoutes()
  }

  /** Color the heatmap for one of the plan's forecast hours (0 = the departure's). Only the cells
   * whose level changes are repainted. */
  showHeatmapHour(hour: number): void {
    this.heatmapHour = hour
    if (this.tipKey?.startsWith('cell:')) this.closeTip() // it named the old hour
    if (this.styleReady) {
      this.applyHeatmap()
      this.moveTrucks(true) // the trucks drive to the new hour's position
    }
  }

  /** Emphasize one route (while its card is hovered), or none. */
  highlightRoute(routeId: string | null): void {
    const index = routeId === null ? -1 : (this.plan?.routes.findIndex((route) => route.id === routeId) ?? -1)
    this.highlightedRoute = index >= 0 ? index : null
    if (this.styleReady) this.applyHighlight()
  }

  destroy(): void {
    this.map.getContainer().removeEventListener('keydown', this.onKeyDown)
    this.stopTrucks()
    this.closeTip()
    this.popup?.remove()
    this.popup = null
    this.map.remove()
  }

  private readonly onKeyDown = (event: KeyboardEvent): void => {
    if (event.key === 'Escape') this.closePopup()
  }

  private addLayers(): void {
    // The truck images must exist before the symbol layer references them. A reloaded style drops
    // them, so this runs on every 'style.load'.
    for (const color of TRUCK_ICON_COLORS) {
      const id = truckIconId(color)
      if (!this.map.hasImage(id)) {
        const image = truckIcon(color)
        if (image) this.map.addImage(id, image, { pixelRatio: TRUCK_ICON_RATIO })
      }
    }
    for (const id of SOURCES) {
      if (!this.map.getSource(id)) this.map.addSource(id, { type: 'geojson', data: EMPTY })
    }
    const firstLabel = this.map.getLayersOrder().find((id) => this.map.getLayer(id)?.type === 'symbol')
    for (const layer of LAYERS_BELOW_LABELS) {
      if (!this.map.getLayer(layer.id)) this.map.addLayer(layer, firstLabel)
    }
    for (const layer of LAYERS_ON_TOP) {
      if (!this.map.getLayer(layer.id)) this.map.addLayer(layer)
    }
  }

  private setData(id: SourceId, data: FeatureCollection): void {
    void (this.map.getSource(id) as GeoJSONSource).setData(data)
  }

  private draw(): void {
    const plan = this.plan
    // New cells get new ids. The map swaps in the new cells a few frames later (setData is
    // asynchronous), and until then the old cells keep their own colors.
    this.heatmapFirstId += HEATMAP_ID_RANGE
    const firstId = this.heatmapFirstId
    this.setData('heatmap', plan ? heatmapCells(plan, firstId) : EMPTY)
    this.heatmapShown = []
    this.applyHeatmap()
    // Once no tile has the old cells, drop their states and set the current ones again.
    this.map.once('idle', () => {
      if (firstId !== this.heatmapFirstId) return // a newer plan has taken over
      this.map.removeFeatureState({ source: 'heatmap' })
      this.heatmapShown = []
      this.applyHeatmap()
    })
    this.moveTrucks(false)
    this.drawRoutes()
    this.setData('endpoints', plan ? endpoints(plan) : EMPTY)
    this.applyHighlight()
    if (plan && this.fitPending) {
      const padding = mapPadding(this.map.getContainer())
      this.map.fitBounds(planBounds(plan), { padding, maxZoom: 10, duration: 700 })
    }
    this.fitPending = false
  }

  /** The routes, their checkpoints and letters, styled by which route is selected. */
  private drawRoutes(): void {
    const plan = this.plan
    this.setData('routes', plan ? routeLines(plan, this.selectedRoute) : EMPTY)
    this.setData('checkpoints', plan ? checkpointPoints(plan, this.selectedRoute) : EMPTY)
    this.setData('route-labels', plan ? routeLabels(plan, this.selectedRoute) : EMPTY)
    this.drawTrucks()
  }

  /** The truck markers at whatever miles they are currently drawn at. */
  private drawTrucks(): void {
    const plan = this.plan
    this.setData('trucks', plan ? truckPositions(plan, this.truckMiles, this.selectedRoute) : EMPTY)
  }

  /** Send the trucks to where they are at the slider's hour. Animated, they drive there along the
   * road, because the miles are what is interpolated and every mile is placed on the route line. */
  private moveTrucks(animate: boolean): void {
    const plan = this.plan
    if (!plan) {
      this.stopTrucks()
      this.truckMiles = []
      this.drawTrucks()
      return
    }
    const targets = truckMiles(plan, this.heatmapHour)
    const settled =
      !animate ||
      this.truckMiles.length !== targets.length ||
      window.matchMedia(REDUCED_MOTION).matches
    if (settled) {
      this.stopTrucks()
      this.truckMiles = targets
      this.drawTrucks()
      return
    }
    // Re-aim from wherever the trucks are now, so dragging the slider makes them chase the hour
    // rather than restarting from the last whole hour.
    this.truckFrom = this.truckMiles
    this.truckTargets = targets
    this.truckStarted = performance.now()
    if (!this.truckFrame) this.truckFrame = requestAnimationFrame(this.stepTrucks)
  }

  private readonly stepTrucks = (now: number): void => {
    const share = Math.min(1, (now - this.truckStarted) / TRUCK_MOVE_MS)
    const eased = share * (2 - share) // ease out, so a truck settles instead of stopping dead
    this.truckMiles = this.truckTargets.map((target, index) => {
      const from = this.truckFrom[index]
      // A route that arrives or reappears has no mile to travel between, so it just moves.
      if (target === null || from === null || from === undefined) return target
      return from + (target - from) * eased
    })
    this.drawTrucks()
    this.truckFrame = share < 1 ? requestAnimationFrame(this.stepTrucks) : 0
  }

  private stopTrucks(): void {
    if (this.truckFrame) cancelAnimationFrame(this.truckFrame)
    this.truckFrame = 0
  }

  private applyHeatmap(): void {
    const levels = this.plan ? cellLevels(this.plan, this.heatmapHour) : []
    for (const [cell, level] of levelChanges(this.heatmapShown, levels)) {
      this.map.setFeatureState({ source: 'heatmap', id: this.heatmapFirstId + cell }, { level })
    }
    this.heatmapShown = levels
  }

  private applyHighlight(): void {
    this.map.removeFeatureState({ source: 'routes' })
    if (this.highlightedRoute !== null) {
      this.map.setFeatureState({ source: 'routes', id: this.highlightedRoute }, { highlight: true })
    }
  }

  /** Cursor, plus a hover tip: the checkpoint under the pointer, or failing that the heatmap cell,
   * so a coloured cell can say why it has its colour. Skipped for a spot the open popup already
   * shows in full, and on devices that can't really hover. */
  private onHover(event: MapMouseEvent): void {
    const features = this.checkpointsAt(event)
    this.setCursor(features.length > 0 ? 'pointer' : '')
    const plan = this.plan
    if (!plan || !window.matchMedia(CAN_HOVER).matches) {
      this.closeTip()
      return
    }
    if (features.length === 0) {
      this.tipForCell(event)
      return
    }
    const routeIndex = Number(features[0].properties.routeIndex) // the topmost checkpoint drawn
    const checkpointIndex = Number(features[0].properties.checkpointIndex)
    const route = plan.routes[routeIndex]
    if (route?.checkpoints[checkpointIndex] === undefined) {
      this.closeTip()
      return
    }
    const key = `${route.id}:${checkpointIndex}`
    if (this.popupKey?.split(' ').includes(key)) {
      this.closeTip() // the popup is already showing this one
      return
    }
    if (key === this.tipKey) return // already tipped
    const checkpoint = route.checkpoints[checkpointIndex]
    // Offset clears the dot, so the tip never sits under the pointer that opened it.
    this.showTip([checkpoint.lon, checkpoint.lat], checkpointTip(route, checkpointIndex), key, 14)
  }

  /** The heatmap cell under the pointer, at the slider's hour. Anchored where the pointer entered
   * the cell, so the tip holds still while the pointer stays inside it. */
  private tipForCell(event: MapMouseEvent): void {
    const plan = this.plan
    if (!plan) return
    const hit = this.map.queryRenderedFeatures(event.point, { layers: ['heatmap'] })[0]
    const index = hit === undefined ? -1 : Number(hit.properties.index)
    const cell = plan.heatmap.cells[index]
    if (cell === undefined) {
      this.closeTip()
      return
    }
    const level = riskAt(cell.levels, this.heatmapHour)
    // A Low cell has nothing worth saying, and most of the map is Low, so it gets no tip.
    if (level === LOW_RISK) {
      this.closeTip()
      return
    }
    const key = `cell:${index}:${this.heatmapHour}`
    if (key === this.tipKey) return
    this.showTip(
      event.lngLat.toArray() as LngLat,
      heatmapTip(
        level,
        causeAt(cell.causes, this.heatmapHour),
        readingAt(cell.values, this.heatmapHour),
        plan.heatmap.hours[this.heatmapHour],
      ),
      key,
      6,
    )
  }

  /** Replaces whatever tip is open with this one. */
  private showTip(at: LngLat, content: HTMLElement, key: string, offset: number): void {
    this.closeTip()
    const tip = new Popup({
      closeButton: false,
      closeOnClick: false,
      maxWidth: '250px',
      className: 'checkpoint-tip',
      offset,
      focusAfterOpen: false, // hovering must never move keyboard focus
    })
    tip.setLngLat(at).setDOMContent(content).addTo(this.map)
    this.tip = tip
    this.tipKey = key
  }

  private closeTip(): void {
    this.tip?.remove()
    this.tip = null
    this.tipKey = null
  }

  private onClick(event: MapMouseEvent): void {
    if (!this.styleReady) return
    const features = this.checkpointsAt(event)
    if (features.length > 0) this.openPopup(features)
    else this.closePopup()
  }

  /** The checkpoints under the pointer. A start or destination ring counts as the checkpoints at
   * its centre, since the ring is drawn outside their dots. */
  private checkpointsAt(event: MapMouseEvent): MapGeoJSONFeature[] {
    if (!this.styleReady) return []
    const ring = this.map.queryRenderedFeatures(event.point, { layers: ['endpoints'] })[0]
    const at = ring?.geometry.type === 'Point' ? this.map.project(ring.geometry.coordinates as LngLat) : event.point
    return this.map.queryRenderedFeatures(at, { layers: ['checkpoints'] })
  }

  /** Shows the clicked checkpoint, and those of other routes at the same spot (such as the
   * destination), the selected route first. */
  private openPopup(features: MapGeoJSONFeature[]): void {
    const plan = this.plan
    if (!plan) return
    const hits = new Map<number, number>() // route index -> checkpoint index (the topmost per route)
    for (const feature of features) {
      const routeIndex = Number(feature.properties.routeIndex)
      if (!hits.has(routeIndex)) hits.set(routeIndex, Number(feature.properties.checkpointIndex))
    }
    const order = (routeIndex: number) => (plan.routes[routeIndex]?.id === this.selectedRoute ? -1 : routeIndex)
    const entries: PopupEntry[] = [...hits]
      .sort(([a], [b]) => order(a) - order(b))
      .map(([routeIndex, checkpointIndex]) => ({ route: plan.routes[routeIndex], checkpointIndex }))
      .filter(({ route, checkpointIndex }) => route?.checkpoints[checkpointIndex] !== undefined)
    if (entries.length === 0) return
    const key = entries.map(({ route, checkpointIndex }) => `${route.id}:${checkpointIndex}`).join(' ')
    if (this.popup && key === this.popupKey) return // already showing these
    const { route, checkpointIndex } = entries[0]
    const checkpoint = route.checkpoints[checkpointIndex]
    // A new popup each time, so the old one can fade out while this one fades in. Closing is
    // handled here (onClick, the close button, Escape) so that it can be animated too.
    this.closePopup()
    this.closeTip()
    const popup = new Popup({
      closeButton: false,
      closeOnClick: false,
      maxWidth: '340px',
      className: 'checkpoint-popup',
      padding: popupPadding(this.map.getContainer()),
    })
    const close = () => {
      if (this.popup === popup) this.closePopup() // a popup that is already fading can't close the new one
    }
    popup.setLngLat([checkpoint.lon, checkpoint.lat]).setDOMContent(checkpointsPopup(entries, close)).addTo(this.map)
    this.popup = popup
    this.popupKey = key
    this.popupOpenedAt = performance.now()
  }

  /** Fades the open popup out, then removes it. */
  private closePopup(): void {
    const popup = this.popup
    if (!popup) return
    this.popup = null
    this.popupKey = null
    const element = popup.getElement()
    if (element?.contains(document.activeElement)) this.map.getCanvas().focus({ preventScroll: true })
    // A popup still opening goes at once: fading it out would first snap it to full size.
    const opening = performance.now() - this.popupOpenedAt < POPUP_OPEN_MS
    if (!element || opening || window.matchMedia(REDUCED_MOTION).matches) {
      popup.remove()
      return
    }
    element.classList.add('closing') // fades out and stops taking clicks (index.css)
    window.setTimeout(() => popup.remove(), POPUP_CLOSE_MS)
  }

  private setCursor(cursor: string): void {
    this.map.getCanvas().style.cursor = cursor
  }
}
