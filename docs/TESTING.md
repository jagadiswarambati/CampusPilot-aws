# Testing

## Automated checks (run on 23 November 2026 in the author's sandbox)

| Check | Command | Result |
|---|---|---|
| Backend tests (planner, parser, simulation, all API flows on mocked DynamoDB) | `cd backend && python -m pytest -q` | **46 passed, 0 failed** |
| SAM/CloudFormation template lint | `cfn-lint template.yaml` | **clean** |
| Shell scripts static analysis | `shellcheck scripts/*.sh` | **clean** |
| Shell and JavaScript syntax | `bash -n`, `node --check frontend/js/*.js` | **ok** |
| UI flow test: the real app in jsdom, every page, over HTTP to the dev server | `./scripts/e2e.sh` | **60 of 60 checks passed** |
| Real-browser flow test: Chromium via Playwright at 1440×900 and 390×844 (plan, book a seat, check in, print, order, no clipped seats, no sideways scrolling on any page, no console errors; plus API-down and failed-script recovery) | `./scripts/browser.sh test` | **36 of 36 checks passed** |
| Content-Security-Policy enforcement in Chromium | ad-hoc script | injected inline script and style blocked; the app itself triggers **0 violations** |
| Visual review of all 8 pages on desktop and phone, including populated states | screenshots reviewed by the author | defects found and fixed (see `docs/AUDIT.md`) |
| Deploy script control flow with stubbed `aws`, `sam`, `curl` | manual run | success path, failed seat booking, failed smoke test and cleanup behaved as designed |

`./scripts/validate.sh` runs the backend tests, lint, syntax checks and the jsdom UI flow test.

### What the automated tests cover

- **Planner and parser:** feasibility, alternatives, vegetarian filter, unavailable dishes, budget, print-only,
  contiguous timeline, hours and "an hour", no false budget or food matches, missing time, sanitising model output.
- **Simulation:** deterministic, lunch peak, queues change with the time of day, times clamped to campus hours,
  invalid times rejected.
- **Library:** seat-map shape, booking, one seat per slot, cancelling, two students for one seat, past slots,
  invalid input, simulated-taken seats, other students' seats never shown as yours.
- **Attendance:** subject numbers and the skip calculator, **brute-force checked for every subject**, check-in
  window, duplicate check-in, percentage updates, ended classes.
- **Print and canteen:** page data, job and order flow, idempotency, validation, unavailable dishes, merged lines.
- **Orders and dashboard:** unified list, status progress over time, dashboard aggregates.
- **Robustness:** malformed bodies, wrong types, missing ids, expired plans, menu changes between plan and
  order, re-seeding after data changes, CORS preflight.
- **UI flows (jsdom):** sidebar and routing, dashboard stats and chart, planner with agent trace and order,
  honest "won't fit" flow, attendance check-in, library slot, zone, seat selection, booking, pass, refusal of a
  second seat, cancel, print estimate and job, canteen filters, cart totals and order, orders list and filters,
  architecture live check, clock presets, unknown routes, mobile drawer button, visitor isolation, and a guard
  that fails if `[object`, `undefined` or `NaN` ever appears on a page.

### What the automated tests do not cover

Real AWS services (DynamoDB transactions are tested against the `moto` mock), Safari, Firefox and real phones,
CORS between two real origins, and Bedrock. Use the manual plan below.

## Manual browser plan after `./scripts/deploy.sh` (needs your AWS account and real devices)

Chromium behaviour is covered by `./scripts/browser.sh test`. On real devices, test on the **live Amplify URL**, not localhost, because CORS between Amplify and API Gateway only exists there.

| Area | Check |
|---|---|
| Devices | iPhone Safari, Android Chrome, desktop Chrome, desktop Firefox or Edge |
| Widths | 360, 390, 768, 1024 and 1440 px (browser dev tools are fine for sizes) |
| Sidebar | Visible on desktop; on phones it opens from the menu button, closes on tapping outside or pressing Escape; the active page is highlighted; the orders badge updates |
| Top bar | Clock menu opens and closes, presets work, API pill shows "online"; nothing overlaps at 360 px |
| Dashboard | Four stat cards and the crowd chart fit without horizontal scroll; links work |
| Planner | Agent steps appear one by one; verdict and break bar readable; Ctrl+Enter plans; result scrolls into view on phones |
| Attendance | Check-in button states are clear; rings and bars render; subject cards stack on phones |
| Library | Seat map readable at 360 px (it may scroll sideways inside its own card, not the page); tapping seats is easy; selected, taken and yours are distinguishable; the pass shows after booking; booking the same seat from two browsers refuses the second |
| Print | Shop cards, bars and the job form usable on phones; estimate updates |
| Canteen | Menu grid and filters usable; the cart bar appears on phones and scrolls to the cart; order token shows |
| Orders | Statuses advance on their own within about a minute |
| Keyboard | Tab order sensible, visible focus ring, skip link works |
| Motion | With "reduce motion" on, animations are minimal |
| Private window | Works; data does not carry over from another browser |
| Network | "Slow 3G" still loads; offline shows the friendly message; no double submits |
| Fonts blocked | Block fonts.googleapis.com: the page stays readable with the system font |
| Console | No red errors, no CORS errors |
| Link | Opens in an incognito window without signing in to AWS |

The README screenshots come from the local app (`./scripts/browser.sh shots`). Retake them from the live site if you prefer.

## Optional checks on AWS

- `curl <ApiUrl>/health` returns `{"status": "ok"}`.
- DynamoDB console: `SHOP`, `MENU`, `WALK`, `META` items appear after the first request; `SEAT#...`, `MYSEAT#...`, `ATT#...` and `ORDER#...` items appear as you use the app.
- CloudWatch: the log group from the stack output `LogGroupName` shows invocations and no unhandled errors.
- **Architecture page → Run live check** should show three green results.
- With `USE_BEDROCK=true`, the planner says "Understood with Amazon Bedrock". If it says "built-in rules", check the Lambda logs.
