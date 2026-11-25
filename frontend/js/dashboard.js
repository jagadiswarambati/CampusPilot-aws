"use strict";
/* Dashboard: "next up" departure board, 60-second tour, live stats, crowd heat strip and agent insights.
   Everything comes from one /dashboard call. */
(function (CP) {
  const { el, icon } = CP;
  const greeting = () => { const h = CP.clock.minutes() / 60; return h < 12 ? "Good morning" : h < 17 ? "Good afternoon" : "Good evening"; };
  const COLOR = { attendance: "--c-attendance", library: "--c-library", print: "--c-print", canteen: "--c-canteen", plan: "--c-planner" };

  function board(d) {
    const rows = d.board.length ? d.board.map((r) => el("a", { class: "board-row", href: "#/" + r.page },
      el("span", { class: "time" }, r.time), el("span", {}, el("b", {}, r.title), el("small", {}, r.detail)), el("span", { class: "tag " + r.tone }, r.status)))
      : [el("div", { class: "board-empty" }, "Nothing scheduled right now. Plan a break or book a library seat.")];
    return el("section", { class: "board", "aria-label": "Next up" },
      el("div", { class: "board-head" }, el("h2", {}, "Next up"), el("span", { class: "at" }, el("small", {}, "Campus time"), d.clock)), ...rows,
      el("div", { class: "board-foot" }, el("span", {}, "Book a seat or place an order and it shows up here with its time."), el("a", { class: "tag", href: "#/library" }, "Book seat"), el("a", { class: "tag", href: "#/canteen" }, "Order food")));
  }

  function tour() {
    const steps = [["planner", "Plan a break with the AI agent"], ["library", "Book a library seat"], ["canteen", "Order from the canteen"], ["orders", "Track your orders"]];
    return el("section", { class: "tour" }, el("div", {}, el("h2", {}, "Try CampusPilot in 60 seconds"),
      el("p", {}, "Four steps cover the whole app. Use the clock at the top to jump to the lunch rush.")),
      el("ol", {}, steps.map(([id, t]) => el("li", {}, el("a", { href: "#/" + id }, t)))));
  }

  function stat({ id, label, big, cap, extra }) {
    return el("a", { class: "card ruled stat", href: "#/" + id, style: `--c: var(${COLOR[id]})` }, el("span", { class: "label" }, label), el("span", { class: "big" }, big), extra, el("span", { class: "cap" }, cap));
  }

  function heat(p, nowMin) {
    const nowIdx = Math.max(0, Math.min(p.hours.length - 1, Math.floor(nowMin / 60) - p.hours[0]));
    const g = el("div", { class: "heat", role: "img", "aria-label": "Expected crowd level for each hour of the day, for print shops, canteen and library" }, el("span"),
      ...p.hours.map((h, i) => el("span", { class: "hr" + (i % 2 ? " alt" : "") }, h)));
    [["print", "Print", "--c-print"], ["canteen", "Canteen", "--c-canteen"], ["library", "Library", "--c-library"]].forEach(([k, label, color]) => {
      g.append(el("span", { class: "lab" }, label), ...p[k].map((v, i) => el("span", { class: "cell" + (i === nowIdx ? " now" : ""), style: `--hc: var(${color}); --v: ${(0.14 + 0.86 * v).toFixed(2)}`,
        title: `${label} at ${p.hours[i]}:00: ${v < 0.35 ? "quiet" : v < 0.65 ? "busy" : "packed"}` })));
    });
    return g;
  }

  function render(root, d) {
    const att = d.attendance, lib = d.library, pr = d.print, ca = d.canteen;
    root.replaceChildren(
      CP.head(greeting() + ", Guest student", "Here is your campus right now: what is next, what is busy, and where to go.", CP.simBadge()),
      el("div", { class: "dash-top" }, board(d), tour()),
      el("div", { class: "stats" },
        stat({ id: "attendance", label: "Attendance", big: att.overall + "%", extra: el("div", { class: "track" }, el("i", { style: `width:${att.overall}%` }), el("u", { style: `left:${att.target}%`, title: `Target ${att.target}%` })),
          cap: `Lowest: ${att.lowest.name} at ${att.lowest.pct}%` }),
        stat({ id: "library", label: "Seats free", big: lib.slot.free, extra: CP.meter(1 - lib.slot.free / lib.slot.total, CP.levelKind(lib.slot.rush)),
          cap: lib.mine.length ? `You hold ${lib.mine.length} booking${lib.mine.length > 1 ? "s" : ""} today` : `Slot ${lib.slot.label}. No seat booked yet` }),
        stat({ id: "print", label: "Print wait", big: pr.best.wait_min + " min", extra: CP.meter(Math.min(1, pr.best.wait_min / 12), pr.best.wait_min > 7 ? "bad" : pr.best.wait_min > 3 ? "warn" : "ok"),
          cap: `${pr.best.name}, ${pr.best.people} waiting` }),
        stat({ id: "canteen", label: "Canteen rush", big: ca.label, extra: CP.meter(ca.rush, CP.levelKind(ca.label)), cap: "Kitchen load right now" })),
      el("div", { class: "grid split" },
        el("section", { class: "card" }, el("div", { class: "card-head" }, el("h3", {}, "Crowd levels today"), CP.simBadge("Simulated")),
          heat(d.pulse, CP.clock.minutes()),
          el("div", { class: "heat-legend" }, "Quiet", ...[0.14, 0.35, 0.57, 0.78, 1].map((o) => el("i", { style: `opacity:${o}` })), "Packed", el("span", { style: "margin-left:auto" }, "Outlined column is now"))),
        el("section", { class: "card" }, el("div", { class: "card-head" }, el("h3", {}, "Agent insights")),
          el("div", {}, d.insights.map((i) => el("a", { class: "insight", href: "#/" + i.page, style: `--k: var(${COLOR[i.kind]})` }, el("i"), el("span", {}, el("b", {}, i.title), i.text), icon("arrow", 18)))))));
    CP.setBadge("orders", d.orders.active);
  }

  CP.pages.dashboard = {
    title: "Dashboard",
    mount(root) {
      const alive = CP.guard();
      root.append(CP.skeleton(4));
      const load = async () => {
        try { const d = await CP.get("/dashboard"); if (alive()) render(root, d); }
        catch (e) { if (alive() && !root.querySelector(".board")) root.replaceChildren(CP.errorBox(e, load)); }
      };
      load(); CP.every(15000, load); CP.onClock(load);
    },
  };
})(window.CP);
