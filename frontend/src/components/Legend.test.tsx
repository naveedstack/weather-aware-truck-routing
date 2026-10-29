import { render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import { Legend } from './Legend'

function swatch(label: string): HTMLElement {
  return screen.getByText(label).querySelector('.legend-line') as HTMLElement
}

describe('Legend', () => {
  it('draws the selected route dark cyan, as on the map and in the cards', () => {
    render(<Legend />)

    expect(swatch('Selected route').style.background).toBe('rgb(14, 116, 144)') // #0e7490
  })

  it("shows both of the other routes' colors", () => {
    render(<Legend />)

    const background = swatch('Other routes').style.background
    expect(background).toContain('rgb(29, 78, 216)') // #1d4ed8, blue
    expect(background).toContain('rgb(100, 116, 139)') // #64748b, slate
  })
})
