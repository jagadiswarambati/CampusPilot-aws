// UI flow test: loads the real app (index.html + js/*.js) in jsdom and drives every page over HTTP against
// `python backend/dev_server.py`. Checks logic and DOM only (no layout, no CSS, no real browser).
import { JSDOM } from "jsdom";

const BASE = process.env.BASE || "http://127.0.0.1:8787";
let failures = 0;
const check = (name, ok, extra = "") => { console.log(`${ok ? "PASS" : "FAIL"}  ${name}${ok ? "" : "  -> " + extra}`); if (!ok) failures++; };
const until = async (fn, ms = 8000) => { const t = Date.now(); while (Date.now() - t < ms) { let v; try { v = fn(); } catch { v = null; } if (v) return v; await new Promise((r) => setTimeout(r, 50)); } return null; };

async function open(hash = "#/dashboard", { student, clock } = {}) {
  const dom = await JSDOM.fromURL(BASE + "/" + hash, {
    runScripts: "dangerously", resources: "usable", pretendToBeVisual: true,
    beforeParse(w) {
      w.fetch = (...a) => fetch(...a); w.AbortController = AbortController;
      w.scrollTo = () => {};
      if (student) w.localStorage.setItem("cp_student", student);
      if (clock) w.localStorage.setItem("cp_clock", clock);
    },
  });
  await new Promise((r) => dom.window.addEventListener("load", r));
  return dom.window;
}
const go = async (w, id) => { w.location.hash = "#/" + id; await new Promise((r) => setTimeout(r, 150)); };
const $ = (w, s) => w.document.querySelector(s);
const $$ = (w, s) => [...w.document.querySelectorAll(s)];
const leaks = (w) => /\[object |undefined|NaN/.test(w.document.getElementById("view").textContent);
const toast = (w) => $$(w, "#toasts .toast").map((t) => t.textContent).join(" | ");

const w = await open();

// ---------- shell ----------
check("sidebar lists all 8 sections", $$(w, "nav a[data-nav]").length === 8, String($$(w, "nav a").length));
check("dashboard is the default page", $(w, "nav a.active").dataset.nav === "dashboard" && $(w, "#page-title").textContent === "Dashboard");
check("API health pill goes online", !!(await until(() => /API online/.test($(w, "#health").textContent))), $(w, "#health").textContent);
check("campus clock shows a time", /^\d\d:\d\d$/.test($(w, "#clock-time").textContent));

// ---------- dashboard ----------
await until(() => $(w, ".board"));
check("dashboard renders the next-up board and 4 stat cards", !!$(w, ".board") && $$(w, ".stat").length === 4, String($$(w, ".stat").length));
check("board lists remaining classes with times", $$(w, ".board-row").length >= 2 && /^\d\d:\d\d$/.test($(w, ".board-row .time").textContent));
check("dashboard shows attendance % and a 3-row crowd heat strip", /%/.test($(w, ".stat .big").textContent) && $$(w, ".heat .cell").length === 36 && $$(w, ".heat .cell.now").length === 3);
check("60-second tour links to the 4 main steps", $$(w, ".tour li a").length === 4 && $(w, ".tour li a").getAttribute("href") === "#/planner");
check("agent insights cover attendance, print, library and canteen", $$(w, ".insight").length === 4);

// ---------- planner + agent trace ----------
await go(w, "planner");
$$(w, ".examples button")[0].click();
check("example fills the planner textarea", $(w, "#ask").value.includes("40 minutes"));
$(w, "#go").click();
check("agent shows 'working' state immediately", !!$(w, ".trace li .tick.wait"));
const verdict = await until(() => $(w, ".verdict.ok"), 15000);
check("agent trace reveals 5+ real steps", $$(w, ".trace li").length >= 5, String($$(w, ".trace li").length));
check("feasible verdict, break bar and steps render", !!verdict && !!$(w, ".bar") && $$(w, "ol.steps li").length >= 5);
$(w, ".plan .btn.primary").click();
check("planner order placed with PO/FO tokens", !!(await until(() => /PO-[A-Z0-9]{6}/.test($(w, ".plan .done")?.textContent || "") && /FO-/.test($(w, ".plan .done").textContent))), "done=" + ($(w, ".plan .done")?.textContent) + " toast=" + toast(w) + " err=" + ($(w, ".plan .err")?.textContent));
check("orders badge appears in the sidebar", !!(await until(() => !$(w, '[data-nav="orders"] .nav-badge').hidden)));

$(w, "#ask").value = CP_EXAMPLE_2();
function CP_EXAMPLE_2() { return "Only 22 minutes left. I need 50 pages in color and a lunch thali."; }
$(w, "#go").click();
await until(() => $(w, ".verdict.bad"), 15000);
check("infeasible plan is honest and offers alternatives", !!$(w, ".verdict.bad") && /What would fit/.test($(w, "#result").textContent) && /can't be ordered/.test($(w, "#result").textContent));
$(w, "#ask").value = "I need 25 pages printed"; $(w, "#go").click();
check("missing time is asked for in the UI", !!(await until(() => /how long/.test($(w, "#result")?.textContent || ""))));

// ---------- attendance ----------
await go(w, "attendance");
await until(() => $$(w, ".subject").length === 6);
check("attendance shows today's classes and 6 subjects", $$(w, ".period").length === 6 && $$(w, ".subject").length === 6);
const before = $$(w, ".subject").map((e) => e.textContent).find((t) => /Environmental/.test(t));
const checkin = await until(() => $(w, 'button[data-period="p4"]'));
check("an in-session class offers check-in", !!checkin);
checkin.click();
check("check-in succeeds and is recorded", !!(await until(() => /Checked in/.test($(w, ".timeline")?.textContent || ""), 6000)), toast(w));
check("percentage updated after check-in", $$(w, ".subject").map((e) => e.textContent).find((t) => /Environmental/.test(t)) !== before);
check("each subject shows a skip calculator", $$(w, ".subject").every((s) => /If you skip the next class: \d+(\.\d)?%/.test(s.textContent)));

check("attendance page has no leaked objects, undefined or NaN", !leaks(w), $(w, "#view").textContent.match(/.{20}(\[object |undefined|NaN).{20}/)?.[0]);
// ---------- library (BookMyShow-style) ----------
await go(w, "library");
await until(() => $(w, ".seat"));
check("6 time slots, earlier ones disabled", $$(w, ".slot").length === 6 && $(w, '.slot[data-slot="0"]').disabled && !$(w, '.slot[data-slot="2"]').disabled);
check("4 zone tabs with seat counts", $$(w, ".tab").length === 4 && /\d+ free/.test($(w, ".tab").textContent));
check("seat map has free and taken seats", $$(w, "button.seat.free").length > 0 && $$(w, "button.seat.taken").length > 0, `${$$(w, "button.seat.free").length}/${$$(w, "button.seat.taken").length}`);
$$(w, "button.seat.free")[0].click();
check("selecting a seat shows it in the side panel", !!$(w, "#book") && $$(w, "button.seat.sel").length === 1, String($$(w, "button.seat.sel").length));
$(w, "#book").click();
check("seat booking creates a digital pass", !!(await until(() => $(w, ".pass"))), toast(w));
check("booked seat is shown as yours", !!(await until(() => $$(w, "button.seat.mine").length === 1)));
$$(w, "button.seat.free")[0].click(); $(w, "#book").click();
check("second seat in the same slot is refused", !!(await until(() => /already have a seat/.test(toast(w)))), toast(w));
$(w, "button[data-cancel]").click();
check("cancelling removes the pass", !!(await until(() => !$(w, ".pass"))));
$(w, '.slot[data-slot="3"]').click();
check("switching slots reloads the map", !!(await until(() => $(w, '.slot[data-slot="3"]').getAttribute("aria-pressed") === "true")));

check("library page has no leaked objects, undefined or NaN", !leaks(w), $(w, "#view").textContent.match(/.{20}(\[object |undefined|NaN).{20}/)?.[0]);
// ---------- print shops + agent ----------
await go(w, "print");
await until(() => $$(w, ".shop").length === 2);
check("2 shop cards with live queue, forecast and jobs", $$(w, ".shop").length === 2 && $$(w, ".bars").length === 2 && $$(w, ".job").length > 0);
check("agent banner and activity log render", /Print agent is working/.test($(w, ".banner").textContent) && $$(w, ".log li").length === 5);
$(w, "#pages").value = "30"; $(w, "#pages").dispatchEvent(new w.Event("input"));
$(w, "#color").click();
check("estimate updates with pages and colour", /min/.test($(w, "#estimate").textContent) && /₹/.test($(w, "#estimate").textContent));
$(w, "#send-job").click();
const ptoken = await until(() => $$(w, ".token").map((t) => t.textContent).find((t) => /^P-\d{4}$/.test(t)));
check("print job returns a P- token", !!ptoken, toast(w));
check("job appears under 'My print jobs'", !!(await until(() => /P-\d{4}/.test($$(w, "section.card").find((s) => /My print jobs/.test(s.textContent))?.textContent || ""))));

check("print page has no leaked objects, undefined or NaN", !leaks(w), $(w, "#view").textContent.match(/.{20}(\[object |undefined|NaN).{20}/)?.[0]);
// ---------- canteen ----------
await go(w, "canteen");
await until(() => $$(w, "[data-dish]").length > 5);
const all = $$(w, "[data-dish]").length;
check("canteen menu shows 15 dishes and live kitchen rush", all === 15 && /Kitchen right now/.test(w.document.body.textContent), String(all));
check("sold-out dish cannot be added", /Sold out/.test($(w, '[data-dish="biryani"]').textContent) && !$(w, '[data-dish="biryani"] [data-add]'));
$(w, "#veg-only").click(); $(w, "#veg-only").dispatchEvent(new w.Event("change"));
check("veg-only filter hides non-veg dishes", $$(w, "[data-dish]").length < all && !$(w, '[data-dish="roll"]'));
$(w, "#veg-only").click(); $(w, "#veg-only").dispatchEvent(new w.Event("change"));
$(w, '[data-cat="Beverages"]').click();
check("category filter shows only beverages", $$(w, "[data-dish]").length === 4, String($$(w, "[data-dish]").length));
$(w, '[data-add="chai"]').click();
$(w, '[data-dish="chai"] button[aria-label="Add one"]').click();
check("cart totals correctly (2 × ₹15)", /₹30/.test($(w, ".total").textContent), $(w, "#cart").textContent);
$(w, "#place-order").click();
const ctoken = await until(() => $(w, "#order-token"));
check("canteen order returns a C- token", !!ctoken && /^C-\d{4}$/.test(ctoken.textContent), toast(w));

check("canteen page has no leaked objects, undefined or NaN", !leaks(w), $(w, "#view").textContent.match(/.{20}(\[object |undefined|NaN).{20}/)?.[0]);
// ---------- orders ----------
await go(w, "orders");
await until(() => $$(w, ".order").length >= 3);
check("orders page lists plan, print and food orders", ["plan", "print", "canteen"].every((k) => $(w, `.order[data-kind="${k}"]`)), $$(w, ".order").map((o) => o.dataset.kind).join(","));
check("each order shows a token, status and stage bar", $$(w, ".order").every((o) => o.querySelector(".tok") && o.querySelector(".pill") && o.querySelectorAll(".stages i").length === 3));
$(w, '[data-kind-filter="print"]').click();
check("filter chips narrow the list", $$(w, ".order").length === 1 && $(w, ".order").dataset.kind === "print");
check("orders progress on their own (simulated status)", !!(await until(() => $$(w, ".order .pill").some((p) => /Ready|Completed|Printing|Preparing|Received|Queued|In progress/.test(p.textContent)))));

check("orders page has no leaked objects, undefined or NaN", !leaks(w), $(w, "#view").textContent.match(/.{20}(\[object |undefined|NaN).{20}/)?.[0]);
// ---------- architecture ----------
await go(w, "architecture");
check("architecture page shows diagram and 6 services", !!$(w, "svg.arch") && $$(w, ".svc").length === 6);
$(w, "#run-check").click();
check("live check pings API and DynamoDB", !!(await until(() => $$(w, "#check-result .pill.ok").length === 3, 10000)));

// ---------- clock and routing ----------
$(w, "#clock-btn").click();
$(w, '[data-clock="morning"]').click();
check("campus clock presets change the time", /^09:/.test($(w, "#clock-time").textContent), $(w, "#clock-time").textContent);
check("clock choice is remembered", w.localStorage.getItem("cp_clock") === "morning");
await go(w, "dashboard");
w.location.hash = "#/nope"; await new Promise((r) => setTimeout(r, 200));
check("unknown route falls back to the dashboard", $(w, "nav a.active").dataset.nav === "dashboard");
$(w, "#burger").click();
check("mobile menu button opens the sidebar drawer", w.document.body.classList.contains("nav-open"));

// ---------- isolation and safety ----------
const sid = w.localStorage.getItem("cp_student");
const other = await open("#/orders", { student: "stu-other99" });
await new Promise((r) => setTimeout(r, 1500));
check("a different visitor sees none of these orders", $$(other, ".order").length === 0);
const returning = await open("#/orders", { student: sid });
check("a returning visitor sees their orders", !!(await until(() => $$(returning, ".order").length >= 3)));
let htmlWriters = 0;
for (const f of ["core", "dashboard", "planner", "attendance", "library", "print", "canteen", "orders", "architecture", "main"]) {
  const src = await (await fetch(`${BASE}/js/${f}.js`)).text();
  if (/\.(innerHTML|outerHTML)\b|insertAdjacentHTML|document\.write/.test(src)) htmlWriters++;
}
check("no client file writes HTML strings (innerHTML, insertAdjacentHTML, document.write)", htmlWriters === 0, String(htmlWriters));

console.log(failures ? `\n${failures} check(s) FAILED` : "\nAll UI flow checks passed");
process.exit(failures ? 1 : 0);
