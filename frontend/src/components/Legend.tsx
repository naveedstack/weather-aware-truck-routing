import { NO_DATA_STYLE, OTHER_ROUTE_COLORS, RISK_LEVELS, RISK_STYLES, SELECTED_ROUTE_COLOR } from '../risk'

// The other routes' two colors, side by side in one swatch.
const OTHER_ROUTES_SWATCH = `linear-gradient(90deg, ${OTHER_ROUTE_COLORS[0]} 0 45%, transparent 45% 55%, ${OTHER_ROUTE_COLORS[1]} 55%)`

/** Every swatch sits in a slot of one width, so all the labels line up in a single column. */
function Swatch({ children }: { children: React.ReactNode }) {
  return (
    <span className="legend-swatch" aria-hidden="true">
      {children}
    </span>
  )
}

export function Legend() {
  return (
    <aside className="legend" aria-label="Map legend">
      <h2>Risk level</h2>
      {/* The five levels, worst last; "No data" is not a step on the scale, so it sits apart. */}
      <ul className="legend-levels">
        {RISK_LEVELS.map((level) => (
          <li key={level}>
            <Swatch>
              <span className="legend-dot" style={{ background: RISK_STYLES[level].color }} />
            </Swatch>
            {RISK_STYLES[level].label}
          </li>
        ))}
      </ul>
      <p className="legend-nodata">
        <Swatch>
          <span className="legend-dot" style={{ background: NO_DATA_STYLE.color }} />
        </Swatch>
        {NO_DATA_STYLE.label} — no forecast for that place and hour
      </p>

      <h2 className="legend-keys-title">On the map</h2>
      <ul className="legend-keys">
        <li>
          <Swatch>
            <span className="legend-line selected" style={{ background: SELECTED_ROUTE_COLOR }} />
          </Swatch>
          Selected route
        </li>
        <li>
          <Swatch>
            <span className="legend-line" style={{ background: OTHER_ROUTES_SWATCH }} />
          </Swatch>
          Other routes
        </li>
        <li>
          <Swatch>
            <span className="legend-dot outlined" />
          </Swatch>
          Checkpoint <span className="legend-hint">hover or click</span>
        </li>
        <li>
          <Swatch>
            <span className="legend-ring" />
          </Swatch>
          Start and destination
        </li>
        <li>
          <Swatch>
            {/* The map's marker: a truck seen from above, pointing the way it drives. */}
            <svg className="legend-truck" viewBox="0 0 20 20">
              <circle cx="10" cy="10" r="8.4" fill={SELECTED_ROUTE_COLOR} stroke="#ffffff" strokeWidth="1.7" />
              <path d="M8.1 5h3.8v2.5H8.1zM7.5 8h5v6.6h-5z" fill="#ffffff" />
            </svg>
          </Swatch>
          Truck at the slider's hour
        </li>
        <li>
          <Swatch>
            <span className="legend-cell" />
          </Swatch>
          Heatmap at the slider's hour
        </li>
      </ul>
    </aside>
  )
}
