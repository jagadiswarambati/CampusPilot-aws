"use strict";
/* Shared utilities: DOM helpers, icons, API client, campus clock, toasts, timers. */
window.CP = { pages: {}, routes: [] };
(function (CP) {
  const NS = "http://www.w3.org/2000/svg";
  CP.API = (window.CAMPUSPILOT_API || "").replace(/\/$/, "");
  CP.$ = (id) => document.getElementById(id);

  function append(node, kids) {
    for (const k of kids.flat(Infinity)) if (k != null && k !== false) node.append(k.nodeType ? k : document.createTextNode(String(k)));
  }
  // Safe DOM builders: server text is always inserted as text nodes, never as HTML.
  CP.el = function (tag, attrs, ...kids) {
    const n = document.createElement(tag);
    for (const [k, v] of Object.entries(attrs || {})) {
      if (v == null || v === false) continue;
      if (k === "class") n.className = v;
      else if (k === "style") n.style.cssText = v;
      else if (k.startsWith("on")) n.addEventListener(k.slice(2), v);
      else n.setAttribute(k, v === true ? "" : v);
    }
    append(n, kids);
    return n;
  };
  CP.svg = function (tag, attrs, ...kids) {
    const n = document.createElementNS(NS, tag);
    for (const [k, v] of Object.entries(attrs || {})) if (v != null) n.setAttribute(k, v);
    append(n, kids);
    return n;
  };

  const ICONS = {
    grid: ["M3 3h7v7H3z", "M14 3h7v7h-7z", "M14 14h7v7h-7z", "M3 14h7v7H3z"],
    zap: ["M13 2L3 14h9l-1 8 10-12h-9l1-8z"],
    check: ["M9 11l3 3L22 4", "M21 12v7a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h11"],
    book: ["M2 3h6a4 4 0 0 1 4 4v14a3 3 0 0 0-3-3H2z", "M22 3h-6a4 4 0 0 0-4 4v14a3 3 0 0 1 3-3h7z"],
    printer: ["M6 9V2h12v7", "M6 18H4a2 2 0 0 1-2-2v-5a2 2 0 0 1 2-2h16a2 2 0 0 1 2 2v5a2 2 0 0 1-2 2h-2", "M6 14h12v8H6z"],
    coffee: ["M18 8h1a4 4 0 0 1 0 8h-1", "M2 8h16v9a4 4 0 0 1-4 4H6a4 4 0 0 1-4-4V8z", "M6 1v3", "M10 1v3", "M14 1v3"],
    bag: ["M6 2L3 6v14a2 2 0 0 0 2 2h14a2 2 0 0 0 2-2V6l-3-4z", "M3 6h18", "M16 10a4 4 0 0 1-8 0"],
    layers: ["M12 2L2 7l10 5 10-5-10-5z", "M2 17l10 5 10-5", "M2 12l10 5 10-5"],
    menu: ["M3 12h18", "M3 6h18", "M3 18h18"],
    x: ["M18 6L6 18", "M6 6l12 12"],
    clock: ["M12 2a10 10 0 1 0 0 20a10 10 0 1 0 0-20", "M12 6v6l4 2"],
    pulse: ["M22 12h-4l-3 9L9 3l-3 9H2"],
    plus: ["M12 5v14", "M5 12h14"],
    minus: ["M5 12h14"],
    tick: ["M20 6L9 17l-5-5"],
    arrow: ["M5 12h14", "M12 5l7 7-7 7"],
    user: ["M20 21v-2a4 4 0 0 0-4-4H8a4 4 0 0 0-4 4v2", "M12 3a4 4 0 1 0 0 8a4 4 0 1 0 0-8"],
    alert: ["M10.3 3.9L1.8 18a2 2 0 0 0 1.7 3h17a2 2 0 0 0 1.7-3L13.7 3.9a2 2 0 0 0-3.4 0z", "M12 9v4", "M12 17h.01"],
    cloud: ["M18 10h-1.3A8 8 0 1 0 9 20h9a5 5 0 0 0 0-10z"],
  };
  CP.icon = (name, size = 20) => CP.svg("svg", { viewBox: "0 0 24 24", width: size, height: size, fill: "none", stroke: "currentColor",
    "stroke-width": 2, "stroke-linecap": "round", "stroke-linejoin": "round", "aria-hidden": "true", class: "icon" },
  ...(ICONS[name] || []).map((d) => CP.svg("path", { d })));

  // ---- formatting ----
  CP.inr = (n) => "₹" + Number(n).toLocaleString("en-IN", { maximumFractionDigits: 2 });
  CP.hhmm = (m) => String(Math.floor(m / 60)).padStart(2, "0") + ":" + String(Math.floor(m % 60)).padStart(2, "0");
  CP.ago = (ts) => {
    const s = Math.max(0, Date.now() / 1000 - ts);
    return s < 45 ? "just now" : s < 3600 ? `${Math.round(s / 60)} min ago` : `${Math.round(s / 3600)} h ago`;
  };
  CP.uuid = () => {
    const b = new Uint8Array(16);
    (window.crypto && crypto.getRandomValues) ? crypto.getRandomValues(b) : b.forEach((_, i) => (b[i] = Math.floor(Math.random() * 256)));
    return Array.from(b, (x) => x.toString(16).padStart(2, "0")).join("");
  };
  CP.toMin = (s) => { const [h, m] = s.split(":"); return +h * 60 + +m; };
  CP.EXAMPLES = [
    "I have 40 minutes before class. I need a vegetarian lunch and 25 pages printed under ₹250.",
    "Only 22 minutes left. I need 50 pages in color and a lunch thali.",
    "Need 40 pages printed, 20 minutes.",
  ];
  CP.pill = (text, kind = "info") => CP.el("span", { class: "pill " + kind }, text);
  CP.levelKind = (label) => (label === "Quiet" ? "ok" : label === "Busy" ? "warn" : "bad");
  CP.meter = (fraction, kind) => CP.el("div", { class: "meter" + (kind ? " " + kind : ""), role: "presentation" },
    CP.el("i", { style: `width:${Math.max(0, Math.min(1, fraction)) * 100}%` }));
  CP.reduceMotion = () => !!(window.matchMedia && matchMedia("(prefers-reduced-motion: reduce)").matches);
  CP.sleep = (ms) => new Promise((r) => setTimeout(r, CP.reduceMotion() ? 0 : ms));

  // ---- anonymous student identity (per browser; never shared in private mode) ----
  const rand = () => Math.random().toString(36).slice(2, 10);
  CP.studentId = (() => {
    try {
      let id = localStorage.getItem("cp_student");
      if (!id) { id = "stu-" + rand(); localStorage.setItem("cp_student", id); }
      return id;
    } catch { return "stu-" + rand(); }
  })();

  // ---- API client ----
  CP.api = async function (path, options = {}) {
    if (!CP.API) throw Object.assign(new Error("The API address is not configured. Deploy with scripts/deploy.sh, or run backend/dev_server.py."), { status: 0 });
    const ctl = new AbortController();
    const timer = setTimeout(() => ctl.abort(), 20000);
    try {
      const res = await fetch(CP.API + path, { ...options, signal: ctl.signal });
      const body = await res.json().catch(() => ({}));
      if (!res.ok) throw Object.assign(new Error(body.error || `Request failed (${res.status}).`), { status: res.status });
      return body;
    } catch (e) {
      if (e.status !== undefined) throw e;
      throw Object.assign(new Error(e.name === "AbortError" ? "The server took too long to answer. Try again."
        : "Can't reach CampusPilot. Check your connection and try again."), { status: 0 });
    } finally { clearTimeout(timer); }
  };
  CP.get = (path, params = {}) => CP.api(`${path}?${new URLSearchParams({ student_id: CP.studentId, at: CP.clock.at(), ...params })}`);
  CP.post = (path, data = {}) => CP.api(path, { method: "POST", headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ student_id: CP.studentId, at: CP.clock.at(), ...data }) });

  // ---- simulated campus clock (campus hours 08:00-20:00, runs 10x faster than real time) ----
  const OPEN = 8 * 60, CLOSE = 20 * 60, SPEED = 10;
  const PRESETS = [["morning", "Morning rush", 9 * 60 + 10], ["lunch", "Lunch hour", 12 * 60 + 40],
    ["afternoon", "Afternoon", 15 * 60 + 30], ["evening", "Evening study", 18 * 60 + 15], ["live", "Real time (IST)", null]];
  const stored = (() => { try { return localStorage.getItem("cp_clock"); } catch { return null; } })();
  CP.clock = {
    presets: PRESETS, mode: PRESETS.some((p) => p[0] === stored) ? stored : "lunch", started: Date.now(),
    minutes() {
      if (this.mode === "live") {
        const ist = new Date(Date.now() + (330 + new Date().getTimezoneOffset()) * 60000);
        return Math.max(OPEN, Math.min(ist.getHours() * 60 + ist.getMinutes(), CLOSE - 1));
      }
      const base = PRESETS.find((p) => p[0] === this.mode)[2];
      const m = base + ((Date.now() - this.started) / 1000) * SPEED / 60;
      return OPEN + ((m - OPEN) % (CLOSE - OPEN));
    },
    at() { return CP.hhmm(this.minutes()); },
    label() { return PRESETS.find((p) => p[0] === this.mode)[1]; },
    set(mode) {
      this.mode = mode; this.started = Date.now();
      try { localStorage.setItem("cp_clock", mode); } catch { /* storage may be blocked */ }
      document.dispatchEvent(new CustomEvent("cp:clock"));
    },
  };

  // ---- toasts ----
  CP.toast = function (message, kind = "info") {
    const box = CP.$("toasts");
    if (!box) return;
    const t = CP.el("div", { class: "toast " + kind, role: kind === "bad" ? "alert" : "status" }, message);
    box.append(t);
    while (box.children.length > 3) box.firstChild.remove();  // never let toasts pile up over the page
    setTimeout(() => t.remove(), 3600);
  };

  // ---- page lifecycle: timers and stale-callback guards ----
  CP._timers = [];
  CP.page = { token: 0 };
  CP.every = (ms, fn) => { const id = setInterval(fn, ms); CP._timers.push(id); return id; };
  CP._listeners = [];
  CP.onClock = (fn) => { document.addEventListener("cp:clock", fn); CP._listeners.push(fn); };
  CP.clearTimers = () => {
    CP._timers.forEach(clearInterval); CP._timers = [];
    CP._listeners.forEach((fn) => document.removeEventListener("cp:clock", fn)); CP._listeners = [];
  };
  CP.guard = () => { const t = CP.page.token; return () => t === CP.page.token; };

  // ---- shared UI pieces ----
  CP.skeleton = (rows = 3) => CP.el("div", { class: "skeleton-wrap", "aria-busy": "true" },
    Array.from({ length: rows }, () => CP.el("div", { class: "skel" })));
  CP.errorBox = (err, retry) => CP.el("div", { class: "card error-card", role: "alert" },
    CP.icon("alert", 22), CP.el("div", {}, CP.el("strong", {}, "Something went wrong"), CP.el("p", {}, err.message || String(err))),
    retry ? CP.el("button", { class: "btn", onclick: retry }, "Try again") : null);
  CP.head = (title, sub, ...actions) => CP.el("div", { class: "page-head" },
    CP.el("div", {}, CP.el("h1", {}, title), sub ? CP.el("p", { class: "sub" }, sub) : null),
    actions.length ? CP.el("div", { class: "page-actions" }, actions) : null);
  CP.simBadge = (text = "Sample data, simulated live") => CP.el("span", { class: "sim-badge", title: "Numbers on this page come from a deterministic campus simulation" }, text);
  CP.navigate = (id) => { location.hash = "#/" + id; };
  CP.setBadge = (id, n) => {
    const b = document.querySelector(`[data-nav="${id}"] .nav-badge`);
    if (b) { b.textContent = n; b.hidden = !n; }
  };
})(window.CP);
