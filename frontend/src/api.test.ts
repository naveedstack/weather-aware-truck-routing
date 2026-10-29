import { afterEach, describe, expect, it, vi } from 'vitest'
import { PlanRequestError, planTrip, suggestPlaces } from './api'
import { makePlan } from './testing/fixtures'
import type { TripRequest } from './types'

const REQUEST: TripRequest = {
  origin: 'Dallas, TX',
  destination: 'Denver, CO',
  departure: '2026-10-24T20:00:00.000Z',
  load_lb: 35000,
  interval_mi: 25,
}

function json(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), { status, headers: { 'Content-Type': 'application/json' } })
}

function stubFetch(response: Response) {
  const fetch = vi.fn().mockResolvedValue(response)
  vi.stubGlobal('fetch', fetch)
  return fetch
}

function stubFetchFailure(reason: unknown) {
  vi.stubGlobal('fetch', vi.fn().mockRejectedValue(reason))
}

async function failure(promise: Promise<unknown>): Promise<PlanRequestError> {
  const error = await promise.then(
    () => null,
    (reason: unknown) => reason,
  )
  expect(error).toBeInstanceOf(PlanRequestError)
  return error as PlanRequestError
}

afterEach(() => {
  vi.unstubAllGlobals()
})

describe('planTrip', () => {
  it('posts the trip as JSON and returns the plan', async () => {
    const plan = makePlan()
    const fetch = stubFetch(json(plan))

    await expect(planTrip(REQUEST)).resolves.toEqual(plan)

    const [url, init] = fetch.mock.calls[0] as [string, RequestInit]
    expect(url).toBe('/api/plan/') // Django's URL has the trailing slash
    expect(init.method).toBe('POST')
    expect(init.headers).toMatchObject({ 'Content-Type': 'application/json' })
    expect(JSON.parse(init.body as string)).toEqual(REQUEST)
  })

  it('keeps the message for each invalid field', async () => {
    const fields = { departure: 'Departure is in the past.', load_lb: 'Ensure this value is less than or equal to 80000.' }
    stubFetch(json({ error: { code: 'invalid_input', message: 'Please check the highlighted fields.', fields } }, 400))

    const error = await failure(planTrip(REQUEST))

    expect(error.message).toBe('Please check the highlighted fields.')
    expect(error.fields).toEqual(fields)
  })

  it('puts an error about one field under that field', async () => {
    const message = "Couldn't find a place called “Dalas”."
    stubFetch(json({ error: { code: 'place_not_found', message, field: 'origin' } }, 422))

    const error = await failure(planTrip(REQUEST))

    expect(error.message).toBe(message)
    expect(error.fields).toEqual({ origin: message })
  })

  it('passes on the server message for a rate limit', async () => {
    const message = "The free weather service's per-minute limit was reached. Please try again in a minute."
    stubFetch(json({ error: { code: 'weather_rate_limited', message } }, 503))

    const error = await failure(planTrip(REQUEST))

    expect(error.message).toBe(message)
    expect(error.fields).toEqual({})
  })

  it('explains an error response that is not JSON', async () => {
    stubFetch(new Response('<html>Gateway Timeout</html>', { status: 504 }))

    const error = await failure(planTrip(REQUEST))

    expect(error.message).toBe("The server couldn't plan this trip (error 504).")
  })

  it('explains a network failure', async () => {
    stubFetchFailure(new TypeError('Failed to fetch'))

    const error = await failure(planTrip(REQUEST))

    expect(error.message).toMatch(/couldn't reach the server/i)
  })
})

describe('suggestPlaces', () => {
  it('asks for the cities that match the text, and returns their names', async () => {
    const fetch = stubFetch(json({ places: [{ name: 'Dallas, TX' }, { name: 'Dallas, GA' }, { name: null }] }))
    const signal = new AbortController().signal

    await expect(suggestPlaces('Dallas, T', signal)).resolves.toEqual(['Dallas, TX', 'Dallas, GA'])

    const [url, init] = fetch.mock.calls[0] as [string, RequestInit]
    expect(url).toBe('/api/places/?q=Dallas%2C+T')
    expect(init.signal).toBe(signal) // so a newer text can cancel it
  })

  it('rejects when the server has no suggestions to give', async () => {
    stubFetch(json({ error: { code: 'routing_unavailable', message: 'The place search service is busy.' } }, 502))

    await expect(suggestPlaces('Dal')).rejects.toThrow('error 502')
  })
})
