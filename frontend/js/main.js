"use strict";
/* App shell: sidebar navigation, hash router, campus clock control, API health, mobile drawer. */
(function (CP) {
  const { el, icon, $ } = CP;
  CP.routes = [
    { id: "dashboard", label: "Dashboard", sub: "Today at a glance" },
    { id: "planner", label: "Break Planner", sub: "AI agent for your gaps" },
    { id: "attendance", label: "Attendance", sub: "Check in and track" },
    { id: "library", label: "Library seats", sub: "Pick your seat" },
    { id: "print", label: "Print shops", sub: "Live queues" },
    { id: "canteen", label: "Canteen", sub: "Order ahead" },
    { id: "orders", label: "My orders", sub: "Tokens and status", badge: true },
    { id: "architecture", label: "AWS architecture", sub: "How it is built" },
  ];

  function buildNav() {
    const nav = $("nav");
    CP.routes.forEach((r) => nav.append(el("a", { class: "stop", href: "#/" + r.id, "data-nav": r.id, style: `--c: var(--c-${r.id})` },
      el("span", { class: "dot" }), el("span", {}, el("b", {}, r.label), el("small", {}, r.sub)), r.badge ? el("span", { class: "nav-badge", hidden: true }, "0") : null)));
    $("me").append(el("span", { class: "avatar" }, "GS"), el("div", {}, el("strong", {}, "Guest student"), el("small", {}, "Demo account · " + CP.studentId.slice(4, 12))));
    $("burger").append(icon("menu", 22));
  }

  function route() {
    const id = (location.hash.match(/^#\/([a-z]+)/) || [])[1];
    const known = CP.routes.some((r) => r.id === id);
    const page = known ? id : "dashboard";   // unknown addresses fall back to the dashboard
    if (!CP.pages[page]) {  // a known section whose script failed to load: say so, never a blank page or a silent redirect
      $("view").replaceChildren(CP.errorBox(new Error("This section failed to load. Check your connection and reload the page."), () => location.reload()));
      return;
    }
    if (!CP.pages[id] && location.hash && location.hash !== "#/dashboard") history.replaceState(null, "", "#/dashboard");
    CP.clearTimers(); CP.page.token++;
    document.body.dataset.page = page;
    document.querySelectorAll("nav a").forEach((a) => { const on = a.dataset.nav === page; a.classList.toggle("active", on); on ? a.setAttribute("aria-current", "page") : a.removeAttribute("aria-current"); });
    $("page-title").textContent = CP.pages[page].title;
    document.title = `${CP.pages[page].title} · CampusPilot`;
    const view = $("view"); view.replaceChildren(); view.style.animation = "none"; void view.offsetWidth; view.style.animation = "";
    document.body.classList.remove("nav-open");
    try { CP.pages[page].mount(view); } catch (e) { view.replaceChildren(CP.errorBox(e)); }
    window.scrollTo(0, 0);
  }

  function buildClock() {
    const box = $("clock"), label = el("small", {}), time = el("span", { id: "clock-time" });
    const btn = el("button", { class: "clock-btn", "aria-haspopup": "true", "aria-expanded": "false", id: "clock-btn" }, icon("clock", 18), time, label);
    const menu = el("div", { class: "clock-menu", role: "menu", hidden: true });
    const tick = () => { time.textContent = CP.clock.at(); label.textContent = CP.clock.label(); };
    const close = () => { menu.hidden = true; btn.setAttribute("aria-expanded", "false"); };
    const fill = () => menu.replaceChildren(el("p", {}, "Campus time. Jump to a busy moment to see how the agent reacts."),
      ...CP.clock.presets.map(([id, name, at]) => { const b = el("button", { role: "menuitemradio", "aria-checked": String(CP.clock.mode === id), "data-clock": id }, el("span", {}, name), el("small", { class: "muted" }, at ? CP.hhmm(at) : "now")); b.addEventListener("click", () => { CP.clock.set(id); fill(); tick(); close(); }); return b; }));
    btn.addEventListener("click", (e) => { e.stopPropagation(); menu.hidden = !menu.hidden; btn.setAttribute("aria-expanded", String(!menu.hidden)); if (!menu.hidden) fill(); });
    document.addEventListener("click", (e) => { if (!box.contains(e.target)) close(); });
    document.addEventListener("keydown", (e) => { if (e.key === "Escape") { close(); document.body.classList.remove("nav-open"); } });
    box.append(btn, menu); tick(); setInterval(tick, 1000);
  }

  function buildHealth() {
    const box = $("health"), dot = el("span", { class: "dot" }), txt = el("span", { class: "txt" }, "Checking API");
    box.append(dot, txt);
    const ping = async () => {
      const t = performance.now();
      try { await CP.api("/health"); dot.className = "dot-s ok"; txt.textContent = `API online · ${Math.round(performance.now() - t)} ms`; }
      catch (e) { dot.className = "dot-s bad"; txt.textContent = CP.API ? "API unreachable" : "API not configured"; }
    };
    ping(); setInterval(ping, 30000);
  }

  CP.refreshBadge = async () => { try { const d = await CP.get("/orders"); CP.setBadge("orders", d.orders.filter((o) => o.progress < 1).length); } catch { /* badge is cosmetic */ } };

  function boot() {
    buildNav(); buildClock(); buildHealth();
    $("burger").addEventListener("click", () => document.body.classList.toggle("nav-open"));
    $("scrim").addEventListener("click", () => document.body.classList.remove("nav-open"));
    window.addEventListener("hashchange", route);
    route(); CP.refreshBadge(); setInterval(CP.refreshBadge, 15000);
  }
  document.readyState === "loading" ? document.addEventListener("DOMContentLoaded", boot) : boot();
})(window.CP);
