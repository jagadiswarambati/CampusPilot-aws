# Architecture

## Request flow

1. The browser loads the static site from **Amplify Hosting**. `config.js` (written by `deploy.sh`) holds the
   API Gateway address. Every call carries an anonymous `student_id` and the campus time `at=HH:MM`.
2. **API Gateway** (HTTP API, one catch-all route, throttled to 10 requests/s) forwards to a single **Lambda**.
   `app.py` looks the route up in a table, validates input, and returns JSON. Browser preflight (OPTIONS) is
   answered by API Gateway's CORS configuration and, as a safeguard, by the handler itself.
3. Lambda reads and writes **DynamoDB**. `sim.py` turns the campus time into rush levels, queues and occupancy.
   `planner.py` does the scheduling maths. Neither makes any AWS call.
4. Optionally (`USE_BEDROCK=true`) `intent.py` asks **Amazon Bedrock** to read a planner request, with an 8 s
   timeout and a rule-based fallback.

## Frontend

A static site with no build step: `index.html`, one stylesheet and classic scripts (`js/core.js`, `js/main.js`
and one file per page). A hash router (`#/library`) keeps it host-agnostic. Fonts are self-hosted, so the page
makes no third-party requests and a strict Content-Security-Policy (no inline script or style) can be applied.
Pages build the DOM with a small helper that inserts server text as text nodes, never as HTML. Each page owns
its timers and cancels them on navigation, so a slow response can never paint into the wrong page.

## Main flows

| Flow | Steps |
|---|---|
| **Plan a break** | validate text → parse (Bedrock or rules) → ask for time if missing → load campus data → apply live queues and prep times from `sim.py` → run planner → store each plan (128-bit id, 1 h TTL) → return verdict, plans and the agent trace |
| **Confirm a plan** | validate ids → load plan (reject if expired, even before TTL cleanup) → reject infeasible → re-check the dish with a strongly consistent read → conditional put (a second confirm returns 409) |
| **Book a seat** | validate slot and seat → reject ended slots → reject seats held by simulated students → **one DynamoDB transaction** puts `SEAT#<date>/<slot>#<seat>` and `MYSEAT#<student>/<date>#<slot>`, each with `attribute_not_exists(sk)`; cancellation reasons tell "seat taken" from "you already have a seat in this slot" |
| **Check in** | validate period → status from the timetable and campus time (`upcoming`, `checkin`, `ongoing`, `ended`) → reject outside the window → conditional put (duplicate returns 409) |
| **Print job / food order** | validate input → price and availability from live server data → ETA → conditional put keyed by the client's `request_id` (double clicks return 409) |
| **Order status** | computed on read from `created_at` and `eta_min` at demo speed (10×), so no background process is needed |

## DynamoDB single-table model

| Entity | `pk` | `sk` | Notes |
|---|---|---|---|
| Print shop | `SHOP` | shop id | seeded from `data.py` |
| Menu item | `MENU` | item id | seeded from `data.py` |
| Walking time | `WALK` | `A#B` | seeded from `data.py` |
| Seed marker | `META` | `seed` | hash of `data.py`; a change re-seeds and removes stale items |
| Plan (temporary) | `PLAN` | plan id | plan JSON, `ttl` 1 hour |
| Order | `ORDER#<student>` | plan id or `request_id` | `kind` = plan, print or canteen; tokens, ETA, items, `ttl` 30 days |
| Seat booking | `SEAT#<date>` | `<slot>#<seat>` | `owner`, `ttl` 2 days |
| Student's slot | `MYSEAT#<student>` | `<date>#<slot>` | `seat`, `ttl` 2 days |
| Attendance mark | `ATT#<student>` | `<date>#<period>` | `ttl` 7 days |

Every access pattern is a key lookup or a single-partition query, so no secondary index is needed. Fetching
`SEAT#<date>` returns all of the day's bookings in one query, which is how every slot's free count is computed.

## IAM

The function role allows `GetItem`, `PutItem`, `DeleteItem`, `Query`, `BatchWriteItem` and `ConditionCheckItem`
on this table only. These are the actions AWS documents for transactions (there is no separate
`TransactWriteItems` permission). With Bedrock enabled it also allows `bedrock:InvokeModel` on Bedrock model and
inference-profile ARNs. CloudWatch Logs access comes from SAM's default execution role.

## Design decisions

- **Deterministic core, optional AI edge.** Scheduling must be correct, so it is plain, tested code. Bedrock
  only extracts fields from a sentence, and its output is clamped and validated. The "agent" trace is built from
  the numbers the planner actually used.
- **One simulation, every page.** Rush, queues and occupancy come from one module, so the planner, print page,
  canteen, library and dashboard always agree at any campus time. The campus clock makes demos independent of
  when a judge opens the site.
- **Real where it matters.** Bookings, check-ins and orders are really stored and protected by conditional
  writes and transactions. Crowd levels and other students are simulated and labelled as such in the UI.
- **Graceful degradation.** Bedrock failure falls back to rules; UI errors are friendly; refresh failures never
  blank a page that already loaded.
- **One Lambda, many routes.** Keeps cold starts, IAM and deployment simple at this scale; the route table makes
  splitting later straightforward.
- **Provisioned DynamoDB (10/10).** Stays inside the always-free allowance. Transactional writes use double
  capacity, which this setting covers for demo traffic.
- **Wayfinding design language.** Services are "lines" with their own colour, the sidebar is a route, the
  dashboard is a departure board, and orders and library passes are tickets. The metaphor is consistent across
  every page, which is what makes the app feel designed rather than assembled.
- **No frontend build step.** Plain classic scripts and one stylesheet deploy as a zip in seconds, and run
  unchanged in the jsdom test.
- **Seed versioning.** Editing `data.py` and redeploying re-seeds the table automatically.
- **Short campus-data cache.** Shops, menu and walking times change rarely, so each Lambda container caches them
  for 20 seconds (callers get a copy, so live queue adjustments never corrupt the cache). This roughly halves
  DynamoDB reads, which is the tightest limit at 10 provisioned read units.
- **Cost guards.** Throttling, 14-day log retention, TTL on every temporary record, Bedrock off by default.
