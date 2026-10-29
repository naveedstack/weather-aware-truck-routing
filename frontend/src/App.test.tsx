import { act, fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import App from './App'
import { makePlan, makeRoute } from './testing/fixtures'

// The map needs WebGL, which jsdom doesn't have; the map itself is checked in a browser. The stand-in
// records the props App gives it.
const mocks = vi.hoisted(() => ({
  routeMap: vi.fn((_props: { heatmapHour: number; selectedRoute: string | null }) => null),
  webgl2: true,
}))
vi.mock('./components/RouteMap', () => ({ RouteMap: mocks.routeMap }))
vi.mock('./map/webgl', () => ({ supportsWebGL2: () => mocks.webgl2 }))

beforeEach(() => {
  vi.useFakeTimers({ toFake: ['Date'] })
  vi.setSystemTime(new Date('2026-10-24T14:20:00Z'))
})

afterEach(() => {
  vi.useRealTimers()
  vi.unstubAllGlobals()
  mocks.routeMap.mockClear()
  mocks.webgl2 = true
})

/** The heatmap hour App last gave the map. */
function mapHour(): number | undefined {
  return mocks.routeMap.mock.lastCall?.[0].heatmapHour
}

/** The route App last told the map to show as selected. */
function mapSelection(): string | null | undefined {
  return mocks.routeMap.mock.lastCall?.[0].selectedRoute
}

function json(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), { status, headers: { 'Content-Type': 'application/json' } })
}

/** A fetch that answers when the test says so. */
function deferredFetch() {
  let answer: (response: Response) => void = () => {}
  const fetch = vi.fn(() => new Promise<Response>((resolve) => (answer = resolve)))
  vi.stubGlobal('fetch', fetch)
  return { fetch, answer: (response: Response) => answer(response) }
}

type User = ReturnType<typeof userEvent.setup>

async function planTrip(user: User) {
  await user.type(screen.getByLabelText('From'), 'Dallas, TX')
  await user.type(screen.getByLabelText('To'), 'Denver, CO')
  await user.click(screen.getByRole('button', { name: 'Plan trip' }))
}

/** The form slides open and closed with the 'open' class, and is inert while closed: hidden from
 * screen readers and out of the tab order. */
function formIsOpen(): boolean {
  const area = screen.getByLabelText('From').closest('.collapsible') as HTMLElement
  const open = area.classList.contains('open')
  expect(area.hasAttribute('inert')).toBe(!open)
  return open
}

/** The page's live region: on the page from the start, so screen readers hear what changes in it. */
function liveRegion(): HTMLElement {
  return document.querySelector('[aria-live]') as HTMLElement
}

async function planned(user: User, server: ReturnType<typeof deferredFetch>, plan = makePlan()) {
  await planTrip(user)
  server.answer(json(plan))
  await screen.findByRole('heading', { name: `Recommended: Route ${plan.recommendation.route_id}` })
}

describe('App', () => {
  it('closes the form while planning, shows progress, then the routes', async () => {
    const user = userEvent.setup()
    const server = deferredFetch()
    const { container } = render(<App />)
    expect(screen.getByText('Enter a trip to compare its routes.')).toBeTruthy()
    expect(formIsOpen()).toBe(true)
    expect(screen.queryByRole('button', { name: 'Cancel' })).toBeNull() // no trip to go back to

    await planTrip(user)

    expect(formIsOpen()).toBe(false)
    const tripBar = within(container.querySelector('.trip-bar') as HTMLElement)
    expect(tripBar.getByText('Dallas, TX → Denver, CO')).toBeTruthy() // the trip being planned
    expect(tripBar.getByText('Planning…')).toBeTruthy()
    expect(container.querySelector('.plan-loading')).not.toBeNull() // the moving bar and placeholders
    const region = liveRegion()
    expect(region.textContent).toMatch(/^Finding routes and forecasts/)
    expect(document.activeElement).toBe(container.querySelector('.results')) // not lost with the form

    server.answer(json(makePlan()))

    expect(await screen.findByRole('heading', { name: 'Recommended: Route A' })).toBeTruthy()
    expect(container.querySelector('.plan-loading')).toBeNull()
    expect(screen.getByRole('button', { name: 'Change trip' })).toBeTruthy()
    expect(formIsOpen()).toBe(false)
    expect(region.textContent).toBe('Routes ready. Recommended: Route A.')
  })

  it('opens the form again with the trip kept, and leaves the routes on screen until the next plan', async () => {
    const user = userEvent.setup()
    const server = deferredFetch()
    render(<App />)
    await planned(user, server)

    await user.click(screen.getByRole('button', { name: 'Change trip' }))

    expect(formIsOpen()).toBe(true)
    expect(document.activeElement).toBe(screen.getByLabelText('From'))
    expect((screen.getByLabelText('From') as HTMLInputElement).value).toBe('Dallas, TX')
    expect(screen.getByRole('heading', { name: 'Recommended: Route A' })).toBeTruthy()

    await user.click(screen.getByRole('button', { name: 'Cancel' }))

    expect(formIsOpen()).toBe(false)
    expect(document.activeElement).toBe(screen.getByRole('button', { name: 'Change trip' }))
  })

  it('announces every plan, with its warnings', async () => {
    const user = userEvent.setup()
    const server = deferredFetch()
    render(<App />)
    await planTrip(user)
    const region = liveRegion()
    server.answer(json(makePlan()))
    await within(region).findByText('Routes ready. Recommended: Route A.')

    await user.click(screen.getByRole('button', { name: 'Change trip' }))
    await user.click(screen.getByRole('button', { name: 'Plan trip' }))
    expect(region.textContent).not.toContain('Routes ready') // so the next result is new to the region
    const warning = 'Every route has No Travel conditions. Route A is the least risky option, not a safe one.'
    const unsafe = makePlan({
      routes: [makeRoute({ unsafe: true }), makeRoute({ id: 'B', recommended: false, unsafe: true })],
      recommendation: { route_id: 'A', reason: 'Fewest No Travel miles: 12.5 mi vs 25.0 mi on Route B.', warnings: [warning] },
    })
    server.answer(json(unsafe))

    expect(await within(region).findByText(`Routes ready. Recommended: Route A. ${warning}`)).toBeTruthy()
  })

  it("opens the form again on the server's error, at the field it is about", async () => {
    const user = userEvent.setup()
    const server = deferredFetch()
    render(<App />)

    await planTrip(user)
    const message = "Couldn't find a place called “Dallas, TX”."
    server.answer(json({ error: { code: 'place_not_found', message, field: 'origin' } }, 422))

    expect((await screen.findByRole('alert')).textContent).toBe(message)
    expect(formIsOpen()).toBe(true)
    const origin = screen.getByLabelText('From')
    expect(origin.getAttribute('aria-invalid')).toBe('true')
    await waitFor(() => expect(document.activeElement).toBe(origin))
  })

  it("drops the edits on Cancel, so Change trip starts again from the trip on screen", async () => {
    const user = userEvent.setup()
    const server = deferredFetch()
    render(<App />)
    await planned(user, server)

    await user.click(screen.getByRole('button', { name: 'Change trip' }))
    await user.clear(screen.getByLabelText('From'))
    await user.type(screen.getByLabelText('From'), 'Houston, TX')
    await user.click(screen.getByRole('radio', { name: '50 mi' }))
    await user.click(screen.getByRole('button', { name: 'Cancel' }))
    await user.click(screen.getByRole('button', { name: 'Change trip' }))

    expect((screen.getByLabelText('From') as HTMLInputElement).value).toBe('Dallas, TX')
    expect((screen.getByRole('radio', { name: '25 mi' }) as HTMLInputElement).checked).toBe(true)
  })

  it('does not announce the routes again when a failed plan is cancelled', async () => {
    const user = userEvent.setup()
    const server = deferredFetch()
    render(<App />)
    await planned(user, server)
    await user.click(screen.getByRole('button', { name: 'Change trip' }))
    await user.click(screen.getByRole('button', { name: 'Plan trip' }))
    server.answer(new Response('Bad gateway', { status: 502 }))
    await screen.findByRole('alert')

    await user.click(screen.getByRole('button', { name: 'Cancel' }))

    expect(liveRegion().textContent).toBe('')
  })

  it('steps through what the server does while planning, every 2 seconds, and stays on the last step', async () => {
    vi.useFakeTimers({ toFake: ['Date', 'setInterval', 'clearInterval'] })
    const user = userEvent.setup()
    const server = deferredFetch()
    const { container } = render(<App />)
    await planTrip(user)
    const status = () => container.querySelector('.plan-loading .status')?.textContent
    const after2s = () => act(() => vi.advanceTimersByTime(2000))

    expect(status()).toBe('Finding Dallas, TX and Denver, CO…')
    after2s()
    expect(status()).toBe('Getting truck routes from TomTom…')
    after2s()
    after2s()
    expect(status()).toBe('Placing checkpoints every 25 miles…')
    after2s()
    after2s()
    after2s()
    expect(status()).toBe('Rating the risk and comparing the routes…') // 12 s: still the last step
    after2s()
    expect(status()).toBe('Almost there… long trips take up to about 20 seconds.')
    expect(liveRegion().textContent).toMatch(/^Finding routes and forecasts/) // screen readers hear it once

    server.answer(json(makePlan()))
    expect(await screen.findByRole('heading', { name: 'Recommended: Route A' })).toBeTruthy()
  })

  it('shows the heatmap slider with the routes, hides it while planning, and starts each plan at its departure', async () => {
    const user = userEvent.setup()
    const server = deferredFetch()
    render(<App />)
    expect(screen.queryByRole('slider')).toBeNull() // no plan yet
    await planned(user, server)

    const slider = screen.getByRole('slider', { name: 'Weather heatmap' }) as HTMLInputElement
    expect(slider.value).toBe('0')
    fireEvent.change(slider, { target: { value: '30' } })
    expect(slider.value).toBe('30')
    expect(mapHour()).toBe(30) // the map follows the slider

    await user.click(screen.getByRole('button', { name: 'Change trip' }))
    await user.click(screen.getByRole('button', { name: 'Plan trip' }))
    expect(screen.queryByRole('slider')).toBeNull() // its results are hidden while planning
    server.answer(json(makePlan()))

    expect(((await screen.findByRole('slider')) as HTMLInputElement).value).toBe('0')
    expect(mapHour()).toBe(0)
  })

  it('starts each plan with its recommended route selected, and lets the user pick another', async () => {
    const user = userEvent.setup()
    const server = deferredFetch()
    render(<App />)
    await planned(user, server)
    const choice = (name: RegExp) => screen.getByRole('radio', { name }) as HTMLInputElement

    expect(choice(/^Route A/).checked).toBe(true)
    expect(mapSelection()).toBe('A')

    await user.click(screen.getByText('812.9 mi')) // on Route B's card
    expect(choice(/^Route B/).checked).toBe(true)
    expect(mapSelection()).toBe('B')

    // The next plan recommends its last route, so the selection can't just be the first one, or the
    // one picked before.
    await user.click(screen.getByRole('button', { name: 'Change trip' }))
    await user.click(screen.getByRole('button', { name: 'Plan trip' }))
    const next = makePlan({
      routes: [
        makeRoute({ recommended: false }),
        makeRoute({ id: 'B', recommended: false }),
        makeRoute({ id: 'C', recommended: true }),
      ],
      recommendation: { route_id: 'C', reason: 'Route C has the lowest average risk.', warnings: [] },
    })
    server.answer(json(next))
    await screen.findByRole('heading', { name: 'Recommended: Route C' })
    expect(choice(/^Route C/).checked).toBe(true)
    expect(mapSelection()).toBe('C')
  })

  it("hides the heatmap slider and the legend when the map can't be shown", async () => {
    mocks.webgl2 = false
    const user = userEvent.setup()
    const server = deferredFetch()
    render(<App />)

    await planned(user, server)

    expect(screen.queryByRole('slider')).toBeNull() // it would change nothing on screen
    expect(screen.queryByRole('complementary', { name: 'Map legend' })).toBeNull()
    expect(mocks.routeMap.mock.lastCall?.[0]).toMatchObject({ failed: true })
  })

  it('keeps the previous routes, and the route picked among them, when a new plan fails', async () => {
    const user = userEvent.setup()
    const server = deferredFetch()
    render(<App />)
    await planned(user, server)
    await user.click(screen.getByText('812.9 mi')) // picks Route B

    await user.click(screen.getByRole('button', { name: 'Change trip' }))
    await user.click(screen.getByRole('button', { name: 'Plan trip' }))
    server.answer(new Response('Bad gateway', { status: 502 }))

    expect((await screen.findByRole('alert')).textContent).toBe("The server couldn't plan this trip (error 502).")
    expect(screen.getByRole('heading', { name: 'Recommended: Route A' })).toBeTruthy()
    expect((screen.getByRole('radio', { name: /^Route B/ }) as HTMLInputElement).checked).toBe(true)
    expect(mapSelection()).toBe('B')
    expect(formIsOpen()).toBe(true) // to try again
    expect((screen.getByRole('button', { name: 'Plan trip' }) as HTMLButtonElement).disabled).toBe(false)
    expect(screen.queryByText(/Finding routes and forecasts/)).toBeNull()
    expect(liveRegion().textContent).toBe('') // the alert says what happened
  })
})
