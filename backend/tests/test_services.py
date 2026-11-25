"""API tests for the campus services (library, attendance, print, canteen, dashboard, orders)."""
import json
import uuid

import boto3
import pytest
from moto import mock_aws

import orders
import sim


@pytest.fixture()
def api():
    with mock_aws():
        boto3.client("dynamodb").create_table(
            TableName="campuspilot-test", BillingMode="PAY_PER_REQUEST",
            AttributeDefinitions=[{"AttributeName": "pk", "AttributeType": "S"},
                                  {"AttributeName": "sk", "AttributeType": "S"}],
            KeySchema=[{"AttributeName": "pk", "KeyType": "HASH"}, {"AttributeName": "sk", "KeyType": "RANGE"}])
        import repo
        repo._table, repo._client, repo._seeded, repo._campus_cache = None, None, False, None
        import app
        yield app


def call(app, method, path, body=None, query=None):
    event = {"requestContext": {"http": {"method": method}}, "rawPath": path,
             "queryStringParameters": query, "body": json.dumps(body) if body is not None else None}
    r = app.handler(event, None)
    return r["statusCode"], json.loads(r["body"])


def rid():
    return uuid.uuid4().hex


def free_seat(state):
    return next(s["id"] for z in state["zones"] for s in z["seats"] if s["status"] == "free")


# ---------------------------------------------------------------- simulation
def test_simulation_is_deterministic_and_peaks_at_lunch():
    assert sim.rush("canteen", 13 * 60 + 10) > sim.rush("canteen", 9 * 60) + 0.5
    assert sim.queue_people({"id": "lib", "capacity": 14}, 790) == sim.queue_people({"id": "lib", "capacity": 14}, 790)
    assert sim.resolve("23:30")[1] == sim.CLOSE - 1 and sim.resolve("03:00")[1] == sim.OPEN  # clamped to campus hours


def test_live_queue_changes_with_time_of_day(api):
    quiet = call(api, "GET", "/campus", query={"at": "08:00"})[1]
    rush = call(api, "GET", "/campus", query={"at": "13:00"})[1]
    lib = lambda c: next(s for s in c["shops"] if s["id"] == "lib")["queue_min"]
    assert lib(rush) > lib(quiet)


def test_invalid_time_is_rejected(api):
    assert call(api, "GET", "/campus", query={"at": "25:99"})[0] == 400
    assert call(api, "POST", "/plan", {"text": "30 minutes, 10 pages", "at": "noon"})[0] == 400


def test_plan_returns_an_agent_trace_derived_from_real_numbers(api):
    _, res = call(api, "POST", "/plan", {"text": "40 minutes, vegetarian lunch and 25 pages printed"})
    labels = [t["label"] for t in res["trace"]]
    assert "Checked print shop queues" in labels and "Simulated every combination" in labels
    assert res["considered"] > 0 and str(res["considered"]) in res["trace"][-2]["detail"]


# ---------------------------------------------------------------- library
def test_library_state_shape(api):
    code, st = call(api, "GET", "/library", query={"student_id": "stu-aaa"})
    assert code == 200 and st["total"] == 142 and len(st["slots"]) == 6
    assert st["chosen"] == 1  # 10:00 -> the 10:00-12:00 slot (the 08:00-10:00 slot has ended)
    assert st["slots"][0]["ended"] and st["slots"][1]["current"]
    assert {z["id"] for z in st["zones"]} == {"hall", "silent", "group", "lab"}
    assert call(api, "GET", "/library", query={"student_id": "stu-aaa", "slot": "9"})[0] == 400
    assert call(api, "GET", "/library")[0] == 400


def test_book_cancel_and_one_seat_per_slot(api):
    q = {"student_id": "stu-aaa"}
    seat = free_seat(call(api, "GET", "/library", query=q)[1])
    assert call(api, "POST", "/library/book", {"student_id": "stu-aaa", "slot": 1, "seat": seat})[0] == 201
    mine = call(api, "GET", "/library", query=q)[1]["mine"]
    assert mine == [{"slot": 1, "label": "10:00–12:00", "seat": seat}]
    other = next(s["id"] for z in call(api, "GET", "/library", query=q)[1]["zones"] for s in z["seats"] if s["status"] == "free")
    code, err = call(api, "POST", "/library/book", {"student_id": "stu-aaa", "slot": 1, "seat": other})
    assert code == 409 and "already have a seat" in err["error"]
    assert call(api, "POST", "/library/cancel", {"student_id": "stu-aaa", "slot": 1})[0] == 200
    assert call(api, "POST", "/library/cancel", {"student_id": "stu-aaa", "slot": 1})[0] == 404
    assert call(api, "POST", "/library/book", {"student_id": "stu-aaa", "slot": 1, "seat": other})[0] == 201


def test_two_students_cannot_book_the_same_seat(api):
    seat = free_seat(call(api, "GET", "/library", query={"student_id": "stu-aaa", "slot": "2"})[1])
    assert call(api, "POST", "/library/book", {"student_id": "stu-aaa", "slot": 2, "seat": seat})[0] == 201
    code, err = call(api, "POST", "/library/book", {"student_id": "stu-bbb", "slot": 2, "seat": seat})
    assert code == 409 and "taken" in err["error"]
    seen = call(api, "GET", "/library", query={"student_id": "stu-bbb", "slot": "2"})[1]
    status = next(s["status"] for z in seen["zones"] for s in z["seats"] if s["id"] == seat)
    assert status == "taken"  # another student's seat shows as taken, never as 'mine'


def test_library_rejects_bad_input_and_past_slots(api):
    base = {"student_id": "stu-aaa"}
    assert call(api, "POST", "/library/book", {**base, "slot": 0, "seat": "hall-A1"})[0] == 422  # slot already ended
    assert call(api, "POST", "/library/book", {**base, "slot": 1, "seat": "nope"})[0] == 400
    assert call(api, "POST", "/library/book", {**base, "slot": 9, "seat": "hall-A1"})[0] == 400
    assert call(api, "POST", "/library/book", {**base, "slot": "1", "seat": "hall-A1"})[0] == 400
    assert call(api, "POST", "/library/book", {"slot": 1, "seat": "hall-A1"})[0] == 400


def test_simulated_occupied_seat_cannot_be_booked(api):
    st = call(api, "GET", "/library", query={"student_id": "stu-aaa"})[1]
    taken = next(s["id"] for z in st["zones"] for s in z["seats"] if s["status"] == "taken")
    assert call(api, "POST", "/library/book", {"student_id": "stu-aaa", "slot": st["chosen"], "seat": taken})[0] == 409


# ---------------------------------------------------------------- attendance
def test_attendance_numbers_and_skip_calculator(api):
    code, a = call(api, "GET", "/attendance", query={"student_id": "stu-aaa", "at": "08:00"})
    assert code == 200 and a["target"] == 75 and all(p["status"] in ("upcoming", "checkin") for p in a["today"])
    cn = next(s for s in a["subjects"] if s["code"] == "CS303")
    assert cn["pct"] == 70.6 and cn["state"] == "low"
    # brute-force the two promises the UI makes to students, for every subject
    for s in a["subjects"]:
        h, at = s["held"], s["attended"]
        assert s["pct"] == round(100 * at / h, 1) and s["pct_if_skip"] == round(100 * at / (h + 1), 1)
        k = s["can_miss"]   # may miss k more classes and still be at 75% or above, but not k+1
        if at / h >= 0.75:
            assert at / (h + k) >= 0.75 and at / (h + k + 1) < 0.75
        else:
            assert k == 0   # already below target: nothing can be skipped
        n = s["need"]       # must attend n in a row to reach 75%, and n-1 is not enough
        assert (at + n) / (h + n) >= 0.75 and (n == 0 or (at + n - 1) / (h + n - 1) < 0.75)
    assert (cn["need"], cn["can_miss"]) == (6, 0)


def test_check_in_window_duplicates_and_percentage_update(api):
    q = {"student_id": "stu-aaa", "at": "08:55"}
    before = next(s for s in call(api, "GET", "/attendance", query=q)[1]["subjects"] if s["code"] == "CS301")
    assert call(api, "POST", "/attendance/checkin", {"student_id": "stu-aaa", "period_id": "p2", "at": "08:55"})[0] == 422  # not open yet
    assert call(api, "POST", "/attendance/checkin", {"student_id": "stu-aaa", "period_id": "p1", "at": "08:55"})[0] == 201
    assert call(api, "POST", "/attendance/checkin", {"student_id": "stu-aaa", "period_id": "p1", "at": "08:55"})[0] == 409
    after = next(s for s in call(api, "GET", "/attendance", query=q)[1]["subjects"] if s["code"] == "CS301")
    assert (after["held"], after["attended"]) == (before["held"] + 1, before["attended"] + 1)
    assert call(api, "POST", "/attendance/checkin", {"student_id": "stu-aaa", "period_id": "zzz"})[0] == 400


def test_ended_classes_are_counted_and_cannot_be_checked_in(api):
    outcomes = set()
    for sid in ("stu-aaa", "stu-bbb", "stu-ccc", "stu-ddd", "stu-eee", "stu-fff"):
        a = call(api, "GET", "/attendance", query={"student_id": sid, "at": "13:00"})[1]
        ended = [p for p in a["today"] if p["status"] == "ended"]
        assert len(ended) == 4 and all(p["result"] in ("attended", "missed") for p in ended)
        outcomes.update(p["result"] for p in ended)
        dbms = next(s for s in a["subjects"] if s["code"] == "CS301")
        assert dbms["held"] == 39 and dbms["attended"] == 33 + (ended[0]["result"] == "attended")
        again = call(api, "GET", "/attendance", query={"student_id": sid, "at": "13:00"})[1]
        assert [p["result"] for p in again["today"]] == [p["result"] for p in a["today"]]   # deterministic
        assert call(api, "POST", "/attendance/checkin", {"student_id": sid, "period_id": "p1", "at": "13:00"})[0] == 422
    assert outcomes == {"attended", "missed"}   # the sample history is mostly attended but not perfect


def test_print_shops_have_different_daily_patterns(api):
    p = call(api, "GET", "/print", query={"student_id": "stu-aaa", "at": "13:00"})[1]
    a, b = (s["people_forecast"] for s in p["shops"])
    assert a != b and [round(x / 14, 1) for x in a] != [round(x / 9, 1) for x in b]


# ---------------------------------------------------------------- print shops
def test_print_page_data_and_agent(api):
    code, p = call(api, "GET", "/print", query={"student_id": "stu-aaa", "at": "13:00"})
    assert code == 200 and len(p["shops"]) == 2 and len(p["agent"]["events"]) == 5
    assert all(len(s["people_forecast"]) == 12 for s in p["shops"]) and p["agent"]["best_shop"] in ("lib", "eng")
    assert all(j["state"] in ("Printing", "Queued") for s in p["shops"] for j in s["jobs"])


def test_print_job_flow(api):
    body = {"student_id": "stu-aaa", "shop_id": "eng", "pages": 30, "color": True, "request_id": rid()}
    code, job = call(api, "POST", "/print/jobs", body)
    assert code == 201 and job["tokens"][0].startswith("P-") and job["total_cost"] == 300 and job["kind"] == "print"
    assert call(api, "POST", "/print/jobs", body)[0] == 409
    for bad in ({"pages": 0}, {"pages": 201}, {"pages": "9"}, {"shop_id": "nope"}, {"request_id": "x"}):
        assert call(api, "POST", "/print/jobs", {**body, "request_id": rid(), **bad})[0] == 400
    assert len(call(api, "GET", "/print", query={"student_id": "stu-aaa"})[1]["mine"]) == 1


# ---------------------------------------------------------------- canteen
def test_canteen_menu_and_order(api):
    code, c = call(api, "GET", "/canteen", query={"at": "13:00"})
    assert code == 200 and len(c["menu"]) == 15 and c["rush_label"] == "Packed" and "Desserts" in c["categories"]
    body = {"student_id": "stu-aaa", "request_id": rid(), "items": [{"id": "chai", "qty": 2}, {"id": "samosa", "qty": 1}, {"id": "chai", "qty": 1}]}
    code, o = call(api, "POST", "/canteen/orders", body)
    assert code == 201 and o["tokens"][0].startswith("C-") and o["total_cost"] == 3 * 15 + 30
    assert {i["id"]: i["qty"] for i in o["items"]} == {"chai": 3, "samosa": 1}  # duplicate lines merged
    assert call(api, "POST", "/canteen/orders", body)[0] == 409


def test_canteen_rejects_unavailable_and_invalid_orders(api):
    base = {"student_id": "stu-aaa"}
    assert call(api, "POST", "/canteen/orders", {**base, "request_id": rid(), "items": [{"id": "biryani", "qty": 1}]})[0] == 409
    for items in ([], [{"id": "chai", "qty": 0}], [{"id": "chai", "qty": 11}], [{"id": "ghost", "qty": 1}], ["chai"],
                  [{"id": "chai", "qty": 10}, {"id": "samosa", "qty": 10}, {"id": "fries", "qty": 1}]):
        assert call(api, "POST", "/canteen/orders", {**base, "request_id": rid(), "items": items})[0] == 400


# ---------------------------------------------------------------- orders and dashboard
def test_order_status_progresses_over_time():
    o = {"kind": "canteen", "created_at": 1000, "eta_min": 10, "title": "x", "tokens": ["C-1"]}
    assert orders.shape(o, now=1001)["status"] == "Received"
    assert orders.shape(o, now=1030)["status"] == "Preparing"
    done = orders.shape(o, now=1000 + 61)
    assert done["status"] == "Ready for pickup" and done["eta_left_min"] == 0 and done["progress"] == 1.0
    assert orders.shape({**o, "kind": "print"}, now=1030)["status"] == "Printing"


def test_unified_orders_list_and_dashboard(api):
    me = {"student_id": "stu-aaa"}
    call(api, "POST", "/canteen/orders", {**me, "request_id": rid(), "items": [{"id": "chai", "qty": 1}]})
    call(api, "POST", "/print/jobs", {**me, "shop_id": "lib", "pages": 5, "request_id": rid()})
    _, plan = call(api, "POST", "/plan", {"text": "40 minutes, 10 pages printed"})
    call(api, "POST", "/orders", {**me, "plan_id": plan["best"]["id"]})
    rows = call(api, "GET", "/orders", query=me)[1]["orders"]
    assert {r["kind"] for r in rows} == {"canteen", "print", "plan"} and all(r["tokens"] for r in rows)
    code, d = call(api, "GET", "/dashboard", query=me)
    assert code == 200 and d["orders"]["total"] == 3 and d["orders"]["active"] == 3
    assert d["attendance"]["overall"] > 0 and len(d["pulse"]["print"]) == 12 and d["library"]["slot"]["free"] > 0
    assert call(api, "GET", "/dashboard")[0] == 400


def test_campus_data_is_cached_briefly_and_callers_cannot_corrupt_the_cache(api, monkeypatch):
    import repo
    first = repo.campus()
    reads = []
    original = repo._items
    monkeypatch.setattr(repo, "_items", lambda pk: (reads.append(pk), original(pk))[1])
    second = repo.campus()
    assert reads == []                          # served from the cache, no DynamoDB read
    second["shops"][0]["queue_min"] = 999       # live-queue adjustment must not leak into the cache
    assert repo.campus()["shops"][0]["queue_min"] == first["shops"][0]["queue_min"]


def test_dashboard_board_and_insights_use_real_data(api):
    me = {"student_id": "stu-aaa"}
    d = call(api, "GET", "/dashboard", query={**me, "at": "11:20"})[1]
    assert [b["title"] for b in d["board"] if b["kind"] == "attendance"][:2] == ["Computer Networks", "Environmental Science"]
    assert d["board"][0]["status"] == "In session" and d["board"] == sorted(d["board"], key=lambda b: b["time"])
    kinds = {i["kind"] for i in d["insights"]}
    assert kinds == {"attendance", "print", "library", "canteen"}
    assert "Computer Networks" in d["insights"][0]["title"] and "6 classes" in d["insights"][0]["text"]
    seat = free_seat(call(api, "GET", "/library", query={**me, "at": "11:20"})[1])
    call(api, "POST", "/library/book", {**me, "slot": 1, "seat": seat, "at": "11:20"})
    call(api, "POST", "/canteen/orders", {**me, "request_id": rid(), "items": [{"id": "chai", "qty": 1}], "at": "11:20"})
    board = call(api, "GET", "/dashboard", query={**me, "at": "11:20"})[1]["board"]
    kinds = [b["kind"] for b in board]
    assert "library" in kinds and "canteen" in kinds
    assert next(b for b in board if b["kind"] == "library")["status"] == "Now"


def test_simulated_seats_have_no_visible_stripes(api):
    st = call(api, "GET", "/library", query={"student_id": "stu-aaa", "at": "13:00"})[1]
    hall = next(z for z in st["zones"] if z["id"] == "hall")
    per_col = [sum(1 for s in hall["seats"] if s["id"].split("-")[1][1:] == str(c) and s["status"] == "taken") for c in range(1, 11)]
    assert max(per_col) < len(hall["rows"]) and min(per_col) > 0 or max(per_col) - min(per_col) < len(hall["rows"])  # not whole columns
    assert len({tuple(s["status"] for s in hall["seats"] if s["id"].split("-")[1][0] == r) for r in hall["rows"]}) > 3  # rows differ


def test_each_print_shop_reports_its_own_rush(api):
    shops = call(api, "GET", "/print", query={"student_id": "stu-aaa", "at": "13:00"})[1]["shops"]
    for s in shops:
        assert s["rush"] == round(min(1.0, s["queue_people"] / s["capacity"]), 3)
    assert len({s["rush_label"] for s in shops}) >= 1 and shops[0]["queue_people"] != shops[1]["queue_people"]
