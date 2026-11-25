import data
import intent
import planner

CAMPUS = {"shops": data.SHOPS, "menu": data.MENU, "walks": data.WALK, "locations": data.LOCATIONS}


def req(**kw):
    base = {"minutes": 35, "pages": 25, "color": False, "food": True, "veg": True, "budget": None, "buffer": 5}
    return {**base, **kw}


def test_feasible_lunch_and_print_fits_35_minutes():
    r = planner.plan(req(), CAMPUS)
    assert r["feasible"] and r["best"]["slack_min"] >= 0
    assert r["best"]["total_min"] + 5 <= 35


def test_infeasible_request_is_reported_honestly_with_alternative():
    r = planner.plan(req(minutes=18, pages=50, color=True, veg=False), CAMPUS)
    assert not r["feasible"] and "short by" in r["reason"]
    assert any(a["label"] == "Print only" and a["feasible"] for a in r["alternatives"])


def test_veg_filter_and_unavailable_items_are_never_chosen():
    r = planner.plan(req(minutes=120), CAMPUS)
    chosen = {p["item"]["id"] for p in [r["best"], *r["alternatives"]]}
    assert not chosen & {"roll", "biryani"}


def test_budget_is_enforced():
    r = planner.plan(req(budget=40), CAMPUS)
    assert not r["feasible"] and "budget" in r["reason"]


def test_print_only_plan_has_no_food():
    r = planner.plan(req(food=False, veg=False, pages=40, minutes=20), CAMPUS)
    assert r["feasible"] and r["best"]["item"] is None and r["best"]["cost"]["food"] == 0


def test_timeline_is_contiguous():
    steps = planner.plan(req(), CAMPUS)["best"]["steps"]
    assert steps[0]["start"] == 0
    assert all(a["end"] == b["start"] for a, b in zip(steps, steps[1:]))


def test_rule_parser_extracts_fields():
    p = intent.parse_rules("I have 35 minutes before class. Need a vegetarian lunch and 25 pages printed under ₹250")
    assert (p["minutes"], p["pages"], p["veg"], p["food"], p["budget"]) == (35, 25, True, True, 250.0)


def test_rule_parser_handles_non_veg_and_color():
    p = intent.parse_rules("only 18 minutes, 50 pages in color and non-veg lunch")
    assert p["color"] and p["food"] and not p["veg"] and p["pages"] == 50


def test_hours_are_not_mistaken_for_a_budget():
    p = intent.parse_rules("I have 2 hours 30 minutes, need 10 pages printed")
    assert p["minutes"] == 150 and p["budget"] is None


def test_word_boundaries_do_not_trigger_food():
    assert intent.parse_rules("great, 30 minutes, 10 pages")["food"] is False


def test_hour_phrases_and_missing_time():
    assert intent.parse_rules("I have an hour, lunch please")["minutes"] == 60
    assert intent.parse_rules("half an hour and 5 pages")["minutes"] == 30
    assert intent.parse_rules("print 20 pages")["minutes"] is None


def test_model_output_is_sanitised():
    c = intent._clean({"minutes": "30", "pages": "9999", "food": "false", "veg": "true", "budget": "abc"})
    assert (c["minutes"], c["pages"], c["food"], c["veg"], c["budget"]) == (30, 500, False, True, None)


def test_lunch_means_a_proper_meal_but_a_snack_request_can_be_a_snack():
    assert intent.parse_rules("40 minutes, vegetarian lunch")["meal"] and not intent.parse_rules("40 minutes, a quick snack")["meal"]
    lunch = planner.plan(req(minutes=120, meal=True), CAMPUS)
    assert all(p["item"]["id"] in ("thali", "chole") for p in [lunch["best"], *lunch["alternatives"]])
    snack = planner.plan(req(minutes=120, meal=False), CAMPUS)
    assert snack["best"]["item"]["id"] in ("samosa", "sandwich", "fries", "wrap", "chole", "thali")
