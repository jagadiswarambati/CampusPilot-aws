"""Deterministic campus simulation: clock, rush levels, print queues, library occupancy.

Pure functions, no AWS calls. The same inputs always give the same numbers, so every page of the
app (planner, print shops, canteen, library) agrees with every other page at any given campus time.
Campus hours are 08:00-20:00; times outside that range are clamped to the nearest campus time.
"""
import hashlib
import math
import os
import re
from datetime import datetime, timedelta, timezone

IST = timezone(timedelta(hours=5, minutes=30))
OPEN, CLOSE = 8 * 60, 20 * 60
AT_RE = re.compile(r"^([01]\d|2[0-3]):[0-5]\d$")
SPEED = 10  # demo speed: one real second is ten simulated seconds (order progress, UI clock)

# (centre hour, width in hours, weight) of each rush peak during the day
PEAKS = {
    "print": [(9.25, 0.6, 0.6), (13.0, 0.7, 0.8), (16.5, 0.8, 0.7)],
    "canteen": [(10.75, 0.5, 0.5), (13.2, 0.7, 1.0), (16.5, 0.6, 0.55)],
    "library": [(11.0, 1.3, 0.5), (15.0, 1.6, 0.6), (18.5, 1.2, 0.7)],
}


def resolve(at=None):
    """Returns (today's IST date, campus minute-of-day). `at` is 'HH:MM'; default is the real IST time."""
    at = at or os.environ.get("CAMPUSPILOT_FIXED_TIME")
    now = datetime.now(IST)
    if at:
        hh, mm = at.split(":")
        minute = int(hh) * 60 + int(mm)
    else:
        minute = now.hour * 60 + now.minute
    return now.strftime("%Y-%m-%d"), max(OPEN, min(minute, CLOSE - 1))


def hhmm(minute):
    return f"{minute // 60:02d}:{minute % 60:02d}"


def parse_hhmm(text):
    hh, mm = text.split(":")
    return int(hh) * 60 + int(mm)


def unit(*parts):
    """Stable pseudo-random number in [0, 1) derived from the parts (well mixed: no visible patterns)."""
    digest = hashlib.sha256("|".join(map(str, parts)).encode()).digest()
    return int.from_bytes(digest[:4], "big") / 2 ** 32


def rush(kind, minute):
    hour = minute / 60
    level = 0.12 + sum(w * math.exp(-(((hour - c) / width) ** 2)) for c, width, w in PEAKS[kind])
    return round(max(0.0, min(1.0, level)), 3)


def rush_label(level):
    return "Quiet" if level < 0.35 else "Busy" if level < 0.65 else "Packed"


def forecast(kind):
    """Rush level for each campus hour (08..19), used for the day charts."""
    return [round(rush(kind, h * 60 + 30), 2) for h in range(OPEN // 60, CLOSE // 60)]


# ---- print shops ----
def queue_people(shop, minute):
    """Each shop's rush is shifted a little in time (shop['shift'] minutes), so the shops differ."""
    noise = int(unit(shop["id"], minute // 5) * 3) - 1
    return max(0, round(rush("print", minute + shop.get("shift", 0)) * shop["capacity"]) + noise)


def queue_forecast(shop):
    """Expected people waiting for each campus hour (08..19)."""
    return [round(rush("print", h * 60 + 30 + shop.get("shift", 0)) * shop["capacity"]) for h in range(OPEN // 60, CLOSE // 60)]


def queue_minutes(shop, minute):
    return math.ceil(queue_people(shop, minute) * shop["job_min"])


def print_jobs(shop, minute, limit=6):
    """A believable live queue for the shop: anonymous job numbers, pages and state."""
    people, bucket = queue_people(shop, minute), minute // 5
    jobs = []
    for i in range(min(people, limit)):
        seed = unit(shop["id"], bucket, i)
        jobs.append({"id": f"#{4000 + int(seed * 900)}", "pages": 1 + int(unit(shop["id"], bucket, i, "p") * 40),
                     "color": unit(shop["id"], bucket, i, "c") > 0.8,
                     "state": "Printing" if i == 0 else "Queued"})
    return jobs


# ---- canteen ----
def prep_extra(minute):
    return round(rush("canteen", minute) * 4)


# ---- library ----
def lib_taken(date, slot_index, seat_id, slot_mid_minute):
    """Whether a seat is occupied by 'other students' in the simulation (not a real booking)."""
    return unit(date, slot_index, seat_id) < 0.2 + 0.7 * rush("library", slot_mid_minute)
