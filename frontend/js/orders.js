"use strict";
/* My orders: planner, print and canteen orders in one list, with live simulated status. */
(function (CP) {
  const { el, icon } = CP;
  const KINDS = { all: "All", plan: "Break plans", print: "Print jobs", canteen: "Food" };
  
  const SINGULAR = { plan: "Break plan", print: "Print job", canteen: "Food order" };

  function card(o) {
    const stages = [0, 1, 2].map((i) => el("i", { class: i < o.stage ? "on" : i === o.stage ? (o.stage === 2 ? "on" : "cur") : "" }));
    return el("article", { class: "card order", "data-kind": o.kind },
      el("div", {}, el("span", { class: "kind" }, SINGULAR[o.kind] || "Order"), el("div", { class: "tok" }, o.tokens.join(" · ") || "Order"),
        el("h4", {}, o.title), el("div", { class: "stages" }, stages)),
      el("div", { class: "right" }, CP.pill(o.status, o.stage === 2 ? "ok" : "info"), el("div", {}, el("strong", {}, CP.inr(o.total_cost))),
        el("div", { class: "muted" }, o.stage === 2 ? "Done" : `${o.eta_left_min} min left`), el("small", { class: "muted" }, CP.ago(o.created_at))));
  }

  CP.pages.orders = {
    title: "My orders",
    mount(root) {
      const alive = CP.guard();
      let rows = null, kind = "all";
      const chips = el("div", { class: "chips" }), list = el("div", { class: "stack" }, CP.skeleton(3));
      function render() {
        chips.replaceChildren(...Object.entries(KINDS).map(([k, label]) => { const n = k === "all" ? rows.length : rows.filter((o) => o.kind === k).length;
          const b = el("button", { class: "chip", "aria-pressed": String(kind === k), "data-kind-filter": k }, `${label} (${n})`); b.addEventListener("click", () => { kind = k; render(); }); return b; }));
        const shown = rows.filter((o) => kind === "all" || o.kind === kind);
        list.replaceChildren(...(shown.length ? shown.map(card) : [el("div", { class: "card empty" }, el("p", {}, "No orders here yet."),
          el("div", { class: "chips", style: "justify-content:center;margin-top:12px" }, el("a", { class: "btn", href: "#/planner" }, "Plan a break"), el("a", { class: "btn", href: "#/canteen" }, "Order food"), el("a", { class: "btn", href: "#/print" }, "Send a print job")))]));
      }
      async function load() {
        try { const d = await CP.get("/orders"); if (!alive()) return; rows = d.orders; render(); CP.setBadge("orders", rows.filter((o) => o.progress < 1).length); }
        catch (e) { if (alive() && !rows) list.replaceChildren(CP.errorBox(e, load)); }
      }
      root.append(CP.head("My orders", "Everything you have ordered on campus. Status updates on its own.", CP.simBadge("Status simulated")), chips, el("div", { style: "height:16px" }), list);
      load(); CP.every(4000, load);
    },
  };
})(window.CP);
