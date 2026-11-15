/* AI Climate Detective on the web explorer.
 *
 * Shows the AI layer's guided investigations exactly as app/climate_detective.py produces them
 * (saved to data/detective.json by scripts/build_detective_json.py). Question matching below is
 * a line-by-line port of interpret_question(); tests/web/test_detective_json.py checks that both
 * give the same answer for the same questions. Gemini is not used.
 */
(function (root) {
  "use strict";

  const VOCABULARY = new Set((
    "which region regions area of phoenix has have did does the a an experienced " +
    "nighttime land surface temperature warming warmed fastest most compare northeast " +
    "southwest northwest southeast and vs versus is getting warmer increased " +
    "significantly statistically significant since from to between through " +
    "accelerated acceleration trend trends show me please evidence for").split(/\s+/));

  function interpretQuestion(question) {
    const q = String(question).toLowerCase().trim();
    const words = q.match(/[a-z]+/g) || [];
    if (!words.every((w) => VOCABULARY.has(w))) return null;
    const years = q.match(/\b\d+\b/g) || [];
    const compass = ["northeast", "southwest", "northwest", "southeast"].filter((r) => q.includes(r));
    const same = (a, b) => a.length === b.length && a.every((x, i) => x === b[i]);
    if (q.includes("accelerat")) {
      return !compass.length && (same(years, []) || same(years, ["2014"])) ? "acceleration" : null;
    }
    if (!(same(years, []) || same(years, ["2003"]) || same(years, ["2003", "2024"]))) return null;
    if (q.includes("compare") || q.includes(" vs ") || q.includes("versus")) {
      return compass.length === 2 && compass.includes("northeast") && compass.includes("southwest")
        ? "compare" : null;
    }
    if (compass.length) return null;
    if (q.includes("fastest") || q.includes("warmed most") || q.includes("most nighttime warming")) return "rank";
    if (["significan", "warmer", "warming", "trend", "increased"].some((w) => q.includes(w))) return "trend";
    return null;
  }

  if (typeof module !== "undefined" && module.exports) {
    module.exports = {interpretQuestion};
    return;
  }

  // ---------- browser UI ----------
  const doc = root.document;
  const $ = (id) => doc.getElementById(id);
  const esc = (s) => String(s).replace(/[&<>"']/g, (c) => ({"&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;"}[c]));
  let data = null;

  function fmtCell(key, value) {
    if (typeof value !== "number") return esc(value);
    if (/p-value/i.test(key)) return value < 0.001 ? "&lt; 0.001" : value.toPrecision(2);
    if (/slope/i.test(key)) return (value >= 0 ? "+" : "−") + Math.abs(value).toFixed(3);
    return String(value);
  }

  function lineChart(traces, xTitle, yTitle, panelTitles) {
    const panels = Math.max(...traces.map((t) => t.panel));
    const W = 720, H = 300, L = 46, R = 12, T = panelTitles.length ? 26 : 12, B = 46, gap = 26;
    const pw = (W - L - R - gap * (panels - 1)) / panels, ph = H - T - B;
    const all = traces.flatMap((t) => t.y).filter((v) => v != null);
    const lo = Math.floor(Math.min(...all) / 5) * 5, hi = Math.ceil(Math.max(...all) / 5) * 5;
    const colors = ["#3355d1", "#d9603b"];
    let svg = "";
    for (let p = 1; p <= panels; p++) {
      const x0 = L + (p - 1) * (pw + gap);
      for (let v = lo; v <= hi; v += 5) {
        const y = T + ph - ((v - lo) / (hi - lo)) * ph;
        svg += `<line x1="${x0}" x2="${x0 + pw}" y1="${y}" y2="${y}" stroke="#e3e6ee"/>`;
        if (p === 1) svg += `<text x="${x0 - 6}" y="${y + 3.5}" text-anchor="end" class="tick">${v}</text>`;
      }
      if (panelTitles[p - 1]) svg += `<text x="${x0 + pw / 2}" y="14" text-anchor="middle" class="ptitle">${esc(panelTitles[p - 1])}</text>`;
      const own = traces.filter((t) => t.panel === p);
      const n = own[0].x.length;
      const years = [...new Set(own[0].x.map((t) => t.slice(0, 4)))];
      years.forEach((yr, i) => {
        if (i % Math.ceil(years.length / 6) !== 0 && i !== years.length - 1) return;
        const xi = own[0].x.indexOf(`${yr}-01`);
        if (xi < 0) return;
        svg += `<text x="${x0 + (xi / (n - 1)) * pw}" y="${T + ph + 16}" text-anchor="middle" class="tick">${yr}</text>`;
      });
      own.forEach((t, ti) => {
        let d = "", pen = false;
        t.y.forEach((v, i) => {
          if (v == null) { pen = false; return; }   // gaps stay gaps
          const x = x0 + (i / (n - 1)) * pw, y = T + ph - ((v - lo) / (hi - lo)) * ph;
          d += `${pen ? "L" : "M"}${x.toFixed(1)},${y.toFixed(1)}`; pen = true;
        });
        const color = colors[traces.indexOf(t) % colors.length] || colors[ti];
        svg += `<path d="${d}" fill="none" stroke="${color}" stroke-width="1.3" stroke-linejoin="round"/>`;
      });
    }
    svg += `<text x="${L + (W - L - R) / 2}" y="${H - 6}" text-anchor="middle" class="axis">${esc(xTitle)}</text>`;
    svg += `<text transform="translate(12 ${T + ph / 2}) rotate(-90)" text-anchor="middle" class="axis">${esc(yTitle)}</text>`;
    const names = [...new Set(traces.map((t) => t.name))];
    const legend = names.length > 1 ? `<div class="det-legend">${names.map((nm, i) => `<span><i style="background:${colors[i]}"></i>${esc(nm)}</span>`).join("")}</div>` : "";
    return `<svg viewBox="0 0 ${W} ${H}" role="img" aria-label="${esc(yTitle)} by ${esc(xTitle)}">${svg}</svg>${legend}`;
  }

  function barChart(trace, xTitle, yTitle) {
    const W = 720, H = 280, L = 56, R = 12, T = 14, B = 52;
    const max = Math.max(...trace.y) * 1.15, n = trace.y.length, bw = (W - L - R) / n;
    let svg = "";
    for (let k = 0; k <= 4; k++) {
      const v = (max / 4) * k, y = T + (H - T - B) - (v / max) * (H - T - B);
      svg += `<line x1="${L}" x2="${W - R}" y1="${y}" y2="${y}" stroke="#e3e6ee"/><text x="${L - 6}" y="${y + 3.5}" text-anchor="end" class="tick">${v.toFixed(3)}</text>`;
    }
    trace.y.forEach((v, i) => {
      const h = (v / max) * (H - T - B), x = L + i * bw + bw * 0.22, y = T + (H - T - B) - h;
      svg += `<rect x="${x}" y="${y}" width="${bw * 0.56}" height="${h}" rx="3" fill="${i === 0 ? "#6a4bd6" : "#9aaee8"}"><title>${esc(trace.x[i])}: ${v.toFixed(3)} °C/year</title></rect>`;
      svg += `<text x="${x + bw * 0.28}" y="${y - 6}" text-anchor="middle" class="val">+${v.toFixed(3)}</text>`;
      svg += `<text x="${x + bw * 0.28}" y="${H - B + 18}" text-anchor="middle" class="tick">${esc(trace.x[i])}</text>`;
    });
    svg += `<text x="${L + (W - L - R) / 2}" y="${H - 8}" text-anchor="middle" class="axis">${esc(xTitle)}</text>`;
    svg += `<text transform="translate(12 ${T + (H - T - B) / 2}) rotate(-90)" text-anchor="middle" class="axis">${esc(yTitle)}</text>`;
    return `<svg viewBox="0 0 ${W} ${H}" role="img" aria-label="${esc(yTitle)} by ${esc(xTitle)}">${svg}</svg>`;
  }

  function render(question) {
    const out = $("det-result");
    const intent = interpretQuestion(question);
    const inv = intent && data.investigations.find((i) => i.intent === intent);
    if (!inv) {
      out.innerHTML = `<p class="det-info">${esc(data.unsupported_message)}</p>`;
      return;
    }
    const chart = inv.intent === "rank"
      ? barChart(inv.traces[0], inv.x_title, inv.y_title)
      : lineChart(inv.traces, inv.x_title, inv.y_title, inv.subplot_titles);
    const cols = [...new Set(inv.rows.flatMap((r) => Object.keys(r)))];
    out.innerHTML = `
      <p class="det-q"><span>Research question</span>${esc(question)}</p>
      <figure class="det-chart"><figcaption>${esc(inv.title)}</figcaption>${chart}
        <p class="det-src">NASA MOD11C3.061 · phoenix-qc-v1.0 · Seasonal MK / Sen's slope</p></figure>
      <div class="det-finding"><span>Key finding</span>${esc(inv.finding)}</div>
      <div class="table-wrap"><table class="findings det-table"><thead><tr>${cols.map((c) => `<th scope="col">${esc(c)}</th>`).join("")}</tr></thead>
        <tbody>${inv.rows.map((r) => `<tr>${cols.map((c) => `<td class="${typeof r[c] === "number" ? "num" : ""}">${r[c] == null ? "—" : fmtCell(c, r[c])}</td>`).join("")}</tr>`).join("")}</tbody></table></div>
      <details class="det-how"><summary>How was this calculated?</summary><p>${esc(data.method_note)}</p><p>${esc(data.source)}</p>
        <p><a href="https://doi.org/10.5067/MODIS/MOD11C3.061">NASA dataset reference</a></p></details>
      <p class="note">${esc(data.limits)}</p>`;
  }

  async function init() {
    const host = $("detective");
    if (!host) return;
    try {
      const res = await fetch("data/detective.json", {cache: "no-store"});
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      data = await res.json();
    } catch (err) {
      $("det-result").innerHTML = `<p class="det-info">The guided investigations could not be loaded (${esc(err.message)}).</p>`;
      return;
    }
    $("det-mode").textContent = data.mode;
    const chips = $("det-chips");
    for (const inv of data.investigations) {
      const b = doc.createElement("button");
      b.type = "button"; b.textContent = inv.label;
      b.addEventListener("click", () => { $("det-input").value = inv.question; render(inv.question); });
      chips.appendChild(b);
    }
    $("det-form").addEventListener("submit", (ev) => { ev.preventDefault(); render($("det-input").value); });
  }
  if (doc.readyState === "loading") doc.addEventListener("DOMContentLoaded", init); else init();
})(typeof window !== "undefined" ? window : globalThis);
