import { fireEvent, render, screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { useState } from 'react'
import { describe, expect, it, vi } from 'vitest'
import { makePlan, makeRoute } from '../testing/fixtures'
import type { Plan } from '../types'
import { PlanSummary } from './PlanSummary'

function card(name: string): HTMLElement {
  return screen.getByRole('heading', { name }).closest('li') as HTMLElement
}

/** Renders the summary with the recommended route selected, as App does for a new plan. */
function renderSummary(plan: Plan, props: Partial<Parameters<typeof PlanSummary>[0]> = {}) {
  return render(
    <PlanSummary
      plan={plan}
      selectedRoute={plan.recommendation.route_id}
      onSelect={vi.fn()}
      onHighlight={vi.fn()}
      {...props}
    />,
  )
}

function swatch(name: string): string {
  return (card(name).querySelector('.route-swatch') as HTMLElement).style.background
}

/** The summary with the selection kept in state, as App keeps it. */
function Choosing({ plan }: { plan: Plan }) {
  const [selected, setSelected] = useState<string | null>(plan.recommendation.route_id)
  return <PlanSummary plan={plan} selectedRoute={selected} onSelect={setSelected} onHighlight={() => {}} />
}

describe('PlanSummary', () => {
  it('shows the recommendation, its reason and the notices', () => {
    renderSummary(makePlan({ notices: ['Only 2 routes were found.'] }))

    expect(screen.getByRole('heading', { name: 'Recommended: Route A' })).toBeTruthy()
    expect(screen.getByText('Route A has the lowest average risk.')).toBeTruthy()
    expect(screen.getByText('Only 2 routes were found.')).toBeTruthy()
  })

  it('warns when every route is unsafe', () => {
    const warning = 'Every route has No Travel miles. Route A is the least risky; consider waiting.'
    const plan = makePlan({
      routes: [makeRoute({ unsafe: true }), makeRoute({ id: 'B', recommended: false, unsafe: true })],
      recommendation: { route_id: 'A', reason: 'Route A has the fewest No Travel miles.', warnings: [warning] },
    })

    const { container } = renderSummary(plan)

    expect(screen.getByText(warning)).toBeTruthy()
    expect(container.querySelector('.recommendation.unsafe')).not.toBeNull()
    expect(within(card('Route B')).getByText('Unsafe')).toBeTruthy()
  })

  it('marks only the recommended route, which need not be the first', () => {
    const plan = makePlan({
      routes: [makeRoute({ recommended: false, unsafe: true }), makeRoute({ id: 'B', recommended: true })],
      recommendation: { route_id: 'B', reason: 'Fewest No Travel miles: 0.0 mi vs 12.5 mi on Route A.', warnings: [] },
    })

    const { container } = renderSummary(plan)

    expect(screen.getByRole('heading', { name: 'Recommended: Route B' })).toBeTruthy()
    expect(container.querySelector('.recommendation.unsafe')).toBeNull()
    expect(within(card('Route B')).getByText('Recommended')).toBeTruthy()
    expect(within(card('Route B')).queryByText('Unsafe')).toBeNull()
    expect(within(card('Route A')).getByText('Unsafe')).toBeTruthy()
    expect(within(card('Route A')).queryByText('Recommended')).toBeNull()
  })

  it('shows the arrival with its date', () => {
    renderSummary(makePlan())

    // The tests run in America/Chicago (see vite.config.ts).
    expect(within(card('Route A')).getByText(/^Sun, Oct 25, 2:52\sAM CDT$/)).toBeTruthy()
  })

  it("lists each route's numbers", () => {
    renderSummary(makePlan())

    const a = within(card('Route A'))
    expect(a.getByText('Recommended')).toBeTruthy()
    expect(a.getByText('790.4 mi')).toBeTruthy()
    expect(a.getByText('11 h 52 min')).toBeTruthy()
    expect(a.getByText('0.13 / 4')).toBeTruthy()
    expect(a.queryByText('Unsafe')).toBeNull()

    const b = within(card('Route B'))
    expect(b.queryByText('Recommended')).toBeNull()
    expect(b.getByText('812.9 mi')).toBeTruthy()
  })

  it('shows the risky miles, and the miles with no forecast', () => {
    const plan = makePlan({
      routes: [makeRoute({ miles: { no_travel: 12.5, severe: 0, high: 25, moderate: 0, low: 700, no_data: 52.9 } })],
    })

    renderSummary(plan)

    const route = within(card('Route A'))
    expect(route.getByText('No Travel').closest('div')?.textContent).toBe('No Travel12.5 mi')
    expect(route.getByText('Severe').closest('div')?.textContent).toBe('Severe0.0 mi')
    expect(route.getByText('High').closest('div')?.textContent).toBe('High25.0 mi')
    expect(route.getByText('No data').closest('div')?.textContent).toBe('No data52.9 mi')
    expect(route.getByRole('img').getAttribute('aria-label')).toBe(
      'Miles by risk level: Low 700.0 mi, High 25.0 mi, No Travel 12.5 mi, No data 52.9 mi',
    )
  })

  it('leaves out No data miles when every mile has a forecast', () => {
    renderSummary(makePlan())

    expect(within(card('Route A')).queryByText('No data')).toBeNull()
  })

  it('says "No data" for an average with no forecast at all', () => {
    renderSummary(makePlan({ routes: [makeRoute({ average_risk: null })] }))

    expect(within(card('Route A')).getByText('No data')).toBeTruthy()
  })

  it('highlights a route on the map while the pointer is over its card', () => {
    const onHighlight = vi.fn()
    renderSummary(makePlan(), { onHighlight })

    fireEvent.mouseEnter(card('Route B'))
    fireEvent.mouseLeave(card('Route B'))

    expect(onHighlight.mock.calls).toEqual([['B'], [null]])
  })

  it('keeps the route highlighted while its card is pressed, even when another card had focus', async () => {
    const user = userEvent.setup()
    const onHighlight = vi.fn()
    renderSummary(makePlan(), { onHighlight })
    await user.click(within(card('Route A')).getByText('790.4 mi')) // Route A's radio now has focus
    await user.hover(within(card('Route B')).getByText('812.9 mi'))
    onHighlight.mockClear()

    // Pressing moves focus off Route A's radio; the highlight must not blink off meanwhile.
    await user.pointer({ keys: '[MouseLeft>]', target: within(card('Route B')).getByText('812.9 mi') })
    await user.pointer({ keys: '[/MouseLeft]' })

    expect(onHighlight).not.toHaveBeenCalled()
  })
})

describe('choosing a route', () => {
  it('offers the routes as one choice, named by their cards, with the selected one checked', () => {
    renderSummary(makePlan(), { selectedRoute: 'B' })

    const group = screen.getByRole('radiogroup', { name: 'Choose a route to show on the map' })
    const choices = within(group).getAllByRole('radio') as HTMLInputElement[]
    expect(choices.map((choice) => choice.checked)).toEqual([false, true])
    expect(within(group).getByRole('radio', { name: /^Route A Recommended$/ })).toBe(choices[0])
    expect(card('Route B').classList.contains('selected')).toBe(true)
    expect(card('Route A').classList.contains('selected')).toBe(false)
  })

  it('selects a route when its card is clicked anywhere', async () => {
    const user = userEvent.setup()
    const onSelect = vi.fn()
    renderSummary(makePlan(), { onSelect })

    await user.click(within(card('Route B')).getByText('812.9 mi'))

    expect(onSelect).toHaveBeenCalledExactlyOnceWith('B')
    expect(document.activeElement).toBe(within(card('Route B')).getByRole('radio')) // arrow keys go on from here
  })

  it('moves the selection with the arrow keys, from one tab stop for all the cards', async () => {
    const user = userEvent.setup()
    const plan = makePlan({
      routes: [makeRoute(), makeRoute({ id: 'B', recommended: false }), makeRoute({ id: 'C', recommended: false })],
    })
    render(<Choosing plan={plan} />)
    const choice = (name: string) => within(card(name)).getByRole('radio') as HTMLInputElement

    await user.tab()
    expect(document.activeElement).toBe(choice('Route A')) // the selected one
    await user.keyboard('{ArrowDown}')
    expect(choice('Route B').checked).toBe(true)
    expect(document.activeElement).toBe(choice('Route B'))
    await user.keyboard('{ArrowDown}')
    expect(choice('Route C').checked).toBe(true)
    await user.keyboard('{ArrowUp}')
    expect(choice('Route B').checked).toBe(true)
    expect(choice('Route A').checked || choice('Route C').checked).toBe(false)
  })

  it("colors each card's swatch like its line on the map: the selected route dark cyan", () => {
    const view = renderSummary(makePlan())
    expect([swatch('Route A'), swatch('Route B')]).toEqual(['rgb(14, 116, 144)', 'rgb(29, 78, 216)']) // A, the recommended, at first

    view.rerender(<PlanSummary plan={makePlan()} selectedRoute="B" onSelect={vi.fn()} onHighlight={vi.fn()} />)
    expect([swatch('Route A'), swatch('Route B')]).toEqual(['rgb(29, 78, 216)', 'rgb(14, 116, 144)'])
  })
})
