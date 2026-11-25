"use strict";
/* Break Planner: natural-language request -> agent trace -> minute-by-minute route -> simulated order. */
(function (CP) {
  const { el, icon } = CP;
  const PARSERS = { rules: "built-in rules", bedrock: "Amazon Bedrock" };
  const KIND_LABEL = { walk: "Walking", print: "Printing", wait: "Waiting for food", buffer: "Safety buffer", slack: "Spare time", over: "Class starts at the dark line" };

  function breakBar(plan, minutes) {
    const used = plan.total_min + plan.buffer_min, scale = Math.max(minutes, used), pct = (m) => (m / scale) * 100;
    const seg = (kind, mins, title) => el("div", { class: "seg " + kind, style: `width:${pct(mins)}%`, title: `${title} (${mins} min)` }, pct(mins) >= 6 ? String(mins) : null);
    const bar = el("div", { class: "bar", role: "img", "aria-label": `${plan.total_min} minutes of tasks plus a ${plan.buffer_min} minute buffer, out of ${minutes} minutes available` });
    plan.steps.filter((s) => s.end > s.start).forEach((s) => bar.append(seg(s.kind, s.end - s.start, s.label)));
    bar.append(seg("buffer", plan.buffer_min, "Safety buffer"));
    if (minutes > used) bar.append(seg("slack", minutes - used, "Spare time"));
    if (used > minutes) bar.append(el("div", { class: "deadline", style: `left:${pct(minutes)}%`, title: "Class starts" }));
    const kinds = ["walk", "print", "wait", "buffer", minutes > used ? "slack" : "over"];
    return [bar, el("div", { class: "bar-legend" }, kinds.map((k) => el("span", {}, el("i", { class: "seg " + k }), KIND_LABEL[k])))];
  }

  function routeList(plan) {
    return el("ol", { class: "steps" }, plan.steps.map((s) => el("li", {}, el("time", {}, s.end > s.start ? `${s.start}–${s.end} min` : `${s.start} min`), el("span", { class: "stn " + s.kind }),
      el("div", {}, s.label, " ", el("span", { class: "where" }, s.end > s.start && s.kind !== "walk" ? "at " + s.where : "")))));
  }

  function planCard(plan, compact) {
    const card = el("article", { class: "card plan" + (plan.feasible ? "" : " nofit") });
    card.append(el("h3", {}, plan.label),
      el("p", { class: "muted", style: "margin-top:4px" }, [plan.shop && plan.shop.name, plan.item && plan.item.name].filter(Boolean).join(" with ") + `, ${plan.total_min} min of tasks`),
      compact ? el("details", { class: "route" }, el("summary", {}, "Show the route"), routeList(plan)) : routeList(plan));
    const foot = el("div", { class: "row" }, el("strong", { class: "h3" }, CP.inr(plan.cost.total)));
    if (plan.feasible) {
      const btn = el("button", { class: "btn primary" }, "Place simulated orders");
      const msg = el("span", { class: "err", role: "alert" });
      btn.addEventListener("click", async () => {
        btn.disabled = true; msg.textContent = "";
        try {
          const o = await CP.post("/orders", { plan_id: plan.id });
          btn.replaceWith(el("span", { class: "done" }, "Ordered: " + o.tokens.join(" and ") + " "), el("a", { href: "#/orders" }, "Track in My orders"));
          CP.toast("Orders placed. Track them in My orders.", "ok"); if (CP.refreshBadge) CP.refreshBadge();
        } catch (e) {
          msg.textContent = e.message;
          if (e.status === 409 && /already confirmed/.test(e.message)) btn.textContent = "Already ordered"; else btn.disabled = false;
        }
      });
      foot.append(el("div", { class: "actions" }, msg, btn));
    } else foot.append(el("span", { class: "err" }, "Doesn't fit, so it can't be ordered"));
    card.append(foot);
    return card;
  }

  CP.pages.planner = {
    title: "Break Planner",
    mount(root) {
      const alive = CP.guard();
      const ask = el("textarea", { id: "ask", maxlength: 500, "aria-label": "Describe your break", placeholder: "I have 40 minutes before class. I need a vegetarian lunch and 25 pages printed." });
      if (CP.state && CP.state.prefill) { ask.value = CP.state.prefill; CP.state = null; }
      const go = el("button", { class: "btn amber", id: "go" }, icon("zap", 18), "Plan my break");
      const trace = el("ol", { class: "trace" });
      const dot = el("span", { class: "pulse-dot done" });
      const agentNote = el("p", { class: "muted", style: "margin-top:10px" }, "Describe your break and I will show my work here as I plan it.");
      const out = el("div", { id: "result", class: "stack", "aria-live": "polite", tabindex: "-1" });

      const idle = () => { trace.replaceChildren(); agentNote.hidden = false; dot.className = "pulse-dot done"; };
      const stepNode = (s, wait) => el("li", {}, el("span", { class: "tick" + (wait ? " wait" : "") }, wait ? null : icon("tick", 15)), el("div", {}, el("strong", {}, s.label), s.detail ? el("span", {}, s.detail) : null));

      async function run() {
        const text = ask.value.trim();
        if (!text) { ask.focus(); return; }
        go.disabled = true; go.lastChild.textContent = "Planning…"; out.replaceChildren(); agentNote.hidden = true; dot.className = "pulse-dot";
        trace.replaceChildren(stepNode({ label: "Reading your request" }, true));
        try {
          const res = await CP.post("/plan", { text });
          if (!alive()) return;
          trace.replaceChildren();
          for (const s of res.trace) { trace.append(stepNode(s)); await CP.sleep(420); if (!alive()) return; }
          dot.className = "pulse-dot done";
          render(res);
        } catch (e) { if (!alive()) return; idle(); out.replaceChildren(el("div", { class: "card error-card", role: "alert" }, icon("alert", 22), el("div", {}, el("strong", {}, "Couldn't plan that"), el("p", {}, e.message)))); }
        finally { go.disabled = false; go.lastChild.textContent = "Plan my break"; }
      }

      function render(res) {
        const minutes = res.request.minutes, r = res.request;
        out.replaceChildren();
        if (!res.best) { out.append(el("div", { class: "card err" }, res.reason)); return; }
        const read = [`${minutes} min`, r.pages ? `${r.pages} pages${r.color ? " colour" : ""}` : null, r.food ? (r.veg ? "vegetarian food" : "food") : null, r.budget ? `budget ${CP.inr(r.budget)}` : null].filter(Boolean);
        out.append(el("section", { class: "card" },
          el("div", { class: "verdict " + (res.feasible ? "ok" : "bad") }, el("span", { class: "big" }, res.feasible ? `Fits, with ${res.best.slack_min} min to spare` : "Won't fit in your break")),
          el("p", { class: "muted", style: "margin-top:10px" }, "Request: " + read.join(" · ") + ". Understood with " + (PARSERS[r.parser] || r.parser) + "."),
          res.reason ? el("p", { class: "sub" }, res.reason) : null, ...breakBar(res.best, minutes)), planCard(res.best));
        if (res.alternatives.length) out.append(el("h2", { class: "h3", style: "margin-top:8px" }, res.feasible ? "Other options" : "What would fit"), ...res.alternatives.map((p) => planCard(p, true)));
        else if (!res.feasible) out.append(el("p", { class: "muted" }, "Nothing fits in this time. Try fewer pages, a quicker dish, or a longer break."));
        out.focus({ preventScroll: true });
        if (out.scrollIntoView) out.scrollIntoView({ behavior: "smooth", block: "start" });
      }

      go.addEventListener("click", run);
      ask.addEventListener("keydown", (e) => { if (e.key === "Enter" && (e.ctrlKey || e.metaKey)) run(); });
      root.append(
        CP.head("Break Planner", "Tell the agent how long you have. It plans printing, food and walking minute by minute, and says honestly whether it fits.", CP.simBadge("Live campus queues")),
        el("div", { class: "planner-grid" },
          el("section", { class: "card pg-input" },
            el("div", { class: "field" }, el("label", { for: "ask" }, "What do you need to do?"), ask),
            el("div", { class: "row", style: "margin-top:14px" }, el("span", { class: "muted" }, "Tip: Ctrl+Enter plans too"), go),
            el("div", { class: "examples" }, CP.EXAMPLES.map((t) => el("button", { onclick: () => { ask.value = t; ask.focus(); } }, t)))),
          el("section", { class: "card pg-agent" }, el("h3", { class: "row", style: "justify-content:flex-start;gap:10px" }, dot, "Planning agent", el("span", { class: "agent-tag" }, "LIVE")), agentNote, trace),
          out));
    },
  };
})(window.CP);
