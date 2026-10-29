import { type FormEvent, useId, useState } from 'react'
import { browserTimeZone, lastForecastHour, nextFullHour, toLocalInputValue } from '../format'
import { INTERVALS, type IntervalMi, type TripRequest } from '../types'
import { PlaceInput } from './PlaceInput'

const MAX_LOAD_LB = 80_000
const DEPARTURE_GRACE_MS = 15 * 60 * 1000 // the server accepts departures up to 15 minutes ago

interface Props {
  /** The values to start from (the trip on screen); the defaults when left out. */
  initial?: TripRequest
  busy: boolean
  errors: Record<string, string> // from the server, by field name
  onSubmit: (request: TripRequest) => void
  /** Closes the form without planning; given when there is a trip on screen to go back to. */
  onCancel?: () => void
}

export function TripForm({ initial, busy, errors, onSubmit, onCancel }: Props) {
  const id = useId()
  // The departure's limits move with the clock; they are refreshed whenever the field gets focus.
  const [now, setNow] = useState(() => new Date())
  const [origin, setOrigin] = useState(initial?.origin ?? '')
  const [destination, setDestination] = useState(initial?.destination ?? '')
  const [departure, setDeparture] = useState(() =>
    toLocalInputValue(initial ? new Date(initial.departure) : nextFullHour(now)),
  )
  const [load, setLoad] = useState(initial ? String(initial.load_lb) : '35000')
  const [interval, setIntervalMi] = useState<IntervalMi>(initial?.interval_mi ?? 25)

  function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    // datetime-local values are in the browser's time zone; the API gets the instant with an offset.
    onSubmit({
      origin: origin.trim(),
      destination: destination.trim(),
      departure: new Date(departure).toISOString(),
      load_lb: Number(load),
      interval_mi: interval,
    })
  }

  const errorId = (name: string) => (errors[name] ? `${id}-${name}-error` : undefined)
  const field = (name: string, hint?: string) => {
    const described = [hint, errorId(name)].filter(Boolean).join(' ')
    return {
      id: `${id}-${name}`,
      'aria-invalid': errors[name] ? true : undefined,
      'aria-describedby': described || undefined,
    }
  }
  const error = (name: string) =>
    errors[name] ? (
      <p className="field-error" id={errorId(name)}>
        {errors[name]}
      </p>
    ) : null

  return (
    <form className="trip-form" onSubmit={submit} aria-busy={busy}>
      {/* Both suggest cities as they're typed, but take any place typed in full. */}
      <div className="field">
        <label htmlFor={`${id}-origin`}>From</label>
        <PlaceInput
          {...field('origin')}
          value={origin}
          onChange={setOrigin}
          placeholder="City, state or address, e.g. Dallas, TX"
          maxLength={200}
          required
        />
        {error('origin')}
      </div>
      <div className="field">
        <label htmlFor={`${id}-destination`}>To</label>
        <PlaceInput
          {...field('destination')}
          value={destination}
          onChange={setDestination}
          placeholder="e.g. Denver, CO"
          maxLength={200}
          required
        />
        {error('destination')}
      </div>
      <div className="field">
        <label htmlFor={`${id}-departure`}>Departure</label>
        <input
          {...field('departure', `${id}-departure-hint`)}
          type="datetime-local"
          value={departure}
          onChange={(event) => setDeparture(event.target.value)}
          onFocus={() => setNow(new Date())}
          min={toLocalInputValue(new Date(now.getTime() - DEPARTURE_GRACE_MS))}
          max={toLocalInputValue(lastForecastHour(now))}
          required
        />
        <p className="field-hint" id={`${id}-departure-hint`}>
          Your time zone: {browserTimeZone()}
        </p>
        {error('departure')}
      </div>
      <div className="field-row">
        <div className="field">
          <label htmlFor={`${id}-load_lb`}>Load (lb)</label>
          <input
            {...field('load_lb')}
            type="number"
            inputMode="numeric"
            min={0}
            max={MAX_LOAD_LB}
            step={1}
            value={load}
            onChange={(event) => setLoad(event.target.value)}
            required
          />
          {error('load_lb')}
        </div>
        {/* Radio buttons drawn as one button group: one choice, and arrow keys move between them. */}
        <div className="field">
          <span className="field-label" id={`${id}-interval-label`}>
            Checkpoints every
          </span>
          <div
            className="segmented"
            role="radiogroup"
            aria-labelledby={`${id}-interval-label`}
            aria-describedby={errorId('interval_mi')}
          >
            {INTERVALS.map((miles) => (
              <label key={miles} className="segment">
                <input
                  type="radio"
                  name={`${id}-interval`}
                  value={miles}
                  checked={interval === miles}
                  onChange={() => setIntervalMi(miles)}
                />
                <span>{miles} mi</span>
              </label>
            ))}
          </div>
          {error('interval_mi')}
        </div>
      </div>
      <div className="form-actions">
        <button type="submit" className="primary" disabled={busy}>
          {busy && <span className="spinner" aria-hidden="true" />}
          {busy ? 'Planning…' : 'Plan trip'}
        </button>
        {onCancel && (
          <button type="button" className="secondary" onClick={onCancel} disabled={busy}>
            Cancel
          </button>
        )}
      </div>
    </form>
  )
}
