// Guided first-time tour: six short steps, skippable, shown once per browser, reopenable.
// Plain JavaScript; no dependencies. It only points at features that exist.
(function () {
  "use strict";
  const KEY = "estd-tour-done";
  const reduce = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
  const $ = (s) => document.querySelector(s);
  const STEPS = [
    {sel: "#map", inset: 0.22, title: "1 · The scene",
     text: "This is Phoenix at night. Each column is one 5 km NASA grid cell: taller and brighter means a hotter night. The dark base follows the Phoenix urban area. Click any column to open its case file."},
    {sel: ".timeline", extra: "#year", controls: true, title: "2 · Move through time",
     text: "Press play to watch 2003–2024, or drag the year. Pick a month, or the annual average (shown only when all 12 months passed quality control)."},
    {sel: "#region", controls: true, title: "3 · Pick a region",
     text: "Focus on one quarter of the city. Scroll down from the map and Phoenix splits into its four quarters, each with its warming rate and 95% range."},
    {sel: "#compare .compare-ctl", extra: "#compare h2", scroll: true, title: "4 · Compare",
     text: "Put any two periods side by side, and test whether two regions really warm at different rates: a direct test, not two separate p-values."},
    {sel: "#ask", scroll: true, title: "5 · Ask the Climate Detective",
     text: "Ask anything about Phoenix's nights: a place, a year, a season, a comparison. Answers come from the statistical tests on the NASA cells, never invented."},
    {sel: ".ctl-actions", controls: true, title: "6 · Keep your evidence",
     text: "'Copy link to this view' saves your exact view (year, month, layer, region, cell) as a link you can reopen or share. 'Download CSV' saves the numbers. There is no saved notebook yet: links are how you keep a case."},
  ];
  let i = 0, root, spot, card;

  function build() {
    root = document.createElement("div");
    root.id = "tour"; root.setAttribute("role", "dialog"); root.setAttribute("aria-modal", "true"); root.setAttribute("aria-labelledby", "tour-title");
    root.innerHTML = `<div class="tour-spot"></div>
      <div class="tour-card"><p class="tour-kicker">Case briefing</p><h3 id="tour-title"></h3><p class="tour-text"></p>
        <div class="tour-nav"><button type="button" class="tour-skip">Skip tour</button><span class="tour-count"></span>
          <button type="button" class="tour-back">Back</button><button type="button" class="tour-next primary">Next</button></div></div>`;
    document.body.appendChild(root);
    spot = root.querySelector(".tour-spot"); card = root.querySelector(".tour-card");
    root.querySelector(".tour-skip").addEventListener("click", end);
    root.querySelector(".tour-back").addEventListener("click", () => go(i - 1));
    root.querySelector(".tour-next").addEventListener("click", () => (i === STEPS.length - 1 ? end() : go(i + 1)));
    root.addEventListener("keydown", (e) => {
      if (e.key === "Escape") end();
      if (e.key === "ArrowRight") root.querySelector(".tour-next").click();
      if (e.key === "ArrowLeft" && i > 0) go(i - 1);
    });
    window.addEventListener("resize", place);
  }

  function target(step) { return $(step.sel); }

  function go(n) {
    i = Math.max(0, Math.min(STEPS.length - 1, n));
    const step = STEPS[i];
    if (step.controls) {
      window.scrollTo({top: 0, behavior: "auto"});
      const panel = $("#controls");
      if (panel && panel.classList.contains("collapsed")) $("#ctl-toggle")?.click();
    } else if (step.scroll) {
      target(step)?.scrollIntoView({behavior: "auto", block: "center"});
    } else {
      window.scrollTo({top: 0, behavior: "auto"});
    }
    root.querySelector("#tour-title").textContent = step.title;
    root.querySelector(".tour-text").textContent = step.text;
    root.querySelector(".tour-count").textContent = `${i + 1} / ${STEPS.length}`;
    root.querySelector(".tour-back").disabled = i === 0;
    root.querySelector(".tour-next").textContent = i === STEPS.length - 1 ? "Done" : "Next";
    requestAnimationFrame(() => requestAnimationFrame(place));
    root.querySelector(".tour-next").focus({preventScroll: true});
  }

  function place() {
    if (!root) return;
    const step = STEPS[i], el = target(step);
    if (!el) { spot.style.opacity = "0"; return; }
    let r = el.getBoundingClientRect();
    if (step.extra && $(step.extra)) {
      const r2 = $(step.extra).getBoundingClientRect();
      r = {left: Math.min(r.left, r2.left), top: Math.min(r.top, r2.top), right: Math.max(r.right, r2.right), bottom: Math.max(r.bottom, r2.bottom)};
    }
    let {left, top, right, bottom} = r;
    if (step.inset) {   // the map fills the screen: spotlight where the grid is drawn
      const w = right - left, h = bottom - top;
      if (innerWidth < 700) { left += w * 0.12; right -= w * 0.12; top += h * 0.52; bottom -= h * 0.2; }
      else { left += w * step.inset; right -= w * step.inset * 0.4; top += h * step.inset; bottom -= h * step.inset * 0.3; }
    }
    const pad = 8;
    left = Math.max(4, left - pad); top = Math.max(4, top - pad);
    right = Math.min(innerWidth - 4, right + pad); bottom = Math.min(innerHeight - 4, bottom + pad);
    Object.assign(spot.style, {opacity: "1", left: `${left}px`, top: `${top}px`, width: `${right - left}px`, height: `${bottom - top}px`});
    const cw = Math.min(360, innerWidth - 24), ch = card.offsetHeight || 200;
    let x, y;
    if (innerWidth < 700) { x = 12; y = bottom + 12 + ch < innerHeight ? bottom + 12 : Math.max(12, top - ch - 12); }
    else if (right + 18 + cw < innerWidth) { x = right + 18; y = Math.min(Math.max(12, top), innerHeight - ch - 12); }
    else if (left - 18 - cw > 0) { x = left - 18 - cw; y = Math.min(Math.max(12, top), innerHeight - ch - 12); }
    else { x = Math.max(12, Math.min(left, innerWidth - cw - 12)); y = bottom + 12 + ch < innerHeight ? bottom + 12 : Math.max(12, top - ch - 12); }
    Object.assign(card.style, {width: `${cw}px`, left: `${x}px`, top: `${Math.max(12, y)}px`});
  }

  function start() {
    if (!root) build();
    root.hidden = false; document.body.classList.add("touring");
    go(0);
  }

  function end() {
    if (root) root.hidden = true;
    document.body.classList.remove("touring");
    try { localStorage.setItem(KEY, "1"); } catch { /* storage blocked: the tour may show again, harmless */ }
    window.scrollTo({top: 0, behavior: reduce ? "auto" : "smooth"});
  }

  document.querySelectorAll("[data-tour-start]").forEach((b) => b.addEventListener("click", start));
  let seen = false;
  try { seen = localStorage.getItem(KEY) === "1"; } catch { seen = true; }
  // First visit only, and not when someone opened a shared link to a specific view.
  if (!seen && !location.hash) {
    const wait = () => (document.querySelector("#data-status")?.textContent.includes("Loading") ? setTimeout(wait, 400) : setTimeout(start, 700));
    setTimeout(wait, 800);
  }
  window.ESTDTour = {start};
})();
