import { type InputHTMLAttributes, type KeyboardEvent, useEffect, useRef, useState } from 'react'
import { suggestPlaces } from '../api'
import { listedSuggestions, looseText, SUGGEST_DELAY_MS, type Suggestions, wantsSuggestions } from '../places'

interface Props extends Omit<InputHTMLAttributes<HTMLInputElement>, 'id' | 'value' | 'onChange'> {
  id: string
  value: string
  onChange: (value: string) => void
}

/** A text field that suggests cities as the user types (the ARIA combobox pattern). Any place can
 * still be typed in full and sent; choosing a suggestion only fills the field in. Suggestions are
 * asked for once typing pauses, from three letters or digits, and each text only once. */
export function PlaceInput({ id, value, onChange, ...input }: Props) {
  const listId = `${id}-suggestions`
  const [found, setFound] = useState<Suggestions | null>(null)
  const [open, setOpen] = useState(false) // closed by a choice, by Escape and by leaving the field
  const [active, setActive] = useState(-1) // the suggestion the arrow keys are on
  const known = useRef(new Map<string, string[]>()) // suggestions already found, by looseText
  const timer = useRef(0)
  const request = useRef<AbortController | null>(null)

  const listed = open ? listedSuggestions(value, found) : []
  const current = active < listed.length ? active : -1

  // Once the field is gone, nothing more is asked for.
  useEffect(
    () => () => {
      window.clearTimeout(timer.current)
      request.current?.abort()
    },
    [],
  )

  function cancel() {
    window.clearTimeout(timer.current)
    request.current?.abort()
    request.current = null
  }

  function show(query: string, names: string[]) {
    setFound({ query, names })
    setActive(-1)
  }

  function ask(text: string) {
    request.current?.abort()
    const controller = new AbortController()
    request.current = controller
    suggestPlaces(text, controller.signal).then(
      (names) => {
        known.current.set(looseText(text), names)
        if (request.current !== controller) return // newer text has taken over
        request.current = null
        show(text, names)
      },
      () => {
        // Cancelled, or the server has no suggestions to give: the field works without them.
        if (request.current !== controller) return
        request.current = null
        show(text, [])
      },
    )
  }

  /** Lists the suggestions for the text: those already found, or the server's. */
  function lookUp(text: string) {
    const names = known.current.get(looseText(text))
    if (names) {
      cancel()
      show(text, names)
    } else {
      ask(text)
    }
  }

  function type(text: string) {
    onChange(text)
    setActive(-1)
    window.clearTimeout(timer.current)
    if (!wantsSuggestions(text)) {
      cancel()
      setOpen(false)
      return
    }
    setOpen(true)
    if (known.current.has(looseText(text))) lookUp(text) // found before: no need to wait
    else timer.current = window.setTimeout(() => lookUp(text), SUGGEST_DELAY_MS)
  }

  function close() {
    cancel()
    setOpen(false)
    setActive(-1)
  }

  function choose(name: string) {
    onChange(name)
    close()
  }

  function onKeyDown(event: KeyboardEvent<HTMLInputElement>) {
    if (event.nativeEvent.isComposing) return // keys that build up a character (IME) aren't ours
    if (event.key === 'ArrowDown' || event.key === 'ArrowUp') {
      const names = listedSuggestions(value, found) // the arrows also open the list after Escape
      if (names.length === 0) return
      event.preventDefault()
      // The user is choosing from this list now, so an answer still on its way mustn't replace it
      // (and the highlight with it) under them. Typing again asks again.
      cancel()
      const step = event.key === 'ArrowDown' ? 1 : -1
      const from = open ? current : -1
      setOpen(true)
      setActive(from === -1 ? (step === 1 ? 0 : names.length - 1) : (from + step + names.length) % names.length)
    } else if (event.key === 'Enter' && current >= 0) {
      event.preventDefault() // fills the field in; the next Enter sends the form
      choose(listed[current])
    } else if (event.key === 'Escape') {
      if (listed.length > 0) event.preventDefault()
      close() // an answer still on its way doesn't open the list afterwards
    }
  }

  return (
    <div className="place-input">
      <input
        {...input}
        id={id}
        value={value}
        onChange={(event) => type(event.target.value)}
        onKeyDown={onKeyDown}
        onBlur={close}
        role="combobox"
        aria-autocomplete="list"
        aria-expanded={listed.length > 0}
        aria-controls={listId}
        aria-activedescendant={current >= 0 ? `${listId}-${current}` : undefined}
        autoComplete="off"
        spellCheck={false} // place names aren't in the dictionary, half-typed ones even less
      />
      {/* Pressing on the list would take focus from the field, closing the list before the click. */}
      <ul
        id={listId}
        className="suggestions"
        role="listbox"
        aria-label="Suggestions"
        hidden={listed.length === 0}
        onMouseDown={(event) => event.preventDefault()}
      >
        {listed.map((name, index) => (
          <li
            key={name}
            id={`${listId}-${index}`}
            role="option"
            aria-selected={index === current}
            className={index === current ? 'active' : undefined}
            onClick={() => choose(name)}
          >
            <Match name={name} text={value} />
          </li>
        ))}
      </ul>
      <p className="visually-hidden" role="status">
        {listed.length === 0 ? '' : listed.length === 1 ? '1 suggestion' : `${listed.length} suggestions`}
      </p>
    </div>
  )
}

/** A suggestion, with the part that matches what's typed in bold. */
function Match({ name, text }: { name: string; text: string }) {
  const typed = text.trim()
  if (!typed || !name.toLowerCase().startsWith(typed.toLowerCase())) return name
  return (
    <>
      <strong>{name.slice(0, typed.length)}</strong>
      {name.slice(typed.length)}
    </>
  )
}
