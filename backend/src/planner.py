"""Deterministic scheduling engine. Pure Python, no AWS calls, fully unit-tested.

The AI layer only *understands the request*; every minute and rupee in a plan
is computed here, so a plan can never be hallucinated.
"""
import math

from data import PLANNER_CATEGORIES

HOME = "CLASS"
CANTEEN = "SAC"


def _walk(walks, a, b):
    if a == b:
        return 0
    return walks.get(f"{a}#{b}", walks.get(f"{b}#{a}", 4))


def print_minutes(shop, pages):
    return shop["queue_min"] + math.ceil(pages / shop["ppm"])


def print_cost(shop, pages, color):
    return round(pages * (shop["price_color"] if color else shop["price_bw"]), 2)


class _Clock:
    """Builds a timeline step by step, tracking time and current location."""

    def __init__(self, walks, locs):
        self.t, self.loc, self.steps, self.walks, self.locs = 0, HOME, [], walks, locs

    def add(self, label, minutes, kind):
        self.steps.append({"kind": kind, "label": label, "where": self.locs[self.loc],
                           "start": self.t, "end": self.t + minutes})
        self.t += minutes

    def go(self, dest):
        if dest != self.loc:
            minutes = _walk(self.walks, self.loc, dest)
            self.loc = dest
            self.add(f"Walk to {self.locs[dest]}", minutes, "walk")


def _run(order, walks, locs, shop, item, pages):
    c, ready = _Clock(walks, locs), None
    for task in order:
        if task == "food":
            c.go(CANTEEN)
            c.add(f"Order {item['name']}", 0, "order")
            ready = c.t + item["prep_min"]
        else:
            c.go(shop["loc"])
            c.add(f"Print {pages} pages at {shop['name']}", print_minutes(shop, pages), "print")
    if ready is not None:
        c.go(CANTEEN)
        if ready > c.t:
            c.add("Wait for food", ready - c.t, "wait")
        c.add("Pick up food", 0, "pickup")
    c.go(HOME)
    return c


SEQUENCE_LABELS = {
    ("food", "print"): "Order food first, print while it cooks",
    ("print", "food"): "Print first, then order food",
    ("food",): "Food only",
    ("print",): "Print only",
}


def _candidates(req, data):
    shops = data["shops"] if req["pages"] > 0 else [None]
    categories = ("Meals",) if req.get("meal") else PLANNER_CATEGORIES  # "lunch" means a proper meal, not a samosa
    items = [m for m in data["menu"] if m["available"] and (m["veg"] or not req["veg"])
             and m.get("category", "Meals") in categories] if req["food"] else [None]
    if not shops or not items:
        return []
    tasks = [t for t, on in (("food", req["food"]), ("print", req["pages"] > 0)) if on]
    orders = [tuple(tasks), tuple(reversed(tasks))] if len(tasks) == 2 else [tuple(tasks)]
    out = []
    for shop in shops:
        for item in items:
            for order in orders:
                c = _run(order, data["walks"], data["locations"], shop, item, req["pages"])
                cost_p = print_cost(shop, req["pages"], req["color"]) if shop else 0
                cost_f = item["price"] if item else 0
                cost = round(cost_p + cost_f, 2)
                slack = req["minutes"] - c.t - req["buffer"]
                in_budget = req["budget"] is None or cost <= req["budget"]
                out.append({
                    "label": SEQUENCE_LABELS[order],
                    "shop": {"id": shop["id"], "name": shop["name"]} if shop else None,
                    "item": {"id": item["id"], "name": item["name"], "price": item["price"]} if item else None,
                    "steps": c.steps, "total_min": c.t, "buffer_min": req["buffer"], "slack_min": slack,
                    "cost": {"print": cost_p, "food": cost_f, "total": cost},
                    "within_budget": in_budget, "feasible": slack >= 0 and in_budget,
                })
    return out


def _rank(plans):
    """Best plan per (shop, item) pair, feasible first, then fastest, then cheapest."""
    plans = sorted(plans, key=lambda p: (not p["feasible"], p["total_min"], p["cost"]["total"]))
    seen, unique = set(), []
    for p in plans:
        key = (p["shop"] and p["shop"]["id"], p["item"] and p["item"]["id"])
        if key not in seen:
            seen.add(key)
            unique.append(p)
    return unique


def _reason(p, req):
    parts = []
    if p["slack_min"] < 0:
        parts.append(f"The fastest plan needs {p['total_min']} min plus a {p['buffer_min']} min safety buffer, "
                     f"but you have {req['minutes']} min (short by {-p['slack_min']} min).")
    if not p["within_budget"]:
        parts.append(f"The cheapest option costs ₹{p['cost']['total']:g}, above your ₹{req['budget']:g} budget.")
    return " ".join(parts)


def plan(req, data):
    """req: minutes, pages, color, food, veg, budget, buffer.  Returns best plan + alternatives."""
    candidates = _candidates(req, data)
    ranked = _rank(candidates)
    if not ranked:
        return {"feasible": False, "reason": "No available menu item or print shop matches this request.",
                "best": None, "alternatives": [], "considered": 0}
    best = ranked[0]
    if best["feasible"]:
        return {"feasible": True, "reason": None, "best": best, "considered": len(candidates),
                "alternatives": [p for p in ranked[1:] if p["feasible"]][:2]}
    alternatives = []
    if req["food"] and req["pages"] > 0:  # offer to drop one of the two tasks
        for drop in ({**req, "food": False}, {**req, "pages": 0}):
            sub = _rank(_candidates(drop, data))
            if sub and sub[0]["feasible"]:
                alternatives.append(sub[0])
    return {"feasible": False, "reason": _reason(best, req), "best": best, "alternatives": alternatives,
            "considered": len(candidates)}
