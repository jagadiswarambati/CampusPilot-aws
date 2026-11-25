"""Order presentation: one list for planner, print and canteen orders, with simulated live status.

Progress is derived from the order's creation time and ETA, so no background job is needed:
at demo speed (sim.SPEED) a 12-minute order is ready after roughly 72 real seconds.
"""
import math
import time

import sim

STAGES = {
    "print": ("Queued", "Printing", "Ready to collect"),
    "canteen": ("Received", "Preparing", "Ready for pickup"),
    "plan": ("Planned", "In progress", "Completed"),
}


def shape(o, now=None):
    now = time.time() if now is None else now
    eta = max(1, int(o.get("eta_min") or 1))
    kind = o.get("kind") or "plan"
    progress = max(0.0, min(1.0, (now - o["created_at"]) / max(30.0, eta * 60 / sim.SPEED)))
    stage = 0 if progress < 0.2 else 1 if progress < 1 else 2
    return {
        "kind": kind, "title": o.get("title") or o.get("summary") or "Order",
        "tokens": o.get("tokens") or [t for t in (o.get("print_order_id"), o.get("food_order_id")) if t],
        "items": o.get("items") or [], "total_cost": o.get("total_cost", 0), "eta_min": eta,
        "created_at": o["created_at"], "simulated": True, "id": o.get("sk"),
        "status": STAGES.get(kind, STAGES["plan"])[stage], "stage": stage, "progress": round(progress, 3),
        "eta_left_min": math.ceil(eta * (1 - progress)) if progress < 1 else 0,
        "print_order_id": o.get("print_order_id"), "food_order_id": o.get("food_order_id"),
        "plan_label": o.get("plan_label"), "summary": o.get("summary"),
    }


def token(prefix, seed):
    return f"{prefix}-{1000 + int(sim.unit(seed) * 9000)}"
