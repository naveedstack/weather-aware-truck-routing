import { type CSSProperties, useId } from 'react'
import { formatDateTime, fromDeparture } from '../format'

interface Props {
  hours: string[] // the heatmap's forecast hours (UTC ISO); hour 0 is the one nearest the departure
  departure: string
  hour: number
  onChange: (hour: number) => void
  /** True once the hour is past every route's arrival, so no truck is on the road. */
  arrived?: boolean
}

const TICKS = [0, 12, 24, 36, 48]

/** Picks the forecast hour the map's heatmap shows. It only recolors the map; nothing is fetched. */
export function HeatmapSlider({ hours, departure, hour, onChange, arrived = false }: Props) {
  const id = useId()
  const last = hours.length - 1
  const time = formatDateTime(hours[hour])
  const offset = fromDeparture(hours[hour], departure)
  return (
    <section className="heatmap-slider" aria-labelledby={`${id}-title`}>
      {/* Three lines that never wrap, so the panel doesn't jump while the slider is dragged. */}
      <h2 id={`${id}-title`}>Weather heatmap</h2>
      <p className="heatmap-time">{time}</p>
      <p className="heatmap-offset">{arrived ? `${offset} · all routes arrived` : offset}</p>
      <input
        type="range"
        min={0}
        max={last}
        step={1}
        value={hour}
        onChange={(event) => onChange(Number(event.target.value))}
        aria-labelledby={`${id}-title`}
        aria-valuetext={`${time}, ${offset}`}
      />
      <div className="heatmap-ticks" aria-hidden="true">
        {TICKS.filter((tick) => tick <= last).map((tick) => (
          // Centred where the thumb sits for that hour.
          <span key={tick} style={{ '--at': tick / last } as CSSProperties}>
            {tick === 0 ? '0 h' : `+${tick} h`}
          </span>
        ))}
      </div>
    </section>
  )
}
