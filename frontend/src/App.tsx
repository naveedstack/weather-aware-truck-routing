import { useEffect, useLayoutEffect, useRef, useState } from 'react'
import { PlanRequestError, planTrip } from './api'
import { HeatmapSlider } from './components/HeatmapSlider'
import { Legend } from './components/Legend'
import { PlanLoading } from './components/PlanLoading'
import { PlanSummary } from './components/PlanSummary'
import { RouteMap } from './components/RouteMap'
import { type TripDetails, TripBar } from './components/TripBar'
import { TripForm } from './components/TripForm'
import { supportsWebGL2 } from './map/webgl'
import type { Plan, TripRequest } from './types'

// Screen readers hear this when planning starts, and resultMessage() when the plan arrives.
const PROGRESS = 'Finding routes and forecasts… long trips take up to about 20 seconds.'
const STEP_MS = 2000
const ALMOST_THERE = 'Almost there… long trips take up to about 20 seconds.'

/** What the server does for a plan, in order. The browser can't see its progress, so the steps
 * follow typical timings (the routes take longest) and stay on the last one until the answer. */
function planningSteps({ origin, destination, interval_mi }: TripRequest): string[] {
  return [
    `Finding ${origin} and ${destination}…`,
    'Getting truck routes from TomTom…',
    'Looking for alternative routes…',
    `Placing checkpoints every ${interval_mi} miles…`,
    "Getting the weather at each checkpoint's ETA…",
    'Rating the risk and comparing the routes…',
  ]
}

function planningMessage(request: TripRequest, step: number): string {
  const steps = planningSteps(request)
  if (step < steps.length) return steps[step]
  return step > steps.length ? ALMOST_THERE : steps[steps.length - 1]
}

function resultMessage(plan: Plan): string {
  const { route_id, warnings } = plan.recommendation
  return [`Routes ready. Recommended: Route ${route_id}.`, ...warnings].join(' ')
}

function tripOf(plan: Plan): TripDetails {
  const { origin, destination, departure, load_lb, interval_mi } = plan
  return { origin: origin.name, destination: destination.name, departure, load_lb, interval_mi }
}

/** Whether the slider's hour is past every route's arrival, so no truck marker is on the map. */
function allArrived(plan: Plan, hour: number): boolean {
  const at = Date.parse(plan.heatmap.hours[hour] ?? plan.departure)
  return plan.routes.every((route) => at > Date.parse(route.arrival))
}

function scrollBehavior(): ScrollBehavior {
  return window.matchMedia('(prefers-reduced-motion: reduce)').matches ? 'auto' : 'smooth'
}

type FocusTarget = 'form' | 'change-trip' | 'results'

export default function App() {
  const [plan, setPlan] = useState<Plan | null>(null)
  const [planRequest, setPlanRequest] = useState<TripRequest | null>(null) // the trip behind `plan`
  const [pending, setPending] = useState<TripRequest | null>(null) // the trip being planned
  const [step, setStep] = useState(0) // of planningSteps, while pending
  const [editing, setEditing] = useState(true) // the form is open
  const [formKey, setFormKey] = useState(0) // a new key gives a fresh form, filled from planRequest
  const [error, setError] = useState<PlanRequestError | null>(null)
  const [announcement, setAnnouncement] = useState('')
  const [selectedRoute, setSelectedRoute] = useState<string | null>(null) // at first the recommended one
  const [highlightedRoute, setHighlightedRoute] = useState<string | null>(null)
  const [heatmapHour, setHeatmapHour] = useState(0) // each new plan starts at hour 0, its departure's
  const [mapFailed, setMapFailed] = useState(() => !supportsWebGL2()) // then no heatmap slider or legend
  const formArea = useRef<HTMLDivElement>(null)
  const changeTripButton = useRef<HTMLButtonElement>(null)
  const results = useRef<HTMLDivElement>(null)
  const focusNext = useRef<FocusTarget | null>(null)
  const busy = pending !== null

  // After the panel changes, move keyboard focus to the next step, so it never falls back to the
  // page because the element that had it was hidden. A layout effect runs in the same commit as
  // the change, and preventScroll keeps the panel from jumping while the form slides.
  useLayoutEffect(() => {
    const target = focusNext.current
    focusNext.current = null
    if (target === 'form') {
      const form = formArea.current
      const first = form?.querySelector<HTMLElement>('[aria-invalid="true"]') ?? form?.querySelector<HTMLElement>('input')
      first?.focus({ preventScroll: true })
      form?.closest('.panel')?.scrollTo({ top: 0, behavior: scrollBehavior() })
    } else if (target === 'change-trip') {
      changeTripButton.current?.focus({ preventScroll: true })
    } else if (target === 'results') {
      results.current?.focus({ preventScroll: true })
    }
  })

  // While planning, step through what the server does, every two seconds.
  useEffect(() => {
    if (!pending) return
    const timer = window.setInterval(() => setStep((current) => current + 1), STEP_MS)
    return () => window.clearInterval(timer)
  }, [pending])

  // The form closes while a plan is computed, so only one request runs at a time.
  async function submit(request: TripRequest) {
    setPending(request)
    setStep(0)
    setEditing(false)
    setError(null)
    setAnnouncement(PROGRESS)
    focusNext.current = 'results'
    try {
      const next = await planTrip(request)
      setPlan(next)
      setPlanRequest(request)
      setSelectedRoute(next.recommendation.route_id)
      setHighlightedRoute(null)
      setHeatmapHour(0)
      setAnnouncement(resultMessage(next))
    } catch (failure) {
      if (failure instanceof PlanRequestError) {
        setError(failure)
      } else {
        console.error(failure) // a bug, not a server answer
        setError(new PlanRequestError('Something went wrong.'))
      }
      setAnnouncement('') // the alert says what happened
      setEditing(true) // to fix the trip and try again
      focusNext.current = 'form'
    } finally {
      setPending(null)
    }
  }

  function changeTrip() {
    setEditing(true)
    focusNext.current = 'form'
  }

  function cancel() {
    setEditing(false)
    setError(null)
    setFormKey((key) => key + 1) // drop the edits: the next Change trip starts from the trip on screen
    focusNext.current = 'change-trip'
  }

  // The bar names the trip being planned, or the one whose routes are shown.
  const trip = pending ?? (plan && tripOf(plan))
  const status = pending && planningMessage(pending, step)

  return (
    <div className="app">
      <RouteMap
        plan={plan}
        selectedRoute={selectedRoute}
        highlightedRoute={highlightedRoute}
        heatmapHour={heatmapHour}
        status={status}
        failed={mapFailed}
        onFailure={setMapFailed}
      />
      <main className="panel">
        <header className="panel-header">
          <h1>Weather-Aware Truck Routing</h1>
          <p>Three truck routes, rated by the weather the truck will meet on the way.</p>
        </header>
        <div ref={formArea} className={editing ? 'collapsible open' : 'collapsible'} inert={!editing}>
          <div className="collapsible-inner">
            <TripForm
              key={formKey}
              initial={planRequest ?? undefined}
              busy={busy}
              errors={error?.fields ?? {}}
              onSubmit={submit}
              onCancel={plan ? cancel : undefined}
            />
          </div>
        </div>
        {trip && (
          <TripBar trip={trip} busy={busy} onChange={editing ? undefined : changeTrip} changeRef={changeTripButton} />
        )}
        {/* Screen readers hear progress and results from this region; it takes no space. */}
        <p className="visually-hidden" aria-live="polite">
          {announcement}
        </p>
        {error && (
          <p className="error" role="alert">
            {error.message}
          </p>
        )}
        {plan && !busy && !mapFailed && plan.heatmap.hours.length > 0 && (
          <HeatmapSlider
            hours={plan.heatmap.hours}
            departure={plan.departure}
            hour={heatmapHour}
            onChange={setHeatmapHour}
            arrived={allArrived(plan, heatmapHour)}
          />
        )}
        <div ref={results} className="results" tabIndex={-1}>
          {/* PlanLoading takes PlanSummary's place while planning, so every new plan mounts it
              afresh and its cards slide in again. */}
          {status ? (
            <PlanLoading message={status} />
          ) : plan ? (
            <PlanSummary
              plan={plan}
              selectedRoute={selectedRoute}
              onSelect={setSelectedRoute}
              onHighlight={setHighlightedRoute}
            />
          ) : (
            <p className="empty">Enter a trip to compare its routes.</p>
          )}
        </div>
      </main>
      {!mapFailed && <Legend />}
    </div>
  )
}
