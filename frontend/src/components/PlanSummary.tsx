import { type CSSProperties, memo, useId, useRef } from 'react'
import { formatDateTime, formatDuration, formatMiles, formatNumber } from '../format'
import { NO_DATA_STYLE, RISK_STYLES, routeColors } from '../risk'
import type { Plan, Route, RouteMiles } from '../types'

interface Props {
  plan: Plan
  selectedRoute: string | null
  onSelect: (routeId: string) => void
  onHighlight: (routeId: string | null) => void
}

/** The block's place in the entrance animation: each slides in a moment after the one above it. */
function entrance(order: number): CSSProperties {
  return { '--order': order } as CSSProperties
}

// Memoized: moving the heatmap slider re-renders the page, but the cards only change with the plan
// and the selection.
export const PlanSummary = memo(function PlanSummary({ plan, selectedRoute, onSelect, onHighlight }: Props) {
  const id = useId()
  const recommended = plan.routes.find((route) => route.id === plan.recommendation.route_id)
  const colors = routeColors(plan.routes, selectedRoute)
  return (
    <section className="plan-summary" aria-label="Routes">
      <div className={`recommendation${recommended?.unsafe ? ' unsafe' : ''}`} style={entrance(0)}>
        <h2>Recommended: Route {plan.recommendation.route_id}</h2>
        <p>{plan.recommendation.reason}</p>
        {plan.recommendation.warnings.map((warning) => (
          <p key={warning} className="warning">
            {warning}
          </p>
        ))}
      </div>

      {plan.notices.map((notice) => (
        <p key={notice} className="notice" style={entrance(1)}>
          {notice}
        </p>
      ))}

      {/* One choice among the routes: a click anywhere on a card, or the arrow keys, selects one. */}
      <div role="radiogroup" aria-label="Choose a route to show on the map">
        <ol className="route-cards">
          {plan.routes.map((route, index) => (
            <RouteCard
              key={route.id}
              group={`${id}-route`}
              route={route}
              color={colors[index]}
              order={index + 1}
              selected={route.id === selectedRoute}
              onSelect={onSelect}
              onHighlight={onHighlight}
            />
          ))}
        </ol>
      </div>
    </section>
  )
})

interface CardProps {
  group: string // the radio buttons' name
  route: Route
  color: string
  order: number
  selected: boolean
  onSelect: (routeId: string) => void
  onHighlight: (routeId: string | null) => void
}

function RouteCard({ group, route, color, order, selected, onSelect, onHighlight }: CardProps) {
  const headerId = useId()
  const radio = useRef<HTMLInputElement>(null)
  function choose() {
    onSelect(route.id)
    radio.current?.focus({ preventScroll: true }) // so the arrow keys carry on from this card
  }
  // Only hovering highlights a route. Focus doesn't need to: the focused radio is always the
  // selected route, which the map already draws on top.
  return (
    <li
      className={`route-card${selected ? ' selected' : ''}`}
      style={entrance(order)}
      onClick={choose}
      onMouseEnter={() => onHighlight(route.id)}
      onMouseLeave={() => onHighlight(null)}
    >
      {/* The card's own radio button: hidden, but it takes focus and the arrow keys. */}
      <input
        ref={radio}
        type="radio"
        className="visually-hidden"
        name={group}
        checked={selected}
        onChange={() => onSelect(route.id)}
        aria-labelledby={headerId}
      />
      <div className="route-card-header" id={headerId}>
        <span className="route-swatch" style={{ background: color }} aria-hidden="true" />
        <h3>Route {route.id}</h3>
        {route.via && <span className="tag">through a via point</span>}
        {route.recommended && <span className="badge recommended">Recommended</span>}
        {route.unsafe && <span className="badge unsafe">Unsafe</span>}
        <span className="route-check" aria-hidden="true" />
      </div>
      <dl className="route-stats">
        <div>
          <dt>Distance</dt>
          <dd>{formatMiles(route.distance_mi)}</dd>
        </div>
        <div>
          <dt>Travel time</dt>
          <dd>{formatDuration(route.travel_time_min)}</dd>
        </div>
        <div>
          <dt>Average risk</dt>
          <dd>{route.average_risk === null ? 'No data' : `${formatNumber(route.average_risk, 2)} / 4`}</dd>
        </div>
        <div className="wide">
          <dt>Arrives</dt>
          <dd>{formatDateTime(route.arrival)}</dd>
        </div>
      </dl>
      <RiskBar miles={route.miles} />
      <dl className="risk-miles">
        <RiskMiles label="No Travel" miles={route.miles.no_travel} color={RISK_STYLES[4].color} />
        <RiskMiles label="Severe" miles={route.miles.severe} color={RISK_STYLES[3].color} />
        <RiskMiles label="High" miles={route.miles.high} color={RISK_STYLES[2].color} />
        {route.miles.no_data > 0 && <RiskMiles label="No data" miles={route.miles.no_data} color={NO_DATA_STYLE.color} />}
      </dl>
    </li>
  )
}

function RiskMiles({ label, miles, color }: { label: string; miles: number; color: string }) {
  return (
    <div className={miles > 0 ? 'nonzero' : undefined}>
      <dt>
        <span className="dot" style={{ background: color }} aria-hidden="true" />
        {label}
      </dt>
      <dd>{formatMiles(miles)}</dd>
    </div>
  )
}

const BAR_PARTS: { key: keyof RouteMiles; label: string; color: string }[] = [
  { key: 'low', label: RISK_STYLES[0].label, color: RISK_STYLES[0].color },
  { key: 'moderate', label: RISK_STYLES[1].label, color: RISK_STYLES[1].color },
  { key: 'high', label: RISK_STYLES[2].label, color: RISK_STYLES[2].color },
  { key: 'severe', label: RISK_STYLES[3].label, color: RISK_STYLES[3].color },
  { key: 'no_travel', label: RISK_STYLES[4].label, color: RISK_STYLES[4].color },
  { key: 'no_data', label: NO_DATA_STYLE.label, color: NO_DATA_STYLE.color },
]

/** The route's miles by risk level, as one bar. */
function RiskBar({ miles }: { miles: RouteMiles }) {
  const total = BAR_PARTS.reduce((sum, part) => sum + miles[part.key], 0)
  if (total <= 0) return null
  const description = BAR_PARTS.filter((part) => miles[part.key] > 0)
    .map((part) => `${part.label} ${formatMiles(miles[part.key])}`)
    .join(', ')
  return (
    <div className="risk-bar" role="img" aria-label={`Miles by risk level: ${description}`}>
      {BAR_PARTS.map((part) =>
        miles[part.key] > 0 ? (
          <span
            key={part.key}
            title={`${part.label}: ${formatMiles(miles[part.key])}`}
            style={{ flexGrow: miles[part.key], background: part.color }}
          />
        ) : null,
      )}
    </div>
  )
}
