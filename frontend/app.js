"use strict";
const API = (window.CAMPUSPILOT_API || "").replace(/\/$/, "");
const EXAMPLES = [
  "I have 35 minutes before class. I need a vegetarian lunch and 25 pages printed under ₹250.",
  "Only 18 minutes left. I need 50 pages in color and a lunch thali.",
  "Need 40 pages printed, 20 minutes.",
];
const PARSERS = { rules: "built-in rules", bedrock: "Amazon Bedrock" };
const $ = (id) => document.getElementById(id);
const idPart = () => Math.random().toString(36).slice(2, 10);
// Anonymous per-browser id. If storage is blocked (private mode) use a fresh id, never a shared one.
const studentId = (() => {
  try {
    let id = localStorage.getItem("cp_student");
    if (!id) { id = "stu-" + idPart(); localStorage.setItem("cp_student", id); }
    return id;
  } catch { return "stu-" + idPart(); }
})();

// Safe DOM builder: all server text goes through text nodes, never innerHTML.
function el(tag, attrs = {}, ...kids) {
  const n = document.createElement(tag);
  for (const [k, v] of Object.entries(attrs)) {
    if (k === "class") n.className = v;
    else if (k === "style") n.style.cssText = v;
    else if (k.startsWith("on")) n.addEventListener(k.slice(2), v);
    else n.setAttribute(k, v);
  }
  for (const k of kids.flat()) if (k != null) n.append(k.nodeType ? k : document.createTextNode(k));
  return n;
}

async function api(path, options = {}) {
  if (!API) throw Object.assign(new Error("The API address is not configured. Deploy with scripts/deploy.sh, or run backend/dev_server.py."), { status: 0 });
  const ctl = new AbortController();
  const timer = setTimeout(() => ctl.abort(), 20000);
  try {
    const res = await fetch(API + path, { ...options, signal: ctl.signal });
    const body = await res.json().catch(() => ({}));
    if (!res.ok) throw Object.assign(new Error(body.error || `Request failed (${res.status}).`), { status: res.status });
    return body;
  } catch (e) {
    if (e.status !== undefined) throw e;
    throw Object.assign(new Error(e.name === "AbortError"
      ? "The server took too long to answer. Try again."
      : "Can't reach CampusPilot. Check your connection and try again."), { status: 0 });
  } finally { clearTimeout(timer); }
}
const post = (path, data) => api(path, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(data) });
const inr = (n) => "₹" + Number(n).toLocaleString("en-IN", { maximumFractionDigits: 2 });

function breakBar(plan, minutes) {
  const used = plan.total_min + plan.buffer_min;
  const scale = Math.max(minutes, used);
  const pct = (m) => (m / scale) * 100 + "%";
  const bar = el("div", { class: "bar", role: "img",
    "aria-label": `${plan.total_min} minutes of tasks plus a ${plan.buffer_min} minute buffer, out of ${minutes} minutes available` });
  plan.steps.filter((s) => s.end > s.start).forEach((s) =>
    bar.append(el("div", { class: "seg " + s.kind, style: `width:${pct(s.end - s.start)}`, title: `${s.label} (${s.end - s.start} min)` })));
  bar.append(el("div", { class: "seg buffer", style: `width:${pct(plan.buffer_min)}`, title: "Safety buffer" }));
  if (minutes > used) bar.append(el("div", { class: "seg slack", style: `width:${pct(minutes - used)}`, title: "Spare time" }));
  if (used > minutes) bar.append(el("div", { class: "deadline", style: `left:${pct(minutes)}`, title: "Class starts" }));
  const legend = el("div", { class: "legend" },
    [["walk", "Walking"], ["print", "Printing"], ["wait", "Waiting for food"], ["buffer", "Safety buffer"],
      minutes > used ? ["slack", "Spare time"] : ["over", "Class starts at the dark line"]]
      .map(([c, t]) => el("span", {}, el("i", { class: "seg " + c }), t)));
  return [bar, legend];
}

function planCard(plan) {
  const card = el("article", { class: "plan" + (plan.feasible ? "" : " nofit") });
  card.append(el("h3", {}, plan.label),
    el("p", { class: "sub" }, [plan.shop?.name, plan.item?.name].filter(Boolean).join(" with ") + `, ${plan.total_min} min of tasks`));
  card.append(el("ol", { class: "steps" }, plan.steps.map((s) =>
    el("li", {}, el("time", {}, s.end > s.start ? `min ${s.start}–${s.end}` : `min ${s.start}`),
      el("span", {}, s.label, " ", el("span", { class: "where" }, s.end > s.start && s.kind !== "walk" ? "at " + s.where : ""))))));
  const foot = el("div", { class: "foot" }, el("span", { class: "cost" }, inr(plan.cost.total)));
  if (plan.feasible) {
    const btn = el("button", { class: "confirm" }, "Place simulated orders");
    const msg = el("span", { class: "err", role: "alert" });
    btn.addEventListener("click", () => confirmPlan(plan, btn, foot, msg));
    foot.append(btn, msg);
  } else foot.append(el("span", { class: "err" }, "Doesn't fit, so it can't be ordered"));
  card.append(foot);
  return card;
}

function renderResult(res) {
  const minutes = res.request.minutes, out = $("result");
  out.replaceChildren();
  if (!res.best) { out.append(el("p", { class: "err" }, res.reason)); return; }
  out.append(el("div", { class: "verdict " + (res.feasible ? "ok" : "bad") },
    el("span", { class: "big" }, res.feasible ? `Fits, with ${res.best.slack_min} min to spare` : "Won't fit in your break"),
    el("span", { class: "ids" }, `${minutes} min available. Request read with ${PARSERS[res.request.parser] || res.request.parser}.`)));
  if (res.reason) out.append(el("p", { class: "reason" }, res.reason));
  out.append(...breakBar(res.best, minutes), planCard(res.best));
  if (res.alternatives.length) {
    out.append(el("h2", {}, res.feasible ? "Other options" : "What would fit"));
    res.alternatives.forEach((p) => out.append(planCard(p)));
  } else if (!res.feasible) out.append(el("p", { class: "reason" }, "Nothing fits in this time. Try fewer pages, a quicker item, or a longer break."));
  out.focus({ preventScroll: true });
  out.scrollIntoView?.({ behavior: "smooth", block: "start" });  // on phones the result sits below the form
}

async function confirmPlan(plan, btn, foot, msg) {
  btn.disabled = true; msg.textContent = "";
  try {
    const o = await post("/orders", { plan_id: plan.id, student_id: studentId });
    btn.remove();
    foot.append(el("p", { class: "done" }, "Ordered: " + [o.print_order_id, o.food_order_id].filter(Boolean).join(" and ")));
    loadOrders();
  } catch (e) {
    msg.textContent = e.message;
    if (e.status === 409 && /already confirmed/.test(e.message)) { btn.textContent = "Already ordered"; loadOrders(); }
    else btn.disabled = false;  // other errors may be temporary, so allow a retry
  }
}

async function loadOrders() {
  try {
    const { orders } = await api("/orders?student_id=" + encodeURIComponent(studentId));
    $("orders-wrap").hidden = orders.length === 0;
    $("orders").replaceChildren(...orders.map((o) => el("li", {},
      el("span", {}, o.summary, el("br"), el("span", { class: "ids" }, [o.print_order_id, o.food_order_id].filter(Boolean).join(" and "))),
      el("span", { class: "cost" }, inr(o.total_cost)))));
  } catch { /* the order list is secondary, so the planning flow keeps working */ }
}

async function planBreak() {
  const text = $("ask").value.trim();
  if (!text) { $("ask").focus(); return; }
  $("go").disabled = true; $("go").textContent = "Planning…"; $("result").setAttribute("aria-busy", "true");
  try { renderResult(await post("/plan", { text })); }
  catch (e) { $("result").replaceChildren(el("p", { class: "err", role: "alert" }, e.message)); }
  finally { $("go").disabled = false; $("go").textContent = "Plan my break"; $("result").removeAttribute("aria-busy"); }
}

$("go").addEventListener("click", planBreak);
$("ask").addEventListener("keydown", (e) => { if (e.key === "Enter" && (e.ctrlKey || e.metaKey)) planBreak(); });
$("examples").append(...EXAMPLES.map((t) => el("button", { onclick: () => { $("ask").value = t; $("ask").focus(); } }, t)));
loadOrders();
