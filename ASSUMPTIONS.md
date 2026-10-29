# Decisions and assumptions

The assignment specification left a number of things open: where threshold bands begin and end,
what "average risk" averages over, how to guarantee three distinct routes, how to stay inside a
free weather tier. Every such decision is recorded here with its reasoning, numbered so it can be
cited. The authoritative business rules are in [PRD.md](PRD.md); this file explains the choices
behind them. Every rule and number given in the specification is kept as written.

## Risk rules

1. **Ranges.** The requirements table has values that fall in two levels (rain of exactly 0.25 in/hr
   is in both Moderate and High) and gaps between whole numbers (34.6 mph is in neither 25–34 nor
   35–44). We use these ranges, which keep the table's numbers. "A up to B" includes A but not B;
   "A to B" includes both. A value in two levels goes to the higher one.

   | Condition | Low | Moderate | High | Severe | No Travel |
   |---|---|---|---|---|---|
   | Wind (mph) | below 25 | 25 up to 35 | 35 up to 45 | 45 up to 55 | 55 and above |
   | Rain (in/hr) | below 0.10 | 0.10 up to 0.25 | 0.25 up to 0.50 | 0.50 to 1.00 | above 1.00 |
   | Snow (in/hr) | below 0.5 | 0.5 up to 1.0 | 1.0 up to 2.0 | 2.0 to 3.0 | above 3.0 |

2. **Inputs.** Wind is the sustained wind speed at 10 m (Open-Meteo `wind_speed_10m`). Gusts
   (`wind_gusts_10m`) are shown in popups for information only. Rain is the liquid rain rate
   including showers (`rain` + `showers`). Snow is the snowfall rate (`snowfall`, which Open-Meteo
   derives from the snow's water content at 7:1). Open-Meteo's hourly rain and snow values are the
   amount that fell during the hour, so inches in an hour equal in/hr. Open-Meteo is asked for mph
   and inches directly.
3. **Precision.** Values are rounded to the API's precision (0.1 mph, 0.001 in) before they are
   classified, so floating-point noise can't move a value across a boundary
   (0.01 + 0.09 in is 0.1 in, Moderate, not 0.0999…, Low).
4. **Load rules** are applied as written: 45 up to 55 mph with a load **above** 30,000 lb is No
   Travel; 35 up to 45 mph with a load **above** 40,000 lb is Severe (exactly 30,000 or 40,000 lb
   does not trigger them). They only raise the wind level. A checkpoint's level is the worst of its
   wind (after the load rules), rain and snow levels.
5. **Missing values.** If wind, rain or snow is missing, the checkpoint is "No data", unless a known
   value is already No Travel (then nothing can make it better or worse).

## Checkpoints, ETAs and forecast hours

6. **Checkpoints** start at the origin, follow every 10, 25 or 50 miles (a user setting, default
   25) and end at the destination. An interval point within 1 m of the destination is merged into it.
7. **Miles per checkpoint.** Each checkpoint's level covers the road halfway to the previous and
   next checkpoints (the first and last cover up to the origin and destination). Severe, High and
   No Travel miles are counted that way, so all the miles of a route add up to its length.
8. **Distances along the route** come from TomTom, so mile totals match the route length TomTom reports.
9. **ETA** = departure time + TomTom's travel time to the checkpoint, to the nearest minute (half a
   minute rounds up), so the departure plus the shown travel time is the shown arrival.
   The timing comes from TomTom's
   per-point progress data (`extendedRouteRepresentation=distance` and `travelTime`), interpolated
   between progress points by straight-line distance, as TomTom documents. If a route has no
   progress data, guidance-instruction timing is used instead. Not one average speed. (TomTom's
   route sections carry no cumulative time, and on interstates its instructions can be 300+ miles apart.)
10. **Travel time** is TomTom's traffic-aware travel time for the chosen departure (historic traffic
    for future departures). Driver rest breaks (hours-of-service rules) are not modeled.
11. **Forecast hour.** A checkpoint uses the forecast hour nearest its ETA (the minute shown);
    exactly half past rounds up. (Open-Meteo's rain and snow at HH:00 are the totals for the hour
    ending at HH:00.)
12. **Time zones.** All time math is in UTC. The departure is entered in the browser's time zone and
    sent with its offset; the API rejects times without one. Times are shown in the browser's time
    zone with its abbreviation. When clocks change, the browser decides what a local time means: in
    the hour that repeats in autumn it takes the first (daylight-time) one, and a time in the hour
    skipped in spring moves an hour later. The abbreviation in the results shows which was used.

## Weather locations and the heatmap

13. **Forecast locations.** Each checkpoint gets the forecast for its own location, rounded to 0.01°
    (about 1 km). Overlapping routes share locations.
14. **Location budget.** Open-Meteo's free tier allows 600 calls per minute per IP and counts every
    location in a request. A plan at the default 25-mile interval uses at most about 300 locations,
    so two plans can run back to back: the 25-mile checkpoints' locations come first, and the
    heatmap only adds what they leave. Measured on real TomTom routes on October 25, 2026 (the
    routes, and so the counts, vary a little from day to day): Dallas → Denver 232 and Chicago →
    Dallas 243. Coast-to-coast trips are the exception, because their 25-mile checkpoints alone need
    more than 300 (Los Angeles → New York 347, Seattle → Miami 378). The 10-mile interval uses more
    (Dallas → Denver 406, Los Angeles → New York 905, Seattle → Miami 982). If Open-Meteo's limit is
    reached, the app shows a clear message.
15. **Heatmap grid.** A fixed latitude/longitude grid over a band around all routes: the cells a
    route passes through plus the cells whose centre is within 10 miles of a route. A cell that
    contains one of the 25-mile checkpoints' forecast locations uses that forecast (a location on the
    line between cells counts for each of them); any other cell is forecast at its centre. The cell size is the finest of 0.05°–2° whose extra locations fit the
    budget, so long trips get coarser cells (Dallas → Denver: 0.2°, about 14 × 11 miles; Los Angeles →
    New York: 2°). The heatmap is the same at every interval. Each cell is colored by its risk level;
    it is not MapLibre's density heatmap, which would blend neighbouring levels together. Cells are
    drawn under the routes and see-through: Low faintly and riskier levels more strongly, so danger
    stands out, and No data in gray.
16. **Slider.** Hour 0 is the departure's forecast hour (the hour nearest the departure); each step
    is one hour later, up to 48. The heatmap uses the same rules and load as the checkpoints.
    Checkpoints keep their ETA-based levels when the slider moves. The slider sits in the trip panel,
    after the trip and above the results (on phones the panel is below the map). Its label gives the
    hour's date and time in the browser's time zone and how long before or after the departure it is
    (hour 0 can be up to half an hour either side of it), and the arrow, Home and End keys work too.
    Each plan starts at hour 0. Moving the slider asks nothing of the server: all 49 hours come with
    the plan, and only the cells whose level changes are repainted. When the map can't be shown, the
    slider and the legend are left out. Hovering a cell shows its level at the slider's hour,
    which of wind, rain or snow set it, and that condition's reading, so a coloured cell explains
    itself. A Low cell gets no tip: most of the map is Low, and a tip saying so on every hover would
    be noise. Because of that the reading is only sent from Moderate upwards, which keeps the whole
    heatmap's readings to about 23 kB on a typical plan. The cause and the reading travel with the
    plan beside the levels, one slot per hour per cell. A checkpoint's own hover tip wins where the
    two overlap. Each route also carries a truck marker showing where that truck is at the slider's
    hour, drawn as a truck seen from above and turned to the road's heading there. Moving the slider
    drives the markers to the new hour over about half a second: the mile is what is interpolated and
    every mile is placed along the route line, so a truck follows the road rather than cutting across
    it. A route that has already arrived has no marker. Browsers set to reduce motion get the new
    positions without the movement.
17. **Forecast window.** From the departure's forecast hour to the later of +48 hours and the last
    checkpoint ETA, limited to what Open-Meteo offers (about 16 days ahead). Hours outside it are "No data".
18. **Cache.** Forecasts (30 minutes), routes (15 minutes) and geocoding results (24 hours) are
    cached in memory per server instance (on Vercel, per function instance), so changing only the
    interval or the load reuses the routes and most forecasts on a warm instance. A route search
    that was cut short is cached too, and the next plan for the same trip carries on searching from
    it instead of asking TomTom for the main route again. The location budget never relies on the
    cache.

## Ranking and recommendation

19. **Order.** Fewest No Travel miles, then the requirements' order: fewest Severe miles, fewest High
    miles, lowest average risk, shortest travel time.
20. **Precision.** Routes are compared at the precision the UI shows (0.1 mi, 0.01 average risk,
    whole minutes), so a tie on screen is a tie in the ranking. Any distance above zero shows and
    ranks as at least 0.1 mi, so a few yards of No Travel can't tie with a route that has none.
    Full ties keep the order the routes were found in (TomTom's, then the extra routes).
21. **Average risk** is weighted by miles with Low = 0, Moderate = 1, High = 2, Severe = 3,
    No Travel = 4, over the miles that have data. "No data" miles are reported separately and count
    as neither risky nor safe; the recommendation warns when the chosen route has any.
22. **Unsafe routes.** A route with any No Travel miles is marked unsafe. If every route is unsafe,
    the least bad one is still recommended, with a warning.
23. **Explanation.** The recommendation names the first measure on which it beats the runner-up,
    writing durations and distances the way the route cards do ("12 h 5 min", "1,234.5 mi").

## Routes and places

24. **Routing.** TomTom Routing API v1 ("TomTom Maps"), because TomTom's newer Orbis routing API has
    no truck mode: `travelMode=truck`, `vehicleCommercial=true`, `departAt` = the departure,
    `maxAlternatives=2`.
25. **Load weight is not sent to TomTom.** TomTom's `vehicleWeight` is the whole vehicle's weight;
    the cargo alone would understate it. The load is used for the risk rules only.
26. **Distinct routes.** Two routes are distinct when at least 10% of one route's length lies more
    than 1 km from the other.
27. **Extra routes.** If TomTom returns fewer than 3 distinct routes, the missing ones go through a
    TomTom circle waypoint (radius 15 km) beside the main route's midpoint, offset by 10% of its
    length (15–100 miles): left, right, then twice as far. A via route is kept only if it takes at
    most 1.5× the main route's time. Two candidates are tried at a time. The search has a time budget
    so a plan finishes in about 20 seconds: it gets at most 8 seconds and must leave 5 seconds of the
    20 for the weather fetch. "No route through this point" is a final answer; a routing error (busy,
    refused) stops the search without blaming the trip. In every case where fewer than 3 routes are
    shown, a notice says why.
28. **Slow alternatives.** TomTom's request with alternatives can take 15 seconds or more on very
    long trips (about 18 seconds for Anchorage → Miami), while the main route alone takes a few. If
    the alternatives don't arrive within 15 seconds, the plan asks for the main route alone and
    continues with it (and a notice); the next plan for that trip looks for extra routes again.
29. **Places** are geocoded with TomTom's Geocoding API, taking the top result in the US, Canada or
    Mexico. The app's units and weight limit are American, and without that filter a ZIP code such
    as 75201 matched a postal area in the United Arab Emirates. The matched address is shown, so a
    wrong match is visible. Places less than 0.5 miles apart count as the same place.
30. **Route lines** sent to the map are simplified to within 15 m of TomTom's geometry. Checkpoints
    and distances use the full geometry.

## Inputs

31. Load weight: 0 to 80,000 lb (the US federal gross weight limit, as a sanity bound), in whole
    pounds in the form. Departure: must include a time zone offset, from 15 minutes ago up to the end
    of Open-Meteo's forecast range (about 16 days ahead), and is rounded to the nearest minute.
    Origin and destination must differ (ignoring case and spaces).

## Display

32. **Layout.** The map fills the window, with the trip panel on the left and the legend at the
    bottom right. On screens narrower than 900 px the map comes first and the panel and legend follow
    below it. A new plan zooms the map to its routes, clear of the panel and, where there is room, the
    legend. After **Plan trip** the form slides closed and a summary of the trip with a **Change trip**
    button takes its place. Change trip opens the form again with the trip's values (**Cancel** closes
    it and drops any edits), and the routes stay on screen until a new trip is planned. If a plan
    fails, the form opens again at the field the error is about, with what was entered.
33. **Colors.** Risk levels are green (Low), yellow (Moderate), orange (High), red (Severe) and
    purple (No Travel), with gray for No data, and every level is also written out in words. Route
    lines use dark cyan, blue and gray, never a risk color: the selected route is dark cyan (the
    app's accent color), thicker and on top, with larger checkpoints, and the others are blue and
    slate gray. Each plan starts with its
    recommended route selected; clicking another route's card (or moving through the cards with the
    arrow keys) selects that one instead, and the "Recommended" badge stays where it was. The legend
    and each card's swatch use the same colors as the map. Each line carries its route's letter,
    placed where that route runs apart from the others so no two letters share a road. While the
    pointer is over a route's card, that route is drawn thicker and over the others, so all of it
    shows, even where it shares a road with the selected route.
34. **Checkpoints** on the map are colored by their own risk level, from the forecast at their ETA.
    The start and destination are dark rings around their checkpoints; clicking a ring opens its
    checkpoints. Where checkpoints of several routes meet (the start, the destination, shared
    roads), the riskiest is drawn on top, then the selected route's, and the popup lists the
    selected route first. Clicking one shows, for every route with a checkpoint there, its ETA,
    forecast hour, wind, gusts, rain and snow, each value's level, and the load rule that applied,
    if any.
35. **Form defaults.** Departure at the next full hour, a load of 35,000 lb (a common cargo weight),
    checkpoints every 25 miles. The interval is a group of three buttons (10, 25, 50 mi) with one
    selected.
36. **Formatting.** Numbers and dates are written in US English (for example 1,234.5 mi) whatever the
    browser's language, to match the app's text. Times use the browser's time zone (assumption 12).
    The departure field is the browser's own date picker, which shows dates in the operating system's
    regional format.
37. **One plan at a time.** While a plan is computed the form is closed, the panel shows the trip
    being planned, a moving progress bar and placeholder cards, and the map shows a chip with the
    same status. Every 2 seconds the status moves to the next thing the server does: finding the
    places, getting the truck routes, looking for alternatives, placing checkpoints, getting the
    weather, rating and comparing. The browser can't see the server's progress, so the steps follow
    typical timings (the routes take longest), never go back, and stay on the last one ("Almost
    there…") until the answer arrives. Screen readers hear one progress message, not every step.
    The loading view appears only after 300 ms, so plans answered from the cache don't flash it.
    The previous routes stay on the map until the new ones arrive. If the new plan fails, the
    previous results come back, with the error and the form open.
38. **Motion.** New results slide in one card after another, and the form slides open and closed.
    Checkpoint popups fade in and grow from their point, and fade out when closed: by their ×
    button, the Escape key (with focus anywhere in the map), a click on empty map, or a click on
    another checkpoint (the old popup fades out as the new one appears). A popup closed while it is
    still opening disappears at once. Browsers set to reduce motion get none of these animations.

## Place suggestions

39. **City suggestions.** The From and To fields suggest up to five cities as the user types, from
    TomTom's fuzzy search with typeahead (cities only, in the US, Canada and Mexico, where places are
    geocoded), each written as the city and its state or province: "Dallas, TX" (Mexican states are
    spelled out, as in "Monterrey, Nuevo León"). They are only suggestions: any place, an address or
    a ZIP code included, can still be typed in full and planned. They are asked for 300 ms after the
    typing pauses, and only once the text has 3 letters or digits (text that is mostly punctuation
    gets random cities from TomTom). Text is asked for once per field (case, accents and punctuation
    aside), and the server caches the answers for 24 hours. Typing on narrows the list at once, and
    once the text names a city in full, only that city is listed: "Dallas, TX" or "dallas tx" lists
    "Dallas, TX", and "St. Louis, MO" lists TomTom's "Saint Louis, MO" (St., Ste., Ft. and Mt. count
    as Saint, Sainte, Fort and Mount). The state is matched as written there, so "Dallas, Texas"
    still lists Dallas, TX among others. The arrow keys and Enter, or a click, fill the field in, and
    once the arrow keys are used the list stays as it is until the user types again, so a late answer
    can't change the city under the highlight. Escape or leaving the field closes the list; Enter
    with no suggestion picked sends the form as before. The fields follow the ARIA combobox pattern,
    so screen readers hear the number of suggestions and each one picked with the arrow keys. If no
    suggestions can be had, the fields work as plain text fields.


## API choices

- **TomTom** for routing, geocoding and city suggestions: truck routing with traffic-aware travel
  times for a chosen departure time, alternatives, and per-point timing for checkpoint ETAs. Free
  tier: 20,000 routing and 20,000 geocoding requests per month.
- **Open-Meteo** for hourly forecasts: no key, many locations per request, up to 16 days ahead, and
  NOAA's 3 km HRRR model blended in for the US. Data is CC BY 4.0, so the app credits it.
- **MapLibre GL JS** with **OpenFreeMap**'s free basemap (no key).

## Known limitations

- Open-Meteo's free tier is limited per IP (600 locations a minute, 5,000 an hour, 10,000 a day). On
  shared hosting such as Vercel, other users of the same IPs count too, so limits can be hit
  sooner. The app shows a clear message when that happens.
- Coast-to-coast plans need more than the ~300-location budget at the 25-mile interval (Los Angeles
  → New York about 350, Seattle → Miami about 380) and up to about 1,000 at 10 miles, so a second
  such plan within the same minute can be rate-limited.
- The in-memory cache is per server instance and is lost when the instance stops.
- TomTom's free tier allows 20,000 routing and 20,000 geocoding requests a month. A plan makes one
  routing request when TomTom returns three distinct routes, otherwise three or five (via points
  are tried two at a time), plus one more on very long trips whose alternatives time out, and up to
  two geocoding requests. Repeating a trip within 15 minutes reuses the cached routes. City
  suggestions use TomTom's search too: about one request per pause in typing, fewer when the same
  text was asked for in the last 24 hours.
- The API itself has no rate limiting.
- ETAs assume continuous driving (no rest breaks).
- Long trips get a coarser heatmap, because the budget is fixed (2° cells coast to coast).
- Place search takes TomTom's best match even when it is a loose one: text that names no real place
  can still match a street with a similar name (for example "Nowhere Road, VA"). The matched names
  are shown above the results.
- The map needs WebGL 2. Without it the app says so and still lists the routes.
- Vercel Services, which host the frontend and the API in one project, are a beta feature.
