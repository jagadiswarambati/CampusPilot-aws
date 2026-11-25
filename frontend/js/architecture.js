"use strict";
/* AWS architecture: diagram, services, a live API check, and an honest real-vs-simulated table. */
(function (CP) {
  const { el, svg, icon } = CP;

  function diagram() {
    const W = 900, H = 350, s = svg("svg", { class: "arch", viewBox: `0 0 ${W} ${H}`, role: "img", "aria-label": "Architecture: the student's browser loads the app from Amplify Hosting and calls API Gateway, which invokes Lambda. Lambda reads and writes DynamoDB, writes logs to CloudWatch and can optionally call Bedrock." });
    s.append(svg("defs", {}, svg("marker", { id: "arr", viewBox: "0 0 10 10", refX: 8, refY: 5, markerWidth: 6, markerHeight: 6, orient: "auto-start-reverse" }, svg("path", { d: "M0,0 L10,5 L0,10 z", fill: "#12181f" }))));
    const node = (x, y, w, t, sub, stripe, dash) => { s.append(svg("rect", { x, y, width: w, height: 70, rx: 8, fill: "#fff", stroke: "#12181f", "stroke-width": 2, "stroke-dasharray": dash ? "7 5" : null }),
      svg("rect", { x, y, width: 10, height: 70, rx: 4, fill: stripe }), svg("text", { x: x + 24, y: y + 31 }, t), svg("text", { x: x + 24, y: y + 51, class: "small" }, sub)); };
    const edge = (d, label, lx, ly, dash) => { s.append(svg("path", { d, fill: "none", stroke: "#12181f", "stroke-width": 3, "marker-end": "url(#arr)", "stroke-dasharray": dash ? "7 5" : null })); if (label) s.append(svg("text", { x: lx, y: ly, class: "small", "text-anchor": "middle" }, label)); };
    node(20, 145, 170, "Student", "phone or laptop", "#ffc400");
    node(270, 30, 200, "AWS Amplify Hosting", "static site over HTTPS", "#5f6b7a");
    node(270, 145, 200, "Amazon API Gateway", "HTTP API, throttled", "#1a73e8");
    node(550, 145, 150, "AWS Lambda", "Python 3.12", "#f57c00");
    node(740, 145, 140, "DynamoDB", "single table, TTL", "#0f9d58");
    node(270, 265, 200, "CloudWatch Logs", "14-day retention", "#5f6b7a");
    node(740, 265, 140, "Bedrock", "optional, off", "#d93025", true);
    edge("M105 145 V65 H270", "loads the app", 190, 56);
    edge("M190 180 H270", "REST + JSON", 230, 170);
    edge("M470 180 H550", "invokes", 510, 170);
    edge("M700 180 H740", "data", 720, 170);
    edge("M590 215 V300 H470", "logs", 530, 292);
    edge("M660 215 V300 H740", "optional", 700, 292, true);
    return s;
  }

  const SERVICES = [
    ["cloud", "AWS Amplify Hosting", "Serves this website over HTTPS. Deployed as a zip with one script."],
    ["zap", "Amazon API Gateway", "Public REST API with CORS and throttling to protect the Free Tier."],
    ["pulse", "AWS Lambda", "All business logic: planning, seat booking, attendance, orders."],
    ["layers", "Amazon DynamoDB", "Seats, attendance, orders and plans in one table, with TTL expiry. Seat booking uses atomic transactions."],
    ["user", "Amazon Bedrock (optional)", "Understands free-text requests. Off by default; the app falls back to built-in rules."],
    ["clock", "Amazon CloudWatch", "Lambda logs kept for 14 days so costs stay predictable."],
  ];

  CP.pages.architecture = {
    title: "AWS architecture",
    mount(root) {
      const alive = CP.guard();
      const CHECKS = ["API Gateway + Lambda (/health)", "DynamoDB read (campus data)", "DynamoDB query (library seats)"];
      const pending = () => CHECKS.map((l) => el("div", { class: "row" }, el("span", {}, l), CP.pill("Not run yet")));
      const result = el("div", { class: "stack", id: "check-result", style: "gap:12px" }, ...pending());
      const region = (CP.API.match(/\.execute-api\.([a-z0-9-]+)\./) || [])[1];
      const btn = el("button", { class: "btn primary", id: "run-check" }, icon("pulse", 18), "Run live check");
      btn.addEventListener("click", async () => {
        btn.disabled = true; result.replaceChildren(CP.skeleton(2));
        const rows = [];
        const time = async (label, fn) => { const t = performance.now(); try { await fn(); rows.push([label, Math.round(performance.now() - t) + " ms", "ok"]); } catch (e) { rows.push([label, e.message, "bad"]); } };
        await time("API Gateway + Lambda (/health)", () => CP.api("/health"));
        await time("DynamoDB read (campus data)", () => CP.get("/campus"));
        await time("DynamoDB query (library seats)", () => CP.get("/library"));
        if (!alive()) return;
        result.replaceChildren(...rows.map(([l, v, k]) => el("div", { class: "row" }, el("span", {}, l), CP.pill(v, k))), el("small", { class: "muted" }, region ? "Region: " + region : "Running locally"));
        btn.disabled = false;
      });
      root.append(CP.head("AWS architecture", "How CampusPilot is built, and what is real versus simulated in this demo."),
        el("section", { class: "card" }, el("h3", { style: "margin-bottom:10px" }, "Serverless on AWS"), diagram()),
        el("div", { class: "grid g3", style: "margin-top:18px" }, SERVICES.map(([ic, t, d]) => el("article", { class: "card svc" }, el("span", { class: "ico" }, icon(ic, 20)), el("div", {}, el("strong", {}, t), el("p", { class: "muted", style: "font-size:.93rem" }, d))))),
        el("div", { class: "grid g2", style: "margin-top:18px" },
          el("section", { class: "card" }, el("div", { class: "card-head" }, el("h3", {}, "Live check"), btn), el("p", { class: "muted", style: "margin-bottom:16px" }, "Calls your deployed API, then reads campus data and the seat map from DynamoDB and times each step."), result),
          el("section", { class: "card" }, el("h3", { style: "margin-bottom:8px" }, "Real versus simulated"),
            el("table", { class: "simple" }, el("thead", {}, el("tr", {}, el("th", {}, "Real"), el("th", {}, "Simulated for the demo"))),
              el("tbody", {}, [["AWS services and data in DynamoDB", "Queue lengths and kitchen load"], ["Atomic seat booking, no double booking", "Seats held by other students"], ["Orders, tokens, check-ins", "Timetable and attendance history"], ["Plans computed by tested code", "Order progress and payments"]]
                .map(([a, b]) => el("tr", {}, el("td", {}, a), el("td", {}, b)))))),
          el("section", { class: "card", style: "grid-column:1/-1" }, el("h3", {}, "Safety and cost guards"),
            el("ul", { style: "margin:10px 0 0;padding-left:20px;line-height:1.8" }, ["Least-privilege IAM: the function can touch only its own table", "API throttling, strict input validation, no HTML injection", "Provisioned DynamoDB capacity inside the always-free allowance, TTL on every temporary record", "Bedrock disabled by default, with a rules fallback"].map((t) => el("li", {}, t))))));
    },
  };
})(window.CP);
