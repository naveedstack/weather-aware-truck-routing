import { describe, expect, it } from 'vitest'
import { listedSuggestions, looseText, wantsSuggestions } from './places'

const DAL = { query: 'Dal', names: ['Dallas, TX', 'Dallas, GA', 'Dalton, GA'] }

describe('looseText', () => {
  it('ignores case, accents, punctuation and extra spaces', () => {
    expect(looseText('  Dallas,TX ')).toBe('dallas tx')
    expect(looseText('Montréal-Est  QC')).toBe('montreal est qc')
    expect(looseText('St. Louis')).toBe('st louis')
  })
})

describe('wantsSuggestions', () => {
  it('needs three letters or digits, wherever they are', () => {
    expect(wantsSuggestions('Da')).toBe(false)
    expect(wantsSuggestions('D a ')).toBe(false)
    expect(wantsSuggestions('...')).toBe(false)
    expect(wantsSuggestions('Dal')).toBe(true)
    expect(wantsSuggestions('D a l')).toBe(true)
    expect(wantsSuggestions('752')).toBe(true)
  })
})

describe('listedSuggestions', () => {
  it('lists every city found for the text, best first', () => {
    expect(listedSuggestions('dal ', DAL)).toEqual(DAL.names)
  })

  it('lists only the city the text names in full', () => {
    expect(listedSuggestions('dallas tx', DAL)).toEqual(['Dallas, TX'])
    expect(listedSuggestions('Dallas, GA', { query: 'Dallas, GA', names: ['Dallas, GA', 'Dallas, TX'] })).toEqual([
      'Dallas, GA',
    ])
  })

  it('narrows the cities found for earlier text to those that start with the text', () => {
    expect(listedSuggestions('Dall', DAL)).toEqual(['Dallas, TX', 'Dallas, GA'])
    expect(listedSuggestions('Dallas, G', DAL)).toEqual(['Dallas, GA'])
    expect(listedSuggestions('Chicago', DAL)).toEqual([])
  })

  // TomTom's answers for "St. Louis, MO" and "St. Lo", which write "Saint" out.
  const ST_LOUIS = {
    query: 'St. Louis, MO',
    names: ['Saint Louis, MO', 'Lake Saint Louis, MO', 'Saint Ferdinand, MO', 'Saint Ann, MO', 'Saint John, MO'],
  }
  const ST_LO = {
    query: 'St. Lo',
    names: ['Saint Louis, MO', 'Bay Saint Louis, MS', 'Saint Louis, MI', 'Saint Louis, SK', 'Saint-Louis, NB'],
  }

  it('counts St., Ste., Ft. and Mt. as the words TomTom writes out', () => {
    expect(listedSuggestions('St. Louis, MO', ST_LOUIS)).toEqual(['Saint Louis, MO'])
    expect(listedSuggestions('Ft Worth, TX', { query: 'Ft Wor', names: ['Fort Worth, TX', 'Fort Wayne, IN'] })).toEqual([
      'Fort Worth, TX',
    ])
    expect(listedSuggestions('Mt. Vernon, IL', { query: 'Mt V', names: ['Mount Vernon, WA', 'Mount Vernon, IL'] })).toEqual(
      ['Mount Vernon, IL'],
    )
    expect(listedSuggestions('Billings, MT', { query: 'Billings', names: ['Billings, MT'] })).toEqual(['Billings, MT'])
  })

  it('narrows earlier cities by the shortened words and by the words as written', () => {
    const louis = ['Saint Louis, MO', 'Saint Louis, MI', 'Saint Louis, SK', 'Saint-Louis, NB']
    expect(listedSuggestions('St. Loui', ST_LO)).toEqual(louis)
    expect(listedSuggestions('Saint Lou', ST_LO)).toEqual(louis)
  })

  it('lists nothing below three letters or digits, or before anything is found', () => {
    expect(listedSuggestions('Da', DAL)).toEqual([])
    expect(listedSuggestions('Dal', null)).toEqual([])
  })
})
