"""End-to-end handler test against a mocked DynamoDB (moto)."""
import json

import boto3
import pytest
from moto import mock_aws


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
             "queryStringParameters": query, "body": json.dumps(body) if body else None}
    r = app.handler(event, None)
    return r["statusCode"], json.loads(r["body"])


def test_plan_confirm_duplicate_and_list(api):
    code, res = call(api, "POST", "/plan", {"text": "35 minutes, vegetarian lunch and 25 pages printed"})
    assert code == 200 and res["feasible"]
    plan_id = res["best"]["id"]

    code, order = call(api, "POST", "/orders", {"plan_id": plan_id, "student_id": "stu-test1"})
    assert code == 201 and order["simulated"] and order["print_order_id"].startswith("PO-")

    code, _ = call(api, "POST", "/orders", {"plan_id": plan_id, "student_id": "stu-test1"})
    assert code == 409  # duplicate protection

    code, listed = call(api, "GET", "/orders", query={"student_id": "stu-test1"})
    assert code == 200 and len(listed["orders"]) == 1


def test_infeasible_plan_cannot_be_ordered(api):
    _, res = call(api, "POST", "/plan", {"text": "only 5 minutes, 50 pages in color and lunch"})
    assert not res["feasible"]
    code, _ = call(api, "POST", "/orders", {"plan_id": res["best"]["id"], "student_id": "stu-test1"})
    assert code == 422


def test_validation_and_unknown_route(api):
    assert call(api, "POST", "/plan", {"text": "hello there"})[0] == 400
    assert call(api, "GET", "/nope")[0] == 404
    assert call(api, "GET", "/health")[1] == {"status": "ok"}


def test_orders_require_a_valid_student_id_and_plan_id(api):
    _, res = call(api, "POST", "/plan", {"text": "35 minutes, 10 pages printed"})
    pid = res["best"]["id"]
    assert call(api, "POST", "/orders", {"plan_id": pid})[0] == 400            # no student_id
    assert call(api, "POST", "/orders", {"plan_id": pid, "student_id": "x"})[0] == 400
    assert call(api, "POST", "/orders", {"student_id": "stu-test1"})[0] == 400  # no plan_id
    assert call(api, "POST", "/orders", {"plan_id": ["a"], "student_id": "stu-test1"})[0] == 400
    assert call(api, "POST", "/orders", {"plan_id": "0" * 32, "student_id": "stu-test1"})[0] == 404
    assert call(api, "GET", "/orders")[0] == 400                                # no default student


def test_malformed_bodies_return_400_not_500(api):
    for bad in ("[]", '"x"', "not json"):
        event = {"requestContext": {"http": {"method": "POST"}}, "rawPath": "/plan", "body": bad}
        assert api.handler(event, None)["statusCode"] == 400
    assert call(api, "POST", "/plan", {"text": 123})[0] == 400


def test_missing_time_is_asked_not_assumed(api):
    code, res = call(api, "POST", "/plan", {"text": "I need 25 pages printed"})
    assert code == 400 and "how long" in res["error"]


def test_expired_plan_cannot_be_ordered_even_before_ttl_cleanup(api):
    import repo
    _, res = call(api, "POST", "/plan", {"text": "35 minutes, 10 pages printed"})
    pid = res["best"]["id"]
    repo.table().update_item(Key={"pk": "PLAN", "sk": pid}, UpdateExpression="SET #t = :past",
                             ExpressionAttributeNames={"#t": "ttl"}, ExpressionAttributeValues={":past": 1})
    assert call(api, "POST", "/orders", {"plan_id": pid, "student_id": "stu-test1"})[0] == 404


def test_order_is_rejected_if_menu_item_became_unavailable(api):
    import repo
    _, res = call(api, "POST", "/plan", {"text": "35 minutes, vegetarian lunch"})
    item_id = res["best"]["item"]["id"]
    repo.table().update_item(Key={"pk": "MENU", "sk": item_id}, UpdateExpression="SET available = :f",
                             ExpressionAttributeValues={":f": False})
    code, body = call(api, "POST", "/orders", {"plan_id": res["best"]["id"], "student_id": "stu-test1"})
    assert code == 409 and "no longer available" in body["error"]


def test_editing_seed_data_reseeds_and_removes_stale_items(api, monkeypatch):
    import data
    import repo
    call(api, "GET", "/campus")
    monkeypatch.setattr(data, "MENU", [m for m in data.MENU if m["id"] != "wrap"])
    repo._seeded = False
    menu_ids = {m["id"] for m in call(api, "GET", "/campus")[1]["menu"]}
    assert "wrap" not in menu_ids and "thali" in menu_ids


def test_cors_preflight_is_answered(api):
    event = {"requestContext": {"http": {"method": "OPTIONS"}}, "rawPath": "/plan", "body": None}
    r = api.handler(event, None)
    assert r["statusCode"] == 204 and r["headers"]["Access-Control-Allow-Origin"] == "*"
    assert "content-type" in r["headers"]["Access-Control-Allow-Headers"]
