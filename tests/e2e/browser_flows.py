"""Real-browser flow test (Playwright + Chromium): plan, book a seat, check in, print, order, plus layout checks.

Run with `scripts/browser.sh test` (starts the dev server). Needs: pip install playwright && playwright install chromium
"""
import sys
from playwright.sync_api import sync_playwright
import os
BASE = os.environ.get("BASE", "http://127.0.0.1:8787")
vp = {"desktop": (1440, 900), "mobile": (390, 844)}
fails = []
def check(name, ok, extra=""):
    print(("PASS " if ok else "FAIL ") + name + ("" if ok else "  -> " + str(extra)))
    if not ok: fails.append(name)
with sync_playwright() as p:
    b = p.chromium.launch(args=["--no-sandbox"])
    for vname, (w, h) in vp.items():
        print(f"--- {vname} ---")
        ctx = b.new_context(viewport={"width": w, "height": h})
        ctx.add_init_script("localStorage.setItem('cp_clock','lunch');")
        page = ctx.new_page(); errors = []
        page.on("pageerror", lambda e: errors.append(str(e)))
        page.on("console", lambda m: errors.append(m.text) if m.type == "error" else None)
        page.goto(BASE + "/#/dashboard"); page.wait_for_selector(".board-row")
        # planner -> order
        page.goto(BASE + "/#/planner"); page.click(".examples button"); page.click("#go")
        page.wait_for_selector(".verdict.ok", timeout=15000)
        page.click(".plan .btn.primary"); page.wait_for_selector(".plan .done")
        check("planner places an order", "PO-" in page.inner_text(".plan .done"))
        # library -> book
        page.goto(BASE + "/#/library"); page.wait_for_selector("button.seat.free")
        seats_visible = page.evaluate("""() => { const r = document.querySelector('.seat-row'); const seats = [...r.querySelectorAll('.seat')]; const box = document.querySelector('.seatmap').getBoundingClientRect();
            return seats.every(s => { const b = s.getBoundingClientRect(); return b.left >= box.left - 1 && b.right <= box.right + 1; }); }""")
        check("all seats of a row fit inside the card (no horizontal clipping)", seats_visible)
        page.click("button.seat.free >> nth=4"); page.click("#book"); page.wait_for_selector(".pass")
        check("library pass appears", page.query_selector(".pass .seatno") is not None)
        # attendance check-in (ongoing class at 12:40)
        page.goto(BASE + "/#/attendance"); page.wait_for_selector(".subject")
        btn = page.query_selector('button[data-period="p4"]')
        if btn: btn.click(); page.wait_for_selector("text=Checked in", timeout=6000)
        check("attendance check-in works", btn is not None)
        # print job
        page.goto(BASE + "/#/print"); page.wait_for_selector(".shop"); page.click("#send-job")
        page.wait_for_selector(".ticket .token"); check("print job token", page.inner_text(".ticket .token").startswith("P-"))
        # canteen order
        page.goto(BASE + "/#/canteen"); page.wait_for_selector("[data-dish]")
        page.click('[data-add="chai"]'); page.click('[data-add="samosa"]')
        page.click("#place-order"); page.wait_for_selector("#order-token")
        check("canteen order token", page.inner_text("#order-token").startswith("C-"))
        # orders
        page.goto(BASE + "/#/orders"); page.wait_for_selector(".order"); page.wait_for_timeout(300)
        check("orders page lists 3 tickets", len(page.query_selector_all(".order")) == 3, len(page.query_selector_all(".order")))
        # horizontal overflow on every page
        for name in ["dashboard","planner","attendance","library","print","canteen","orders","architecture"]:
            page.goto(f"{BASE}/#/{name}"); page.wait_for_timeout(900)
            over = page.evaluate("document.documentElement.scrollWidth - document.documentElement.clientWidth")
            check(f"no horizontal page scroll on {name}", over <= 1, over)
        real = [e for e in errors if "font" not in e.lower()]
        check("no console or page errors", not real, real[:3])
    print("--- failure states ---")
    ctx = b.new_context(viewport={"width": 1280, "height": 800}); page = ctx.new_page()
    ctx.add_init_script("localStorage.setItem('cp_clock','lunch');")
    down = {"on": True}
    api_paths = ("/dashboard?", "/health", "/orders?", "/campus?", "/plan")
    page.route(lambda url: down["on"] and url.startswith(BASE) and any(url[len(BASE):].startswith(x) for x in api_paths), lambda r: r.abort())
    page.goto(BASE + "/#/dashboard"); page.wait_for_selector(".error-card", timeout=8000)
    check("API down: the dashboard shows an error card, not a blank page", "reach" in page.inner_text(".error-card").lower() or "wrong" in page.inner_text(".error-card").lower())
    check("API down: the health pill says unreachable and navigation still works", "unreachable" in page.inner_text("#health") and page.is_visible("nav a[data-nav='library']"))
    down["on"] = False; page.click(".error-card button"); page.wait_for_selector(".board-row", timeout=8000)
    check("API back: the Try again button recovers the page", True)
    ctx2 = b.new_context(); p2 = ctx2.new_page(); p2.route(lambda url: url.endswith("/js/planner.js"), lambda r: r.abort())
    p2.goto(BASE + "/#/planner"); p2.wait_for_selector(".error-card", timeout=8000)
    check("a script that fails to load shows a recoverable message, not a blank page", "failed to load" in p2.inner_text(".error-card").lower())
    b.close()
print("\nFAILED:", fails if fails else "none"); sys.exit(1 if fails else 0)
