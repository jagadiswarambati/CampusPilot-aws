"use strict";
/* Attendance: today's timetable with simulated check-in, per-subject percentages and a skip calculator. */
(function (CP) {
  const { el, icon } = CP;
  const STATE = { good: ["On track", "ok"], low: ["Low", "warn"], short: ["Shortage", "bad"] };

  function ring(pct, state) {
    const r = 60, c = 2 * Math.PI * r, color = state === "good" ? "#1a9a69" : state === "low" ? "#f0b429" : "#cf3f3a";
    return el("div", { class: "ring", role: "img", "aria-label": `Overall attendance ${pct} percent` },
      CP.svg("svg", { viewBox: "0 0 150 150", width: 150, height: 150 },
        CP.svg("circle", { cx: 75, cy: 75, r, fill: "none", stroke: "#e3e9f0", "stroke-width": 14 }),
        CP.svg("circle", { cx: 75, cy: 75, r, fill: "none", stroke: color, "stroke-width": 14, "stroke-linecap": "round", "stroke-dasharray": c, "stroke-dashoffset": c * (1 - Math.min(pct, 100) / 100) })),
      el("div", { class: "num" }, el("div", {}, el("b", {}, pct + "%"), el("small", { class: "muted" }, "overall"))));
  }

  function period(p, onCheckIn) {
    let right;
    if (p.marked) right = CP.pill("Checked in", "ok");
    else if (p.result === "attended") right = CP.pill("Attended", "ok");
    else if (p.can_check_in) {
      right = el("button", { class: "btn amber small", "data-period": p.id }, icon("check", 16), "Check in");
      right.addEventListener("click", () => onCheckIn(p, right));
    } else if (p.status === "ended") right = CP.pill("Missed", "bad");
    else right = el("button", { class: "btn small", disabled: true }, "Opens " + CP.hhmm(CP.toMin(p.start) - 10));
    const status = { ended: ["Ended", ""], ongoing: ["In session", "ok"], checkin: ["Check-in open", "info"], upcoming: ["Upcoming", ""] }[p.status];
    return el("div", { class: "period" + (p.status === "ongoing" ? " now" : "") },
      el("div", { class: "time" }, p.start, el("small", {}, "to " + p.end)),
      el("div", {}, el("strong", {}, p.subject), el("br"), el("span", { class: "muted" }, `${p.code} · ${p.room} `), status[1] ? CP.pill(status[0], status[1]) : null),
      el("div", {}, right));
  }

  function subject(s) {
    const [label, kind] = STATE[s.state];
    const msg = s.state === "good"
      ? (s.can_miss > 0 ? `You can miss ${s.can_miss} more class${s.can_miss > 1 ? "es" : ""} and stay above 75%.` : "Right at the limit. Don't skip the next one.")
      : `Attend the next ${s.need} class${s.need > 1 ? "es" : ""} in a row to reach 75%.`;
    return el("article", { class: "card ruled subject " + s.state },
      el("div", { class: "row" }, el("small", { class: "muted" }, s.code), CP.pill(label, kind)),
      el("h3", { class: "name" }, s.name),
      el("div", { class: "pct" }, s.pct + "%"),
      el("div", { class: "track" }, el("i", { style: `width:${s.pct}%` }), el("u", { style: "left:75%", title: "Target 75%" })),
      el("p", {}, msg),
      el("p", { class: "muted", style: "margin-top:6px;font-size:.92rem" }, `${s.attended} of ${s.held} classes attended. If you skip the next class: ${s.pct_if_skip}%.`));
  }

  CP.pages.attendance = {
    title: "Attendance",
    mount(root) {
      const alive = CP.guard();
      const body = el("div", { class: "stack" }, CP.skeleton(4));
      root.append(CP.head("Attendance", "Check in to class, and see exactly how many classes you can still miss.", CP.simBadge("Sample timetable")), body);

      async function checkIn(p, btn) {
        btn.disabled = true; btn.lastChild.textContent = "Verifying location…";
        await CP.sleep(900); // cosmetic: a real deployment would verify a QR code or the campus Wi-Fi here
        try {
          await CP.post("/attendance/checkin", { period_id: p.id });
          CP.toast(`Checked in to ${p.subject}.`, "ok");
        } catch (e) { CP.toast(e.message, "bad"); }
        load();
      }

      async function load() {
        try {
          const d = await CP.get("/attendance");
          if (!alive()) return;
          const low = d.subjects.filter((s) => s.state !== "good").length;
          const state = d.overall >= d.target ? "good" : d.overall >= d.target - 10 ? "low" : "short";
          body.replaceChildren(
            el("div", { class: "grid split" },
              el("section", { class: "card" }, el("div", { class: "card-head" }, el("h3", {}, "Today's classes"), CP.pill("Campus time " + d.clock, "info")),
                el("div", { class: "timeline" }, d.today.map((p) => period(p, checkIn)))),
              el("section", { class: "card", style: "display:flex;gap:20px;align-items:center;flex-wrap:wrap" }, ring(d.overall, state),
                el("div", {}, el("h3", {}, "Overall attendance"),
                  el("p", { class: "muted", style: "margin:6px 0" }, `Target is ${d.target}%.`),
                  low ? CP.pill(low > 1 ? `${low} subjects need attention` : "1 subject needs attention", "warn") : CP.pill("All subjects on track", "ok"),
                  el("p", { class: "muted", style: "margin-top:12px;font-size:.9rem" }, "Check-in is simulated: it opens 10 minutes before class and closes when class ends.")))),
            el("h2", { class: "h3" }, "Subjects"), el("div", { class: "grid g3" }, d.subjects.map(subject)));
        } catch (e) { if (alive()) body.replaceChildren(CP.errorBox(e, load)); }
      }
      load(); CP.every(15000, load); CP.onClock(load);
    },
  };
})(window.CP);
