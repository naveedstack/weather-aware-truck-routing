# Product Requirements Document

**Product:** Weather-Aware Truck Routing
**Version:** 1.0
**Last updated:** 2026-10-27
**Status:** Implemented — all functional requirements complete and verified by automated tests

---

## 1. Problem

A truck driver choosing between routes needs to know more than which one is shortest. A 45 mph
crosswind that is merely uncomfortable for a car can be a legal and physical stop for a loaded
semi-trailer, and the same storm matters differently depending on when the truck actually reaches
it. General-purpose navigation answers "which way is fastest"; it does not answer **"which way is
safest for *this* load, leaving at *this* time."**

Weather forecasts and routing both exist as services, but nothing joins them along a route at the
times a specific truck will be at specific places. That join is the product.

## 2. Goals

| # | Goal |
|---|---|
| G1 | Give a driver three genuinely different route options for one trip |
| G2 | Rate the weather risk at points along each route, at the time the truck arrives there |
| G3 | Account for load weight, which changes what counts as dangerous |
| G4 | Recommend one route, and explain in one sentence why it won |
| G5 | Show the whole picture on a map: routes, risk, ETAs, and weather over the next 48 hours |
| G6 | Return a complete plan in about 20 seconds, even for a coast-to-coast trip |

### Non-goals

- Building a routing engine. Third-party routing, geocoding and weather APIs are used deliberately.
- Turn-by-turn navigation or live in-cab guidance. This is a pre-trip planning tool.
- Modelling hours-of-service rest breaks. ETAs assume continuous driving.
- Accounts, saved trips, fleet management, or dispatch workflow.
- Native mobile apps. The deliverable is a responsive web app.

## 3. Users

**Primary — the driver or owner-operator.** Plans a trip the day before or the morning of. Knows
their load weight. Wants a quick, legible answer and the detail to back it up.

**Secondary — the dispatcher.** Compares options for a driver and needs to justify the choice.

Both are assumed to be in the US, Canada or Mexico, working in miles, pounds, mph and inches.

## 4. User stories

1. As a driver, I enter where I'm going, when I'm leaving and what I'm hauling, and I get three
   route options back.
2. As a driver, I can see which route is recommended and the one measure that decided it.
3. As a driver, I can see *where* on a route the weather turns bad, not only how much bad weather
   there is.
4. As a driver, I can click any point on a route and see the exact forecast for the hour I'll be
   there, and which condition drove its risk level.
5. As a driver hauling 45,000 lb, I see higher risk levels than I would hauling 10,000 lb through
   the same wind.
6. As a driver, I can scrub forward through 48 hours of forecast to see whether leaving later would
   be better.
7. As a driver, if a route has conditions I should not drive in, I am told plainly — even if it is
   the best of the three.

## 5. Functional requirements

### 5.1 Trip input

| ID | Requirement |
|---|---|
| FR-1 | Accept an origin and destination as free text (city/state, address or ZIP), up to 200 characters |
| FR-2 | Suggest up to five matching cities as the user types, from 3 characters, without blocking free-text entry |
| FR-3 | Accept a departure date and time, which must carry a time zone offset |
| FR-4 | Accept a load weight from 0 to 80,000 lb (the US federal gross limit, as a sanity bound) |
| FR-5 | Accept a checkpoint sampling interval of 10, 25 or 50 miles, defaulting to 25 |
| FR-6 | Reject a departure more than 15 minutes in the past, or beyond the weather forecast horizon (~16 days) |
| FR-7 | Reject an origin and destination that are the same place (textually, or within 0.5 miles) |

### 5.2 Routing

| ID | Requirement |
|---|---|
| FR-8 | Return **3 truck route options** per trip, using a commercial-vehicle routing profile |
| FR-9 | Routes must be meaningfully distinct — at least 10% of one route's length more than 1 km from another |
| FR-10 | When the routing provider returns fewer than 3 distinct routes, search for more via offset waypoints |
| FR-11 | Reject an alternative route taking more than 1.5× the main route's travel time |
| FR-12 | When fewer than 3 routes can be found, return the routes found plus a notice saying why |
| FR-13 | Use traffic-aware travel time for the chosen departure, and per-point timing for checkpoint ETAs |

### 5.3 Weather sampling

| ID | Requirement |
|---|---|
| FR-14 | Place checkpoints at the origin, every N miles (N = 10/25/50) and the destination |
| FR-15 | Compute each checkpoint's ETA from the routing provider's own cumulative timing, not an average speed |
| FR-16 | Fetch the forecast for each checkpoint at **the hour nearest its ETA** |
| FR-17 | Each checkpoint accounts for the road halfway to its neighbours, so a route's miles sum to its length |
| FR-18 | Treat a missing forecast value as "No data" rather than as zero or as safe |

### 5.4 Risk assessment

| ID | Requirement |
|---|---|
| FR-19 | Classify wind, rain and snow at each checkpoint per the thresholds in §6.1 |
| FR-20 | Apply the load rules in §6.2, which may only raise a level, never lower it |
| FR-21 | A checkpoint's overall level is the worst of its wind, rain and snow levels |
| FR-22 | Report each condition's own level alongside the overall level, and name any load rule applied |

### 5.5 Recommendation

| ID | Requirement |
|---|---|
| FR-23 | Rank routes by: fewest No Travel miles → fewest Severe miles → fewest High miles → lowest average risk → shortest travel time |
| FR-24 | State the first measure on which the winner beat the runner-up, with both values |
| FR-25 | Mark any route with No Travel miles as unsafe |
| FR-26 | If every route is unsafe, still recommend the least bad one, with an explicit warning |
| FR-27 | Warn when the recommended route has miles with no forecast data |
| FR-28 | Compare routes at the precision shown on screen, so a tie on screen is a tie in the ranking |

### 5.6 Map and results

| ID | Requirement |
|---|---|
| FR-29 | Draw all routes on one map, the selected route emphasised and on top |
| FR-30 | Draw every checkpoint coloured by its own risk level, with the start and destination marked |
| FR-31 | Open a detail popup for any checkpoint: ETA, forecast hour, wind, gusts, rain, snow, each level, any load rule |
| FR-32 | Show a summary card per route: distance, travel time, arrival, average risk, and miles per risk level |
| FR-33 | Let the user select a route by card or keyboard, which re-emphasises it on the map |
| FR-34 | Zoom the map to fit the plan's routes, clear of the overlaid panel and legend |
| FR-35 | Provide a legend for every colour and marker used |

### 5.7 Heatmap

| ID | Requirement |
|---|---|
| FR-36 | Show a weather risk heatmap over a corridor band around the routes (10 miles either side) |
| FR-37 | Provide a **0–48 hour forecast slider**, hour 0 being the departure's forecast hour |
| FR-38 | Apply the same risk rules and the entered load to heatmap cells as to checkpoints |
| FR-39 | Moving the slider must require no server request — all 49 hours arrive with the plan |
| FR-40 | Keep checkpoints at their ETA-based levels when the slider moves |

## 6. Business rules

These are the authoritative rules. The implementation is verified against every boundary value
below by an automated test.

### 6.1 Risk thresholds

| Condition | Low | Moderate | High | Severe | No Travel |
|---|---|---|---|---|---|
| **Wind** | < 25 mph | 25–34 mph | 35–44 mph | 45–54 mph | ≥ 55 mph |
| **Rain** | < 0.10 in/hr | 0.10–0.25 in/hr | 0.25–0.50 in/hr | 0.50–1.00 in/hr | > 1.00 in/hr |
| **Snow** | < 0.5 in/hr | 0.5–1.0 in/hr | 1.0–2.0 in/hr | 2.0–3.0 in/hr | > 3.0 in/hr |

The source table leaves two kinds of edge undefined: values that fall in two bands (rain of exactly
0.25 in/hr) and values that fall in none (34.6 mph). Resolution: **"A up to B" includes A but not B;
"A to B" includes both; a value in two bands takes the higher one.** Values are rounded to the
weather API's own precision (0.1 mph, 0.001 in) before classification, so float noise cannot move a
value across a boundary.

### 6.2 Load rules

| Condition | Result |
|---|---|
| Wind ≥ 55 mph | **No Travel**, for any load |
| Wind 45–54 mph **and** load > 30,000 lb | **No Travel** |
| Wind 35–44 mph **and** load > 40,000 lb | **Severe** |

The thresholds are strict: exactly 30,000 lb or 40,000 lb does not trigger a rule. Load rules apply
to wind only and can only raise a level.

### 6.3 Average risk

Miles-weighted mean over the miles that have forecast data, scoring Low = 0, Moderate = 1,
High = 2, Severe = 3, No Travel = 4. Miles with no data are reported separately and count as
neither risky nor safe.

### 6.4 Ranking order

> **Note — a deliberate addition.** The source specification lists four criteria, beginning with
> fewest Severe miles. This implementation prepends **fewest No Travel miles**. Without it, a route
> carrying No Travel conditions could beat a drivable route on Severe miles alone, and the product
> would recommend a route the driver should not take. No Travel is a distinct level in §6.1, so
> ranking on it is consistent with the rules. The remaining four criteria are unchanged and in the
> specified order.

## 7. Non-functional requirements

| ID | Requirement |
|---|---|
| NFR-1 | A plan completes in about 20 seconds; the alternative-route search yields rather than overrun it |
| NFR-2 | A plan uses at most ~300 weather locations at the default interval, so two plans can run back to back within the free weather tier |
| NFR-3 | Moving the heatmap slider repaints only the cells whose level changed |
| NFR-4 | The map never rebuilds layers in response to interaction — only source data and feature state change |
| NFR-5 | Every upstream failure maps to a specific, actionable message; rate limits include a retry time |
| NFR-6 | Keyboard operable throughout; risk level is never conveyed by colour alone |
| NFR-7 | Honour `prefers-reduced-motion` and forced-colours mode |
| NFR-8 | Degrade gracefully without WebGL 2: the map is replaced by a message, results still listed |
| NFR-9 | API keys stay server-side and are never exposed to the browser or written to logs |
| NFR-10 | No database; the service is stateless apart from an in-process cache |

## 8. Integrations

| Service | Used for | Notes |
|---|---|---|
| **TomTom Routing v1** | Truck routes, alternatives, per-point timing | v1 rather than Orbis, which has no truck mode. Free tier 20,000 req/month |
| **TomTom Search/Geocoding** | Place lookup, city suggestions | Restricted to US/CA/MX |
| **Open-Meteo** | Hourly forecasts | No key, many locations per request, 16-day horizon, HRRR blended for the US. CC BY 4.0, credited in-app |
| **MapLibre GL JS + OpenFreeMap** | Map rendering and basemap | No key |

Load weight is deliberately **not** sent to the routing provider: its vehicle-weight parameter means
gross vehicle weight, and passing cargo weight alone would understate it. Load is used for risk
rules only.

## 9. Out of scope

Rest-break modelling · road closures and construction · hazmat routing · bridge height and weight
restrictions · fuel stops · multi-stop trips · live tracking · accounts and saved trips · push
notifications · native apps.

## 10. Acceptance criteria

A build is acceptable when all of the following hold:

1. Every FR in §5 is implemented and exercised by an automated test.
2. Every boundary value in §6.1 and §6.2 classifies as the table states.
3. A Dallas → Denver plan returns 3 distinct routes, a recommendation with a reason, a populated
   49-hour heatmap, and completes within the time budget.
4. Each route's miles by risk level sum to its reported distance.
5. The heatmap is identical at all three sampling intervals.
6. Every error path returns the documented JSON error shape with an appropriate status.
7. Backend and frontend test suites, type checking and linting all pass.

**Current status:** all seven met. 481 automated tests pass (356 backend, 125 frontend); `ruff`,
`tsc` and `oxlint` are clean.

## 11. Decision log

Roughly 39 decisions were required where the source specification was silent — threshold edges,
what "average risk" averages over, how to guarantee three distinct routes, how to stay inside a free
weather tier, what the slider's hour 0 means. Each is recorded with its rationale in the
[README's Assumptions section](README.md#assumptions), numbered for reference.

## 12. Success measures

| Measure | Target |
|---|---|
| Plan latency, typical trip | < 10 s |
| Plan latency, coast-to-coast | < 20 s |
| Distinct routes returned | 3 for the large majority of trips |
| Heatmap slider interaction | No perceptible lag; no network request |
| Risk rule correctness | 100% of specified boundary values |
