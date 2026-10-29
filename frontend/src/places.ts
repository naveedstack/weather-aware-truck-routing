// City suggestions for the trip form's From and To fields (README "Assumptions" 39). Pure
// functions, so they're easy to test.

export const MIN_SUGGEST_CHARS = 3 // letters or digits typed before cities are suggested
export const SUGGEST_DELAY_MS = 300 // the pause in typing after which they are asked for

/** Text as it is compared: case, accents, punctuation and extra spaces don't count, so "dallas tx"
 * is the same as "Dallas, TX". */
export function looseText(text: string): string {
  return text
    .normalize('NFD')
    .replace(/\p{M}/gu, '')
    .toLowerCase()
    .replace(/[^\p{L}\p{N}]+/gu, ' ')
    .trim()
}

/** Whether enough has been typed to ask for suggestions: three letters or digits, like the server. */
export function wantsSuggestions(text: string): boolean {
  return (text.match(/[\p{L}\p{N}]/gu)?.length ?? 0) >= MIN_SUGGEST_CHARS
}

// TomTom writes these words out ("Saint Louis, MO"), and people often shorten them ("St. Louis").
const SHORTENED = new Map([
  ['saint', 'st'],
  ['sainte', 'ste'],
  ['fort', 'ft'],
  ['mount', 'mt'],
])

/** Text as typed text and suggestions are matched: looseText, with those words shortened. */
function matchText(text: string): string {
  return looseText(text)
    .split(' ')
    .map((word) => SHORTENED.get(word) ?? word)
    .join(' ')
}

/** Cities the server suggested for some text, best match first. */
export interface Suggestions {
  query: string
  names: string[]
}

/** The suggestions to list for the text in the field:
 * - only the city the text names in full, once it does ("dallas tx" lists just "Dallas, TX", and
 *   "St. Louis, MO" just "Saint Louis, MO");
 * - otherwise every city found for this text;
 * - while the cities for this text are still on their way, the earlier ones that start with it,
 *   so typing on narrows the list at once. */
export function listedSuggestions(text: string, found: Suggestions | null): string[] {
  if (!found || !wantsSuggestions(text)) return []
  const typed = matchText(text)
  const exact = found.names.find((name) => matchText(name) === typed)
  if (exact) return [exact]
  if (matchText(found.query) === typed) return found.names
  const start = looseText(text) // "Sain" starts "Saint Louis" only before the shortening
  return found.names.filter((name) => matchText(name).startsWith(typed) || looseText(name).startsWith(start))
}
