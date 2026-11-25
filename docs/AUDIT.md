# Audit report

Two audit rounds before challenge submission (21 and 22 November 2026). Scope: backend, frontend, SAM template,
scripts and documentation. Method: code review, automated tests, linting, local end-to-end runs, stubbed script
runs, and checks of AWS documentation. **No live AWS account and no real browser were available**, so those
areas are listed under "Not verified".

## Round 1: security and robustness of the first version

| # | Severity | Issue | Fix |
|---|---|---|---|
| S1 | Medium | `student_id` defaulted to a shared value, so orders from users without an id would mix | `student_id` is required and validated |
| S2 | Medium | An expired plan could be ordered until DynamoDB's TTL cleanup (which can lag) removed it | Expiry enforced in code on every read |
| S3 | Low | Broad IAM policies (`DynamoDBCrudPolicy`, Bedrock `*`) | Explicit table-scoped actions; Bedrock limited to Bedrock ARNs |
| S4 | Low | 40-bit plan ids | 128-bit ids, format-validated |
| S5 | Low | Non-object JSON, wrong types or a missing id caused 500 errors | All return 400 with a clear message |
| S6 | Low | Private browsing shared one student id | Fresh random id instead |
| B1–B4 | Bug | "2 hours 30" read as a ₹30 budget; "great" triggered food; a missing time silently became 35 min; "1 hour" unsupported | Parser fixed; the API now asks for the time |
| B5 | Bug | Model output such as `"false"` became true | Strict sanitising |
| B6 | Bug | Editing `data.py` and redeploying changed nothing | Seed version marker re-seeds automatically |
| A1–A6 | Config | Never-expiring logs, throttle mismatch, unverified Bedrock model id, Bedrock timeout, no order TTL, outdated Free Tier text | Fixed (details in git history of this file) |
| D1–D4 | Scripts | Deploy overwrote tracked config, no preflight or verification, unsafe destroy | Rewritten with checks, smoke test, polling, clear errors, confirmation |

## Round 2: the multi-page application (sidebar, library, attendance, print, canteen, orders)

### Bugs found and fixed

| # | Issue | How it was found | Fix |
|---|---|---|---|
| B7 | **Canteen cart rendered `[object HTMLDivElement]` text** instead of the cart: an array was passed to the native `replaceChildren`, which does not flatten arrays | UI flow test (jsdom) | Fixed with a spread; the test now fails if `[object`, `undefined` or `NaN` appears on any page |
| B8 | Seat-booking transaction raised a `TypeError`: values were hand-typed for DynamoDB but sent through the boto3 *resource* client, which serialises again | Backend test | Transactions now use the low-level client with explicit types |
| B9 | With a catch-all API route it is not certain that API Gateway answers browser preflight itself | Design review | Lambda also answers OPTIONS with correct CORS headers; test added |
| B10 | A demo opened at the "wrong" time of day (night, or a peak) would show an empty or failing app | Design review | Campus clock with presets, ticking at 10× speed; times clamped to campus hours; examples chosen to stay meaningful at every time of day |

### Configuration changes

- DynamoDB capacity raised from 5/5 to 10/10 (transactions use double write capacity); still inside the always-free 25/25.
- API throttle raised from 5 to 10 requests/s, burst 20, because pages make several calls.
- One catch-all API route; the Lambda route table validates and returns 404 for unknown paths.
- IAM gained `dynamodb:ConditionCheckItem`. **Verified against AWS documentation:** transactions are authorised by the underlying `PutItem`, `UpdateItem`, `DeleteItem`, `GetItem` permissions plus `ConditionCheckItem`; there is no separate `TransactWriteItems` permission.
- `deploy.sh` now also books and cancels a real seat during its smoke test, so a transaction or IAM problem is caught at deploy time. Its `grep` patterns were verified against real handler output.

### Honest note on testing mistakes

Four mistakes in my own test code were found and fixed during development: wrong hand-computed attendance
numbers (replaced with a brute-force check of the formulas for every subject), a property that ignored subjects
already below target, UI selectors that also matched the seat legend and the agent's status dot, and a swapped
argument order. None of them hid an application bug, but they are listed so the test history is transparent.

## Round 3: design and real-browser pass

A headless Chromium became available, so for the first time the app was **looked at**, not just tested. The
first screenshots showed a generic dark-sidebar, gradient-hero dashboard template, which was replaced by a
wayfinding design (route sidebar, departure board, ticket orders, flat colour, self-hosted fonts). Defects found
by looking at real renders, and fixed:

| # | Defect | Fix |
|---|---|---|
| V1 | Hamburger button visible on desktop (a later CSS rule overrode `display: none`) | Rule order fixed; shell rebuilt |
| V2 | Chart y-axis labels clipped; three overlapping lines were hard to read | Replaced by an hourly heat strip |
| V3 | Zone tab "Computer Lab" clipped | Zone tabs are a 4-column grid |
| V4 | **Simulated taken seats formed vertical stripes**: a weak hash (CRC32 of near-identical strings) correlated seats across rows and slots | SHA-256 based mixing; tests added |
| V5 | **Seats 9 and 10 hidden off-screen on phones**, row labels clipped | Fluid seat grid that always fits; a test checks every seat is inside its card |
| V6 | Selected seat lost its colour on hover (CSS specificity) | Hover rule scoped away from selected and own seats |
| V7 | Both print shops showed identical queue charts and the same "Packed" label regardless of their own load | Per-shop time shift and per-shop load label |
| V8 | "Vegetarian lunch" resolved to a 2-piece samosa | "Lunch", "meal", "thali" now mean a proper meal |
| V9 | Demo opened with three red "Missed" classes (unrealistic first impression) | Sample history is mostly attended, deterministic per student |
| V10 | Menu in alphabetical order, no categories; subject cards misaligned when a name wrapped; duplicate item lists on orders; plural kind labels; toasts piling up; booking required scrolling past the map on phones; architecture arrows overlapping boxes | All fixed (grouped menu, aligned cards, sticky "Book seat" bar on phones, capped toasts, redrawn diagram) |
| V11 | Insight text repeated the shop name; board had dead space | Rewritten text; board footer with actions |
| V12 | **If any script failed to load, the router crashed into a blank page** (found while testing an API outage); a missing section silently redirected to the dashboard | The router shows a recoverable error for a section whose script is missing; browser tests cover API-down recovery and a failed script |

Also added: a **strict Content-Security-Policy** (possible now that fonts are self-hosted and there are no inline
scripts or styles), verified to be enforced in Chromium, plus HSTS in the Amplify headers.

## Verified (run in the sandbox)

- 46 of 46 backend tests passed.
- `cfn-lint` clean, `shellcheck` clean, `bash -n` and `node --check` clean.
- jsdom UI flow test: 60 of 60 checks passed against the real handler and mocked DynamoDB.
- Real-browser test (Chromium, desktop and phone viewports, plus failure states): 36 of 36 checks passed, with no console errors and no horizontal scrolling on any page.
- CSP enforcement confirmed in Chromium; the app itself raised no violations.
- All 8 pages reviewed visually on desktop and phone, including states with data (booked seat, cart, orders).
- Every CSS class used by the JavaScript exists in the stylesheet (scripted check).
- Deploy and destroy scripts: stubbed scenarios behaved as designed, including cleanup of `.build/`.
- The whole app ran locally end to end: real Lambda code, mocked DynamoDB, HTTP server and the real frontend.

## Not verified (needs your account or real devices)

- `sam build` and `sam deploy`, and IAM permissions at runtime.
- DynamoDB transactions on real DynamoDB (tested on the `moto` mock; semantics confirmed in AWS documentation).
- Amplify manual deployment, and that `update-app --custom-headers` applies the headers (a failure only prints a warning).
- CORS from the Amplify origin to API Gateway.
- **Other browsers and real devices:** layout was verified in Chromium only (desktop and phone-sized viewports).
  Safari, Firefox and real phones were not tested. Open the live site on a phone and a laptop and follow
  `docs/TESTING.md` before submitting.
- That Amplify applies the custom headers (including the CSP) after `deploy.sh` runs.
- Bedrock: model availability, account model access and the Converse call.
- Whether Amplify and Bedrock are enabled on a Free plan account.

## Remaining recommendations

1. Do the manual pass on real devices (Safari on iPhone, Chrome on Android) and retake screenshots from the live site if you prefer.
2. After deploying, open the browser console on the live site and confirm there are no Content-Security-Policy errors.
3. Add Cognito if you want real per-user ownership of data.
4. Create an AWS Budgets alert in the console (account-level, not created by this project).
5. Replace sample data with real campus values only if you can obtain real numbers; otherwise say "sample data" in your demo.
