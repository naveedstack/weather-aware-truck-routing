import { cleanup } from '@testing-library/react'
import { afterEach } from 'vitest'

// jsdom lacks two browser APIs the app uses: media queries (answered as "no match") and element
// scrolling (a no-op, since jsdom has no layout).
window.matchMedia ??= (query: string) =>
  ({
    matches: false,
    media: query,
    onchange: null,
    addEventListener: () => {},
    removeEventListener: () => {},
    addListener: () => {},
    removeListener: () => {},
    dispatchEvent: () => false,
  }) as MediaQueryList
Element.prototype.scrollTo ??= () => {}

afterEach(() => cleanup())
