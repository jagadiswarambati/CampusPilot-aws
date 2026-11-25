"use strict";
/* Print shops: live rush per shop, the print agent's reasoning, and a working "send a print job" form. */
(function (CP) {
  const { el, icon } = CP;

  CP.pages.print = {
    title: "Print shops",
    mount(root) {
      const alive = CP.guard();
      const form = { shop: null, pages: 20, color: false, rid: CP.uuid(), busy: false };
      let data = null;
      const bannerBox = el("div"), shopsBox = el("div", { class: "grid g2" }), logBox = el("section", { class: "card" }),
        mineBox = el("section", { class: "card" }), formBox = el("section", { class: "card" }), resultBox = el("div");

      const shopById = (id) => data.shops.find((s) => s.id === id);
      const estimate = () => { const s = shopById(form.shop); const print = Math.ceil(form.pages / s.ppm); return { wait: s.queue_min, print, total: s.queue_min + print, cost: form.pages * (form.color ? s.price_color : s.price_bw) }; };

      function renderBanner() {
        const a = data.agent, best = shopById(a.best_shop);
        bannerBox.replaceChildren(el("section", { class: "card banner" },
          el("div", {}, el("div", { class: "row", style: "justify-content:flex-start;gap:10px" }, el("span", { class: "pulse-dot" }), el("strong", {}, "Print agent is working")),
            el("p", { style: "margin-top:6px" }, a.text)),
          el("button", { class: "btn amber", id: "use-best" }, "Use " + best.name.split(" ").slice(0, 2).join(" "))));
        bannerBox.querySelector("#use-best").addEventListener("click", () => { form.shop = a.best_shop; renderForm(); formBox.scrollIntoView && formBox.scrollIntoView({ behavior: "smooth", block: "center" }); });
      }
      function renderShops() {
        const nowIdx = Math.max(0, Math.min(11, Math.floor(CP.clock.minutes() / 60) - 8));
        shopsBox.replaceChildren(...data.shops.map((s) => el("section", { class: "card ruled shop", "data-shop": s.id },
          el("h3", {}, el("span", {}, s.name), CP.pill(s.rush_label, CP.levelKind(s.rush_label))),
          el("p", { class: "muted" }, `${s.location} · ${s.walk_min} min walk from class`),
          el("div", { class: "kpis" }, el("div", {}, el("b", {}, s.queue_people), el("small", {}, "waiting")), el("div", {}, el("b", {}, s.queue_min + " min"), el("small", {}, "queue wait")), el("div", {}, el("b", {}, s.ppm), el("small", {}, "pages/min"))),
          CP.meter(s.rush, CP.levelKind(s.rush_label)),
          el("p", { class: "muted", style: "margin-top:10px;font-size:.9rem" }, `B&W ${CP.inr(s.price_bw)}/page · Colour ${CP.inr(s.price_color)}/page`),
          el("div", { style: "margin-top:14px" }, el("strong", {}, "Expected queue today"),
            el("div", { class: "bars", role: "img", "aria-label": "Expected people waiting by hour" }, s.people_forecast.map((v, i) => el("i", { class: i === nowIdx ? "now" : "", style: `height:${Math.max(5, (v / s.capacity) * 100)}%`, title: `${8 + i}:00 · about ${v} waiting` }))),
            el("div", { class: "bars-axis" }, el("span", {}, "8:00"), el("span", {}, "14:00"), el("span", {}, "19:00"))),
          el("div", { style: "margin-top:14px" }, el("strong", {}, "Live queue"),
            s.jobs.length ? el("div", { style: "margin-top:8px" }, s.jobs.slice(0, 4).map((j) => el("div", { class: "job" }, el("strong", {}, j.id), el("span", { class: "muted" }, `${j.pages} pages${j.color ? ", colour" : ""}`), CP.pill(j.state, j.state === "Printing" ? "info" : ""))), s.queue_people > 4 ? el("div", { class: "more" }, `+ ${s.queue_people - 4} more in the queue`) : null) : el("p", { class: "muted", style: "margin-top:6px" }, "No one waiting. Walk right in.")))));
      }
      function renderLog() {
        logBox.replaceChildren(el("div", { class: "card-head" }, el("h3", {}, "Agent activity"), CP.simBadge("Simulated activity")),
          el("ul", { class: "log" }, data.agent.events.map((e) => el("li", {}, el("time", {}, e.time), el("span", {}, e.text)))));
      }
      function renderMine() {
        mineBox.replaceChildren(el("h3", {}, "My print jobs"), data.mine.length
          ? el("div", { class: "list", style: "margin-top:12px" }, data.mine.map((o) => el("div", {}, el("div", { class: "row" }, el("strong", {}, o.tokens[0]), CP.pill(o.status, o.stage === 2 ? "ok" : "info")),
            el("p", { class: "muted", style: "font-size:.92rem" }, o.title), CP.meter(o.progress, o.stage === 2 ? "ok" : ""))))
          : el("p", { class: "muted", style: "margin-top:6px" }, "No print jobs yet."));
      }
      function renderForm() {
        const pagesIn = el("input", { type: "number", min: 1, max: 200, value: form.pages, "aria-label": "Number of pages", id: "pages" });
        pagesIn.addEventListener("input", () => { form.pages = Math.max(1, Math.min(200, parseInt(pagesIn.value, 10) || 1)); renderEstimate(); });
        const color = el("input", { type: "checkbox", id: "color" }); color.checked = form.color;
        color.addEventListener("change", () => { form.color = color.checked; renderEstimate(); });
        const send = el("button", { class: "btn primary", id: "send-job", style: "width:100%" }, icon("printer", 18), "Send to shop");
        send.addEventListener("click", submit);
        const est = el("div", { id: "estimate", class: "ticket", style: "margin:16px 0;border-style:solid;border-width:1.5px" });
        function renderEstimate() {
          const x = estimate(), sh = shopById(form.shop);
          est.replaceChildren(el("div", { class: "row" }, el("span", { class: "muted" }, "Ready in about"), el("strong", { style: "font-size:1.3rem" }, x.total + " min")),
            el("div", { class: "row" }, el("span", { class: "muted" }, `${x.wait} min queue + ${x.print} min printing`), el("strong", {}, CP.inr(x.cost))));
          send.lastChild.textContent = "Send to " + sh.name.split(" ")[0];
        }
        formBox.replaceChildren(el("h3", {}, "Send a print job"),
          el("div", { class: "field", style: "margin-top:12px" }, el("label", {}, "Print shop"), el("div", { class: "chips" }, data.shops.map((x) => {
            const b = el("button", { class: "chip", "aria-pressed": String(x.id === form.shop), "data-pick": x.id }, x.name.split(" ").slice(0, 2).join(" "));
            b.addEventListener("click", () => { form.shop = x.id; renderForm(); }); return b; }))),
          el("div", { class: "field", style: "margin-top:14px" }, el("label", { for: "pages" }, "Pages"), pagesIn,
            el("div", { class: "chips", style: "margin-top:8px" }, [10, 25, 50, 100].map((n) => { const b = el("button", { class: "chip" }, String(n)); b.addEventListener("click", () => { form.pages = n; pagesIn.value = n; renderEstimate(); }); return b; }))),
          el("label", { class: "switch", style: "margin-top:14px" }, color, "Colour print"), est, send, resultBox);
        renderEstimate();
      }
      async function submit() {
        if (form.busy) return;
        form.busy = true; const btn = formBox.querySelector("#send-job"); btn.disabled = true;
        try {
          const o = await CP.post("/print/jobs", { shop_id: form.shop, pages: form.pages, color: form.color, request_id: form.rid });
          form.rid = CP.uuid();
          resultBox.replaceChildren(el("div", { class: "ticket", style: "margin-top:16px" },
            el("div", { class: "muted" }, "Job sent. Show this token at the counter"), el("div", { class: "token" }, o.tokens[0]), el("div", { style: "margin-top:6px" }, `Ready in about ${o.eta_min} min · ${CP.inr(o.total_cost)} · `, el("a", { href: "#/orders" }, "Track in My orders"))));
          CP.toast("Print job sent.", "ok"); if (CP.refreshBadge) CP.refreshBadge(); load();
        } catch (e) { CP.toast(e.message, "bad"); }
        form.busy = false; btn.disabled = false;
      }

      async function load() {
        try {
          const d = await CP.get("/print");
          if (!alive()) return;
          const first = !data; data = d;
          if (first) { form.shop = d.agent.best_shop; renderForm(); } else { renderEstimateSafe(); }
          renderBanner(); renderShops(); renderLog(); renderMine();
        } catch (e) { if (alive() && !data) root.replaceChildren(CP.head("Print shops"), CP.errorBox(e, () => { root.replaceChildren(); CP.pages.print.mount(root); })); }
      }
      function renderEstimateSafe() { const est = formBox.querySelector("#estimate"); if (est && data) { const x = estimate(); est.replaceChildren(el("div", { class: "row" }, el("span", { class: "muted" }, "Ready in about"), el("strong", { style: "font-size:1.3rem" }, x.total + " min")), el("div", { class: "row" }, el("span", { class: "muted" }, `${x.wait} min queue + ${x.print} min printing`), el("strong", {}, CP.inr(x.cost)))); } }

      root.append(CP.head("Print shops", "Live queues at every print shop, and an agent that tells you where to go.", CP.simBadge()), bannerBox, el("div", { style: "height:18px" }), shopsBox,
        el("div", { class: "grid split", style: "margin-top:18px" }, logBox, el("div", { class: "stack" }, formBox, mineBox)));
      logBox.append(CP.skeleton(2));
      load(); CP.every(10000, load); CP.onClock(load);
    },
  };
})(window.CP);
