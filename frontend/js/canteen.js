"use strict";
/* Canteen: live kitchen rush, filterable menu, cart and ordering with a pickup token. */
(function (CP) {
  const { el, icon } = CP;

  CP.pages.canteen = {
    title: "Canteen",
    mount(root) {
      const alive = CP.guard();
      const cart = new Map();
      const f = { cat: "All", veg: false, q: "" };
      let menu = [], meta = null, rid = CP.uuid(), placing = false;
      const rushBox = el("section", { class: "card" }), filterBox = el("div", { class: "stack" }), gridBox = el("div", { class: "menu" }),
        cartBox = el("section", { class: "card sticky cart", id: "cart" }), bar = el("div", { class: "cart-bar" });
      const find = (id) => menu.find((m) => m.id === id);
      const qty = () => [...cart.values()].reduce((a, b) => a + b, 0);
      const total = () => [...cart].reduce((a, [id, n]) => a + (find(id) ? find(id).price * n : 0), 0);
      const eta = () => { const ids = [...cart.keys()].filter(find); return ids.length ? Math.max(...ids.map((i) => find(i).prep_min)) + Math.ceil(qty() / 4) : 0; };
      const change = (id, d) => { const n = (cart.get(id) || 0) + d; n <= 0 ? cart.delete(id) : cart.set(id, Math.min(10, n)); renderGrid(); renderCart(); };

      function renderRush() {
        rushBox.replaceChildren(el("div", { class: "row" }, el("div", {}, el("h3", {}, "Kitchen right now"), el("p", { class: "muted" }, `About ${meta.queue} orders ahead of you`)),
          CP.pill(meta.rush_label, CP.levelKind(meta.rush_label))),
          el("div", { style: "margin-top:12px" }, CP.meter(meta.rush, CP.levelKind(meta.rush_label))));
      }
      function renderFilters() {
        const cats = ["All", ...meta.categories];
        const search = el("input", { type: "search", placeholder: "Search the menu", "aria-label": "Search the menu", value: f.q, id: "menu-search" });
        search.addEventListener("input", () => { f.q = search.value; renderGrid(); });
        const veg = el("input", { type: "checkbox", id: "veg-only" }); veg.checked = f.veg; veg.addEventListener("change", () => { f.veg = veg.checked; renderGrid(); });
        filterBox.replaceChildren(el("div", { class: "row" }, el("div", { class: "chips" }, cats.map((c) => { const b = el("button", { class: "chip", "aria-pressed": String(f.cat === c), "data-cat": c }, c); b.addEventListener("click", () => { f.cat = c; renderFilters(); renderGrid(); }); return b; })),
          el("label", { class: "switch" }, veg, "Veg only")), search);
      }
      function dishCard(m) {
        const n = cart.get(m.id) || 0;
        const act = !m.available ? CP.pill("Sold out", "bad") : n ? stepper(m.id, n) : el("button", { class: "btn small", "data-add": m.id }, icon("plus", 16), "Add");
        if (m.available && !n) act.addEventListener("click", () => change(m.id, 1));
        return el("article", { class: "card dish" + (m.available ? "" : " out"), "data-dish": m.id },
          el("div", { class: "row" }, el("span", { class: "vegmark" + (m.veg ? "" : " non"), title: m.veg ? "Vegetarian" : "Non-vegetarian" }), m.popular ? CP.pill("Popular", "warn") : null),
          el("h4", {}, m.name), el("div", { class: "meta" }, el("span", {}, `About ${m.prep_min} min`), el("strong", {}, CP.inr(m.price))), act);
      }
      function renderGrid() {
        const items = menu.filter((m) => (f.cat === "All" || m.category === f.cat) && (!f.veg || m.veg) && m.name.toLowerCase().includes(f.q.trim().toLowerCase()));
        const groups = meta.categories.map((c) => [c, items.filter((m) => m.category === c).sort((a, b) => (b.popular - a.popular) || a.name.localeCompare(b.name))]).filter(([, list]) => list.length);
        gridBox.replaceChildren(...(groups.length ? groups.flatMap(([c, list]) => [el("h3", { class: "cat" }, c), el("div", { class: "menu-grid" }, list.map(dishCard))]) : [el("p", { class: "empty" }, "Nothing matches your filters.")]));
      }
      function stepper(id, n) {
        const minus = el("button", { "aria-label": "Remove one" }, icon("minus", 16)), plus = el("button", { "aria-label": "Add one" }, icon("plus", 16));
        minus.addEventListener("click", () => change(id, -1)); plus.addEventListener("click", () => change(id, 1));
        return el("div", { class: "stepper" }, minus, el("span", {}, n), plus);
      }
      function renderCart() {
        const lines = [...cart].filter(([id]) => find(id));
        cartBox.replaceChildren(el("div", { class: "card-head" }, el("h3", {}, "Your order"), lines.length ? el("button", { class: "btn small", id: "clear-cart", onclick: () => { cart.clear(); renderGrid(); renderCart(); } }, "Clear") : null),
          ...(lines.length ? [el("div", {}, lines.map(([id, n]) => el("div", { class: "cart-line" }, el("span", {}, el("strong", {}, find(id).name), el("br"), el("small", { class: "muted" }, CP.inr(find(id).price) + " each")), stepper(id, n)))),
            el("div", { class: "total" }, el("span", {}, "Total"), el("span", {}, CP.inr(total()))),
            el("p", { class: "muted", style: "margin:8px 0 14px" }, `Ready in about ${eta()} min`),
            el("button", { class: "btn amber", id: "place-order", style: "width:100%", disabled: placing, onclick: place }, placing ? "Placing…" : "Place order")]
            : [el("p", { class: "muted" }, "Your cart is empty. Add something tasty.")]));
        bar.replaceChildren(el("span", {}, el("strong", {}, `${qty()} item${qty() === 1 ? "" : "s"}`), " · " + CP.inr(total())), el("button", { class: "btn amber small", onclick: () => cartBox.scrollIntoView({ behavior: "smooth" }) }, "View cart"));
        bar.classList.toggle("show", qty() > 0);
      }
      async function place() {
        if (placing || !cart.size) return;
        placing = true; renderCart();
        try {
          const o = await CP.post("/canteen/orders", { request_id: rid, items: [...cart].map(([id, qty]) => ({ id, qty })) });
          rid = CP.uuid(); cart.clear(); placing = false; renderGrid();
          cartBox.replaceChildren(el("h3", {}, "Order placed"), el("p", { class: "muted", style: "margin-top:6px" }, "Show this token at the counter"), el("div", { class: "ticket" }, el("div", { class: "token", id: "order-token" }, o.tokens[0])),
            el("p", { style: "margin:8px 0 14px" }, `Ready in about ${o.eta_min} min · ${CP.inr(o.total_cost)}`), el("a", { class: "btn", href: "#/orders" }, "Track in My orders"),
            el("button", { class: "btn", style: "margin-left:8px", onclick: renderCart }, "New order"));
          bar.classList.remove("show"); CP.toast("Order placed. Token " + o.tokens[0], "ok"); if (CP.refreshBadge) CP.refreshBadge();
        } catch (e) { placing = false; CP.toast(e.message, "bad"); renderCart(); }
      }
      async function load() {
        try {
          const d = await CP.get("/canteen");
          if (!alive()) return;
          const first = !meta; meta = d; menu = d.menu;
          renderRush(); if (first) renderFilters(); renderGrid(); if (!placing && !cartBox.querySelector("#order-token")) renderCart();
        } catch (e) { if (alive() && !meta) root.replaceChildren(CP.head("Canteen"), CP.errorBox(e, () => { root.replaceChildren(); CP.pages.canteen.mount(root); })); }
      }
      root.append(CP.head("Canteen", "Order ahead, skip the queue, collect with your token.", CP.simBadge("Sample menu")), rushBox, el("div", { style: "height:18px" }),
        el("div", { class: "grid split" }, el("div", { class: "stack" }, filterBox, gridBox), cartBox), bar);
      gridBox.append(CP.skeleton(3)); load(); CP.every(10000, load); CP.onClock(load);
    },
  };
})(window.CP);
