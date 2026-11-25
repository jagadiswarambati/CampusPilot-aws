"""AWS Lambda entry point (API Gateway HTTP API, payload v2).

Routes (see ROUTES): health, campus, plan, orders, dashboard, attendance, library, print, canteen.
Every route validates its input, returns JSON, and never leaks a stack trace.
"""
import base64
import json
import math
import os
import re
import time
import uuid

import attendance
import data
import intent
import library
import orders
import planner
import repo
import sim

BUFFER = int(os.environ.get("SAFETY_BUFFER_MIN", "5"))
STUDENT_RE = re.compile(r"^[A-Za-z0-9_-]{3,40}$")
ID32_RE = re.compile(r"^[0-9a-f]{32}$")
BAD_STUDENT = "student_id is required: 3-40 letters, digits, '-' or '_'."
ROUTES = {}


def route(method, path):
    def register(fn):
        ROUTES[f"{method} {path}"] = fn
        return fn
    return register


class Ctx:
    def __init__(self, body, query, date, minute):
        self.body, self.query, self.date, self.minute = body, query, date, minute

    def student(self, source=None):
        sid = (source if source is not None else {**self.query, **self.body}).get("student_id")
        return sid if isinstance(sid, str) and STUDENT_RE.match(sid) else None

    @property
    def clock(self):
        return sim.hhmm(self.minute)


def _resp(code, body):
    return {"statusCode": code, "headers": {"Content-Type": "application/json"},
            "body": json.dumps(body, default=repo._num)}


def _error(code, message):
    return _resp(code, {"error": message})


def _int(value, lo, hi):
    """Strict integer in [lo, hi] (no bools, no strings), else None."""
    return value if isinstance(value, int) and not isinstance(value, bool) and lo <= value <= hi else None


def _body(event):
    raw = event.get("body") or "{}"
    if event.get("isBase64Encoded"):
        raw = base64.b64decode(raw).decode("utf-8")
    body = json.loads(raw)
    if not isinstance(body, dict):
        raise ValueError("Body must be a JSON object.")
    return body


def live_campus(minute):
    """Campus data with queue lengths and kitchen prep times adjusted to the simulated time of day."""
    campus = repo.campus()
    extra = sim.prep_extra(minute)
    for s in campus["shops"]:
        s["queue_people"] = sim.queue_people(s, minute)
        s["queue_min"] = sim.queue_minutes(s, minute)
    for m in campus["menu"]:
        m["prep_min"] += extra
    return campus


def _walk(campus, a, b):
    return 0 if a == b else campus["walks"].get(f"{a}#{b}", campus["walks"].get(f"{b}#{a}", 4))


# --------------------------------------------------------------------------- health / campus
@route("GET", "/health")
def health(ctx):
    return _resp(200, {"status": "ok"})


@route("GET", "/campus")
def campus_route(ctx):
    return _resp(200, {**live_campus(ctx.minute), "clock": ctx.clock})


# --------------------------------------------------------------------------- break planner
def _trace(req, campus, result, clock):
    steps = [{"label": "Understood your request", "detail":
              f"{req['minutes']} min available" + (f", {req['pages']} pages{' in colour' if req['color'] else ''}" if req["pages"] else "")
              + (", vegetarian food" if req["food"] and req["veg"] else ", food" if req["food"] else "")
              + (f", budget ₹{req['budget']:g}" if req["budget"] else "") + f". Campus time {clock}."}]
    if req["pages"]:
        steps.append({"label": "Checked print shop queues", "detail": "; ".join(
            f"{s['name']}: {s['queue_people']} waiting, about {s['queue_min']} min" for s in campus["shops"])})
    if req["food"]:
        categories = ("Meals",) if req.get("meal") else data.PLANNER_CATEGORIES
        menu = [m for m in campus["menu"] if m["available"] and m["category"] in categories and (m["veg"] or not req["veg"])]
        label = sim.rush_label(sim.rush("canteen", req["_minute"]))
        steps.append({"label": "Checked the canteen kitchen", "detail": f"{len(menu)} matching dishes available. Kitchen is {label.lower()}."})
    steps.append({"label": "Simulated every combination", "detail":
                  f"{result['considered']} plans, each with walking, queueing and cooking times."})
    best = result["best"]
    if best:
        steps.append({"label": "Picked the best plan" if result["feasible"] else "No plan fits",
                      "detail": f"{best['label']}: {best['total_min']} min of tasks plus a {BUFFER} min safety buffer."})
    return steps


@route("POST", "/plan")
def create_plan(ctx):
    text = ctx.body.get("text")
    if not isinstance(text, str) or not 3 <= len(text.strip()) <= 500:
        return _error(400, "Describe what you need in 3-500 characters.")
    req = intent.parse_request(text.strip())
    if req["minutes"] is None:
        return _error(400, "Tell me how long you have, for example '30 minutes' or '1 hour'.")
    if req["pages"] == 0 and not req["food"]:
        return _error(400, "Say what you need, for example '25 pages printed' or 'a vegetarian lunch'.")
    campus = live_campus(ctx.minute)
    result = planner.plan({**req, "buffer": BUFFER}, campus)
    plans = ([result["best"]] if result["best"] else []) + result["alternatives"]
    for p in plans:
        p["id"] = uuid.uuid4().hex
        repo.save_plan(p)
    trace = _trace({**req, "_minute": ctx.minute}, campus, result, ctx.clock)
    return _resp(200, {"request": req, "trace": trace, "clock": ctx.clock, **result})


@route("POST", "/orders")
def confirm_order(ctx):
    student, plan_id = ctx.student(), ctx.body.get("plan_id")
    if not student:
        return _error(400, BAD_STUDENT)
    if not isinstance(plan_id, str) or not ID32_RE.match(plan_id):
        return _error(400, "plan_id is missing or invalid.")
    plan = repo.get_plan(plan_id)
    if not plan:
        return _error(404, "Plan not found or expired. Create a new plan.")
    if not plan["feasible"]:
        return _error(422, "This plan does not fit your time or budget, so it cannot be ordered.")
    item = plan["item"]
    if item:  # server-side revalidation: never trust the client or a stale plan
        live = repo.get_menu_item(item["id"])
        if not live or not live["available"] or live["price"] != item["price"]:
            return _error(409, f"{item['name']} is no longer available at that price. Plan again.")
    po = f"PO-{uuid.uuid4().hex[:6].upper()}" if plan["shop"] else None
    fo = f"FO-{uuid.uuid4().hex[:6].upper()}" if item else None
    summary = " + ".join(x["name"] for x in (plan["shop"], item) if x)
    order = {
        "created_at": int(time.time()), "simulated": True, "kind": "plan", "plan_label": plan["label"],
        "title": summary, "summary": summary, "tokens": [t for t in (po, fo) if t],
        "total_cost": plan["cost"]["total"], "total_min": plan["total_min"], "eta_min": plan["total_min"],
        "print_order_id": po, "food_order_id": fo,
    }
    try:
        repo.create_order(student, plan_id, order)
    except repo.DuplicateOrder:
        return _error(409, "This plan was already confirmed.")
    return _resp(201, order)


@route("GET", "/orders")
def list_orders(ctx):
    student = ctx.student()
    if not student:
        return _error(400, BAD_STUDENT)
    return _resp(200, {"orders": [orders.shape(o) for o in repo.list_orders(student)]})


# --------------------------------------------------------------------------- dashboard
def _board(att, lib, rows, minute):
    """'Next up' departure board: remaining classes, upcoming library seats and active orders, by time."""
    items = []
    for p in att["today"]:
        if p["status"] != "ended":
            items.append({"time": p["start"], "title": p["subject"], "detail": f"{p['code']} · {p['room']}", "kind": "attendance", "page": "attendance",
                          "status": {"ongoing": "In session", "checkin": "Check-in open", "upcoming": "Upcoming"}[p["status"]],
                          "tone": "ok" if p["status"] == "ongoing" else "info" if p["status"] == "checkin" else ""})
    for m in lib["mine"]:
        start, end = data.SLOTS[m["slot"]]
        if end * 60 > minute:
            items.append({"time": sim.hhmm(start * 60), "title": "Library seat " + library.seat_name(m["seat"]), "detail": m["label"],
                          "kind": "library", "page": "library", "status": "Now" if start * 60 <= minute else "Booked", "tone": "ok"})
    for o in rows:
        if o["progress"] < 1:
            items.append({"time": sim.hhmm(min(minute + o["eta_left_min"], sim.CLOSE - 1)), "title": o["title"][:46],
                          "detail": " · ".join(o["tokens"]), "kind": o["kind"], "page": "orders", "status": o["status"], "tone": "warn"})
    return sorted(items, key=lambda i: i["time"])[:6]


def _insights(att, lib, campus, minute):
    """Agent insights computed from the same live numbers as every other page."""
    out = []
    low = [s for s in att["subjects"] if s["state"] != "good"]
    if low:
        w = min(low, key=lambda s: s["pct"])
        out.append({"kind": "attendance", "page": "attendance", "tone": "warn", "title": f"{w['name']} is at {w['pct']}%",
                    "text": f"Attend the next {w['need']} classes in a row to get back to {att['target']}%."})
    else:
        out.append({"kind": "attendance", "page": "attendance", "tone": "ok", "title": "Attendance is on track", "text": "Every subject is above the target."})
    agent = _print_agent(campus, minute)
    best = next(s for s in campus["shops"] if s["id"] == agent["best_shop"])
    others = [s for s in campus["shops"] if s["id"] != best["id"]]
    out.append({"kind": "print", "page": "print", "tone": "info", "title": f"Print at {best['name']}",
                "text": (f"About {agent['saved_min']} min quicker than {others[0]['name']} for a {agent['pages']}-page job, walk included."
                         if agent["saved_min"] and others else "Both shops are equally quick right now.")})
    open_slots = [s for s in lib["slots"] if not s["ended"]]
    top = max(open_slots, key=lambda s: s["free"])
    out.append({"kind": "library", "page": "library", "tone": "ok", "title": f"Most free seats: {top['label']}",
                "text": f"{top['free']} of {top['total']} seats are free{' right now' if top['current'] else ''}."})
    hours, now_i = sim.forecast("canteen"), max(0, minute // 60 - sim.OPEN // 60)
    quiet = min(range(now_i, len(hours)), key=lambda i: hours[i])
    label = sim.rush_label(sim.rush("canteen", minute))
    out.append({"kind": "canteen", "page": "canteen", "tone": "warn" if label == "Packed" else "info", "title": f"Canteen is {label.lower()}",
                "text": "This is the quietest it will be today." if quiet == now_i else f"Quietest hour left today: {sim.OPEN // 60 + quiet}:00."})
    return out


@route("GET", "/dashboard")
def dashboard(ctx):
    student = ctx.student()
    if not student:
        return _error(400, BAD_STUDENT)
    att = attendance.summary(student, ctx.date, ctx.minute)
    lib = library.state(student, ctx.date, ctx.minute)
    campus = live_campus(ctx.minute)
    shops = sorted(campus["shops"], key=lambda s: s["queue_min"])
    nxt = next((p for p in att["today"] if p["status"] != "ended"), None)
    slot = lib["slots"][lib["chosen"]]
    lowest = min(att["subjects"], key=lambda s: s["pct"])
    rows = [orders.shape(o) for o in repo.list_orders(student)]
    canteen_rush = sim.rush("canteen", ctx.minute)
    return _resp(200, {
        "clock": ctx.clock,
        "attendance": {"overall": att["overall"], "target": att["target"], "lowest": lowest},
        "next_class": nxt,
        "library": {"slot": slot, "mine": lib["mine"]},
        "print": {"best": {"name": shops[0]["name"], "wait_min": shops[0]["queue_min"], "people": shops[0]["queue_people"]},
                  "shops": [{"name": s["name"], "wait_min": s["queue_min"]} for s in shops]},
        "canteen": {"rush": canteen_rush, "label": sim.rush_label(canteen_rush)},
        "orders": {"active": sum(1 for o in rows if o["progress"] < 1), "total": len(rows), "recent": rows[:3]},
        "board": _board(att, lib, rows, ctx.minute), "insights": _insights(att, lib, campus, ctx.minute),
        "pulse": {"hours": list(range(sim.OPEN // 60, sim.CLOSE // 60)), "print": sim.forecast("print"),
                  "canteen": sim.forecast("canteen"), "library": sim.forecast("library")},
    })


# --------------------------------------------------------------------------- attendance
@route("GET", "/attendance")
def attendance_route(ctx):
    student = ctx.student()
    if not student:
        return _error(400, BAD_STUDENT)
    return _resp(200, {**attendance.summary(student, ctx.date, ctx.minute), "clock": ctx.clock})


@route("POST", "/attendance/checkin")
def attendance_checkin(ctx):
    student, pid = ctx.student(), ctx.body.get("period_id")
    if not student:
        return _error(400, BAD_STUDENT)
    p = attendance.period(pid) if isinstance(pid, str) else None
    if not p:
        return _error(400, "period_id is missing or invalid.")
    status = attendance.status_of(p, ctx.minute)
    if status == "ended":
        return _error(422, f"{p['code']} ended at {p['end']}. Check-in is closed.")
    if status == "upcoming":
        return _error(422, f"Check-in opens {attendance.CHECKIN_OPENS_BEFORE} minutes before class, at "
                           f"{sim.hhmm(sim.parse_hhmm(p['start']) - attendance.CHECKIN_OPENS_BEFORE)}.")
    try:
        repo.mark_attendance(student, ctx.date, p["id"], p["code"])
    except repo.AlreadyMarked:
        return _error(409, "You are already checked in for this class.")
    return _resp(201, {"period_id": p["id"], "code": p["code"], "checked_in": True})


# --------------------------------------------------------------------------- library
def _slot(value):
    return _int(value, 0, len(data.SLOTS) - 1)


@route("GET", "/library")
def library_route(ctx):
    student = ctx.student()
    if not student:
        return _error(400, BAD_STUDENT)
    slot = None
    if "slot" in ctx.query:
        slot = _slot(int(ctx.query["slot"])) if str(ctx.query["slot"]).isdigit() else None
        if slot is None:
            return _error(400, "slot must be a number from 0 to 5.")
    return _resp(200, {**library.state(student, ctx.date, ctx.minute, slot), "clock": ctx.clock})


@route("POST", "/library/book")
def library_book(ctx):
    student, slot, seat = ctx.student(), _slot(ctx.body.get("slot")), ctx.body.get("seat")
    if not student:
        return _error(400, BAD_STUDENT)
    if slot is None or not isinstance(seat, str) or seat not in library.VALID_SEATS:
        return _error(400, "slot (0-5) and a valid seat id are required.")
    if data.SLOTS[slot][1] * 60 <= ctx.minute:
        return _error(422, f"The {library.slot_label(slot)} slot has already ended.")
    if sim.lib_taken(ctx.date, slot, seat, library.slot_mid(slot)):
        return _error(409, "That seat is already taken. Pick another one.")
    try:
        repo.book_seat(ctx.date, slot, seat, student)
    except repo.SeatTaken:
        return _error(409, "That seat was just taken by someone else. Pick another one.")
    except repo.AlreadyBooked:
        return _error(409, "You already have a seat in this slot. Cancel it first to pick another.")
    return _resp(201, {"slot": slot, "label": library.slot_label(slot), "seat": seat})


@route("POST", "/library/cancel")
def library_cancel(ctx):
    student, slot = ctx.student(), _slot(ctx.body.get("slot"))
    if not student:
        return _error(400, BAD_STUDENT)
    if slot is None:
        return _error(400, "slot (0-5) is required.")
    try:
        seat = repo.cancel_seat(ctx.date, slot, student)
    except repo.NoBooking:
        return _error(404, "You have no booking in this slot.")
    return _resp(200, {"cancelled": seat, "slot": slot})


# --------------------------------------------------------------------------- print shops
def _print_agent(campus, minute, pages=20):
    rows = []
    for s in campus["shops"]:
        total = _walk(campus, "CLASS", s["loc"]) * 2 + s["queue_min"] + math.ceil(pages / s["ppm"])
        rows.append((total, s))
    rows.sort(key=lambda r: r[0])
    best, other = rows[0][1], rows[-1][1]
    saved = rows[-1][0] - rows[0][0]
    busiest = max(campus["shops"], key=lambda s: s["queue_people"])
    redirected = 1 + int(sim.unit("redirect", minute // 3) * 4)
    events = [
        (0, f"{busiest['name']} has {busiest['queue_people']} jobs waiting. Recommending {best['name']} "
            f"for a {pages}-page job (saves about {saved} min)."),
        (2, f"Re-routed {redirected} new print request{'s' if redirected > 1 else ''} to {best['name']}."),
        (5, f"Forecast: {other['name']} queue clears around {sim.hhmm(min(minute + other['queue_min'] + 2, sim.CLOSE - 1))}."),
        (8, f"Checked {sum(s['queue_people'] for s in campus['shops'])} jobs across {len(campus['shops'])} shops."),
        (12, "Learned today's peaks: morning submissions, lunch hour and the late-afternoon deadline rush."),
    ]
    return {"best_shop": best["id"], "saved_min": saved, "pages": pages,
            "text": f"Fastest for {pages} pages including the walk: {best['name']} (about {saved} min quicker)." if saved
            else f"Both shops are equally quick for {pages} pages right now.",
            "events": [{"time": sim.hhmm(max(sim.OPEN, minute - ago)), "text": text} for ago, text in events]}


@route("GET", "/print")
def print_route(ctx):
    student = ctx.student()
    if not student:
        return _error(400, BAD_STUDENT)
    campus = live_campus(ctx.minute)
    load = lambda s: min(1.0, s["queue_people"] / s["capacity"])  # each shop's own load, not the campus average
    shops = [{**s, "rush": round(load(s), 3), "rush_label": sim.rush_label(load(s)),
              "walk_min": _walk(campus, "CLASS", s["loc"]), "location": campus["locations"][s["loc"]], "jobs": sim.print_jobs(s, ctx.minute),
              "people_forecast": sim.queue_forecast(s)} for s in campus["shops"]]
    mine = [orders.shape(o) for o in repo.list_orders(student) if o.get("kind") == "print"]
    return _resp(200, {"clock": ctx.clock, "shops": shops, "hours": list(range(sim.OPEN // 60, sim.CLOSE // 60)),
                       "agent": _print_agent(campus, ctx.minute), "mine": mine})


@route("POST", "/print/jobs")
def print_job(ctx):
    student, rid = ctx.student(), ctx.body.get("request_id")
    if not student:
        return _error(400, BAD_STUDENT)
    pages = _int(ctx.body.get("pages"), 1, 200)
    shop = next((s for s in live_campus(ctx.minute)["shops"] if s["id"] == ctx.body.get("shop_id")), None)
    if not isinstance(rid, str) or not ID32_RE.match(rid) or pages is None or not shop:
        return _error(400, "shop_id, pages (1-200) and a valid request_id are required.")
    color = ctx.body.get("color") is True
    eta = shop["queue_min"] + math.ceil(pages / shop["ppm"])
    order = {"created_at": int(time.time()), "simulated": True, "kind": "print", "eta_min": eta,
             "title": f"{pages} pages{' in colour' if color else ''} at {shop['name']}",
             "tokens": [orders.token("P", rid)], "total_cost": planner.print_cost(shop, pages, color)}
    try:
        repo.create_order(student, rid, order)
    except repo.DuplicateOrder:
        return _error(409, "This print job was already submitted.")
    return _resp(201, orders.shape({**order, "sk": rid}))


# --------------------------------------------------------------------------- canteen
@route("GET", "/canteen")
def canteen_route(ctx):
    campus = live_campus(ctx.minute)
    level = sim.rush("canteen", ctx.minute)
    return _resp(200, {"clock": ctx.clock, "rush": level, "rush_label": sim.rush_label(level),
                       "queue": round(level * 18), "menu": campus["menu"],
                       "categories": ["Meals", "Snacks", "Beverages", "Desserts"],
                       "forecast": sim.forecast("canteen"), "hours": list(range(sim.OPEN // 60, sim.CLOSE // 60))})


@route("POST", "/canteen/orders")
def canteen_order(ctx):
    student, rid, items = ctx.student(), ctx.body.get("request_id"), ctx.body.get("items")
    if not student:
        return _error(400, BAD_STUDENT)
    if not isinstance(rid, str) or not ID32_RE.match(rid) or not isinstance(items, list) or not 1 <= len(items) <= 15:
        return _error(400, "request_id and 1-15 items are required.")
    menu = {m["id"]: m for m in live_campus(ctx.minute)["menu"]}
    wanted = {}
    for it in items:
        qty = _int(it.get("qty"), 1, 10) if isinstance(it, dict) else None
        if qty is None or not isinstance(it.get("id"), str) or it["id"] not in menu:
            return _error(400, "Each item needs a valid id and a quantity from 1 to 10.")
        wanted[it["id"]] = wanted.get(it["id"], 0) + qty
    if sum(wanted.values()) > 20:
        return _error(400, "A single order can have at most 20 items.")
    for item_id in wanted:
        if not menu[item_id]["available"]:
            return _error(409, f"{menu[item_id]['name']} is not available right now.")
    lines = [{"id": i, "name": menu[i]["name"], "qty": q, "price": menu[i]["price"]} for i, q in wanted.items()]
    eta = max(menu[i]["prep_min"] for i in wanted) + math.ceil(sum(wanted.values()) / 4)
    order = {"created_at": int(time.time()), "simulated": True, "kind": "canteen", "eta_min": eta, "items": lines,
             "title": ", ".join(f"{l['qty']} × {l['name']}" for l in lines)[:120],
             "tokens": [orders.token("C", rid)], "total_cost": sum(l["qty"] * l["price"] for l in lines)}
    try:
        repo.create_order(student, rid, order)
    except repo.DuplicateOrder:
        return _error(409, "This order was already placed.")
    return _resp(201, orders.shape({**order, "sk": rid}))


# --------------------------------------------------------------------------- entry point
CORS_HEADERS = {"Access-Control-Allow-Origin": "*", "Access-Control-Allow-Methods": "GET,POST,OPTIONS",
                "Access-Control-Allow-Headers": "content-type", "Access-Control-Max-Age": "600"}


def handler(event, context):
    http = event["requestContext"]["http"]
    if http["method"] == "OPTIONS":  # browser preflight: answered here too, in case API Gateway forwards it
        return {"statusCode": 204, "headers": CORS_HEADERS, "body": ""}
    key = f"{http['method']} {event['rawPath']}"
    try:
        body = _body(event)
    except ValueError:  # includes bad JSON, bad base64 and non-object bodies
        return _error(400, "Body must be a valid JSON object.")
    fn = ROUTES.get(key)
    if not fn:
        return _error(404, "Not found")
    query = event.get("queryStringParameters") or {}
    at = query.get("at", body.get("at"))
    if at is not None and not (isinstance(at, str) and sim.AT_RE.match(at)):
        return _error(400, "at must be a time like 12:40.")
    try:
        date, minute = sim.resolve(at)
        return fn(Ctx(body, query, date, minute))
    except Exception as exc:
        print(f"Unhandled error on {key}: {exc!r}")
        return _error(500, "Something went wrong. Please try again.")
