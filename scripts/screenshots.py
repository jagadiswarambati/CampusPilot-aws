"""Generates the README screenshots (docs/screenshots/*.png) from the running dev server with Playwright.

Run with `scripts/browser.sh shots`. Needs: pip install playwright && playwright install chromium
"""
import os
from playwright.sync_api import sync_playwright

BASE = os.environ.get("BASE", "http://127.0.0.1:8787")
OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "docs", "screenshots")
os.makedirs(OUT, exist_ok=True)


def settle(page, ms=500):
    page.evaluate("window.scrollTo(0, 0)")
    page.wait_for_timeout(ms)


def desktop(b):
    ctx = b.new_context(viewport={"width": 1440, "height": 900})
    ctx.add_init_script("localStorage.setItem('cp_clock','lunch'); localStorage.setItem('cp_student','stu-shots01');")
    page = ctx.new_page()
    snap = lambda name, full=False: (settle(page), page.screenshot(path=f"{OUT}/{name}.png", full_page=full))
    page.goto(BASE + "/#/planner"); page.click(".examples button"); page.click("#go"); page.wait_for_selector(".verdict.ok", timeout=15000)
    page.wait_for_timeout(800); snap("planner-desktop", True)
    page.click(".plan .btn.primary"); page.wait_for_selector(".plan .done")
    page.goto(BASE + "/#/library"); page.wait_for_selector("button.seat.free")
    page.click("button.seat.free >> nth=6"); page.click("#book"); page.wait_for_selector(".pass"); page.click("button.seat.free >> nth=9"); page.set_viewport_size({"width": 1440, "height": 1120}); page.wait_for_timeout(4500); snap("library-desktop"); page.set_viewport_size({"width": 1440, "height": 900})
    page.goto(BASE + "/#/attendance"); page.wait_for_selector(".subject")
    if page.query_selector('button[data-period="p4"]'): page.click('button[data-period="p4"]'); page.wait_for_selector("text=Checked in")
    page.wait_for_timeout(4000); snap("attendance-desktop")
    page.goto(BASE + "/#/print"); page.wait_for_selector(".shop"); page.click("#send-job"); page.wait_for_selector(".ticket .token"); page.wait_for_timeout(4000); snap("print-desktop")
    page.goto(BASE + "/#/canteen"); page.wait_for_selector("[data-dish]"); page.click('[data-add="chai"]'); page.click('[data-add="samosa"]'); page.wait_for_timeout(4000); snap("canteen-desktop")
    page.click("#place-order"); page.wait_for_selector("#order-token")
    page.goto(BASE + "/#/orders"); page.wait_for_selector(".order"); page.wait_for_timeout(4000); snap("orders-desktop")
    page.goto(BASE + "/#/dashboard"); page.wait_for_selector(".board-row"); page.wait_for_timeout(4000); snap("dashboard-desktop")
    ctx.close()


def mobile(b):
    ctx = b.new_context(viewport={"width": 390, "height": 844}, device_scale_factor=2, is_mobile=True, has_touch=True)
    ctx.add_init_script("localStorage.setItem('cp_clock','lunch'); localStorage.setItem('cp_student','stu-shots02');")
    page = ctx.new_page()
    page.goto(BASE + "/#/dashboard"); page.wait_for_selector(".board-row"); page.wait_for_timeout(700); settle(page); page.screenshot(path=f"{OUT}/dashboard-mobile.png")
    page.goto(BASE + "/#/library"); page.wait_for_selector("button.seat.free"); page.click("button.seat.free >> nth=5")
    page.evaluate("document.querySelector('.seatmap').scrollIntoView({block:'start'})"); page.wait_for_timeout(500); page.screenshot(path=f"{OUT}/library-mobile.png")
    page.goto(BASE + "/#/canteen"); page.wait_for_selector("[data-dish]"); page.click('[data-add="chai"]'); page.click('[data-add="samosa"]'); settle(page); page.screenshot(path=f"{OUT}/canteen-mobile.png")
    ctx.close()


with sync_playwright() as p:
    browser = p.chromium.launch(args=["--no-sandbox"])
    desktop(browser)
    mobile(browser)
    browser.close()
print("Screenshots written to docs/screenshots/")
