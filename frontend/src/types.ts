// The JSON of POST /api/plan/ (see the README's "API" section). Times are UTC ISO strings, distances
// are miles, and risk levels are 0 (Low) to 4 (No Travel), or null for "No data".

export type RiskLevel = 0 | 1 | 2 | 3 | 4

export const INTERVALS = [10, 25, 50] as const
export type IntervalMi = (typeof INTERVALS)[number]

export interface TripRequest {
  origin: string
  destination: string
  departure: string // ISO 8601 with an offset
  load_lb: number
  interval_mi: IntervalMi
}

export interface Place {
  query: string
  name: string
  lat: number
  lon: number
}

export interface Checkpoint {
  mile: number
  lat: number
  lon: number
  covers_mi: number
  eta: string
  forecast_hour: string
  wind_mph: number | null
  gust_mph: number | null
  rain_in_per_hr: number | null
  snow_in_per_hr: number | null
  risk: RiskLevel | null
  wind_risk: RiskLevel | null
  rain_risk: RiskLevel | null
  snow_risk: RiskLevel | null
  load_rule: string | null
}

export interface RouteMiles {
  no_travel: number
  severe: number
  high: number
  moderate: number
  low: number
  no_data: number
}

export interface Route {
  id: string
  via: boolean
  recommended: boolean
  unsafe: boolean
  distance_mi: number
  travel_time_min: number
  arrival: string
  average_risk: number | null
  miles: RouteMiles
  line: [number, number][] // [lon, lat]
  checkpoints: Checkpoint[]
}

export interface HeatmapCell {
  bounds: [number, number, number, number] // west, south, east, north
  levels: string // one character per hour: "0"-"4", or "-" for No data
  causes: string // what set each hour's level: "w" wind, "r" rain, "s" snow, or "-" for none
  values: string // that condition's reading per hour, comma separated; empty below Moderate
}

export interface Plan {
  origin: Place
  destination: Place
  departure: string
  load_lb: number
  interval_mi: IntervalMi
  routes: Route[]
  recommendation: { route_id: string; reason: string; warnings: string[] }
  notices: string[]
  heatmap: { cell_size_deg: number; hours: string[]; cells: HeatmapCell[] }
  weather_locations: number
}
