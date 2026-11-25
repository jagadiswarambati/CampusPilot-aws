"use strict";
/* Library: BookMyShow-style seat picker. Seats held by "other students" are simulated; your bookings are real
   (stored in DynamoDB with an atomic conditional transaction, so two people can never get the same seat). */
(function (CP) {
  const { el, icon } = CP;

  function qr(seed) {  // decorative pass code derived from the seat id (not a real QR code)
    let h = 2166136261;
    for (const ch of seed) h = Math.imul(h ^ ch.charCodeAt(0), 16777619);
    const N = 11, cells = [];
    for (let y = 0; y < N; y++) for (let x = 0; x < N; x++) {
      const finder = (x < 3 && y < 3) || (x > N - 4 && y < 3) || (x < 3 && y > N - 4);
      h = Math.imul(h ^ (y * N + x), 2654435761);
      if (finder || ((h >>> 28) & 1)) cells.push(CP.svg("rect", { x, y, width: 1, height: 1, fill: "#0f1c2e" }));
    }
    return CP.svg("svg", { class: "qr", viewBox: `0 0 ${N} ${N}`, role: "img", "aria-label": "Pass code" }, ...cells);
  }

  CP.pages.library = {
    title: "Library seats",
    mount(root) {
      const alive = CP.guard();
      const st = { data: null, slot: null, zone: "hall", sel: null, busy: false };
      const slotsBox = el("div", { class: "slots", role: "group", "aria-label": "Time slots" });
      const tabsBox = el("div", { class: "zones", role: "tablist" });
      const mapBox = el("div", { class: "seatmap" });
      const sideBox = el("div", { class: "stack" });
      const bookBar = el("div", { class: "cart-bar" });  // phones: booking without scrolling past the map
      const zoneOf = (id) => st.data.zones.find((z) => z.id === id.split("-")[0]);
      const seatLabel = (id) => `${zoneOf(id).name}, seat ${id.split("-")[1]}`;

      function renderSlots() {
        slotsBox.replaceChildren(...st.data.slots.map((s) => {
          const b = el("button", { class: "slot", "aria-pressed": String(s.index === st.slot), disabled: s.ended, "data-slot": s.index },
            el("strong", {}, s.label), el("small", {}, s.ended ? "Ended" : `${s.free} of ${s.total} free`),
            CP.meter(1 - s.free / s.total, s.ended ? "" : CP.levelKind(s.rush)), s.current ? CP.pill("Now", "info") : null);
          b.addEventListener("click", () => { st.slot = s.index; st.sel = null; load(); });
          return b;
        }));
      }
      function renderTabs() {
        tabsBox.replaceChildren(...st.data.zones.map((z) => {
          const t = el("button", { class: "tab", role: "tab", "aria-selected": String(z.id === st.zone), "data-zone": z.id }, el("b", {}, z.name), el("small", {}, `${z.free} free`));
          t.addEventListener("click", () => { st.zone = z.id; renderTabs(); renderMap(); });
          return t;
        }));
      }
      function renderMap() {
        const z = st.data.zones.find((x) => x.id === st.zone);
        const rows = z.rows.map((r) => {
          const cells = [];
          z.seats.filter((s) => s.id.split("-")[1][0] === r).forEach((s) => {
            const n = +s.id.split("-")[1].slice(1);
            const status = st.sel === s.id ? "sel" : s.status;
            const b = el("button", { class: `seat ${status}`, "data-seat": s.id, "aria-label": `Seat ${s.id.split("-")[1]}, ${s.status === "mine" ? "yours" : s.status}`,
              "aria-pressed": st.sel === s.id ? "true" : null, disabled: s.status === "taken" }, n);
            b.addEventListener("click", () => { if (s.status !== "free") return; st.sel = st.sel === s.id ? null : s.id; renderMap(); renderSide(); });
            cells.push(b);
            if (n === z.aisle) cells.push(el("span", { class: "aisle", "aria-hidden": "true" }));
          });
          // fluid columns: the seat map always fits the width, with a walkway after the aisle seat
          return el("div", { class: "seat-row", style: `grid-template-columns: 22px repeat(${z.aisle}, minmax(0, 1fr)) 18px repeat(${z.cols - z.aisle}, minmax(0, 1fr))` }, el("span", { class: "row-label" }, r), cells);
        });
        mapBox.replaceChildren(el("div", { class: "seat-rows" }, rows));
      }
      async function book() {
        if (!st.sel || st.busy) return;
        st.busy = true; renderSide();
        try {
          const r = await CP.post("/library/book", { slot: st.slot, seat: st.sel });
          CP.toast(`Seat booked for ${r.label}.`, "ok"); st.sel = null;
        } catch (e) { CP.toast(e.message, "bad"); st.sel = null; }
        st.busy = false; load();
      }
      async function cancel(slot) {
        try { await CP.post("/library/cancel", { slot }); CP.toast("Booking cancelled.", "ok"); }
        catch (e) { CP.toast(e.message, "bad"); }
        load();
      }
      function renderSide() {
        const d = st.data, slot = d.slots[st.slot];
        const pick = el("section", { class: "card" }, el("h3", {}, "Your selection"),
          el("p", { class: "muted", style: "margin:4px 0 12px" }, `${slot.label} · ${slot.free} seats free`),
          st.sel ? el("div", {}, el("div", { class: "seatno", style: "font-size:1.5rem;font-weight:700" }, seatLabel(st.sel)),
            el("button", { class: "btn amber", id: "book", style: "width:100%;margin-top:14px", disabled: st.busy }, st.busy ? "Booking…" : "Book this seat"))
            : el("p", { class: "muted" }, "Pick a seat on the map. One seat per time slot."));
        const book_ = pick.querySelector("#book"); if (book_) book_.addEventListener("click", book);
        const mine = el("section", { class: "card" }, el("h3", {}, "Your passes today"),
          d.mine.length ? el("div", { class: "stack", style: "margin-top:12px" }, d.mine.map((m) => {
            const c = el("button", { class: "btn small danger", "data-cancel": m.slot }, "Cancel");
            c.addEventListener("click", () => cancel(m.slot));
            return el("div", { class: "pass" }, el("div", { class: "main-part" }, el("span", { class: "pass-top" }, "Library pass"), el("div", { class: "seatno" }, seatLabel(m.seat)), el("div", { class: "muted" }, m.label), el("div", { style: "margin-top:10px" }, c)), el("div", { class: "stub" }, qr(m.seat + m.slot)));
          })) : el("p", { class: "muted", style: "margin-top:6px" }, "No bookings yet. Your digital pass will appear here."));
        sideBox.replaceChildren(pick, mine);
        const go = el("button", { class: "btn amber small", "data-book-bar": true, disabled: st.busy }, "Book seat");
        go.addEventListener("click", book);
        bookBar.replaceChildren(el("span", {}, el("strong", {}, st.sel ? seatLabel(st.sel) : ""), ` · ${slot.label}`), go);
        bookBar.classList.toggle("show", !!st.sel);
      }
      function renderAll() { renderSlots(); renderTabs(); renderMap(); renderSide(); }

      async function load() {
        try {
          const d = await CP.get("/library", st.slot === null ? {} : { slot: st.slot });
          if (!alive()) return;
          st.data = d; if (st.slot === null || d.slots[st.slot].ended) st.slot = d.chosen;
          if (st.sel) { const seat = d.zones.flatMap((z) => z.seats).find((s) => s.id === st.sel); if (!seat || seat.status !== "free") { CP.toast("Someone just took that seat. Pick another.", "bad"); st.sel = null; } }
          renderAll();
        } catch (e) { if (alive() && !st.data) root.replaceChildren(CP.head("Library seats"), CP.errorBox(e, () => { root.replaceChildren(); CP.pages.library.mount(root); })); }
      }
      root.append(
        CP.head("Library seats", "Pick a time slot and a seat, like choosing seats at the cinema. Your pass is stored in DynamoDB.", CP.simBadge("Other students simulated")),
        el("section", { class: "card" }, el("h3", { style: "margin-bottom:12px" }, "Choose a time slot"), slotsBox),
        el("div", { class: "grid split", style: "margin-top:18px" },
          el("section", { class: "card" }, tabsBox, el("div", { class: "screen" }), el("div", { class: "screen-label" }, "Librarian desk and entrance"), mapBox,
            el("div", { class: "seat-legend" }, [["", "Available"], ["taken", "Taken"], ["sel", "Selected"], ["mine", "Yours"]].map(([c, t]) => el("span", {}, el("span", { class: "seat " + c }), t)))),
          el("div", { class: "sticky" }, sideBox)), bookBar);
      load(); CP.every(12000, load); CP.onClock(() => { st.slot = null; st.sel = null; load(); });
    },
  };
})(window.CP);
