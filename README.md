# Weather-Aware Truck Routing

A React + Django web app that answers one question: **given this load, leaving at this time, which
route is safest?**

General navigation tells a driver which way is fastest. It doesn't know that a 45 mph crosswind is a
legal stop for a loaded semi-trailer but a non-event for a car, and it doesn't know *when* the truck
will reach the storm. This app joins truck routing to hourly weather forecasts along each route, at
the time the truck actually arrives at each point, and weighs the result against the load.

**Status:** complete. 481 automated tests pass (356 backend, 125 frontend).

## What it does

The driver enters an origin, a destination, a departure time, the load weight and a sampling
interval (10, 25 or 50 miles). The app then:

- gets **3 distinct truck routes** from TomTom;
- places **checkpoints** at the chosen interval and works out when the truck reaches each one;
- fetches the **hourly forecast** for each checkpoint at the hour nearest its ETA;
- rates each one **Low / Moderate / High / Severe / No Travel** from the wind, rain and snow
  thresholds and the load rules;
- **recommends** a route and says in one sentence which measure decided it;
- draws it on a **map** — routes, checkpoints coloured by risk, ETAs in popups, summary cards, and a
  **risk heatmap** with a **0–48 hour slider**.

## How it works

One `POST /api/plan/` request runs this pipeline, inside a 20-second budget:

```
  trip form
     │
     ▼
  1. GEOCODE          origin + destination looked up in parallel (TomTom)
     ▼
  2. FIND ROUTES      TomTom main route + 2 alternatives; keep the distinct ones
     │                 (10% of length, >1 km apart). Still short of 3? search via
     │                 offset waypoints, two at a time, rejecting detours over 1.5x
     ▼
  3. CHECKPOINTS      every N miles; ETA from TomTom's cumulative per-point timing
     │                 each accounts for the road halfway to its neighbours
     ▼
  4. HEATMAP GRID     cells over a 10-mile band around the routes, sized to fit
     │                 the ~300-location weather budget
     ▼
  5. WEATHER          ONE batched Open-Meteo request for every location and hour
     ▼
  6. ASSESS           classify at each ETA's forecast hour; apply load rules;
     │                 worst of wind/rain/snow wins
     ▼
  7. RANK             five criteria in order; the margin becomes the reason
     │
     ▼
  plan JSON  ──▶  map + route cards + 49 hourly heatmap frames
```

Two choices carry most of the weight:

**Timing comes from the routing API, not an average speed.** TomTom's per-point progress data is
interpolated between points, so a checkpoint's ETA reflects real road conditions. That's what makes
"the weather when the truck gets there" meaningful rather than decorative.

**The whole 48-hour forecast ships with the plan.** All 49 hourly frames arrive as compact level
strings, so dragging the slider is pure client-side recolouring — no request, no lag.

## Quick start

Requirements: Python 3.12+ (developed on 3.14), Node.js 22.22.2+ or 24.15+, and a free
[TomTom API key](https://developer.tomtom.com).

**Backend** — with [uv](https://docs.astral.sh/uv/), which reads `.python-version` for you:

```bash
cd backend
uv venv
uv pip install -r requirements-dev.txt
cp .env.example .env          # then fill in TOMTOM_API_KEY
uv run manage.py runserver 8000
```

With stock pip instead: `python3 -m venv .venv`, `.venv/bin/pip install -r requirements-dev.txt`,
`.venv/bin/python manage.py runserver 8000`.

> **`.env` is not optional.** Without `DJANGO_SECRET_KEY` the settings refuse to load and the server
> won't start. `DJANGO_DEBUG=true` (already in `.env.example`) makes the key optional locally, but
> `TOMTOM_API_KEY` is always required — without it `/api/health/` answers and every plan fails.

**Frontend**, in a second terminal:

```bash
cd frontend
npm ci
npm run dev        # http://localhost:5173; /api is proxied to Django on port 8000
```

Open http://localhost:5173 and plan Dallas, TX → Denver, CO.

## Environment variables

| Variable | Required | Meaning |
|---|---|---|
| `TOMTOM_API_KEY` | yes | Routing, geocoding and city suggestions |
| `DJANGO_SECRET_KEY` | yes, unless `DJANGO_DEBUG=true` | Any long random string |
| `DJANGO_DEBUG` | no (default `false`) | `true` for local development only |
| `DJANGO_ALLOWED_HOSTS` | no | Extra comma-separated hosts. `localhost` is allowed when debugging; on Vercel, `*.vercel.app` and the production domain are automatic |

Locally these live in `backend/.env`, which is never committed.

## API

The browser talks only to Django, so the TomTom key never reaches it.

**`POST /api/plan/`**

```jsonc
{ "origin": "Dallas, TX", "destination": "Denver, CO",
  "departure": "2026-10-28T08:00:00-05:00",  // ISO 8601, offset required
  "load_lb": 42000,                          // 0–80,000
  "interval_mi": 25 }                         // 10, 25 or 50
```

Returns the matched places, up to 3 routes and the heatmap. Times are UTC, distances are miles, and
risk levels are `0` (Low) to `4` (No Travel), or `null` for no data. Numbers arrive already rounded
the way the ranking compared them, so the UI never rounds differently.

- `routes[]` — `id`, `recommended`, `unsafe`, `distance_mi`, `travel_time_min`, `arrival`,
  `average_risk`, `miles` (per level), `line` for the map, and `checkpoints[]`
- `checkpoints[]` — `mile`, `lat`/`lon`, `eta`, `forecast_hour`, the four weather values, a level per
  condition, and `load_rule` if one applied
- `recommendation` — `route_id`, `reason`, `warnings[]`
- `heatmap` — `hours[]` (49 of them) and `cells[]`, each with `bounds`, a `levels` string of one
  character per hour, a `causes` string saying which condition set each hour's level (`w` wind,
  `r` rain, `s` snow, `-` none), and a comma-separated `values` string with that condition's
  reading. A value is sent only where the level is Moderate or worse

**`GET /api/places/?q=Dal`** suggests up to five cities for the form's From/To fields.
**`GET /api/health/`** returns `{"status": "ok"}` and calls nothing upstream.

Errors all share one shape — `{"error": {"code", "message"}}` — with `fields` for validation errors.
Codes: `invalid_input` (400), `place_not_found` / `same_place` / `no_route` (422),
`routing_unavailable` / `weather_unavailable` (502), `weather_rate_limited` (503, with
`Retry-After`), `internal_error` (500).

## Architecture

```
backend/
  config/            Django settings (all from env vars), URLs, WSGI entry point
  trips/
    domain/          the trip logic as plain Python — no Django, no HTTP
      risk.py          risk levels, thresholds, load rules
      weather.py       forecast values -> risk inputs
      times.py         UTC helpers, the nearest forecast hour
      geo.py           distances, bearings, sampling along a line
      profile.py       distance and time at every route point, from TomTom's timing
      checkpoints.py   checkpoints every N miles and the miles each covers
      grid.py          the heatmap grid and the weather-location budget
      ranking.py       mile totals, average risk, ranking, recommendation text
      alternatives.py  telling routes apart, choosing via points
    clients/         tomtom.py, openmeteo.py, http.py (per-thread sessions, keys redacted)
    planner.py       orchestrates one plan, within the time budget
    serializers.py   request validation      presenters.py  the response JSON
    views.py         the three endpoints     errors.py      failures and their statuses
    tests/           unit tests + whole-pipeline tests against fake upstream services

frontend/src/
  App.tsx            page state: plan, loading, errors, selection, heatmap hour
  api.ts types.ts    the API client and its typed JSON
  risk.ts format.ts places.ts    colours and labels, display formatting, suggestion rules
  components/        TripForm, PlaceInput, TripBar, PlanSummary, HeatmapSlider,
                     RouteMap, Legend, PlanLoading
  map/
    MapController.ts the one MapLibre map: layers added once, then only data and
                     feature-state change
    geojson.ts heatmap.ts popup.ts    pure functions turning a plan into map features
```

There is no database. The API is stateless apart from an in-process cache (forecasts 30 min, routes
15 min, geocoding 24 h).

## Running tests

```bash
cd backend   && uv run pytest && uv run ruff check .
cd frontend  && npm test && npm run typecheck && npm run lint
```

No API key or `.env` is needed: `config/settings_test.py` supplies fixed values and the fakes block
all real HTTP. The planner and API tests run the whole pipeline against fake TomTom and Open-Meteo
services serving trimmed real Dallas → Denver routes, with weather from simple rules such as a
windstorm over Amarillo.

## More documentation

| File | What's in it |
|---|---|
| **[PRD.md](PRD.md)** | Problem, goals, 40 numbered requirements, and the authoritative risk and load rules |
| **[ASSUMPTIONS.md](ASSUMPTIONS.md)** | Every decision the specification left open, numbered, with reasoning — plus API choices and known limitations |
| **[DEPLOYMENT.md](DEPLOYMENT.md)** | The Vercel runbook, with troubleshooting |
