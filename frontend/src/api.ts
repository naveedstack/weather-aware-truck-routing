import type { Plan, TripRequest } from './types'

/** A failed plan request, with the server's message and any per-field messages. */
export class PlanRequestError extends Error {
  readonly fields: Record<string, string>

  constructor(message: string, fields: Record<string, string> = {}) {
    super(message)
    this.name = 'PlanRequestError'
    this.fields = fields
  }
}

interface ErrorBody {
  error?: { message?: string; field?: string; fields?: Record<string, string> }
}

export async function planTrip(request: TripRequest): Promise<Plan> {
  let response: Response
  try {
    response = await fetch('/api/plan/', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', Accept: 'application/json' },
      body: JSON.stringify(request),
    })
  } catch {
    throw new PlanRequestError("Couldn't reach the server. Check your connection and try again.")
  }

  const body: unknown = await response.json().catch(() => null)
  if (response.ok && body) return body as Plan

  const error = (body as ErrorBody | null)?.error
  if (!error?.message) {
    throw new PlanRequestError(`The server couldn't plan this trip (error ${response.status}).`)
  }
  const fields = { ...error.fields }
  if (error.field) fields[error.field] = error.message
  // The message already says when to try again after a rate limit.
  throw new PlanRequestError(error.message, fields)
}

interface PlacesBody {
  places?: { name?: unknown }[]
}

/** Cities for text typed in the From or To field, best match first. Rejects when the server
 * can't suggest any; the field then just goes without suggestions. */
export async function suggestPlaces(text: string, signal?: AbortSignal): Promise<string[]> {
  const response = await fetch(`/api/places/?${new URLSearchParams({ q: text })}`, {
    headers: { Accept: 'application/json' },
    signal,
  })
  if (!response.ok) throw new Error(`The server couldn't suggest places (error ${response.status}).`)
  const body = (await response.json()) as PlacesBody
  return (body.places ?? []).map((place) => place.name).filter((name): name is string => typeof name === 'string')
}
