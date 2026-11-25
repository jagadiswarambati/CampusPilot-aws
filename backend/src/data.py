"""Sample campus data. Everything here is illustrative: replace it with your own college's
real print shops, menu, timetable and library layout, then redeploy (changes re-seed automatically)."""

LOCATIONS = {
    "CLASS": "Academic Block",
    "LIB": "Central Library",
    "ENG": "Engineering Block",
    "SAC": "SAC Canteen",
}

# Walking minutes between locations (symmetric).
WALK = {
    "CLASS#LIB": 3, "CLASS#ENG": 2, "CLASS#SAC": 4,
    "LIB#SAC": 3, "ENG#SAC": 5, "LIB#ENG": 4,
}

# queue_min is the off-peak base queue; the live value is derived from the simulation (sim.py).
SHOPS = [
    {"id": "lib", "name": "Central Library Print Center", "loc": "LIB", "queue_min": 6, "ppm": 20,
     "price_bw": 1.5, "price_color": 8.0, "capacity": 14, "job_min": 0.7, "shift": 20},
    {"id": "eng", "name": "Engineering FastPrint Hub", "loc": "ENG", "queue_min": 2, "ppm": 15,
     "price_bw": 2.0, "price_color": 10.0, "capacity": 9, "job_min": 0.5, "shift": -15},
]

MENU = [
    {"id": "thali", "name": "Mini Veg Thali", "category": "Meals", "price": 110, "prep_min": 11, "veg": True, "available": True, "popular": True},
    {"id": "biryani", "name": "Veg Biryani", "category": "Meals", "price": 120, "prep_min": 14, "veg": True, "available": False, "popular": False},
    {"id": "chole", "name": "Chole Kulche", "category": "Meals", "price": 70, "prep_min": 7, "veg": True, "available": True, "popular": True},
    {"id": "eggrice", "name": "Egg Fried Rice", "category": "Meals", "price": 100, "prep_min": 10, "veg": False, "available": True, "popular": False},
    {"id": "sandwich", "name": "Grilled Sandwich", "category": "Snacks", "price": 60, "prep_min": 6, "veg": True, "available": True, "popular": False},
    {"id": "wrap", "name": "Paneer Wrap", "category": "Snacks", "price": 80, "prep_min": 8, "veg": True, "available": True, "popular": False},
    {"id": "roll", "name": "Chicken Roll", "category": "Snacks", "price": 90, "prep_min": 9, "veg": False, "available": True, "popular": False},
    {"id": "samosa", "name": "Samosa (2 pcs)", "category": "Snacks", "price": 30, "prep_min": 4, "veg": True, "available": True, "popular": True},
    {"id": "fries", "name": "French Fries", "category": "Snacks", "price": 50, "prep_min": 6, "veg": True, "available": True, "popular": False},
    {"id": "chai", "name": "Masala Chai", "category": "Beverages", "price": 15, "prep_min": 3, "veg": True, "available": True, "popular": True},
    {"id": "coffee", "name": "Filter Coffee", "category": "Beverages", "price": 25, "prep_min": 3, "veg": True, "available": True, "popular": False},
    {"id": "coldcoffee", "name": "Cold Coffee", "category": "Beverages", "price": 50, "prep_min": 4, "veg": True, "available": True, "popular": True},
    {"id": "lime", "name": "Fresh Lime Soda", "category": "Beverages", "price": 35, "prep_min": 3, "veg": True, "available": True, "popular": False},
    {"id": "gulab", "name": "Gulab Jamun (2 pcs)", "category": "Desserts", "price": 40, "prep_min": 2, "veg": True, "available": True, "popular": False},
    {"id": "icecream", "name": "Ice Cream Cup", "category": "Desserts", "price": 35, "prep_min": 1, "veg": True, "available": True, "popular": False},
]

# The break planner only considers these categories when someone asks for "lunch" or "food".
PLANNER_CATEGORIES = ("Meals", "Snacks")

# Sample subjects: attendance held/attended so far this semester, before today.
SUBJECTS = {
    "CS301": {"name": "Database Management Systems", "held": 38, "attended": 33},
    "CS302": {"name": "Operating Systems", "held": 36, "attended": 27},
    "CS303": {"name": "Computer Networks", "held": 34, "attended": 24},
    "ES301": {"name": "Environmental Science", "held": 20, "attended": 19},
    "CS391": {"name": "Web Technologies Lab", "held": 14, "attended": 14},
    "CS304": {"name": "Software Engineering", "held": 30, "attended": 25},
}

# The demo uses the same timetable every day (times are minutes-of-day friendly "HH:MM").
PERIODS = [
    {"id": "p1", "code": "CS301", "room": "Room 204", "start": "09:00", "end": "09:50"},
    {"id": "p2", "code": "CS302", "room": "Room 204", "start": "10:00", "end": "10:50"},
    {"id": "p3", "code": "CS303", "room": "Room 301", "start": "11:00", "end": "11:50"},
    {"id": "p4", "code": "ES301", "room": "Room 105", "start": "12:00", "end": "12:50"},
    {"id": "p5", "code": "CS391", "room": "Lab 2", "start": "14:00", "end": "15:40"},
    {"id": "p6", "code": "CS304", "room": "Room 204", "start": "15:50", "end": "16:40"},
]
ATTENDANCE_TARGET = 75

# Library layout: rows are letters, aisle is the seat number after which a walkway is drawn.
ZONES = [
    {"id": "hall", "name": "Reading Hall", "rows": "ABCDEF", "cols": 10, "aisle": 5},
    {"id": "silent", "name": "Silent Zone", "rows": "ABCD", "cols": 8, "aisle": 4},
    {"id": "group", "name": "Group Study", "rows": "ABC", "cols": 6, "aisle": 3},
    {"id": "lab", "name": "Computer Lab", "rows": "ABCD", "cols": 8, "aisle": 4},
]
SLOTS = [(8, 10), (10, 12), (12, 14), (14, 16), (16, 18), (18, 20)]  # library hours 08:00-20:00


def seed_items():
    """Single-table DynamoDB items: pk groups an entity type, sk identifies it."""
    items = [{"pk": "SHOP", "sk": s["id"], **s} for s in SHOPS]
    items += [{"pk": "MENU", "sk": m["id"], **m} for m in MENU]
    items += [{"pk": "WALK", "sk": k, "minutes": v} for k, v in WALK.items()]
    return items
