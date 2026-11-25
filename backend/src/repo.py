"""DynamoDB access layer (single-table design: pk = entity type, sk = id)."""
import copy
import hashlib
import json
import os
import time
from decimal import Decimal

import boto3
from boto3.dynamodb.conditions import Key
from boto3.dynamodb.types import TypeSerializer
from botocore.exceptions import ClientError

import data

_table = None
_client = None
_seeded = False
_campus_cache = None  # (expires_at, data): campus data changes rarely, so reads are cached briefly
CAMPUS_CACHE_SECONDS = 20
PLAN_TTL_SECONDS = 3600
ORDER_TTL_SECONDS = 30 * 86400


class DuplicateOrder(Exception):
    pass


class SeatTaken(Exception):
    pass


class AlreadyBooked(Exception):
    pass


class NoBooking(Exception):
    pass


class AlreadyMarked(Exception):
    pass


def table():
    global _table
    if _table is None:
        _table = boto3.resource("dynamodb").Table(os.environ["TABLE_NAME"])
    return _table


def client():
    """Low-level client: transactions use explicit DynamoDB-typed values (the resource API would re-serialize them)."""
    global _client
    if _client is None:
        _client = boto3.client("dynamodb")
    return _client


def _num(o):
    if isinstance(o, Decimal):
        return int(o) if o == o.to_integral_value() else float(o)
    raise TypeError(type(o))


def plain(obj):
    """Decimal -> int/float so results are JSON/planner friendly."""
    return json.loads(json.dumps(obj, default=_num))


def _to_ddb(obj):
    return json.loads(json.dumps(obj), parse_float=Decimal)


def _items(pk):
    return plain(table().query(KeyConditionExpression=Key("pk").eq(pk))["Items"])


def _seed_version():
    return hashlib.sha1(json.dumps(data.seed_items(), sort_keys=True).encode()).hexdigest()[:12]


def ensure_seed():
    """Seeds campus data on first use, and re-seeds when data.py changed after a redeploy."""
    global _seeded, _campus_cache
    if _seeded:
        return
    version = _seed_version()
    meta = table().get_item(Key={"pk": "META", "sk": "seed"}).get("Item")
    if not meta or meta.get("version") != version:
        wanted = {(i["pk"], i["sk"]) for i in data.seed_items()}
        with table().batch_writer() as batch:
            for pk in ("SHOP", "MENU", "WALK"):  # remove entries that no longer exist in data.py
                for row in _items(pk):
                    if (pk, row["sk"]) not in wanted:
                        batch.delete_item(Key={"pk": pk, "sk": row["sk"]})
            for item in data.seed_items():
                batch.put_item(Item=_to_ddb(item))
            batch.put_item(Item={"pk": "META", "sk": "seed", "version": version})
        _campus_cache = None
    _seeded = True


def campus():
    global _campus_cache
    ensure_seed()
    if _campus_cache and _campus_cache[0] > time.time():
        return copy.deepcopy(_campus_cache[1])  # callers adjust the copy (live queues), never the cache
    strip = lambda rows: [{k: v for k, v in r.items() if k not in ("pk", "sk")} for r in rows]
    fresh = {"shops": strip(_items("SHOP")), "menu": strip(_items("MENU")),
             "walks": {r["sk"]: r["minutes"] for r in _items("WALK")}, "locations": data.LOCATIONS}
    _campus_cache = (time.time() + CAMPUS_CACHE_SECONDS, fresh)
    return copy.deepcopy(fresh)


def get_menu_item(item_id):
    """Strongly consistent read, used to revalidate an order against live data."""
    item = table().get_item(Key={"pk": "MENU", "sk": item_id}, ConsistentRead=True).get("Item")
    return plain(item) if item else None


def save_plan(plan):
    table().put_item(Item=_to_ddb({"pk": "PLAN", "sk": plan["id"], "plan": plan,
                                   "ttl": int(time.time()) + PLAN_TTL_SECONDS}))


def get_plan(plan_id):
    """TTL deletion can lag by hours, so expiry is also enforced here."""
    item = table().get_item(Key={"pk": "PLAN", "sk": plan_id}).get("Item")
    if not item or int(item.get("ttl", 0)) <= time.time():
        return None
    return plain(item["plan"])


def create_order(student_id, plan_id, order):
    """One order per plan: the conditional write rejects duplicate submissions."""
    try:
        table().put_item(
            Item=_to_ddb({"pk": f"ORDER#{student_id}", "sk": plan_id,
                          "ttl": int(time.time()) + ORDER_TTL_SECONDS, **order}),
            ConditionExpression="attribute_not_exists(sk)")
    except ClientError as exc:
        if exc.response["Error"]["Code"] == "ConditionalCheckFailedException":
            raise DuplicateOrder() from exc
        raise


def list_orders(student_id):
    rows = _items(f"ORDER#{student_id}")
    return sorted(rows, key=lambda r: r["created_at"], reverse=True)[:30]


# ---- library seats ----
def _typed(item):
    ser = TypeSerializer()
    return {k: ser.serialize(v) for k, v in item.items()}


def seat_bookings(date):
    """All real bookings for the day: items {sk: '<slot>#<seat>', owner}."""
    return _items(f"SEAT#{date}")


def book_seat(date, slot, seat, student):
    """Atomically claims the seat AND the student's one-seat-per-slot allowance (all or nothing)."""
    ttl = int(time.time()) + 2 * 86400
    name = os.environ["TABLE_NAME"]
    try:
        client().transact_write_items(TransactItems=[
            {"Put": {"TableName": name, "ConditionExpression": "attribute_not_exists(sk)",
                     "Item": _typed({"pk": f"SEAT#{date}", "sk": f"{slot}#{seat}", "owner": student, "ttl": ttl})}},
            {"Put": {"TableName": name, "ConditionExpression": "attribute_not_exists(sk)",
                     "Item": _typed({"pk": f"MYSEAT#{student}", "sk": f"{date}#{slot}", "seat": seat, "ttl": ttl})}},
        ])
    except ClientError as exc:
        if exc.response["Error"]["Code"] == "TransactionCanceledException":
            codes = [r.get("Code") for r in exc.response.get("CancellationReasons", [])]
            if codes[:1] == ["ConditionalCheckFailed"]:
                raise SeatTaken() from exc
            if codes[1:2] == ["ConditionalCheckFailed"]:
                raise AlreadyBooked() from exc
        raise


def cancel_seat(date, slot, student):
    mine = table().get_item(Key={"pk": f"MYSEAT#{student}", "sk": f"{date}#{slot}"}).get("Item")
    if not mine:
        raise NoBooking()
    name = os.environ["TABLE_NAME"]
    try:
        client().transact_write_items(TransactItems=[
            {"Delete": {"TableName": name, "Key": _typed({"pk": f"SEAT#{date}", "sk": f"{slot}#{mine['seat']}"}),
                        "ConditionExpression": "#o = :me", "ExpressionAttributeNames": {"#o": "owner"},
                        "ExpressionAttributeValues": _typed({":me": student})}},
            {"Delete": {"TableName": name, "Key": _typed({"pk": f"MYSEAT#{student}", "sk": f"{date}#{slot}"})}},
        ])
    except ClientError as exc:
        if exc.response["Error"]["Code"] == "TransactionCanceledException":
            raise NoBooking() from exc
        raise
    return mine["seat"]


# ---- attendance ----
def attendance_marks(student, date):
    resp = table().query(KeyConditionExpression=Key("pk").eq(f"ATT#{student}") & Key("sk").begins_with(f"{date}#"))
    return plain(resp["Items"])


def mark_attendance(student, date, period_id, code):
    try:
        table().put_item(
            Item=_to_ddb({"pk": f"ATT#{student}", "sk": f"{date}#{period_id}", "code": code,
                          "ttl": int(time.time()) + 7 * 86400}),
            ConditionExpression="attribute_not_exists(sk)")
    except ClientError as exc:
        if exc.response["Error"]["Code"] == "ConditionalCheckFailedException":
            raise AlreadyMarked() from exc
        raise
