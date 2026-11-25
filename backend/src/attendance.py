"""Class attendance: today's timetable, check-in window, per-subject percentages and a skip calculator."""
import math

import data
import repo
import sim

CHECKIN_OPENS_BEFORE = 10  # minutes before the class starts


def _status(period, minute):
    start, end = sim.parse_hhmm(period["start"]), sim.parse_hhmm(period["end"])
    if minute >= end:
        return "ended"
    if minute >= start:
        return "ongoing"
    return "checkin" if minute >= start - CHECKIN_OPENS_BEFORE else "upcoming"


def period(period_id):
    return next((p for p in data.PERIODS if p["id"] == period_id), None)


def status_of(p, minute):
    return _status(p, minute)


def summary(student, date, minute):
    marked = {m["sk"].split("#", 1)[1] for m in repo.attendance_marks(student, date)}
    today = []
    counted, attended = {}, {}
    for p in data.PERIODS:
        status = _status(p, minute)
        done = p["id"] in marked
        # Simulated history: a class that ended without a check-in was attended most of the time (sample data).
        result = "attended" if done else (("attended" if sim.unit("attend", student, p["id"]) < 0.88 else "missed") if status == "ended" else None)
        today.append({**p, "subject": data.SUBJECTS[p["code"]]["name"], "status": status, "marked": done, "result": result,
                      "can_check_in": status in ("checkin", "ongoing") and not done})
        if result:
            counted[p["code"]] = counted.get(p["code"], 0) + 1
        if result == "attended":
            attended[p["code"]] = attended.get(p["code"], 0) + 1
    subjects = []
    for code, s in data.SUBJECTS.items():
        held = s["held"] + counted.get(code, 0)
        att = s["attended"] + attended.get(code, 0)
        pct = round(100 * att / held, 1)
        target = data.ATTENDANCE_TARGET / 100
        subjects.append({
            "code": code, "name": s["name"], "held": held, "attended": att, "pct": pct,
            "state": "good" if pct >= data.ATTENDANCE_TARGET else "low" if pct >= data.ATTENDANCE_TARGET - 10 else "short",
            "can_miss": max(0, math.floor(att / target - held + 1e-9)),
            "need": max(0, math.ceil((target * held - att) / (1 - target) - 1e-9)),
            "pct_if_skip": round(100 * att / (held + 1), 1),
        })
    held_all, att_all = sum(s["held"] for s in subjects), sum(s["attended"] for s in subjects)
    return {"target": data.ATTENDANCE_TARGET, "today": today, "subjects": subjects,
            "overall": round(100 * att_all / held_all, 1)}
