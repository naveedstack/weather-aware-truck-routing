// Display formatting. The UI is in US English; times are shown in the browser's time zone, with its
// abbreviation.

const LOCALE = 'en-US'

const timeFormat = new Intl.DateTimeFormat(LOCALE, {
  weekday: 'short',
  hour: 'numeric',
  minute: '2-digit',
  timeZoneName: 'short',
})
const dateTimeFormat = new Intl.DateTimeFormat(LOCALE, {
  weekday: 'short',
  month: 'short',
  day: 'numeric',
  hour: 'numeric',
  minute: '2-digit',
  timeZoneName: 'short',
})

/** "Sat, 3:00 PM CDT" */
export function formatTime(iso: string): string {
  return timeFormat.format(new Date(iso))
}

/** "Sat, Oct 25, 3:00 PM CDT" */
export function formatDateTime(iso: string): string {
  return dateTimeFormat.format(new Date(iso))
}

/** "11 h 52 min", or "45 min" under an hour. */
export function formatDuration(minutes: number): string {
  const total = Math.round(minutes)
  const hours = Math.floor(total / 60)
  const rest = total % 60
  return hours > 0 ? `${hours} h ${rest} min` : `${rest} min`
}

/** "1 h", "1 h 20 min" or "40 min". */
export function formatSpan(minutes: number): string {
  const hours = Math.floor(minutes / 60)
  const rest = minutes % 60
  if (hours === 0) return `${rest} min`
  return rest === 0 ? `${hours} h` : `${hours} h ${rest} min`
}

/** How far a forecast hour is from the departure: "at departure", "1 h 20 min after departure".
 * The heatmap's hour 0 is the forecast hour nearest the departure, so it can be up to half an hour
 * before or after it. */
export function fromDeparture(hour: string, departure: string): string {
  const minutes = Math.round((Date.parse(hour) - Date.parse(departure)) / 60_000)
  if (minutes === 0) return 'at departure'
  return `${formatSpan(Math.abs(minutes))} ${minutes > 0 ? 'after' : 'before'} departure`
}

/** A number with exactly `digits` decimals: "1,234.5". */
export function formatNumber(value: number, digits: number): string {
  return value.toLocaleString(LOCALE, { minimumFractionDigits: digits, maximumFractionDigits: digits })
}

/** "882.7 mi". The API has already rounded the value; this only formats it. */
export function formatMiles(miles: number): string {
  return `${formatNumber(miles, 1)} mi`
}

export function formatMph(mph: number | null): string {
  return mph === null ? 'No data' : `${formatNumber(mph, 1)} mph`
}

/** Rain and snow keep the API's three decimals, so a shown value always matches its level. */
export function formatRate(inPerHr: number | null): string {
  return inPerHr === null ? 'No data' : `${formatNumber(inPerHr, 3)} in/hr`
}

export function formatPounds(pounds: number): string {
  return `${formatNumber(pounds, 0)} lb`
}

export function browserTimeZone(): string {
  return Intl.DateTimeFormat().resolvedOptions().timeZone
}

/** A Date as the "YYYY-MM-DDTHH:MM" local value a datetime-local input uses. */
export function toLocalInputValue(date: Date): string {
  const pad = (n: number) => String(n).padStart(2, '0')
  return `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())}T${pad(date.getHours())}:${pad(date.getMinutes())}`
}

export function nextFullHour(now: Date): Date {
  const next = new Date(now)
  next.setMinutes(0, 0, 0)
  next.setHours(next.getHours() + 1)
  return next
}

/** The last departure the weather forecast covers: 16 days from the start of today in UTC, minus an hour. */
export function lastForecastHour(now: Date): Date {
  const startOfTodayUtc = Date.UTC(now.getUTCFullYear(), now.getUTCMonth(), now.getUTCDate())
  return new Date(startOfTodayUtc + (16 * 24 - 1) * 3600 * 1000)
}
