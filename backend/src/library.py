"""Library seat map and booking (BookMyShow-style): simulated 'other students' + real bookings."""
import data
import repo
import sim

SEATS = {z["id"]: [f"{z['id']}-{r}{c}" for r in z["rows"] for c in range(1, z["cols"] + 1)] for z in data.ZONES}
VALID_SEATS = {s for ids in SEATS.values() for s in ids}
TOTAL = len(VALID_SEATS)


def slot_mid(i):
    start, end = data.SLOTS[i]
    return (start + end) * 30  # midpoint in minutes of day


def slot_label(i):
    start, end = data.SLOTS[i]
    return f"{start:02d}:00–{end:02d}:00"


def default_slot(minute):
    for i, (_, end) in enumerate(data.SLOTS):
        if end * 60 > minute:
            return i
    return len(data.SLOTS) - 1


def _bookings(date):
    by_slot = {}
    for item in repo.seat_bookings(date):
        slot, seat = item["sk"].split("#", 1)
        by_slot.setdefault(int(slot), {})[seat] = item["owner"]
    return by_slot


def is_taken(date, slot, seat, real):
    return seat in real or sim.lib_taken(date, slot, seat, slot_mid(slot))


def state(student, date, minute, slot=None):
    by_slot = _bookings(date)
    slots = []
    for i, (start, end) in enumerate(data.SLOTS):
        taken = sum(1 for s in VALID_SEATS if is_taken(date, i, s, by_slot.get(i, {})))
        slots.append({"index": i, "label": slot_label(i), "free": TOTAL - taken, "total": TOTAL,
                      "ended": end * 60 <= minute, "current": start * 60 <= minute < end * 60,
                      "rush": sim.rush_label(sim.rush("library", slot_mid(i)))})
    chosen = default_slot(minute) if slot is None else slot
    real = by_slot.get(chosen, {})
    zones = []
    for z in data.ZONES:
        seats = []
        for sid in SEATS[z["id"]]:
            status = "mine" if real.get(sid) == student else "taken" if is_taken(date, chosen, sid, real) else "free"
            seats.append({"id": sid, "status": status})
        zones.append({"id": z["id"], "name": z["name"], "rows": list(z["rows"]), "cols": z["cols"], "aisle": z["aisle"],
                      "seats": seats, "free": sum(1 for s in seats if s["status"] == "free")})
    mine = [{"slot": i, "label": slot_label(i), "seat": seat}
            for i, owners in sorted(by_slot.items()) for seat, owner in owners.items() if owner == student]
    return {"slots": slots, "chosen": chosen, "zones": zones, "mine": mine, "total": TOTAL}


def seat_name(seat_id):
    """'hall-B7' -> 'Reading Hall B7'."""
    zone = next(z for z in data.ZONES if z["id"] == seat_id.split("-")[0])
    return f"{zone['name']} {seat_id.split('-')[1]}"
