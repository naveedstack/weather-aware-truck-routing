import type { Ref } from 'react'
import { formatDateTime, formatPounds } from '../format'

export interface TripDetails {
  origin: string
  destination: string
  departure: string // ISO 8601
  load_lb: number
  interval_mi: number
}

interface Props {
  trip: TripDetails
  busy: boolean
  /** Opens the form again; left out while the form is already open. */
  onChange?: () => void
  changeRef?: Ref<HTMLButtonElement>
}

/** The trip whose routes are shown (or are being planned), with a button to change it. */
export function TripBar({ trip, busy, onChange, changeRef }: Props) {
  return (
    <div className="trip-bar">
      <p className="trip-places">
        {trip.origin} → {trip.destination}
      </p>
      {busy ? (
        <span className="trip-status">
          <span className="spinner" aria-hidden="true" />
          Planning…
        </span>
      ) : (
        onChange && (
          <button type="button" className="secondary" onClick={onChange} ref={changeRef}>
            Change trip
          </button>
        )
      )}
      <p className="trip-details">
        Departs {formatDateTime(trip.departure)} · {formatPounds(trip.load_lb)} · checkpoints every{' '}
        {trip.interval_mi} mi
      </p>
    </div>
  )
}
