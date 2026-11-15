/* Earth System Trend Detective — map explorer.
 *
 * Data rules (same as the rest of the project):
 *  - Every number comes from the backend: regional results (/regions, /series, /anomaly,
 *    /region-stats, /region-compare), one map frame at a time (/map-frame: one month's value per
 *    grid cell, never the whole dataset), per-cell trend and coverage (/map-static) and verified
 *    AI discoveries (/discoveries). Nothing is interpolated or estimated in the browser.
 *  - A missing month stays missing. An annual average needs all 12 months (enforced server-side).
 *  - One shared state object drives every view; the URL hash mirrors it for shareable links.
 * The camera never moves. One map: regions, cells, comparison and data information open from it;
 * scrolling splits it into its four quarters, each with its own panel.
 */
(() => {
  "use strict";
  const {Deck, ColumnLayer, PolygonLayer, PathLayer, TextLayer, TileLayer, BitmapLayer,
         WebMercatorViewport} = deck;

  // ---------- constants ----------
  const W = -112.4, S = 33.2, E = -111.6, N = 33.8, MID_LON = -112.0, MID_LAT = 33.5;
  const QUARTERS = {
    NW: {name: "Northwest", b: [W, MID_LAT, MID_LON, N]},
    NE: {name: "Northeast", b: [MID_LON, MID_LAT, E, N]},
    SW: {name: "Southwest", b: [W, S, MID_LON, MID_LAT]},
    SE: {name: "Southeast", b: [MID_LON, S, E, MID_LAT]},
  };
  const ORDER = ["NW", "NE", "SW", "SE"];
  const MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];
  const PLACES = [["Downtown Phoenix", -112.074, 33.4484], ["Tempe", -111.94, 33.4255],
                  ["Glendale", -112.186, 33.5387], ["Scottsdale", -111.926, 33.4942]];
  const HIGHLIGHT = {ask: [230, 60, 50], faster: [230, 60, 50], slower: [110, 170, 230], extremes: [255, 255, 255],
                     anomalies: [255, 255, 255], none: [230, 60, 50]};   // evidence-string red, steel blue, chalk white
  const METRES_PER_DEG_C = 95;                 // column height scale (fixed for every period)
  const PITCH = 42;
  const reduceMotion = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
  const params = new URLSearchParams(location.search);
  const API = (params.get("api") || (location.pathname.startsWith("/app") ? "" : "http://127.0.0.1:8000"))
    .replace(/\/$/, "");
  const CHARS = " ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789.,:+-()°·–/".split("");

  // ---------- layer definitions (each with its own scale, units and description) ----------
  // Case-file theme ramps: Inferno for temperature, a saturated diverging ramp for anomalies,
  // Plasma for warming rate, Viridis for coverage (all ordered light/dark monotonic enough to read).
  const RAMP_TEMP = [[20, 11, 52], [66, 10, 104], [120, 28, 109], [171, 51, 95], [214, 84, 60],
                     [243, 128, 30], [250, 180, 40], [252, 230, 120], [252, 255, 190]];   // Inferno-like: dark desk, hot = bright
  const RAMP_DIV = [[8, 81, 156], [49, 163, 233], [158, 218, 250], [246, 246, 246], [255, 196, 150],
                    [250, 104, 64], [190, 18, 60]];
  const RAMP_RATE = [[13, 8, 135], [106, 0, 168], [177, 42, 144], [225, 100, 98], [252, 166, 54],
                     [240, 249, 33]];
  const RAMP_COV = [[68, 1, 84], [59, 82, 139], [33, 145, 140], [94, 201, 98], [253, 231, 37]];
  const LAYERS = {
    temperature: {label: "Ground temperature", unit: "°C", min: 0, max: 40, ramp: RAMP_TEMP,
      ticks: ["0 °C", "10", "20", "30", "40 °C"],
      note: "How hot the ground was at night. Taller and brighter means hotter. An empty outline means the satellite had no reliable reading there."},
    anomaly: {label: "Warmer or cooler than usual", unit: "°C", min: -4, max: 4, ramp: RAMP_DIV,
      ticks: ["−4 °C", "−2", "0", "+2", "+4 °C"],
      note: "Each square compared with its own normal for that month (its 2003–2024 average). Red means warmer than usual, blue cooler."},
    rate: {label: "Warming speed", unit: "°C per year", min: 0, max: 0.2, ramp: RAMP_RATE,
      ticks: ["0", "0.05", "0.10", "0.15", "0.20 °C/yr"],
      note: "How fast each square has warmed since 2003. Brighter means faster. Faded squares do not have strong enough evidence. This does not change with the year or month."},
    coverage: {label: "Months with data", unit: "months", min: 0, max: 12, ramp: RAMP_COV,
      ticks: ["0", "3", "6", "9", "12 months"],
      note: "How many of the 12 months in this year have a reliable reading. Clouds or sensor problems cause gaps. Gaps are never filled in."},
  };

  // ---------- shared state ----------
  const state = {
    // selections (mirrored in the URL)
    year: 2024, month: 7, layer: "temperature", region: "all", cell: null, finding: null,
    compA: {year: 2003, month: "avg"}, compB: {year: 2023, month: "avg"}, rtA: "phoenix_southeast", rtB: "phoenix_northeast",
    // playback / scroll
    playing: false, speed: 900, progress: 0, eased: 0,
    // map chrome (not in the URL): floating legend on/off, which drawer is open
    legend: window.innerWidth > 900, drawer: null,
    // data
    regions: null, regionStats: null, series: {}, anomaly: {}, baseline: null, discoveries: null,
    cells: null, cellIndex: {}, frames: new Map(), frame: null, quarterIds: {}, view: null, targets: {},
    error: null, cellsError: null,
  };
  const URL_KEYS = ["year", "month", "layer", "region", "cell", "finding", "a", "b"];

  function setState(patch, {skipUrl = false} = {}) {
    Object.assign(state, patch);
    if (!skipUrl) writeUrl();
    renderAll();
  }

  function writeUrl() {
    const p = new URLSearchParams();
    p.set("year", state.year); p.set("month", state.month); p.set("layer", state.layer);
    if (state.region !== "all") p.set("region", state.region);
    if (state.cell) p.set("cell", state.cell);
    if (state.finding && state.finding !== "ask") p.set("finding", state.finding);
    p.set("a", `${state.compA.year}-${state.compA.month}`); p.set("b", `${state.compB.year}-${state.compB.month}`);
    history.replaceState(null, "", `#${p.toString()}`);
  }

  function readUrl() {
    const p = new URLSearchParams(location.hash.slice(1));
    const out = {};
    if (p.get("year") && /^\d{4}$/.test(p.get("year"))) out.year = +p.get("year");
    if (p.get("month")) out.month = p.get("month") === "avg" ? "avg" : clamp(+p.get("month") || 7, 1, 12);
    if (LAYERS[p.get("layer")]) out.layer = p.get("layer");
    if (["all", ...ORDER].includes(p.get("region"))) out.region = p.get("region");
    if (/^r\d{2}_c\d{2}$/.test(p.get("cell") || "")) out.cell = p.get("cell");
    if (/^[a-z-]+$/.test(p.get("finding") || "")) out.finding = p.get("finding");
    for (const key of ["a", "b"]) {
      const m = (p.get(key) || "").match(/^(\d{4})-(avg|\d{1,2})$/);
      if (m) out[key === "a" ? "compA" : "compB"] = {year: +m[1], month: m[2] === "avg" ? "avg" : +m[2]};
    }
    return out;
  }

  // ---------- helpers ----------
  const $ = (id) => document.getElementById(id);
  function clamp(x, a = 0, b = 1) { return Math.min(b, Math.max(a, x)); }
  const easeInOut = (t) => (t < 0.5 ? 4 * t * t * t : 1 - Math.pow(-2 * t + 2, 3) / 2);
  const fmt = (x, d = 1) => (x == null ? "—" : x.toFixed(d));
  const signed = (x, d) => (x == null ? "—" : (x >= 0 ? "+" : "−") + Math.abs(x).toFixed(d));
  const pText = (p) => (p == null ? "—" : p < 0.001 ? "p < 0.001" : `p = ${p.toPrecision(2)}`);
  const esc = (s) => String(s).replace(/[&<>"']/g, (c) => ({"&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;"}[c]));
  const periodLabel = (y = state.year, m = state.month) => (m === "avg" ? `${y} annual average` : `${MONTHS[m - 1]} ${y}`);
  const quarterOfRegion = (rid) => ORDER.find((q) => state.quarterIds[q] === rid);

  // Plain-language helpers. They only describe numbers the backend already produced.
  const CORNER = {NW: "upper-left", NE: "upper-right", SW: "lower-left", SE: "lower-right"};
  const quarterAt = (lon, lat) => (lat >= MID_LAT ? "N" : "S") + (lon < MID_LON ? "W" : "E");
  function whereText(q) {   // e.g. "The lower-right part of the map, around Tempe and Scottsdale."
    const names = PLACES.filter((pl) => quarterAt(pl[1], pl[2]) === q).map((pl) => pl[0]);
    const around = names.length ? `, around ${names.length > 1 ? names.slice(0, -1).join(", ") + " and " + names[names.length - 1] : names[0]}` : "";
    return `The ${CORNER[q]} part of the map${around}.`;
  }
  const areaName = (q) => `${QUARTERS[q].name} Phoenix`;
  function sureText(p) {   // how strong is the evidence that the pattern is real rather than random
    if (p == null) return "We could not test this.";
    if (p < 0.001) return "Very strong evidence. A pattern this clear would almost never show up by chance.";
    if (p < 0.05) return "Good evidence. This is unlikely to be chance.";
    return "Weak evidence. This could be chance, so we do not call it a trend.";
  }
  const sureShort = (p) => (p == null ? "not tested" : p < 0.001 ? "very strong evidence" : p < 0.05 ? "good evidence" : "weak evidence");
  function happened(direction, p) {
    if (p == null || p >= 0.05 || direction === "no trend") return "No clear change in night-time ground temperature here.";
    return direction === "increasing" ? "The ground at night has been getting warmer here." : "The ground at night has been getting cooler here.";
  }

  function rampColor(ramp, t, alpha = 235) {
    const x = clamp(t) * (ramp.length - 1);
    const i = Math.min(ramp.length - 2, Math.floor(x)), f = x - i, a = ramp[i], b = ramp[i + 1];
    return [a[0] + (b[0] - a[0]) * f, a[1] + (b[1] - a[1]) * f, a[2] + (b[2] - a[2]) * f, alpha];
  }
  const scaleColor = (L, v, alpha) => rampColor(L.ramp, (v - L.min) / (L.max - L.min), alpha);
  const layerColor = (layer, v, alpha) => scaleColor(LAYERS[layer], v, alpha);
  const DIFF_SCALE = {ramp: RAMP_DIV, min: -6, max: 6};   // comparison only: ΔT = B − A
  const rampCss = (ramp) => `linear-gradient(90deg, ${ramp.map((c) => `rgb(${c.join(",")})`).join(", ")})`;

  async function getJSON(path, optional = false) {
    const res = await fetch(path, {cache: "no-store"});
    if (!res.ok) {
      if (optional) return null;
      throw new Error(`${path} answered HTTP ${res.status}`);
    }
    return res.json();
  }

  function periodValue(times, values, year, month) {
    if (month !== "avg") {
      const i = times.indexOf(`${year}-${String(month).padStart(2, "0")}`);
      return i < 0 ? null : values[i];
    }
    let sum = 0;
    for (let m = 1; m <= 12; m++) {
      const i = times.indexOf(`${year}-${String(m).padStart(2, "0")}`);
      if (i < 0 || values[i] == null) return null;   // annual mean only with all 12 months
      sum += values[i];
    }
    return sum / 12;
  }

  // ---------- frames (one period at a time from the server, cached) ----------
  async function loadFrame(year, month) {
    const key = `${year}-${month}`;
    if (!state.frames.has(key)) {
      state.frames.set(key, getJSON(`${API}/map-frame?year=${year}&month=${month}`)
        .then((f) => ({...f, byId: Object.fromEntries(f.cells.map((c) => [c.id, c]))}))
        .catch((err) => { state.frames.delete(key); throw err; }));
    }
    return state.frames.get(key);
  }

  async function showPeriod() {
    if (!state.cells) return;
    const want = `${state.year}-${state.month}`;
    try {
      const frame = await loadFrame(state.year, state.month);
      if (want !== `${state.year}-${state.month}`) return;   // a newer request superseded this one
      state.frame = frame; state.cellsError = null;
    } catch (err) {
      state.cellsError = err.message;
    }
    renderAll();
  }

  // ---------- geometry for the split ----------
  function pieceTransform(q, e) {
    const [w, s, ea, n] = QUARTERS[q].b;
    const cx = (w + ea) / 2, cy = (s + n) / 2;
    const t = state.targets[q] || {lon: cx, lat: cy, k: 1};
    const k = 1 + (t.k - 1) * e;
    const tx = cx + (t.lon - cx) * e, ty = cy + (t.lat - cy) * e;
    return {k, f: ([x, y]) => [tx + k * (x - cx), ty + k * (y - cy)]};
  }
  const rect = (w, s, e, n) => [[w, s], [e, s], [e, n], [w, n], [w, s]];
  function layoutMode() {
    const w = window.innerWidth, h = window.innerHeight;
    return w >= 900 && w / h >= 1.15 ? "wide" : "tall";
  }
  function computeTargets() {
    const w = $("map").clientWidth, h = $("map").clientHeight;
    const vp = new WebMercatorViewport({...state.view, width: w, height: h});
    const wide = layoutMode() === "wide";
    const spec = wide ? {xs: {W: 0.165, E: 0.835}, ys: {N: 0.25, S: 0.76}, width: 0.29}
      : {xs: {W: 0.255, E: 0.745}, ys: {N: 0.13, S: 0.6}, width: 0.45};
    state.targets = {};
    for (const q of ORDER) {
      const [bw, bs, be, bn] = QUARTERS[q].b;
      const cx = (bw + be) / 2, cy = (bs + bn) / 2;
      const [lon, lat] = vp.unproject([spec.xs[q[1]] * w, spec.ys[q[0]] * h]);
      const corners = [[bw, bs], [be, bs], [be, bn], [bw, bn]].map(([x, y]) => vp.project([lon + x - cx, lat + y - cy]));
      const pw = Math.max(...corners.map((c) => c[0])) - Math.min(...corners.map((c) => c[0]));
      state.targets[q] = {lon, lat, k: Math.min(1, (spec.width * w) / pw)};
    }
  }
  function clipPolyline(path, [w, s, e, n]) {
    const out = []; let cur = null;
    for (let i = 0; i < path.length - 1; i++) {
      const [x0, y0] = path[i], [x1, y1] = path[i + 1];
      let t0 = 0, t1 = 1;
      const dx = x1 - x0, dy = y1 - y0, p = [-dx, dx, -dy, dy], qv = [x0 - w, e - x0, y0 - s, n - y0];
      let ok = true;
      for (let j = 0; j < 4 && ok; j++) {
        if (p[j] === 0) { if (qv[j] < 0) ok = false; } else { const r = qv[j] / p[j]; if (p[j] < 0) t0 = Math.max(t0, r); else t1 = Math.min(t1, r); }
      }
      if (!ok || t0 > t1) { cur = null; continue; }
      const a = [x0 + t0 * dx, y0 + t0 * dy], b = [x0 + t1 * dx, y0 + t1 * dy];
      if (cur && t0 === 0) cur.push(b); else { cur = [a, b]; out.push(cur); }
      if (t1 < 1) cur = null;
    }
    return out;
  }
  const freeways = {NW: [], NE: [], SW: [], SE: []};
  // Phoenix metro outline (Natural Earth urban area, MODIS c. 2002-2003): shapes the map base.
  // Visual only: cells outside it are not drawn on the map, but every cell is still analysed.
  const urban = {parts: null, inside: null};

  // ---------- deck ----------
  const deckgl = new Deck({
    parent: $("map"), controller: false, initialViewState: fitView(), getTooltip, layers: [],
    useDevicePixels: Math.min(window.devicePixelRatio || 1, 2),
    onClick: ({object}) => {
      if (object && object.kind === "cell") setState({cell: object.id});
      else if (object && object.kind === "piece") selectRegion(state.region === object.q && !state.cell ? "all" : object.q);
    },
    onError: (err) => console.warn("deck.gl:", err),
  });

  function fitView() {
    const el = $("map"), w = el.clientWidth || window.innerWidth, h = el.clientHeight || window.innerHeight;
    const phone = w < 640;
    const ctlBottom = ($("controls").getBoundingClientRect().bottom || 300) + 12;
    const brandH = w < 900 ? (document.querySelector(".brand").offsetHeight || 120) + 70 : 70;
    const ctlRight = ($("controls").getBoundingClientRect().right || 340) + 16;
    const pad = w > 1100 ? {top: 70, bottom: 70, left: 360, right: 40}
      : w >= 900 ? {top: 150, bottom: 50, left: ctlRight, right: 20}   // mid-size: map beside the panel
      : {top: ctlBottom, bottom: brandH, left: phone ? 6 : 24, right: phone ? 6 : 24};
    const vp = new WebMercatorViewport({width: w, height: h}).fitBounds([[W, S], [E, N]], {padding: pad});
    state.view = {longitude: vp.longitude, latitude: vp.latitude + 0.03, zoom: vp.zoom + (w > 1100 || w < 900 ? 0.02 : -0.28),   // mid-size: room for the tilted near edge
                 
                  pitch: PITCH, bearing: 0, maxPitch: 60};
    return state.view;
  }

  function cellRecord(id) {
    const c = state.cellIndex[id];
    const f = state.frame && state.frame.byId[id];
    return {...c, kind: "cell", value: f ? f.value : null, anomaly: f ? f.anomaly : null,
            validInYear: f ? f.valid_months_in_year : null};
  }

  function layerValue(rec) {
    switch (state.layer) {
      case "temperature": return rec.value;
      case "anomaly": return rec.anomaly;
      case "rate": return rec.slope_per_year;
      case "coverage": return rec.validInYear;
      default: return null;
    }
  }

  function getTooltip({object}) {
    if (!object) return null;
    const style = {backgroundColor: "#e9dbb8", color: "#2a2418", border: "1px solid #b9a67c", borderRadius: "3px", fontFamily: "\"Courier Prime\", monospace",
                   fontSize: "12px", boxShadow: "0 6px 16px rgba(20,26,43,.12)", padding: "8px 10px"};
    if (object.kind === "cell") {
      const v = layerValue(object), L = LAYERS[state.layer];
      const shown = v == null ? "no reliable reading" : state.layer === "rate" ? `${signed(v, 3)} °C each year` :
        state.layer === "anomaly" ? `${signed(v, 2)} °C compared with usual` : state.layer === "coverage" ? `${v} of 12 months` : `${fmt(v, 1)} °C`;
      return {style, html: `<b>${esc(areaName(object.quarter))}</b> · square ${esc(object.id)}<br>${esc(L.label)}${state.layer === "rate" ? "" : `, ${esc(periodLabel())}`}: <b>${shown}</b><br><span style="color:#7a6a45">Click to see more</span>`};
    }
    if (object.kind === "piece") {
      return {style, html: `<b>${esc(areaName(object.q))}</b><br>${esc(whereText(object.q))}<br><span style="color:#7a6a45">Click to see how it has changed</span>`};
    }
    if (object.kind === "quarter") {
      return {style, html: `<b>${esc(object.label)} Phoenix</b><br>Average, ${esc(periodLabel())}: <b>${object.value == null ? "no reliable reading" : fmt(object.value, 1) + " °C"}</b>`};
    }
    return null;
  }

  function buildLayers() {
    const e = state.eased, layers = [];
    const trans = reduceMotion ? {} : {getElevation: {duration: 450, easing: easeInOut}, getFillColor: {duration: 450, easing: easeInOut}};
    layers.push(new TileLayer({
      // Esri World Dark Gray Canvas: no API key needed.
      id: "basemap", minZoom: 0, maxZoom: 16, tileSize: 256, opacity: 1 - 0.9 * e,
      data: "https://server.arcgisonline.com/ArcGIS/rest/services/Canvas/World_Dark_Gray_Base/MapServer/tile/{z}/{y}/{x}",
      onTileError: () => {}, maxRequests: 8,
      renderSubLayers: (props) => {
        const {boundingBox} = props.tile;
        return new BitmapLayer(props, {data: null, image: props.data,
          bounds: [boundingBox[0][0], boundingBox[0][1], boundingBox[1][0], boundingBox[1][1]]});
      },
    }));
    const finding = currentFinding();
    for (const q of ORDER) {
      const {k, f} = pieceTransform(q, e);
      const [w, s, ea, n] = QUARTERS[q].b;
      const dim = state.region !== "all" && state.region !== q;
      const shaped = urban.parts && urban.parts[q] && urban.parts[q].length;
      layers.push(new PathLayer({   // the study window (the NASA grid is rectangular): a faint frame
        id: `frame-${q}`, data: [rect(w, s, ea, n)], getPath: (d) => [...d, d[0]].map(f),
        getColor: state.region === q ? [200, 55, 45, 200] : [120, 108, 84, shaped ? 90 : 220], widthUnits: "pixels",
        getWidth: state.region === q ? 2 : 1, updateTriggers: {getPath: e, getColor: state.region, getWidth: state.region},
      }));
      layers.push(new PolygonLayer({   // the base, cut to the Phoenix metro outline
        id: `piece-${q}`, pickable: true,
        data: shaped ? urban.parts[q].map((poly) => ({poly, kind: "piece", q})) : [{poly: rect(w, s, ea, n), kind: "piece", q}],
        getPolygon: (d) => d.poly.map(f), getFillColor: shaped ? [44, 40, 32, Math.round(170 + 70 * e)] : [28, 29, 33, Math.round(150 + 90 * e)],
        getLineColor: state.region === q ? [200, 55, 45, 255] : [224, 164, 58, 200],
        lineWidthUnits: "pixels", getLineWidth: state.region === q ? 2.5 : 1.4, stroked: true, filled: true,
        updateTriggers: {getPolygon: e, getFillColor: e, getLineColor: state.region, getLineWidth: state.region},
      }));
      layers.push(new PathLayer({id: `roads-${q}`, data: freeways[q], getPath: (d) => d.map(f),
        getColor: [150, 126, 84, 130], widthUnits: "pixels", getWidth: 1.2, updateTriggers: {getPath: e}}));

      if (state.cells) {
        // Cells outside the Phoenix outline are transparent (not drawn); they stay in every statistic.
        const recs = state.cells.filter((c) => c.quarter === q && (!urban.inside || urban.inside.has(c.id))).map((c) => cellRecord(c.id));
        const alpha = dim ? 70 : 235;
        const has = recs.filter((r) => layerValue(r) != null), missing = recs.filter((r) => layerValue(r) == null);
        layers.push(new PolygonLayer({   // missing cells: outline only, never a value
          id: `missing-${q}`, data: missing, pickable: true,
          getPolygon: (c) => c.footprint.map((p) => [c.lon + (p[0] - c.lon) * 0.84, c.lat + (p[1] - c.lat) * 0.84]).map(f),
          getFillColor: [255, 255, 255, 0], getLineColor: [120, 108, 84, dim ? 70 : 200], lineWidthUnits: "pixels",
          getLineWidth: 1, stroked: true, filled: true,
          updateTriggers: {getPolygon: e, getLineColor: dim},
        }));
        const colour = (r) => {
          let a = state.layer === "rate" && !r.significant_fdr ? Math.round(alpha * 0.35) : alpha;

          return layerColor(state.layer, layerValue(r), a);
        };
        if (state.layer === "temperature") {
          layers.push(new ColumnLayer({
            id: `cells-${q}`, data: has, pickable: true, extruded: true, diskResolution: 4, angle: 45,
            radius: 0.05 * 0.3 * 111320 * Math.SQRT2 * Math.cos(33.5 * Math.PI / 180) * k,
            getPosition: (c) => f([c.lon, c.lat]), getElevation: (c) => Math.max(0, c.value) * METRES_PER_DEG_C,
            elevationScale: k, getFillColor: colour, autoHighlight: true, highlightColor: [200, 55, 45, 200],
            material: {ambient: 0.55, diffuse: 0.55, shininess: 24}, transitions: trans,
            updateTriggers: {getPosition: e, getElevation: state.frame, getFillColor: [state.frame, state.region, !!urban.inside]},
          }));
        } else {
          layers.push(new PolygonLayer({
            id: `flat-${q}`, data: has, pickable: true, stroked: false, filled: true, autoHighlight: true,
            highlightColor: [106, 75, 214, 120],
            getPolygon: (c) => c.footprint.map((p) => [c.lon + (p[0] - c.lon) * 0.92, c.lat + (p[1] - c.lat) * 0.92]).map(f),
            getFillColor: colour, transitions: reduceMotion ? {} : {getFillColor: {duration: 450, easing: easeInOut}},
            updateTriggers: {getPolygon: e, getFillColor: [state.frame, state.layer, state.region]},
          }));
        }
        if (finding) {   // AI overlay: outlines on top of the measurements, never replacing them
          const color = HIGHLIGHT[finding.highlight] || HIGHLIGHT.none;
          layers.push(new PathLayer({
            id: `found-${q}`, data: finding.cells.filter((c) => c.quarter === q),
            getPath: (c) => [...c.footprint, c.footprint[0]].map(f), getColor: [...color, 255],
            widthUnits: "pixels", getWidth: 3, parameters: {depthTest: false},
            updateTriggers: {getPath: [e, state.finding]},
          }));
        }
        if (state.cell && state.cellIndex[state.cell]?.quarter === q) {
          const c = state.cellIndex[state.cell];
          layers.push(new PathLayer({id: `sel-${q}`, data: [c], getPath: (d) => [...d.footprint, d.footprint[0]].map(f),
            getColor: [239, 230, 210, 255], widthUnits: "pixels", getWidth: 3, parameters: {depthTest: false},
            updateTriggers: {getPath: [e, state.cell]}}));
        }
      } else {
        const rid = state.quarterIds[q], ser = rid && state.series[rid];
        const value = ser ? periodValue(ser.times, ser.values, state.year, state.month) : null;
        layers.push(new PolygonLayer({
          id: `quarter-${q}`, data: [{kind: "quarter", label: QUARTERS[q].name, value}], pickable: true,
          getPolygon: () => rect(w, s, ea, n).map(f), getFillColor: value == null ? [255, 255, 255, 0] : layerColor("temperature", value, 105),
          stroked: false, filled: true, updateTriggers: {getPolygon: e, getFillColor: [state.year, state.month]},
        }));
      }
      layers.push(new TextLayer({
        id: `qname-${q}`, data: [{t: QUARTERS[q].name.toUpperCase(), kind: "piece", q}], characterSet: CHARS, pickable: true,
        getPosition: () => f([q.endsWith("W") ? w + 0.012 : ea - 0.012, n - 0.012]),
        getTextAnchor: q.endsWith("W") ? "start" : "end", getAlignmentBaseline: "top",
        getText: (d) => d.t, getSize: 13, getColor: state.region === q ? [200, 55, 45, 255] : [224, 164, 58, 230],
        fontWeight: 700, fontFamily: "system-ui, -apple-system, Segoe UI, Arial", parameters: {depthTest: false},
        updateTriggers: {getPosition: e, getColor: state.region},
      }));
    }
    const placeAlpha = Math.round(230 * (1 - clamp(e * 3)));
    layers.push(new TextLayer({
      id: "places", data: PLACES, characterSet: CHARS, getPosition: (d) => [d[1], d[2], 4200],
      getText: (d) => d[0], getSize: 12, getColor: [239, 230, 210, placeAlpha], fontWeight: 600,
      fontFamily: "system-ui, -apple-system, Segoe UI, Arial", outlineWidth: 3, outlineColor: [255, 255, 255, placeAlpha],
      fontSettings: {sdf: true}, visible: placeAlpha > 4, parameters: {depthTest: false}, updateTriggers: {getColor: placeAlpha},
    }));
    return layers;
  }

  // ---------- rendering ----------
  let frameReq = 0;
  function renderAll() {
    if (frameReq) return;
    frameReq = requestAnimationFrame(() => {
      frameReq = 0;
      deckgl.setProps({layers: buildLayers()});
      const e = state.eased;
      $("hint").hidden = !!(state.cell || state.region !== "all" || state.drawer);
      $("hint").style.opacity = String(1 - clamp(e * 4));
      document.querySelector(".brand").style.opacity = String(1 - clamp(e * 2.5));
      for (const id of ["controls", "toolbar", "legend"]) {
        const el = $(id);
        el.style.opacity = String(1 - clamp((e - 0.15) * 3));
        el.style.pointerEvents = e > 0.4 ? "none" : "auto";
        el.setAttribute("aria-hidden", e > 0.4 ? "true" : "false");
      }
      $("inspector").style.opacity = String(1 - clamp((e - 0.1) * 4));
      $("inspector").style.pointerEvents = e > 0.3 ? "none" : "auto";
      syncControls(); renderLegend(); renderInspector(); renderStatus(); renderChrome(); placePanels(); updatePanels();
    });
  }

  function syncControls() {
    $("year-out").textContent = state.year;
    $("year").value = state.year;
    $("period-label").textContent = state.layer === "rate" ? "2003–2024 trend" : periodLabel();
    $("region").value = state.region;
    for (const b of $("months").querySelectorAll("button")) {
      const on = String(b.dataset.value) === String(state.month);
      b.setAttribute("aria-checked", on ? "true" : "false"); b.tabIndex = on ? 0 : -1;
    }
    for (const b of $("layers").querySelectorAll("button")) {
      const on = b.dataset.layer === state.layer;
      b.setAttribute("aria-checked", on ? "true" : "false"); b.tabIndex = on ? 0 : -1;
    }
    $("play").textContent = state.playing ? "❚❚" : "▶";
    $("play").setAttribute("aria-label", state.playing ? "Pause playback" : "Play through the years");
    if ($("finding").value !== (state.finding || "")) $("finding").value = state.finding || "";
  }

  function renderLegend() {
    const L = LAYERS[state.layer], box = $("legend");
    const finding = currentFinding();
    box.hidden = !state.legend;
    if (!state.legend) return;
    box.innerHTML = `<div class="legend-title">${esc(L.label)} <span>(${esc(L.unit)})</span></div>
      <div class="legend-bar" style="background:${rampCss(L.ramp)}" aria-hidden="true"></div>
      <div class="legend-scale" aria-hidden="true">${L.ticks.map((t) => `<span>${esc(t)}</span>`).join("")}</div>
      <p class="legend-note">${esc(L.note)}</p>
      ${!reduceMotion && state.layer !== "rate" ? '<p class="legend-note">Changes ease between observed frames; only the settled frame is data.</p>' : ""}
      ${finding ? `<p class="legend-note overlay"><i style="border-color:rgb(${(HIGHLIGHT[finding.highlight] || HIGHLIGHT.none).join(",")})"></i>AI highlight (outline only, not a measurement): ${finding.id === "ask" ? `cells from your question, ${finding.cells.length} outlined.` : `${esc(finding.title)} (${esc(finding.status)}), ${finding.cells.length} cells outlined.`} <button type="button" id="finding-clear">Clear</button></p>` : ""}`;
    $("finding-clear")?.addEventListener("click", () => setState({finding: null}));
  }

  // ---------- toolbar, drawers, reset ----------
  const DRAWERS = {info: ["info-drawer", "tb-info"], compare: ["compare-drawer", "tb-compare"]};
  function renderChrome() {
    for (const [name, [id, btn]] of Object.entries(DRAWERS)) {
      const open = state.drawer === name;
      $(id).hidden = !open;
      $(btn).setAttribute("aria-expanded", open ? "true" : "false");
    }
    $("tb-legend").setAttribute("aria-pressed", state.legend ? "true" : "false");
  }
  function openDrawer(name) {
    const opening = state.drawer !== name;
    setState({drawer: opening ? name : null}, {skipUrl: true});
    if (opening) {
      if (name === "compare") { renderCompare(); renderRegionTest(); }
      requestAnimationFrame(() => $(DRAWERS[name][0]).querySelector(".drawer-close")?.focus());
    }
  }
  function closeDrawer() {
    if (!state.drawer) return;
    const btn = $(DRAWERS[state.drawer][1]);
    setState({drawer: null}, {skipUrl: true});
    btn.focus();
  }
  function selectRegion(q) { setState({region: q, cell: null}); }
  // Reset view: back to the whole, unobstructed map. Year, month and layer are settings, so they stay.
  function resetView() {
    stopPlayback();
    setState({region: "all", cell: null, finding: null, drawer: null});
    document.querySelectorAll(".disc.active").forEach((el) => el.classList.remove("active"));
    deckgl.setProps({initialViewState: fitView()});
    window.scrollTo({top: 0, behavior: reduceMotion ? "auto" : "smooth"});
  }
  function setupChrome() {
    $("tb-info").addEventListener("click", () => openDrawer("info"));
    $("tb-compare").addEventListener("click", () => openDrawer("compare"));
    $("tb-legend").addEventListener("click", () => setState({legend: !state.legend}, {skipUrl: true}));
    $("tb-reset").addEventListener("click", resetView);
    document.querySelectorAll("[data-drawer-close]").forEach((b) => b.addEventListener("click", closeDrawer));
    $("zoom-close").addEventListener("click", closeZoom);
    $("zoom").addEventListener("click", (ev) => { if (ev.target === $("zoom")) closeZoom(); });
    document.addEventListener("keydown", (ev) => {
      if (ev.key !== "Escape" || document.body.classList.contains("touring")) return;
      if (!$("zoom").hidden) { ev.stopPropagation(); closeZoom(); } else if (state.drawer) closeDrawer();
    });
  }

  function renderStatus() {
    const el = $("data-status");
    el.classList.remove("warn");
    if (state.error) {
      el.classList.add("warn");
      el.innerHTML = `We could not load the NASA results (${esc(state.error)}). <button type="button" id="retry">Try again</button>`;
      $("retry").onclick = () => location.reload();
      return;
    }
    if (!state.cells) {
      el.classList.add("warn");
      el.innerHTML = state.cellsError ? `The detailed map is unavailable right now (${esc(state.cellsError)}), so the four area averages are shown instead.` : "Loading the map…";
      return;
    }
    if (state.layer === "rate") {
      el.innerHTML = `<b>${state.cells.filter((c) => c.significant_fdr).length} of ${state.cells.length}</b> squares show a clear warming or cooling pattern.`;
      return;
    }
    if (!state.frame) { el.textContent = state.cellsError ? `We could not load this month (${state.cellsError}). Try another one.` : "Loading…"; return; }
    const shown = state.frame.cells.filter((c) => c.value != null).length;
    el.innerHTML = `<b>${shown} of ${state.frame.cells.length}</b> squares have a reliable reading for ${esc(periodLabel())}.${state.month === "avg" ? " A yearly average needs all 12 months." : ""}`;
  }

  const cellYears = {};   // cell id -> /cell-years result (derived yearly values), fetched on demand
  function cellYearsSvg(id) {
    const d = cellYears[id];
    if (d === undefined) {
      cellYears[id] = null;
      getJSON(`${API}/cell-years?id=${encodeURIComponent(id)}`, true)
        .then((res) => { cellYears[id] = res || {error: true}; if (state.cell === id) renderInspector(); })
        .catch(() => { cellYears[id] = {error: true}; if (state.cell === id) renderInspector(); });
    }
    if (!d) return '<p class="ins-note">Loading the yearly record…</p>';
    if (d.error) return '<p class="ins-note">Yearly record unavailable right now.</p>';
    const W2 = 260, H2 = 92, pad = 4, ys = d.years, n = ys.length, bw = (W2 - 2 * pad) / n;
    const vals = ys.map((y) => y.anomaly).filter((v) => v != null);
    const m = Math.max(1, ...vals.map(Math.abs)), mid = H2 / 2, sc = (H2 / 2 - 6) / m;
    const bars = ys.map((y, i) => {
      const x = pad + i * bw;
      if (y.anomaly == null) return `<rect x="${x + bw * 0.3}" y="${mid - 0.5}" width="${bw * 0.4}" height="1" fill="#9c927d"><title>${y.year}: incomplete year (${y.valid_months} of 12 months)</title></rect>`;
      const h = Math.abs(y.anomaly) * sc;
      return `<rect x="${x + bw * 0.15}" y="${y.anomaly >= 0 ? mid - h : mid}" width="${bw * 0.7}" height="${Math.max(h, 0.8)}" fill="${y.anomaly >= 0 ? "#b3261e" : "#4f6f8f"}"><title>${y.year}: ${fmt(y.value, 2)} °C (${signed(y.anomaly, 2)} vs usual)</title></rect>`;
    }).join("");
    const t = d.trend_line, X = (yr) => pad + (yr - ys[0].year + 0.5) * bw, Y = (a) => mid - a * sc;
    const a0 = t.intercept + t.slope_per_year * (ys[0].year - t.centre_year), a1 = t.intercept + t.slope_per_year * (ys[n - 1].year - t.centre_year);
    return `<svg viewBox="0 0 ${W2} ${H2 + 14}" role="img" aria-label="Yearly mean anomaly bars for cell ${esc(id)}, ${ys[0].year} to ${ys[n - 1].year}">
      <line x1="0" x2="${W2}" y1="${mid}" y2="${mid}" stroke="#b9a67c"/>${bars}
      <line x1="${X(ys[0].year)}" y1="${Y(a0)}" x2="${X(ys[n - 1].year)}" y2="${Y(a1)}" stroke="#2a2418" stroke-width="1.6" stroke-dasharray="4 3"/>
      <text x="${pad}" y="${H2 + 11}" font-size="9" fill="#6b5d40">${ys[0].year}</text><text x="${W2 - pad}" y="${H2 + 11}" font-size="9" fill="#6b5d40" text-anchor="end">${ys[n - 1].year}</text>
      <text x="${W2 - pad}" y="10" font-size="9" fill="#6b5d40" text-anchor="end">±${m.toFixed(1)} °C</text></svg>`;
  }
  let insSig = "", insKey = "";
  function renderInspector() {
    const box = $("inspector");
    const isCell = !!(state.cell && state.cellIndex[state.cell]);
    const key = isCell ? `cell:${state.cell}` : state.region !== "all" && state.regions ? `region:${state.region}` : "";
    const cy = isCell ? cellYears[state.cell] : null;
    const sig = [key, state.year, state.month, state.layer, state.frame ? state.frame.period : "", cy ? (cy.error ? "err" : "ok") : "wait", !!state.cells, !!state.regionStats].join("|");
    if (sig === insSig) return;
    insSig = sig;
    if (key !== insKey) {   // a new subject: fade and rise in (one panel only, never stacked)
      insKey = key;
      if (key && !reduceMotion) { box.classList.remove("pop"); void box.offsetWidth; box.classList.add("pop"); }
    }
    if (!isCell) { renderRegionPanel(box); return; }
    const r = cellRecord(state.cell);
    box.hidden = false; box.dataset.mode = "cell";
    const sigCell = r.q != null && r.significant_fdr, up = r.slope_per_year > 0;
    $("inspector-body").innerHTML = `
      <h3>One 5 km square</h3>
      <p class="ins-sub">Square ${esc(r.id)}, in ${esc(areaName(r.quarter))}. Each square is about 5 km across.</p>
      <p class="ins-main">${r.value == null ? `No reliable reading for ${esc(periodLabel())}.` : `In ${esc(periodLabel())} the ground here was <b>${fmt(r.value, 1)} °C</b> at night.`}
        ${r.anomaly == null ? "" : ` That is <b>${fmt(Math.abs(r.anomaly), 1)} °C ${r.anomaly >= 0 ? "warmer" : "cooler"}</b> than usual for this ${state.month === "avg" ? "place" : "month"}.`}</p>
      <p class="ins-rate">${signed(r.slope_per_year, 3)} °C<small> ${up ? "warmer" : "cooler"} each year, on average since 2003</small></p>
      <p class="ins-sure"><b>How sure are we?</b> ${r.q == null ? "We could not test this square." : sigCell ? "Strong evidence. The pattern still holds after checking every square on the map at once." : "Not enough evidence. This could be chance."}</p>
      <figure class="ins-chart">${cellYearsSvg(r.id)}<figcaption>Each bar is one year: red was warmer than usual for this square, blue cooler. The dashed line is the long-term direction.</figcaption></figure>
      <details class="ins-tech"><summary>Technical details</summary><dl>
        <dt>Location</dt><dd>${r.lat.toFixed(3)}° N, ${Math.abs(r.lon).toFixed(3)}° W</dd>
        <dt>${esc(periodLabel())}</dt><dd>${r.value == null ? "no valid measurement" : `${fmt(r.value, 2)} °C`}</dd>
        <dt>Anomaly</dt><dd>${r.anomaly == null ? "—" : `${signed(r.anomaly, 2)} °C vs usual`}</dd>
        <dt>Valid months in ${state.year}</dt><dd>${r.validInYear ?? "—"} of 12</dd>
        <dt>Trend 2003–2024</dt><dd>${signed(r.slope_per_year, 3)} °C/yr</dd>
        <dt>95% CI</dt><dd>${signed(r.ci_low_per_year, 3)} to ${signed(r.ci_high_per_year, 3)}</dd>
        <dt>Significance</dt><dd>${r.q == null ? "—" : `${r.significant_fdr ? "significant" : "not significant"} (q = ${r.q.toPrecision(2)})`}</dd>
        <dt>Valid months overall</dt><dd>${r.valid_months} of ${r.months}</dd>
        ${urban.inside ? `<dt>Phoenix urban area (c. 2002)</dt><dd>${urban.inside.has(r.id) ? "inside" : "outside"}</dd>` : ""}
      </dl>
      <p class="ins-note">q is the p-value corrected for testing all ${state.cells.length} cells (Benjamini-Hochberg). Seasonal Mann-Kendall and Sen's slope on this cell's own QC'd months.</p></details>
      <p class="ins-actions"><button type="button" id="ins-region">See all of ${esc(areaName(r.quarter))}</button></p>`;
    $("ins-region").addEventListener("click", () => selectRegion(r.quarter));
  }

  // Region case file: everything that used to sit in a separate section per quarter, shown once, on request.
  function monthlySvg(rid) {
    const s = state.series[rid];
    if (!s) return "";
    const W2 = 260, H2 = 84, pad = 4, n = s.times.length;
    const vals = s.values.filter((v) => v != null), lo = Math.min(...vals), hi = Math.max(...vals);
    const X = (i) => pad + (i / (n - 1)) * (W2 - 2 * pad), Y = (v) => pad + (1 - (v - lo) / (hi - lo || 1)) * (H2 - 2 * pad);
    let d = "", pen = false;
    s.values.forEach((v, i) => { if (v == null) { pen = false; return; } d += `${pen ? "L" : "M"}${X(i).toFixed(1)} ${Y(v).toFixed(1)}`; pen = true; });
    const gaps = s.values.map((v, i) => (v == null ? `<line x1="${X(i).toFixed(1)}" x2="${X(i).toFixed(1)}" y1="${pad}" y2="${H2 - pad}" stroke="#b9a67c" stroke-dasharray="2 3"><title>${s.times[i]}: missing (failed quality control)</title></line>` : "")).join("");
    let dot = "";
    if (state.month !== "avg") {
      const i = s.times.indexOf(`${state.year}-${String(state.month).padStart(2, "0")}`);
      if (i >= 0 && s.values[i] != null) dot = `<circle cx="${X(i).toFixed(1)}" cy="${Y(s.values[i]).toFixed(1)}" r="3.5" fill="#b3261e" stroke="#f6edd5" stroke-width="1.5"><title>${esc(periodLabel())}: ${fmt(s.values[i], 2)} °C</title></circle>`;
    }
    return `<svg viewBox="0 0 ${W2} ${H2 + 14}" role="img" aria-label="Monthly quarter average, ${s.times[0]} to ${s.times[n - 1]}; ${n - vals.length} missing months shown as gaps">
      ${gaps}<path d="${d}" fill="none" stroke="#2a2418" stroke-width="1"/>${dot}
      <text x="${pad}" y="${H2 + 11}" font-size="9" fill="#6b5d40">${s.times[0].slice(0, 4)}</text><text x="${W2 - pad}" y="${H2 + 11}" font-size="9" fill="#6b5d40" text-anchor="end">${s.times[n - 1].slice(0, 4)}</text>
      <text x="${W2 / 2}" y="${H2 + 11}" font-size="9" fill="#6b5d40" text-anchor="middle">${fmt(lo, 1)} to ${fmt(hi, 1)} °C</text></svg>`;
  }
  // Strength of evidence: the published p-value of each area on one scale (further right = stronger).
  // Same numbers in the compact and the large view; nothing is recomputed.
  const SUP = {"-": "⁻", 0: "⁰", 1: "¹", 2: "²", 3: "³", 4: "⁴", 5: "⁵", 6: "⁶", 7: "⁷", 8: "⁸", 9: "⁹"};
  const pow10 = (k) => "10" + String(k).split("").map((ch) => SUP[ch]).join("");
  const pExact = (p) => { const [m, e] = p.toExponential(1).split("e"); return +e > -3 ? String(+p.toPrecision(2)) : `${m} × ${pow10(+e)}`; };
  function pvalRows() {
    return [state.quarterIds.whole, ...ORDER.map((q) => state.quarterIds[q])].map((id) => state.regions.find((r) => r.region_id === id)).filter(Boolean)
      .map((r) => ({id: r.region_id, name: r.region_id === state.quarterIds.whole ? "Whole study area" : areaName(quarterOfRegion(r.region_id)), p: r.trend.p}));
  }
  function pvalSvg(rid, big) {
    const rows = pvalRows(), L10 = (p) => -Math.log10(Math.max(p, 1e-300));
    const maxX = Math.max(4, Math.ceil(Math.max(...rows.map((r) => L10(r.p))) + 1));
    const ticks = [[0, "1"], [L10(0.05), "0.05"], [3, "0.001"]]; for (let k = 6; k <= maxX; k += 3) ticks.push([k, pow10(-k)]);
    if (!big) {
      const W2 = 260, H2 = 58, x0 = 8, x1 = W2 - 8, X = (v) => x0 + (v / maxX) * (x1 - x0), tx = X(L10(0.05));
      return `<svg viewBox="0 0 ${W2} ${H2}" role="img" aria-label="Strength of evidence for each area; all values are listed in the enlarged view">
        <rect x="${x0}" y="14" width="${(tx - x0).toFixed(1)}" height="20" fill="#d9c9a0"/><line x1="${x0}" x2="${x1}" y1="24" y2="24" stroke="#b9a67c"/>
        <line x1="${tx.toFixed(1)}" x2="${tx.toFixed(1)}" y1="8" y2="40" stroke="#2a2418" stroke-dasharray="3 3"/>
        ${rows.map((r) => `<circle cx="${X(L10(r.p)).toFixed(1)}" cy="24" r="${r.id === rid ? 6 : 4}" fill="${r.id === rid ? "#b3261e" : "#7a6a45"}" stroke="#f6edd5" stroke-width="1.5"><title>${esc(r.name)}: ${pText(r.p)}</title></circle>`).join("")}
        <text x="${x0}" y="53" font-size="9" fill="#6b5d40">could be chance</text><text x="${x1}" y="53" font-size="9" fill="#6b5d40" text-anchor="end">stronger evidence →</text></svg>`;
    }
    const W2 = 900, rowH = 46, x0 = 210, x1 = W2 - 150, top = 30, H2 = top + rows.length * rowH + 70, X = (v) => x0 + (v / maxX) * (x1 - x0), tx = X(L10(0.05));
    return `<svg viewBox="0 0 ${W2} ${H2}" role="img" aria-label="p-value of the warming trend for each area on a logarithmic axis, with the 0.05 threshold marked">
      <rect x="${x0}" y="${top - 8}" width="${(tx - x0).toFixed(1)}" height="${rows.length * rowH + 8}" fill="#2a2620"/>
      <line x1="${tx.toFixed(1)}" x2="${tx.toFixed(1)}" y1="${top - 8}" y2="${top + rows.length * rowH}" stroke="#e0a43a" stroke-dasharray="5 4"/>
      <text x="${(tx + 8).toFixed(1)}" y="${top - 14}" font-size="12" fill="#e0a43a">threshold p = 0.05 (left of this line could be chance)</text>
      ${rows.map((r, i) => { const y = top + i * rowH + rowH / 2, on = r.id === rid; return `
        <text x="${x0 - 14}" y="${y + 5}" font-size="14" fill="${on ? "#efe6d2" : "#cfc4ad"}" text-anchor="end" font-weight="${on ? 700 : 400}">${esc(r.name)}</text>
        <line x1="${x0}" x2="${X(L10(r.p)).toFixed(1)}" y1="${y}" y2="${y}" stroke="${on ? "#c8372d" : "#7a6a45"}" stroke-width="3"/>
        <circle cx="${X(L10(r.p)).toFixed(1)}" cy="${y}" r="${on ? 8 : 6}" fill="${on ? "#c8372d" : "#9c927d"}"/>
        <text x="${(X(L10(r.p)) + 14).toFixed(1)}" y="${y + 5}" font-size="13" fill="#efe6d2">p = ${pExact(r.p)}</text>`; }).join("")}
      <line x1="${x0}" x2="${x1}" y1="${top + rows.length * rowH}" y2="${top + rows.length * rowH}" stroke="#6b6557"/>
      ${ticks.map(([v, l]) => `<line x1="${X(v).toFixed(1)}" x2="${X(v).toFixed(1)}" y1="${top + rows.length * rowH}" y2="${top + rows.length * rowH + 6}" stroke="#6b6557"/><text x="${X(v).toFixed(1)}" y="${top + rows.length * rowH + 22}" font-size="12" fill="#9c927d" text-anchor="middle">${l}</text>`).join("")}
      <text x="${(x0 + x1) / 2}" y="${H2 - 12}" font-size="13" fill="#cfc4ad" text-anchor="middle">p-value: smaller (further right) means stronger evidence</text></svg>`;
  }
  // Large temperature graph: the same monthly measurements as the compact one, with axes and yearly averages.
  function tempBigSvg(rid) {
    const s = state.series[rid];
    if (!s) return "";
    const W2 = 900, H2 = 440, x0 = 64, x1 = W2 - 20, y0 = 20, y1 = H2 - 64, n = s.times.length;
    const vals = s.values.filter((v) => v != null), lo = Math.floor(Math.min(...vals) / 5) * 5, hi = Math.ceil(Math.max(...vals) / 5) * 5;
    const X = (i) => x0 + (i / (n - 1)) * (x1 - x0), Y = (v) => y1 - ((v - lo) / (hi - lo || 1)) * (y1 - y0);
    let d = "", pen = false;
    s.values.forEach((v, i) => { if (v == null) { pen = false; return; } d += `${pen ? "L" : "M"}${X(i).toFixed(1)} ${Y(v).toFixed(1)}`; pen = true; });
    const years = [...new Set(s.times.map((t) => +t.slice(0, 4)))];
    const yTicks = []; for (let v = lo; v <= hi; v += 5) yTicks.push(v);
    const grid = yTicks.map((v) => `<line x1="${x0}" x2="${x1}" y1="${Y(v).toFixed(1)}" y2="${Y(v).toFixed(1)}" stroke="#34322d"/><text x="${x0 - 10}" y="${(Y(v) + 4).toFixed(1)}" font-size="12" fill="#9c927d" text-anchor="end">${v}</text>`).join("");
    const xt = years.filter((y) => (y - years[0]) % 3 === 0).map((y) => { const i = s.times.indexOf(`${y}-01`); return i < 0 ? "" : `<line x1="${X(i).toFixed(1)}" x2="${X(i).toFixed(1)}" y1="${y1}" y2="${y1 + 6}" stroke="#6b6557"/><text x="${X(i).toFixed(1)}" y="${y1 + 22}" font-size="12" fill="#9c927d" text-anchor="middle">${y}</text>`; }).join("");
    const gaps = s.values.map((v, i) => (v == null ? `<line x1="${X(i).toFixed(1)}" x2="${X(i).toFixed(1)}" y1="${y0}" y2="${y1}" stroke="#e0a43a" stroke-dasharray="2 4" opacity=".7"><title>${s.times[i]}: no reliable reading</title></line>` : "")).join("");
    const pts = s.values.map((v, i) => (v == null ? "" : `<circle cx="${X(i).toFixed(1)}" cy="${Y(v).toFixed(1)}" r="5" fill="transparent"><title>${s.times[i]}: ${fmt(v, 2)} °C</title></circle>`)).join("");
    const yr = years.map((y) => ({y, v: periodValue(s.times, s.values, y, "avg"), i: s.times.indexOf(`${y}-07`)})).filter((o) => o.v != null && o.i >= 0);
    const yrLine = yr.map((o, k) => `${k ? "L" : "M"}${X(o.i).toFixed(1)} ${Y(o.v).toFixed(1)}`).join("");
    const yrDots = yr.map((o) => `<circle cx="${X(o.i).toFixed(1)}" cy="${Y(o.v).toFixed(1)}" r="4.5" fill="#c8372d" stroke="#141518" stroke-width="1.5"><title>${o.y} yearly average: ${fmt(o.v, 2)} °C</title></circle>`).join("");
    let dot = "";
    if (state.month !== "avg") { const i = s.times.indexOf(`${state.year}-${String(state.month).padStart(2, "0")}`); if (i >= 0 && s.values[i] != null) dot = `<circle cx="${X(i).toFixed(1)}" cy="${Y(s.values[i]).toFixed(1)}" r="6" fill="none" stroke="#e0a43a" stroke-width="2.5"><title>${esc(periodLabel())}: ${fmt(s.values[i], 2)} °C (the month on the map)</title></circle>`; }
    return `<svg viewBox="0 0 ${W2} ${H2}" role="img" aria-label="Monthly night-time ground temperature, ${s.times[0]} to ${s.times[n - 1]}, in degrees Celsius, with yearly averages">
      ${grid}${gaps}<line x1="${x0}" x2="${x1}" y1="${y1}" y2="${y1}" stroke="#6b6557"/>${xt}
      <path d="${d}" fill="none" stroke="#9c927d" stroke-width="1.3"/><path d="${yrLine}" fill="none" stroke="#c8372d" stroke-width="2.5"/>${yrDots}${dot}${pts}
      <text x="16" y="${(y0 + y1) / 2}" font-size="13" fill="#cfc4ad" text-anchor="middle" transform="rotate(-90 16 ${(y0 + y1) / 2})">Ground temperature at night (°C)</text>
      <text x="${(x0 + x1) / 2}" y="${H2 - 18}" font-size="13" fill="#cfc4ad" text-anchor="middle">Year</text></svg>
      <p class="eng-key"><i style="background:#9c927d"></i>each month's measurement<i style="background:#c8372d"></i>yearly average (full years only)<i style="background:#e0a43a"></i>month with no reliable reading</p>`;
  }
  let zoomFrom = null;
  function zoomBody(kind, rid) {
    const q = quarterOfRegion(rid), r = state.regions.find((x) => x.region_id === rid), t = r.trend, st = state.regionStats?.regions?.[rid] || {};
    const s = state.series[rid], months = s ? s.times.length : 264, name = q ? areaName(q) : "Whole study area";
    const tiles = (rows) => `<div class="answer-stats">${rows.map((x, i) => `<div class="tile t${i}"><span class="tile-label">${esc(x[0])}</span><b class="tile-value">${esc(x[1])}</b><span class="tile-sub">${esc(x[2])}</span></div>`).join("")}</div>`;
    if (kind === "temp") {
      return `<h2 id="zoom-title">${esc(name)}: how hot the ground is at night</h2>
        <figure class="eng-viz">${tempBigSvg(rid)}</figure>
        ${tiles([["Change each year", `${signed(t.slope * 12, 3)} °C`, "on average (Sen's slope)"], ["Likely range", st.ci_low_per_year != null ? `${signed(st.ci_low_per_year, 3)} to ${signed(st.ci_high_per_year, 3)}` : "—", "°C a year, 95% confidence"],
          ["Over the whole period", `≈ ${signed(t.slope * months, 1)} °C`, "yearly change × years"], ["How sure", sureShort(t.p), `${pText(t.p)}, τ ${t.tau.toFixed(2)}`]])}
        <p class="zoom-text">The grey line is every monthly measurement: it goes up each summer and down each winter. The red line joins the yearly averages, so you can see the slow rise underneath. Hover a point for its exact value. ${st.valid_months != null ? `${st.valid_months} of ${st.months ?? months} months have a reliable reading; ` : ""}missing months are left empty, never filled in.</p>
        <p class="note">The long-term change is tested with a seasonal Mann-Kendall test, which compares each month only with the same month in other years. The published result is a yearly rate, so no fitted line is drawn here.</p>`;
    }
    return `<h2 id="zoom-title">How strong is the evidence?</h2>
      <figure class="eng-viz">${pvalSvg(rid, true)}</figure>
      ${tiles([[name, pExact(t.p), "its p-value"], ["Threshold", "0.05", "below this counts as a real pattern"], ["Verdict", sureShort(t.p), t.p < 0.05 ? "unlikely to be chance" : "could be chance"]])}
      <p class="zoom-text">A p-value answers one question: if nothing were really changing, how often would we see a pattern this strong just by luck? A small p-value means "almost never", so the warming is very unlikely to be an accident. Anything left of the dashed line (above 0.05) could be chance. The scale is stretched (each step is 1,000 times smaller) because these values are tiny.</p>
      <p class="note">p-values come from the seasonal Mann-Kendall test on each area's monthly averages, as published by the project's analysis. A small p-value shows the warming is real; it does not show how large it is or what causes it.</p>`;
  }
  function openZoom(kind, rid, fromEl) {
    const layer = $("zoom"), box = $("zoom-box");
    state.zoom = {kind, rid}; zoomFrom = fromEl;
    $("zoom-body").innerHTML = zoomBody(kind, rid);
    layer.hidden = false;
    const a = fromEl.getBoundingClientRect(), b = box.getBoundingClientRect();
    if (!reduceMotion && b.width) {   // grow from where the small graph sits
      box.style.transition = "none"; box.style.transformOrigin = "top left";
      box.style.transform = `translate(${a.left - b.left}px, ${a.top - b.top}px) scale(${a.width / b.width}, ${a.height / b.height})`; box.style.opacity = "0.4";
      void box.offsetWidth;
      box.style.transition = ""; box.style.transform = ""; box.style.opacity = "";
    }
    requestAnimationFrame(() => layer.classList.add("open"));
    $("zoom-close").focus({preventScroll: true});
  }
  function closeZoom() {
    const layer = $("zoom"), box = $("zoom-box");
    if (layer.hidden) return;
    const from = zoomFrom && document.body.contains(zoomFrom) ? zoomFrom : document.querySelector(`.zoomable[data-zoom="${state.zoom?.kind}"]`);
    layer.classList.remove("open");
    const done = () => { layer.hidden = true; box.style.transform = ""; box.style.opacity = ""; state.zoom = null; from?.focus({preventScroll: true}); };
    if (reduceMotion || !from) { done(); return; }
    const a = from.getBoundingClientRect(), b = box.getBoundingClientRect();
    box.style.transformOrigin = "top left";
    box.style.transform = `translate(${a.left - b.left}px, ${a.top - b.top}px) scale(${a.width / b.width}, ${a.height / b.height})`; box.style.opacity = "0";
    setTimeout(done, 360);
  }

  function renderRegionPanel(box) {
    const q = state.region, rid = q !== "all" && state.quarterIds[q];
    const r = rid && state.regions?.find((x) => x.region_id === rid);
    if (!r) { box.hidden = true; return; }
    const t = r.trend, st = state.regionStats?.regions?.[rid] || {}, perYear = t.slope * 12, sig = t.p < 0.05;
    const s = state.series[rid], months = s ? s.times.length : 264;
    const val = s ? periodValue(s.times, s.values, state.year, state.month) : null;
    const quarters = ORDER.map((k) => state.regions.find((x) => x.region_id === state.quarterIds[k])).filter(Boolean);
    const fastest = quarters.reduce((a, b) => (b.trend.slope > a.trend.slope ? b : a), quarters[0]);
    const inQ = state.cells ? state.cells.filter((c) => c.quarter === q) : [];
    const sigCells = inQ.filter((c) => c.significant_fdr).length;
    const rates = inQ.map((c) => c.slope_per_year).filter((v) => v != null);
    const shown = state.frame ? inQ.filter((c) => state.frame.byId[c.id]?.value != null).length : null;
    box.hidden = false; box.dataset.mode = "region";
    const years = Math.round(months / 12);
    $("inspector-body").innerHTML = `
      <h3>${esc(areaName(q))}</h3>
      <p class="ins-sub">${esc(whereText(q))}${r === fastest && sig && t.slope > 0 ? ' <b class="stamp">warming fastest</b>' : ""}</p>
      <p class="ins-main">${esc(happened(t.trend, t.p))}</p>
      <p class="ins-rate">${signed(perYear, 3)} °C<small> ${perYear >= 0 ? "warmer" : "cooler"} each year, on average</small></p>
      <p class="ins-main">That adds up to about <b>${signed(t.slope * months, 1)} °C</b> over ${years} years (${s ? s.times[0].slice(0, 4) : 2003}–${s ? s.times[months - 1].slice(0, 4) : 2024}).</p>
      <p class="ins-sure"><b>How sure are we?</b> ${esc(sureText(t.p))}${st.ci_low_per_year != null ? ` The yearly change is most likely between ${signed(st.ci_low_per_year, 3)} and ${signed(st.ci_high_per_year, 3)} °C.` : ""}</p>
      <p class="ins-main">${val == null ? `No reliable average for ${esc(periodLabel())}.` : `In ${esc(periodLabel())} the ground here averaged <b>${fmt(val, 1)} °C</b> at night.`}</p>
      <button type="button" class="ins-chart zoomable" data-zoom="temp" aria-label="Enlarge the temperature graph for ${esc(areaName(q))}">${monthlySvg(rid)}<span class="zoom-cap"><b>Temperature, every month since 2003.</b> The big swings are summer and winter. <i>Click to enlarge</i></span></button>
      <button type="button" class="ins-chart zoomable" data-zoom="pval" aria-label="Enlarge the strength-of-evidence graph">${pvalSvg(rid, false)}<span class="zoom-cap"><b>How strong is the evidence?</b> Further right is stronger. The red dot is this area. <i>Click to enlarge</i></span></button>
      <details class="ins-tech"><summary>Technical details</summary><dl>
        <dt>Sen's slope</dt><dd>${signed(perYear, 3)} °C/yr</dd>
        <dt>95% CI</dt><dd>${st.ci_low_per_year != null ? `${signed(st.ci_low_per_year, 3)} to ${signed(st.ci_high_per_year, 3)}` : "—"}</dd>
        <dt>Significance</dt><dd>${sig ? "significant" : "not significant"} (${pText(t.p)})</dd>
        <dt>Kendall's τ</dt><dd>${t.tau.toFixed(2)}</dd>
        <dt>${esc(periodLabel())}, area avg</dt><dd>${val == null ? "no valid value" : `${fmt(val, 2)} °C`}</dd>
        <dt>Valid months</dt><dd>${st.valid_months ?? "—"} of ${st.months ?? months}</dd>
        ${shown != null && state.layer !== "rate" ? `<dt>Cells measured, ${esc(periodLabel())}</dt><dd>${shown} of ${inQ.length}</dd>` : ""}
        ${rates.length ? `<dt>Cell trends in this area</dt><dd>${signed(Math.min(...rates), 3)} to ${signed(Math.max(...rates), 3)} °C/yr</dd><dt>Cells significant (FDR)</dt><dd>${sigCells} of ${inQ.length}</dd>` : ""}
      </dl>
      <p class="ins-note">Seasonal Mann-Kendall test with seasonal Sen's slope on the area's monthly averages (${inQ.length || 48} grid cells). "Over the period" is a trend-line estimate, not a measured difference.</p></details>
      <p class="ins-actions"><button type="button" id="ins-compare">Compare with another area</button><button type="button" id="ins-method">How we know</button></p>`;
    box.querySelectorAll(".zoomable").forEach((b) => b.addEventListener("click", () => openZoom(b.dataset.zoom, rid, b)));
    $("ins-compare").addEventListener("click", () => {
      state.rtA = rid; if (state.rtB === rid) state.rtB = state.quarterIds.whole;
      $("rt-a").value = state.rtA; $("rt-b").value = state.rtB;
      if (state.drawer !== "compare") openDrawer("compare"); else renderRegionTest();
    });
    $("ins-method").addEventListener("click", () => { if (state.drawer !== "info") openDrawer("info"); });
  }

  // ---------- scroll ----------
  function onScroll() {
    const stage = $("stage"), vh = window.innerHeight;
    const travelled = -stage.getBoundingClientRect().top;
    const raw = clamp((travelled - 0.3 * vh) / (1.5 * vh));
    const p = reduceMotion ? (raw > 0.5 ? 1 : 0) : raw;
    if (state.playing && travelled > 2.4 * vh) stopPlayback();   // left the map section
    if (p === state.progress) return;
    state.progress = p;
    state.eased = reduceMotion ? p : easeInOut(p);
    renderAll();
  }

  // ---------- playback (one timer at most) ----------
  let timer = null;
  function stopPlayback() {
    if (timer) clearInterval(timer);
    timer = null;
    if (state.playing) setState({playing: false}, {skipUrl: true});
  }
  function startPlayback() {
    if (timer) return;
    if (state.layer === "rate") setState({layer: "temperature"});
    const yr = $("year");
    if (state.year >= +yr.max) setState({year: +yr.min}); else setState({playing: true}, {skipUrl: true});
    state.playing = true;
    timer = setInterval(() => {
      const next = state.year + 1;
      if (next > +yr.max) { stopPlayback(); return; }
      loadFrame(next, state.month).catch(() => {});
      setState({year: next});
      showPeriod();
      loadFrame(Math.min(next + 1, +yr.max), state.month).catch(() => {});   // prefetch
    }, state.speed);
    renderAll();
  }
  document.addEventListener("visibilitychange", () => { if (document.hidden) stopPlayback(); });

  // ---------- regional panels ----------
  function placePanels() {
    const e = state.eased, o = clamp((e - 0.72) / 0.28);
    const vp = new WebMercatorViewport({...state.view, width: $("map").clientWidth, height: $("map").clientHeight});
    for (const q of ORDER) {
      const el = document.getElementById(`panel-${q}`);
      if (!el) continue;
      const {f} = pieceTransform(q, e);
      const [w, s, ea, n] = QUARTERS[q].b;
      const pts = [[w, s], [ea, s], [ea, n], [w, n]].map((pt) => vp.project(f(pt)));
      const xs = pts.map((pt) => pt[0]), ys = pts.map((pt) => pt[1]);
      const left = Math.min(...xs), right = Math.max(...xs), top = Math.min(...ys), bottom = Math.max(...ys);
      let x, y, width;
      if (layoutMode() === "tall") {
        width = Math.max(150, right - left); el.style.width = `${width}px`; x = left; y = bottom + 8;
      } else {
        const gap = 16, half = window.innerWidth / 2;
        width = Math.min(310, Math.max(210, (q.endsWith("W") ? half - right : left - half) - 1.5 * gap));
        el.style.width = `${width}px`;
        const h = el.offsetHeight || 200;
        x = q.endsWith("W") ? right + gap : left - gap - width;
        y = q.startsWith("N") ? top : bottom - h;
      }
      const h = el.offsetHeight || 200;
      el.style.left = `${clamp(x, 8, window.innerWidth - width - 8)}px`;
      el.style.top = `${clamp(y, 8, window.innerHeight - h - 8)}px`;
      el.style.opacity = String(o);
      el.style.transform = `translateY(${(1 - o) * 6}px)`;
      el.style.visibility = o > 0.01 ? "visible" : "hidden";
      el.setAttribute("aria-hidden", o > 0.5 ? "false" : "true");
      el.classList.toggle("selected", state.region === q);
    }
  }

  function yearlyAnomalyMeans(rid) {
    const a = state.anomaly[rid];
    if (!a) return [];
    return [...new Set(a.times.map((t) => t.slice(0, 4)))].map((y) => ({y, v: periodValue(a.times, a.values, y, "avg")}));
  }
  function sparkSVG(rid) {
    const bars = yearlyAnomalyMeans(rid);
    if (!bars.length) return "";
    const W2 = 240, H2 = 44, max = Math.max(0.5, ...bars.map((b) => Math.abs(b.v || 0))), bw = W2 / bars.length, mid = H2 / 2;
    const rects = bars.map((b, i) => {
      if (b.v == null) return `<rect x="${i * bw + bw * 0.2}" y="${mid - 0.5}" width="${bw * 0.6}" height="1" fill="#9c927d"><title>${b.y}: incomplete year</title></rect>`;
      const h = (Math.abs(b.v) / max) * (mid - 2), y = b.v >= 0 ? mid - h : mid;
      return `<rect x="${i * bw + bw * 0.15}" y="${y}" width="${bw * 0.7}" height="${Math.max(h, 0.8)}" fill="${b.v >= 0 ? "#b3261e" : "#4f6f8f"}"><title>${b.y}: ${signed(b.v, 2)} °C vs average</title></rect>`;
    }).join("");
    return `<svg viewBox="0 0 ${W2} ${H2}" preserveAspectRatio="none" role="img" aria-label="Yearly mean anomaly bars, 2003 to 2024"><line x1="0" x2="${W2}" y1="${mid}" y2="${mid}" stroke="#b9a67c"/>${rects}</svg>`;
  }

  function buildPanels() {
    const host = $("panels");
    host.innerHTML = "";
    const stats = state.regionStats?.regions || {};
    const quarterRegions = ORDER.map((q) => state.regions.find((r) => r.region_id === state.quarterIds[q])).filter(Boolean);
    const fastest = quarterRegions.reduce((a, b) => (b.trend.slope > a.trend.slope ? b : a), quarterRegions[0]);
    for (const q of ORDER) {
      const r = state.regions.find((x) => x.region_id === state.quarterIds[q]);
      if (!r) continue;
      const t = r.trend, st = stats[r.region_id] || {}, perYear = t.slope * 12, sig = t.p < 0.05;
      const isFastest = r === fastest && t.slope > 0 && sig;
      const el = document.createElement("article");
      el.className = `panel q-${q}` + (isFastest ? " fastest" : "");
      el.id = `panel-${q}`;
      el.tabIndex = 0;
      el.setAttribute("aria-label", `${areaName(q)}; select to focus this area`);
      el.innerHTML = `
        <div class="panel-head"><h3>${QUARTERS[q].name}</h3>${isFastest ? '<span class="tag">Warming fastest</span>' : ""}</div>
        <p class="rate${perYear < 0 ? " cool" : ""}">${signed(perYear, 3)} °C<small>${perYear >= 0 ? "warmer" : "cooler"} each year</small></p>
        <p class="ci">${st.ci_low_per_year != null ? `Most likely between ${signed(st.ci_low_per_year, 3)} and ${signed(st.ci_high_per_year, 3)}` : ""}</p>
        <p class="sig">How sure? ${sureShort(t.p).replace(/^./, (ch) => ch.toUpperCase())}.</p>
        ${sparkSVG(r.region_id)}
        <div class="spark-cap"><span>2003</span><span>one bar per year; red = warmer</span><span>2024</span></div>
        <dl><dt id="pl-${q}">—</dt><dd id="pv-${q}">—</dd><dt>Months with data</dt><dd>${st.valid_months ?? "—"} of ${st.months ?? 264}</dd></dl>`;
      el.addEventListener("click", () => selectRegion(state.region === q ? "all" : q));
      el.addEventListener("keydown", (ev) => { if (ev.key === "Enter" || ev.key === " ") { ev.preventDefault(); el.click(); } });
      host.appendChild(el);
    }
  }
  function updatePanels() {
    for (const q of ORDER) {
      const rid = state.quarterIds[q], s = rid && state.series[rid];
      const l = document.getElementById(`pl-${q}`), v = document.getElementById(`pv-${q}`);
      if (!l || !s) continue;
      l.textContent = `${periodLabel()}, average`;
      const val = periodValue(s.times, s.values, state.year, state.month);
      v.textContent = val == null ? "no reading" : `${fmt(val)} °C`;
    }
  }

  // ---------- controls ----------
  function buildControls(years) {
    const yr = $("year");
    yr.min = years[0]; yr.max = years[years.length - 1];
    state.year = clamp(state.year, +yr.min, +yr.max);
    yr.disabled = false;
    $("year-min").textContent = yr.min; $("year-max").textContent = yr.max;
    yr.addEventListener("input", () => { stopPlayback(); setState({year: +yr.value}); showPeriod(); });
    $("prev").addEventListener("click", () => { stopPlayback(); setState({year: Math.max(+yr.min, state.year - 1)}); showPeriod(); });
    $("next").addEventListener("click", () => { stopPlayback(); setState({year: Math.min(+yr.max, state.year + 1)}); showPeriod(); });
    $("play").addEventListener("click", () => (state.playing ? stopPlayback() : startPlayback()));
    $("speed").addEventListener("change", () => { state.speed = +$("speed").value; if (state.playing) { stopPlayback(); startPlayback(); } });
    $("region").addEventListener("change", () => selectRegion($("region").value));
    const host = $("months");
    for (const [val, label] of [["avg", "Annual avg"], ...MONTHS.map((m, i) => [i + 1, m])]) {
      const b = document.createElement("button");
      b.type = "button"; b.textContent = label; b.dataset.value = val; b.setAttribute("role", "radio");
      if (val === "avg") b.className = "avg";
      b.addEventListener("click", () => { setState({month: val === "avg" ? "avg" : +val}); showPeriod(); });
      host.appendChild(b);
    }
    for (const group of [host, $("layers")]) {
      group.addEventListener("keydown", (ev) => {
        if (!["ArrowLeft", "ArrowRight", "ArrowUp", "ArrowDown"].includes(ev.key)) return;
        const btns = [...group.querySelectorAll("button")], i = btns.indexOf(document.activeElement);
        if (i < 0) return;
        ev.preventDefault();
        const next = btns[(i + (ev.key === "ArrowLeft" || ev.key === "ArrowUp" ? -1 : 1) + btns.length) % btns.length];
        next.focus(); next.click();
      });
    }
    for (const b of $("layers").querySelectorAll("button")) b.addEventListener("click", () => setState({layer: b.dataset.layer}));
    $("inspector-close").addEventListener("click", () => setState(state.cell ? {cell: null} : {region: "all"}));
    $("share").addEventListener("click", async () => {
      writeUrl();
      try { await navigator.clipboard.writeText(location.href); $("share").textContent = "Link copied"; }
      catch { $("share").textContent = "Copy from the address bar"; }
      setTimeout(() => { $("share").textContent = "Copy link to this view"; }, 2000);
    });
    $("csv").addEventListener("click", downloadCsv);
    $("png").addEventListener("click", downloadPng);
    $("map").addEventListener("keydown", onMapKey);
    setupNav(); setupChrome();
  }

  // ---------- map image (PNG) ----------
  function downloadPng() {
    const btn = $("png");
    try {
      deckgl.redraw("png-export");                 // draw now, then copy in the same task (before the buffer clears)
      const src = deckgl.getCanvas ? deckgl.getCanvas() : deckgl.canvas;
      const k = src.width / (src.clientWidth || src.width);
      const cw = src.clientWidth || src.width;   // crop away the strip under the control panel on wide screens
      const sx = cw >= 900 && state.eased < 0.2 ? Math.round((($("controls").getBoundingClientRect().right || 0) + 8) * k) : 0;
      const sw = src.width - sx, head = 78 * k, foot = 74 * k;
      const out = document.createElement("canvas");
      out.width = Math.max(sw, 900 * k); out.height = src.height + head + foot;
      const g = out.getContext("2d");
      g.fillStyle = "#141518"; g.fillRect(0, 0, out.width, out.height);
      g.drawImage(src, sx, 0, sw, src.height, 0, head, sw, src.height);
      const L = LAYERS[state.layer];
      g.fillStyle = "#efe6d2"; g.font = `${26 * k}px "Special Elite", monospace`;
      g.fillText("Phoenix nighttime land surface temperature", 24 * k, 36 * k);
      g.fillStyle = "#e0a43a"; g.font = `bold ${15 * k}px "Courier Prime", monospace`;
      g.fillText(`${L.label} · ${state.layer === "rate" ? "2003–2024 trend" : periodLabel()} · ${state.region === "all" ? "All Phoenix" : QUARTERS[state.region].name}`, 24 * k, 62 * k);
      const y0 = head + src.height + 16 * k, bw = 220 * k;
      const grad = g.createLinearGradient(24 * k, 0, 24 * k + bw, 0);
      L.ramp.forEach((c, i) => grad.addColorStop(i / (L.ramp.length - 1), `rgb(${c.join(",")})`));
      g.fillStyle = grad; g.fillRect(24 * k, y0, bw, 10 * k);
      g.fillStyle = "#cfc4ad"; g.font = `${12 * k}px "Courier Prime", monospace`;
      L.ticks.forEach((t, i) => { const x = 24 * k + bw * i / (L.ticks.length - 1); g.textAlign = i === 0 ? "left" : i === L.ticks.length - 1 ? "right" : "center"; g.fillText(t, x, y0 + 26 * k); });
      g.textAlign = "left"; g.fillStyle = "#9c927d";
      g.font = `${11 * k}px "Courier Prime", monospace`;
      g.fillText("Data: NASA Terra MODIS MOD11C3 v061 LST_Night_CMG (phoenix-qc-v1.0); failed-QC months never filled.", 264 * k, y0 + 8 * k);
      g.fillText("Basemap © Esri, HERE, Garmin, OpenStreetMap · Earth System Trend Detective, NASA Space Apps 2026", 264 * k, y0 + 26 * k);
      out.toBlob((blob) => {
        if (!blob) throw new Error("empty image");
        const a = document.createElement("a");
        a.href = URL.createObjectURL(blob);
        a.download = `estd_phoenix_${state.layer}_${state.layer === "rate" ? "trend" : (state.frame?.period || "map").replace(/\s+/g, "_")}.png`;
        a.click(); setTimeout(() => URL.revokeObjectURL(a.href), 1000);
        btn.textContent = "Image downloaded"; setTimeout(() => { btn.textContent = "Download map image (PNG)"; }, 2000);
      }, "image/png");
    } catch (err) {
      console.warn("PNG export failed:", err);
      btn.textContent = "Image export blocked by the browser"; setTimeout(() => { btn.textContent = "Download map image (PNG)"; }, 3000);
    }
  }

  // ---------- keyboard: arrow keys move between the cells drawn on the map ----------
  function onMapKey(ev) {
    const steps = {ArrowUp: [-1, 0], ArrowDown: [1, 0], ArrowLeft: [0, -1], ArrowRight: [0, 1]};
    if (ev.key === "Escape") {
      if (!$("zoom").hidden) return;
      if (state.cell) { setState({cell: null}); $("cell-live").textContent = "Cell closed."; }
      else if (state.region !== "all") { setState({region: "all"}); $("cell-live").textContent = "Region closed."; }
      return;
    }
    if (!(ev.key in steps) && ev.key !== "Enter" && ev.key !== " ") return;
    if (!state.cells) return;
    ev.preventDefault();
    const shown = (id) => !!state.cellIndex[id] && (!urban.inside || urban.inside.has(id));
    const id2 = (r, c) => `r${String(r).padStart(2, "0")}_c${String(c).padStart(2, "0")}`;
    let cur = state.cell && shown(state.cell) ? state.cell : null;
    if (!cur) {   // start downtown (or the first drawn cell)
      const start = shown("r07_c06") ? "r07_c06" : state.cells.map((c) => c.id).find(shown);
      return selectByKey(start);
    }
    if (!(ev.key in steps)) return selectByKey(cur);
    const [dr, dc] = steps[ev.key];
    let r = +cur.slice(1, 3), c = +cur.slice(5, 7);
    for (let k = 1; k < 16; k++) {
      const rr = r + dr * k, cc = c + dc * k;
      if (rr < 0 || rr > 11 || cc < 0 || cc > 15) break;
      if (shown(id2(rr, cc))) return selectByKey(id2(rr, cc));
    }
    $("cell-live").textContent = "Edge of the map.";
  }
  function selectByKey(id) {
    if (!id) return;
    setState({cell: id});
    const r = cellRecord(id), L = LAYERS[state.layer];
    const v = layerValue(r);
    $("cell-live").textContent = `Cell ${id}, ${QUARTERS[r.quarter].name} quarter. ${L.label}: ${v == null ? "no valid value" : `${fmt(v, state.layer === "rate" ? 3 : 1)} ${L.unit}`}.`;
  }

  // ---------- section menu ----------
  function setupNav() {
    const nav = $("case-nav");
    const go = (where) => {
      const smooth = reduceMotion ? "auto" : "smooth";
      if (where === "map") window.scrollTo({top: 0, behavior: smooth});
      else if (where === "quarters") window.scrollTo({top: $("stage").offsetTop + 1.9 * window.innerHeight, behavior: smooth});
      else $(where)?.scrollIntoView({behavior: smooth, block: "start"});
    };
    nav.querySelectorAll("button[data-go]").forEach((b) => b.addEventListener("click", () => go(b.dataset.go)));
    const ids = ["discoveries"];
    const update = () => {
      const y = window.scrollY, vh = window.innerHeight;
      nav.hidden = y < 0.6 * vh;
      let cur = y < 1.4 * vh ? "map" : "quarters";
      for (const id of ids) { const el = $(id); if (el && el.getBoundingClientRect().top < vh * 0.4) cur = id; }
      nav.querySelectorAll("button[data-go]").forEach((b) => b.toggleAttribute("aria-current", b.dataset.go === cur && cur !== "map"));
    };
    window.addEventListener("scroll", update, {passive: true});
    update();
  }

  function downloadCsv() {
    if (!state.cells || !state.frame) return;
    const rows = [["cell_id", "lat", "lon", "quarter", "period", "value_degC", "anomaly_degC", "valid_months_in_year",
                   "trend_degC_per_year", "trend_ci_low", "trend_ci_high", "trend_q_fdr"]];
    for (const c of state.cells) {
      const r = cellRecord(c.id);
      rows.push([r.id, r.lat, r.lon, r.quarter, state.frame.period, r.value ?? "", r.anomaly ?? "", r.validInYear ?? "",
                 r.slope_per_year ?? "", r.ci_low_per_year ?? "", r.ci_high_per_year ?? "", r.q ?? ""]);
    }
    const meta = `# NASA MOD11C3 v061 LST_Night_CMG, ${state.frame.data_version}; missing = failed quality control (never filled). Anomaly baseline: ${state.frame.anomaly_baseline}.`;
    const blob = new Blob([meta + "\n" + rows.map((r) => r.join(",")).join("\n") + "\n"], {type: "text/csv"});
    const a = document.createElement("a");
    a.href = URL.createObjectURL(blob);
    a.download = `estd_phoenix_cells_${state.frame.period.replace(/\s+/g, "_")}.csv`;
    a.click();
    setTimeout(() => URL.revokeObjectURL(a.href), 1000);
  }

  // ---------- comparison workspace ----------
  function gridSVG(svg, valueOf, scale, title) {
    if (!state.cells) { svg.innerHTML = `<text x="160" y="120" text-anchor="middle" class="svg-note">Cell data unavailable</text>`; return; }
    const cw = 320 / 16, ch = 240 / 12;
    svg.innerHTML = state.cells.map((c) => {
      const col = Math.round((c.lon - W) / 0.05 - 0.5), row = Math.round((N - c.lat) / 0.05 - 0.5), v = valueOf(c.id);
      const fill = v == null ? "#ffffff" : `rgb(${scaleColor(scale, v).slice(0, 3).map(Math.round).join(",")})`;
      return `<rect x="${col * cw + 0.5}" y="${row * ch + 0.5}" width="${cw - 1}" height="${ch - 1}" fill="${fill}" stroke="${v == null ? "#cfd4e2" : "none"}"><title>${c.id}: ${v == null ? "no valid value" : (scale === DIFF_SCALE ? `${signed(v, 2)} °C` : `${v.toFixed(2)} °C`)}</title></rect>`;
    }).join("") + `<line x1="160" y1="0" x2="160" y2="240" stroke="#141a2b" stroke-opacity=".25"/><line x1="0" y1="120" x2="320" y2="120" stroke="#141a2b" stroke-opacity=".25"/>`;
    svg.setAttribute("aria-label", title);
  }

  async function renderCompare() {
    const {compA: A, compB: B} = state;
    $("a-cap").textContent = `Period A · ${periodLabel(A.year, A.month)}`;
    $("b-cap").textContent = `Period B · ${periodLabel(B.year, B.month)}`;
    let fa = null, fb = null;
    try { [fa, fb] = await Promise.all([loadFrame(A.year, A.month), loadFrame(B.year, B.month)]); } catch (err) {
      $("compare-stats").innerHTML = `<p class="det-info">Could not load the periods (${esc(err.message)}).</p>`;
    }
    const val = (f) => (id) => (f && f.byId[id] ? f.byId[id].value : null);
    const diff = (id) => { const a = val(fa)(id), b = val(fb)(id); return a == null || b == null ? null : b - a; };
    gridSVG($("a-map"), val(fa), LAYERS.temperature, `Temperature per cell, ${periodLabel(A.year, A.month)}`);
    gridSVG($("b-map"), val(fb), LAYERS.temperature, `Temperature per cell, ${periodLabel(B.year, B.month)}`);
    gridSVG($("d-map"), diff, DIFF_SCALE, `Difference B minus A per cell`);
    if (!fa || !fb) return;
    const diffs = state.cells.map((c) => diff(c.id)).filter((d) => d != null);
    const mean = diffs.length ? diffs.reduce((s, d) => s + d, 0) / diffs.length : null;
    const regional = [["phoenix_study_area", "Whole area"], ...ORDER.map((q) => [state.quarterIds[q], QUARTERS[q].name])].map(([rid, name]) => {
      const s = state.series[rid];
      const a = s ? periodValue(s.times, s.values, A.year, A.month) : null, b = s ? periodValue(s.times, s.values, B.year, B.month) : null;
      return `<tr><td>${esc(name)}</td><td class="num">${fmt(a, 2)}</td><td class="num">${fmt(b, 2)}</td><td class="num">${a == null || b == null ? "—" : signed(b - a, 2)}</td></tr>`;
    }).join("");
    $("compare-stats").innerHTML = `
      <div class="legend-bar" style="background:${rampCss(RAMP_DIV)}" aria-hidden="true"></div>
      <div class="legend-scale" aria-hidden="true"><span>−6 °C</span><span>0</span><span>+6 °C</span></div>
      <p>On average, B was <b>${mean == null ? "—" : `${fmt(Math.abs(mean), 2)} °C ${mean >= 0 ? "warmer" : "cooler"}</b> than A`}, across the <b>${diffs.length}</b> squares with a reading in both. White squares are missing a reading in at least one.</p>
      <table class="mini"><thead><tr><th>Area average</th><th>A (°C)</th><th>B (°C)</th><th>Change</th></tr></thead><tbody>${regional}</tbody></table>
      <p class="note">Two single periods can differ just because of the weather that year. This is a simple difference, not proof of a trend. For the long-term change, use the Warming speed layer.</p>`;
  }

  function buildCompareControls(years) {
    const opts = (sel, value) => { sel.innerHTML = years.map((y) => `<option value="${y}" ${y === value ? "selected" : ""}>${y}</option>`).join(""); };
    const mopts = (sel, value) => { sel.innerHTML = [["avg", "Annual average"], ...MONTHS.map((m, i) => [i + 1, m])].map(([v, l]) => `<option value="${v}" ${String(v) === String(value) ? "selected" : ""}>${l}</option>`).join(""); };
    opts($("a-year"), state.compA.year); mopts($("a-month"), state.compA.month);
    opts($("b-year"), state.compB.year); mopts($("b-month"), state.compB.month);
    const read = () => {
      const m = (v) => (v === "avg" ? "avg" : +v);
      setState({compA: {year: +$("a-year").value, month: m($("a-month").value)}, compB: {year: +$("b-year").value, month: m($("b-month").value)}});
      renderCompare();
    };
    for (const id of ["a-year", "a-month", "b-year", "b-month"]) $(id).addEventListener("change", read);
    const names = [["phoenix_study_area", "Whole area"], ...ORDER.map((q) => [state.quarterIds[q], QUARTERS[q].name])];
    for (const [id, val] of [["rt-a", state.rtA], ["rt-b", state.rtB]]) {
      $(id).innerHTML = names.map(([rid, n]) => `<option value="${rid}" ${rid === val ? "selected" : ""}>${n}</option>`).join("");
      $(id).addEventListener("change", () => { state.rtA = $("rt-a").value; state.rtB = $("rt-b").value; renderRegionTest(); });
    }
  }

  async function renderRegionTest() {
    const out = $("rt-result");
    if (state.rtA === state.rtB) { out.textContent = "Choose two different regions."; return; }
    out.textContent = "Testing…";
    try {
      const r = await getJSON(`${API}/region-compare?a=${encodeURIComponent(state.rtA)}&b=${encodeURIComponent(state.rtB)}`);
      const name = (rid) => (rid === "phoenix_study_area" ? "Whole area" : QUARTERS[quarterOfRegion(rid)]?.name || rid);
      out.innerHTML = `<b>${esc(name(r.region_a))}</b> warmed ${fmt(Math.abs(r.difference_slope_per_year), 3)} °C a year ${r.difference_slope_per_year >= 0 ? "faster" : "slower"} than <b>${esc(name(r.region_b))}</b> (most likely between ${signed(r.ci_low_per_year, 3)} and ${signed(r.ci_high_per_year, 3)}; ${pText(r.p)}, ${r.months_used} months). <span class="badge ${r.significant ? "supported" : "not_supported"}">${r.significant ? "Strong evidence the two really differ" : "Not enough evidence that they differ"}</span>`;
    } catch (err) {
      out.innerHTML = `<span class="det-info">The comparison could not be run (${esc(err.message)}).</span>`;
    }
  }

  // ---------- coverage ----------
  function renderCoverage() {
    if (!state.cells) { $("coverage-summary").textContent = "The square-by-square data is unavailable right now."; return; }
    const svg = $("cov-map"), cw = 320 / 16, ch = 240 / 12;
    const minV = Math.min(...state.cells.map((c) => c.valid_months));
    svg.innerHTML = state.cells.map((c) => {
      const col = Math.round((c.lon - W) / 0.05 - 0.5), row = Math.round((N - c.lat) / 0.05 - 0.5);
      const t = (c.valid_months - minV) / Math.max(1, c.months - minV);
      const fill = `rgb(${rampColor(RAMP_COV, 0.15 + 0.85 * t).slice(0, 3).map(Math.round).join(",")})`;
      return `<rect x="${col * cw + 0.5}" y="${row * ch + 0.5}" width="${cw - 1}" height="${ch - 1}" fill="${fill}"><title>${c.id}: ${c.valid_months} of ${c.months} months valid</title></rect>`;
    }).join("");
    const total = state.cells.reduce((s, c) => s + c.months, 0), valid = state.cells.reduce((s, c) => s + c.valid_months, 0);
    const worst = [...state.cells].sort((a, b) => a.valid_months - b.valid_months)[0];
    $("coverage-summary").innerHTML = `<b>${valid.toLocaleString()} of ${total.toLocaleString()}</b> monthly readings passed NASA's quality checks (${(100 * valid / total).toFixed(1)}%). The square with the most gaps, ${esc(worst.id)}, still has ${worst.valid_months} of ${worst.months} months. If less than 80% of an area has a reading in a month, that area's average is left blank.`;
  }

  // ---------- discovery engine ----------
  function currentFinding() {
    if (state.finding === "ask") return state.askFinding || null;
    return (state.finding && state.discoveries?.findings.find((x) => x.id === state.finding)) || null;
  }
  const STATUS = {supported: "Strong evidence", exploratory: "Early lead, not confirmed", not_supported: "Not supported by the data"};
  const ASK_RULES = [
    [/faster|hot ?spot|cluster|pocket|quick/, "local-faster"], [/slower|cool|lag/, "local-slower"],
    [/season|summer|winter|spring|autumn|fall/, "seasons"], [/hide|hidden|conceal|spread|range|average/, "hidden-spread"],
    [/anomal|unusual|extreme|outlier|odd/, "unusual-months"], [/widespread|every|all cells|individual|consistent/, "widespread-warming"],
  ];
  function showDiscovery(id, scroll = true) {
    const f = state.discoveries?.findings.find((x) => x.id === id);
    if (!f) return;
    setState({finding: f.cells.length ? f.id : null});
    document.querySelectorAll(".disc").forEach((el) => el.classList.toggle("active", el.dataset.id === id));
    const card = document.querySelector(`.disc[data-id="${id}"]`);
    if (f.cells.length && scroll) window.scrollTo({top: 0, behavior: reduceMotion ? "auto" : "smooth"});
    else if (card) card.scrollIntoView({behavior: reduceMotion ? "auto" : "smooth", block: "center"});
  }
  const EXAMPLES = ["Is Tempe warming faster than Glendale?", "Which cell warmed the most, and where is it?",
    "How hot was downtown Phoenix in July 2024?", "Do summer nights warm faster than winter nights?",
    "What was unusual about this month?", "What is land surface temperature?"];
  function setAskBusy(busy) { $("ask-go").disabled = busy; $("ask-go").textContent = busy ? "Working…" : "Investigate"; }
  const TOOL_NAMES = {cell_trend: "cell trend", all_cell_trends: "all 192 cell trends", localized_differences: "local hot-spot test",
    seasonal_trend: "seasonal trends", anomalies: "unusual-month scan", region_stats: "region trends",
    region_difference: "region vs region test", difference_test: "direct difference test", period_values: "map values", region_monthly: "regional record", list_cells: "coverage count"};
  const KIND_LABEL = {compare: "Comparison", value: "Measurement", ranking: "Ranking", seasons: "Seasons", unusual: "Unusual months",
    hotspots: "Neighbourhood hot spots", coverage: "Data coverage", background: "Background", forecast: "Not a forecast",
    cause: "Causes", halves: "Both halves check", cluster: "Clustering", outside_data: "Needs outside data", no_data: "No valid data", answer: "Warming trend", help: "What I can answer", error: "Couldn't answer"};
  function askAgain(q) { ask(q); }
  async function askAI(q) {
    const box = $("ask-result");
    box.hidden = false; box.className = "answer loading";
    box.innerHTML = `<p class="answer-q">${esc(q)}</p><div class="dots" aria-label="Working"><i></i><i></i><i></i></div><p class="answer-meta">Checking the NASA measurements…</p>`;
    box.scrollIntoView({behavior: reduceMotion ? "auto" : "smooth", block: "nearest"});
    setAskBusy(true);
    let out;
    try {
      const r = await fetch(`${API}/ask`, {method: "POST", headers: {"Content-Type": "application/json"},
        body: JSON.stringify({question: q, context: {year: state.year, month: String(state.month), cell: state.cell, region: state.region}})});
      out = r.ok ? await r.json() : {status: "error", kind: "error", headline: r.status === 429 ? "Too many questions in a minute. Wait a moment and try again." : `Something went wrong on our side (code ${r.status}). Please try again.`};
    } catch { out = {status: "error", kind: "error", headline: "We could not reach the server. Check your connection and try again."}; }
    setAskBusy(false);
    const cells = (out.cells || []).map((id) => state.cellIndex[id]).filter(Boolean);
    state.askFinding = cells.length ? {id: "ask", title: "Cells in this answer", status: "answer", highlight: "ask", cells} : null;
    let opt = $("finding").querySelector('option[value="ask"]');
    if (cells.length && !opt) { opt = document.createElement("option"); opt.value = "ask"; $("finding").insertBefore(opt, $("finding").options[1] || null); }
    if (opt) { if (cells.length) opt.textContent = `Your question: ${q.length > 40 ? q.slice(0, 40) + "…" : q}`; else opt.remove(); }
    if (state.finding === "ask") setState({finding: cells.length ? "ask" : null});
    const tools = [...new Set((out.tools_used || []).map((t) => TOOL_NAMES[t] || t))];
    box.className = `answer kind-${esc(out.kind || "answer")}`;
    box.innerHTML = `
      <p class="answer-q">${esc(q)}</p>
      <span class="answer-kind">${esc(KIND_LABEL[out.kind] || "Answer")}</span>
      <p class="answer-head">${esc(out.headline || "")}</p>
      ${(out.stats || []).length ? `<div class="answer-stats">${out.stats.map((s, i) => `
        <div class="tile t${i}"><span class="tile-label">${esc(s.label)}</span><b class="tile-value">${esc(s.value)}</b>${s.sub ? `<span class="tile-sub">${esc(s.sub)}</span>` : ""}</div>`).join("")}</div>` : ""}
      ${(out.details || []).length ? `<ul class="answer-details">${out.details.map((d) => `<li>${esc(d)}</li>`).join("")}</ul>` : ""}
      <div class="answer-foot">
        ${cells.length ? `<button type="button" class="primary small" id="ask-map">Show ${cells.length} cell${cells.length > 1 ? "s" : ""} on the map</button>` : ""}
        ${out.method ? `<span class="pill">Method: ${esc(out.method)}</span>` : ""}
        ${tools.length ? `<span class="pill ok">Computed from: ${esc(tools.join(", "))}</span>` : ""}
      </div>
      ${out.caveat ? `<p class="answer-meta">${esc(out.caveat)}</p>` : ""}
      ${(out.suggestions || []).length ? `<div class="chips answer-sugg">${out.suggestions.map((x) => `<button type="button" class="chip">${esc(x)}</button>`).join("")}</div>` : ""}`;
    box.querySelectorAll(".answer-sugg .chip").forEach((b) => b.addEventListener("click", () => askAgain(b.textContent)));
    $("ask-map")?.addEventListener("click", () => {
      setState({finding: "ask", cell: cells.length === 1 ? cells[0].id : state.cell});
      window.scrollTo({top: 0, behavior: reduceMotion ? "auto" : "smooth"});
    });
  }
  // ---------- AI Scientific Discovery Engine (prototype workflow) ----------
  // Deterministic routing to four fixed investigations. The WORKFLOW is scripted; the NUMBERS are not:
  // every value comes from this project's endpoints (/regions, /region-stats, /region-compare,
  // /discoveries, /map-static, /cell-years). Nothing is typed in here and no language model runs.
  const INVESTIGATIONS = [
    ["hidden_pattern", "Find a hidden warming pattern", "Find a warming pattern that regional averages might hide."],
    ["rank_regions", "Which region is warming fastest?", "Which Phoenix region is warming fastest?"],
    ["local_vs_region", "Compare a local observation with its regional average", "Can a regional average hide local warming?"],
    ["trend_acceleration", "Has Phoenix warming accelerated?", "Has Phoenix warming accelerated since 2014?"],
  ];
  const INTENT_LABEL = {hidden_pattern: "look for places that warm faster than their surroundings", rank_regions: "rank the four parts of the city",
    local_vs_region: "compare one small place with the area around it", trend_acceleration: "check whether warming has sped up"};
  const CAUTION = "We compared every square with the area around it. Because we tested many squares at once, we used a stricter bar so lucky flukes do not count. We kept a result only if it showed up in both halves of the record (2003–2013 and 2014–2024). Squares next to each other behave alike, so a cluster is one pattern, not many. We do not know the cause.";
  function detectDemoIntent(q) {
    const s = q.toLowerCase();
    if (/accelerat|since 2014|speed(ing|ed)? up|getting faster/.test(s)) return "trend_acceleration";
    if (/hidden|discover|pattern|might hide|locali[sz]ed/.test(s)) return "hidden_pattern";
    if (/regional average|compare (a )?local|local observation|hide local|local vs/.test(s)) return "local_vs_region";
    if (/fastest|warming most|warms? (the )?most|which (region|quarter)/.test(s)) return "rank_regions";
    return "unsupported";
  }
  const qName = (rid) => (rid === state.quarterIds.whole ? "Whole study area" : QUARTERS[quarterOfRegion(rid)]?.name || rid);
  const finding = (id) => state.discoveries?.findings.find((x) => x.id === id) || null;
  const quarterRegions = () => ORDER.map((q) => state.regions.find((r) => r.region_id === state.quarterIds[q])).filter(Boolean);

  function stripPlot() {   // every cell's trend on one axis, with the quarter and whole-area averages marked
    const cells = state.cells.filter((c) => c.slope_per_year != null), W2 = 720, H2 = 118, x0 = 16, x1 = W2 - 16;
    const X = (v) => x0 + clamp(v / 0.2) * (x1 - x0);
    const ticks = cells.map((c) => `<line x1="${X(c.slope_per_year).toFixed(1)}" x2="${X(c.slope_per_year).toFixed(1)}" y1="54" y2="82" stroke="rgb(${rampColor(RAMP_RATE, c.slope_per_year / 0.2).slice(0, 3).map(Math.round).join(",")})" stroke-width="2"><title>${c.id}: ${signed(c.slope_per_year, 3)} °C/yr</title></line>`).join("");
    const marks = [...quarterRegions().map((r) => [quarterOfRegion(r.region_id), r.trend.slope * 12]),
      ["All", state.regions.find((r) => r.region_id === state.quarterIds.whole).trend.slope * 12]];
    marks.sort((a, b) => a[1] - b[1]);
    const tri = marks.map(([n, v], i) => `<path d="M${X(v).toFixed(1)} 50 l-4 -7 h8 z" fill="#efe6d2"/><line x1="${X(v).toFixed(1)}" x2="${X(v).toFixed(1)}" y1="${14 + (i % 3) * 11}" y2="43" stroke="#6b6557"/><text x="${X(v).toFixed(1)}" y="${11 + (i % 3) * 11}" font-size="10" fill="#efe6d2" text-anchor="middle">${esc(n)} ${signed(v, 3)}</text>`).join("");
    const axis = [0, 0.05, 0.1, 0.15, 0.2].map((v) => `<text x="${X(v)}" y="102" font-size="10" fill="#9c927d" text-anchor="middle">${v === 0 ? "0" : "+" + v.toFixed(2)}</text>`).join("");
    return `<svg viewBox="0 0 ${W2} ${H2}" role="img" aria-label="How fast each of the ${cells.length} map squares is warming, on one line, with the four area averages and the whole-area average marked above">
      <line x1="${x0}" x2="${x1}" y1="86" y2="86" stroke="#4a463e"/>${ticks}${tri}${axis}<text x="${x1}" y="116" font-size="10" fill="#9c927d" text-anchor="end">°C warmer per year (each line is one 5 km square; triangles are the area averages)</text></svg>`;
  }
  function rankBars(ranked) {
    const st = state.regionStats?.regions || {}, W2 = 720, rowH = 34, x0 = 110, x1 = W2 - 90, max = 0.15;
    const X = (v) => x0 + clamp(v / max) * (x1 - x0);
    const rows = ranked.map((r, i) => {
      const v = r.trend.slope * 12, s = st[r.region_id] || {}, y = 8 + i * rowH;
      return `<text x="${x0 - 10}" y="${y + 15}" font-size="12" fill="#efe6d2" text-anchor="end">${esc(qName(r.region_id))}</text>
        <rect x="${x0}" y="${y}" width="${(X(v) - x0).toFixed(1)}" height="22" rx="2" fill="${i === 0 ? "#c8372d" : "#7a6a45"}"><title>${qName(r.region_id)}: ${signed(v, 3)} °C/yr</title></rect>
        ${s.ci_low_per_year != null ? `<line x1="${X(s.ci_low_per_year).toFixed(1)}" x2="${X(s.ci_high_per_year).toFixed(1)}" y1="${y + 11}" y2="${y + 11}" stroke="#efe6d2" stroke-width="1.5"/>` : ""}
        <text x="${(Math.max(X(v), s.ci_high_per_year != null ? X(s.ci_high_per_year) : 0) + 8).toFixed(1)}" y="${y + 15}" font-size="12" fill="#efe6d2">${signed(v, 3)}</text>`;
    }).join("");
    return `<svg viewBox="0 0 ${W2} ${ranked.length * rowH + 26}" role="img" aria-label="Estimated warming rate per quarter with 95% confidence intervals">${rows}
      <text x="${x0}" y="${ranked.length * rowH + 20}" font-size="10" fill="#9c927d">°C warmer per year; the thin line is the likely range</text></svg>`;
  }
  function twoLines(years, a, b, nameA, nameB, splitYear) {   // yearly anomalies; gaps stay gaps
    const W2 = 720, H2 = 170, x0 = 34, x1 = W2 - 12, y0 = 12, y1 = H2 - 26;
    const vals = [...a, ...(b || [])].filter((v) => v != null), m = Math.max(1, ...vals.map(Math.abs));
    const X = (i) => x0 + (i / (years.length - 1)) * (x1 - x0), Y = (v) => (y0 + y1) / 2 - (v / m) * ((y1 - y0) / 2);
    const path = (arr) => { let d = "", pen = false; arr.forEach((v, i) => { if (v == null) { pen = false; return; } d += `${pen ? "L" : "M"}${X(i).toFixed(1)} ${Y(v).toFixed(1)}`; pen = true; }); return d; };
    const dots = (arr, fill, name) => arr.map((v, i) => (v == null ? "" : `<circle cx="${X(i).toFixed(1)}" cy="${Y(v).toFixed(1)}" r="2.6" fill="${fill}"><title>${name}, ${years[i]}: ${signed(v, 2)} °C vs usual</title></circle>`)).join("");
    const si = splitYear ? years.indexOf(splitYear) : -1;
    return `<svg viewBox="0 0 ${W2} ${H2}" role="img" aria-label="Yearly mean anomaly, ${years[0]} to ${years[years.length - 1]}: ${esc(nameA)}${b ? " and " + esc(nameB) : ""}">
      <line x1="${x0}" x2="${x1}" y1="${Y(0)}" y2="${Y(0)}" stroke="#4a463e"/>
      ${si > 0 ? `<line x1="${((X(si - 1) + X(si)) / 2).toFixed(1)}" x2="${((X(si - 1) + X(si)) / 2).toFixed(1)}" y1="${y0}" y2="${y1}" stroke="#e0a43a" stroke-dasharray="4 4"/><text x="${((X(si - 1) + X(si)) / 2 + 6).toFixed(1)}" y="${y0 + 10}" font-size="10" fill="#e0a43a">${splitYear} onward</text>` : ""}
      ${b ? `<path d="${path(b)}" fill="none" stroke="#9c927d" stroke-width="2"/>${dots(b, "#9c927d", nameB)}` : ""}
      <path d="${path(a)}" fill="none" stroke="#c8372d" stroke-width="2.4"/>${dots(a, "#c8372d", nameA)}
      <text x="4" y="${y0 + 8}" font-size="10" fill="#9c927d">+${m.toFixed(1)}</text><text x="4" y="${y1}" font-size="10" fill="#9c927d">−${m.toFixed(1)}</text>
      <text x="${x0}" y="${H2 - 6}" font-size="10" fill="#9c927d">${years[0]}</text><text x="${x1}" y="${H2 - 6}" font-size="10" fill="#9c927d" text-anchor="end">${years[years.length - 1]}</text>
      <text x="${(x0 + x1) / 2}" y="${H2 - 6}" font-size="10" fill="#9c927d" text-anchor="middle">each year compared with usual, °C (full years only)</text></svg>
      <p class="eng-key"><i style="background:#c8372d"></i>${esc(nameA)}${b ? `<i style="background:#9c927d"></i>${esc(nameB)}` : ""}</p>`;
  }

  async function investigate(intent) {
    const prov = state.discoveries?.provenance, haveCells = !!state.cells;
    const whole = state.regions.find((r) => r.region_id === state.quarterIds.whole);
    const st = state.regionStats?.regions || {};
    const out = {tools: [["GET /regions, /series, /anomaly", "published regional results (seasonal Mann-Kendall, Sen's slope)"]], cells: [], stats: []};
    if (intent === "hidden_pattern") {
      const spread = finding("hidden-spread"), local = finding("local-faster");
      if (haveCells && spread && local) {
        const rates = state.cells.map((c) => c.slope_per_year).filter((v) => v != null);
        const q = quarterRegions().map((r) => r.trend.slope * 12);
        out.viz = stripPlot();
        const lo = Math.min(...rates), hi = Math.max(...rates);
        out.discovery = `Some parts of Phoenix are warming much faster than others, and the area averages hide it. The slowest square warms by ${signed(lo, 3)} °C a year and the fastest by ${signed(hi, 3)} °C${lo > 0 ? `: about ${(hi / lo).toFixed(1)} times as fast` : ""}. ${local.cells.length} squares warm clearly faster than the area around them.`;
        out.evidence = [`The four area averages only range from ${signed(Math.min(...q), 3)} to ${signed(Math.max(...q), 3)} °C a year.`,
          `The ${rates.length} individual squares range from ${signed(lo, 3)} to ${signed(hi, 3)} °C a year.`];
        out.technical = [local.statement, `Cells: ${local.evidence_text}.`, `Method: ${local.method}.`, local.limitations];
        out.challenge = CAUTION;
        out.verdict = [STATUS[local.status] || local.status, local.status];
        out.cells = local.cells; out.mapFinding = "local-faster";
        out.tools.push(["GET /map-static", `each cell's own trend, 95% CI and FDR q-value (${state.cells.length} cells)`], ["GET /discoveries", "cell-minus-quarter tests, FDR correction, both-halves challenge"]);
      } else {
        const ranked = quarterRegions().sort((a, b) => b.trend.slope - a.trend.slope);
        out.viz = rankBars(ranked); out.notice = "The detailed square-by-square data is unavailable right now, so this uses the four area averages instead.";
        out.discovery = `${qName(ranked[0].region_id)} Phoenix warms faster (${signed(ranked[0].trend.slope * 12, 3)} °C a year) than the study area as a whole (${signed(whole.trend.slope * 12, 3)} °C a year).`;
        out.evidence = [`All four areas: ${ranked.map((r) => `${qName(r.region_id)} ${signed(r.trend.slope * 12, 3)}`).join(", ")} °C a year.`];
        out.challenge = "We can see the difference, but we have not tested whether it is real or just chance.";
        out.verdict = ["Early lead, not confirmed", "exploratory"];
      }
      out.why = "An average can be correct and still hide neighbourhoods that heat up much faster. Those are the places to look at first when planning shade, cooling centres or further study.";
    } else if (intent === "rank_regions") {
      const ranked = quarterRegions().sort((a, b) => b.trend.slope - a.trend.slope), top = ranked[0];
      out.viz = rankBars(ranked);
      out.discovery = `${qName(top.region_id)} Phoenix is warming fastest: the ground there has warmed by about ${signed(top.trend.slope * 12, 3)} °C each year${st[top.region_id]?.ci_low_per_year != null ? ` (most likely between ${signed(st[top.region_id].ci_low_per_year, 3)} and ${signed(st[top.region_id].ci_high_per_year, 3)})` : ""}.`;
      out.evidence = ranked.map((r) => `${qName(r.region_id)}: ${signed(r.trend.slope * 12, 3)} °C a year (${sureShort(r.trend.p)}).`);
      out.technical = ranked.map((r) => `${qName(r.region_id)}: Sen's slope ${signed(r.trend.slope * 12, 3)} °C/yr, ${pText(r.trend.p)}, τ ${r.trend.tau.toFixed(2)}.`);
      const tests = await Promise.all(ranked.slice(1).map((r) => getJSON(`${API}/region-compare?a=${encodeURIComponent(top.region_id)}&b=${encodeURIComponent(r.region_id)}`, true).catch(() => null)));
      const ok = tests.filter(Boolean);
      if (ok.length) {
        out.challenge = `Coming first does not prove an area is truly faster than the others, so we tested each gap directly. ` +
          ok.map((t) => `${qName(t.region_a)} warms ${fmt(Math.abs(t.difference_slope_per_year), 3)} °C a year ${t.difference_slope_per_year >= 0 ? "faster" : "slower"} than ${qName(t.region_b)} (${t.significant ? "strong evidence the gap is real" : "not enough evidence of a real gap"})`).join("; ") + ".";
        out.technical.push(...ok.map((t) => `${qName(t.region_a)} minus ${qName(t.region_b)}: ${signed(t.difference_slope_per_year, 3)} °C/yr, 95% CI ${signed(t.ci_low_per_year, 3)} to ${signed(t.ci_high_per_year, 3)}, ${pText(t.p)}.`));
        const all = ok.length === ranked.length - 1 && ok.every((t) => t.significant);
        out.verdict = all ? ["Strong evidence: fastest, and clearly faster than each other area", "supported"] : ["Ranked first, but not clearly faster than every other area", "exploratory"];
        out.tools.push(["GET /region-compare", `seasonal Mann-Kendall on the monthly difference between two regions (${ok.length} tests run)`]);
      } else {
        out.challenge = "Coming first does not prove an area is truly faster than the others. The direct test could not be run right now.";
        out.verdict = ["Early lead, not confirmed", "exploratory"];
      }
      out.tools.push(["GET /region-stats", "95% confidence interval for each regional Sen's slope"]);
      out.mapRegion = quarterOfRegion(top.region_id);
      out.why = "Hot nights are when bodies need to cool down. Knowing which part of the city heats up fastest shows where help may be needed most. This does not tell us the cause.";
    } else if (intent === "local_vs_region") {
      const local = finding("local-faster");
      const pick = haveCells && local && [...local.cells].sort((a, b) => b.metric - a.metric)[0];
      if (pick) {
        const c = state.cellIndex[pick.id], rid = state.quarterIds[c.quarter], r = state.regions.find((x) => x.region_id === rid);
        const cy = await getJSON(`${API}/cell-years?id=${encodeURIComponent(c.id)}`, true).catch(() => null);
        const reg = yearlyAnomalyMeans(rid);
        if (cy) out.viz = twoLines(cy.years.map((y) => y.year), cy.years.map((y) => y.anomaly), reg.map((b) => b.v), "This one square", `${areaName(c.quarter)} average`);
        out.stats = [["One 5 km square", c.id, `in ${areaName(c.quarter)}`], ["This square", `${signed(c.slope_per_year, 3)} °C a year`, `most likely ${signed(c.ci_low_per_year, 3)} to ${signed(c.ci_high_per_year, 3)}`],
          [`${areaName(c.quarter)} average`, `${signed(r.trend.slope * 12, 3)} °C a year`, sureShort(r.trend.p)], ["Gap", `${signed(pick.metric, 3)} °C a year`, "square compared with its area"]];
        out.discovery = `Yes. One 5 km square in ${areaName(c.quarter)} warms by ${signed(c.slope_per_year, 3)} °C a year, while the area around it averages ${signed(r.trend.slope * 12, 3)} °C a year. Looking only at the area average, you would never see it.`;
        out.evidence = [`We tested the gap between this square and its area directly, month by month. The evidence that the gap is real is strong.`, `This square has a reliable reading in ${c.valid_months} of ${c.months} months. Missing months stay missing.`];
        out.technical = [`Cell ${c.id}: ${c.lat.toFixed(3)}° N, ${Math.abs(c.lon).toFixed(3)}° W.`, `Cell minus its quarter: ${signed(pick.metric, 3)} °C/yr, q = ${pick.q.toPrecision(2)} after FDR correction.`, `Cell trend 95% CI ${signed(c.ci_low_per_year, 3)} to ${signed(c.ci_high_per_year, 3)} °C/yr; quarter ${pText(r.trend.p)}.`, `Method: ${local.method}.`, local.limitations];
        out.challenge = CAUTION;
        out.verdict = [STATUS[local.status] || local.status, local.status];
        out.cells = [c]; out.mapCell = c.id; out.mapFinding = "local-faster";
        out.tools.push(["GET /discoveries", "cell-minus-quarter test with FDR correction and both-halves challenge"], ["GET /cell-years", "this cell's yearly record and trend line"], ["GET /map-static", "the cell's own trend and 95% CI"]);
      } else {
        const ranked = quarterRegions().sort((a, b) => b.trend.slope - a.trend.slope), top = ranked[0];
        out.notice = "The detailed square-by-square data is unavailable right now, so this compares one area with the whole study area instead.";
        out.viz = twoLines(yearlyAnomalyMeans(top.region_id).map((b) => +b.y), yearlyAnomalyMeans(top.region_id).map((b) => b.v), yearlyAnomalyMeans(whole.region_id).map((b) => b.v), `${qName(top.region_id)} Phoenix`, "Whole study area");
        out.discovery = `${qName(top.region_id)} Phoenix (${signed(top.trend.slope * 12, 3)} °C a year) warms faster than the study area as a whole (${signed(whole.trend.slope * 12, 3)} °C a year).`;
        out.evidence = ["This uses the area averages only."]; out.challenge = "We can see the difference, but we have not tested whether it is real or just chance.";
        out.verdict = ["Early lead, not confirmed", "exploratory"];
      }
      out.why = "One neighbourhood can heat up much faster than the area around it. Comparing a place with its surroundings is how hidden hot spots are found.";
    } else {   // trend_acceleration
      const yrs = yearlyAnomalyMeans(whole.region_id), split = 2014;
      const mean = (arr) => (arr.length ? arr.reduce((a, b) => a + b, 0) / arr.length : null);
      const early = yrs.filter((b) => +b.y < split && b.v != null).map((b) => b.v), late = yrs.filter((b) => +b.y >= split && b.v != null).map((b) => b.v);
      const wide = finding("widespread-warming");
      out.hypothesis = "Nights have been warming faster in recent years than before.";
      out.viz = twoLines(yrs.map((b) => +b.y), yrs.map((b) => b.v), null, "Whole study area", "", split);
      out.stats = [[`${yrs[0].y}–${split - 1}`, `${signed(mean(early), 2)} °C`, `compared with usual, ${early.length} full years`], [`${split}–${yrs[yrs.length - 1].y}`, `${signed(mean(late), 2)} °C`, `compared with usual, ${late.length} full years`],
        ["Whole period", `${signed(whole.trend.slope * 12, 3)} °C a year`, sureShort(whole.trend.p)]];
      const me = mean(early), ml = mean(late), sig = whole.trend.p < 0.05;
      out.discovery = `We cannot say. Phoenix nights were ${me == null || ml == null ? "not comparable" : ml > me ? "warmer" : "not warmer"} in ${split}–${yrs[yrs.length - 1].y} than in ${yrs[0].y}–${split - 1} on average, and the long-term warming has ${sig ? sureShort(whole.trend.p) : "weak evidence"}. But being warmer is not the same as warming faster.`;
      out.evidence = [`Whole study area, ${whole.period.start.slice(0, 4)}–${whole.period.end.slice(0, 4)}: about ${signed(whole.trend.slope * 12, 3)} °C warmer each year.`,
        "The two period figures above are simple averages, not warming speeds."];
      out.technical = [`Whole study area: Sen's slope ${signed(whole.trend.slope * 12, 3)} °C/yr, ${pText(whole.trend.p)}.`, "Period means are descriptive averages of the published yearly anomalies (complete years only), not trend estimates.", ...(wide ? [`Both-halves check on cells: ${wide.statement}`] : [])];
      out.challenge = "Two different speeds in two periods do not prove the speed really changed. It could be ordinary year-to-year weather. We have not run a test for a change in speed, and about ten years per half is short for one. So we do not claim that warming sped up.";
      out.verdict = ["Verdict: INCONCLUSIVE (not enough evidence either way)", "not_supported"];
      if (wide) out.tools.push(["GET /discoveries", "each cell re-tested separately in 2003–2013 and 2014–2024"]);
      out.why = "A tool that says \"we don't know yet\" is more useful than one that always says yes. The next step is a proper test on a longer record.";
    }
    out.retrieved = [["Source", "NASA Terra MODIS MOD11C3 Collection 6.1 (LP DAAC, doi:10.5067/MODIS/MOD11C3.061)"], ["Variable", "Nighttime land surface temperature (LST_Night_CMG)"],
      ["Study area", "Phoenix, Arizona: 112.4°–111.6° W, 33.2°–33.8° N"], ["Analysis period", `${whole.period.start} to ${whole.period.end}`],
      ["Retrieved data", `Regional monthly series for ${state.regions.length} areas${haveCells ? ` and per-cell trend records for ${state.cells.length} grid cells` : ""}`],
      ...(prov ? [["Granularity", `Individual MODIS grid cells: ${prov.cells} cells × ${prov.months} months`], ["Data version", `${prov.data_version}, grid_cells.csv sha256 ${prov.sha256.slice(0, 12)}…`]] : [["Granularity", "Regional averages only in this build"]]),
      ["Statistical method", "Seasonal Mann-Kendall, seasonal Sen's slope, Kendall's τ; Benjamini-Hochberg FDR for cells"], ["Provenance", "Existing processed Earth System Trend Detective dataset; failed-QC months stay missing"]];
    return out;
  }

  let engineRun = 0;
  async function runInvestigation(intent, question) {
    const box = $("ask-result"), run = ++engineRun;
    const haveCells = !!state.cells, prov = state.discoveries?.provenance;
    const stages = [
      ["Understanding the question", `Plan: ${INTENT_LABEL[intent]}`],
      ["Getting the NASA measurements", `Night-time ground temperature over Phoenix, 2003–2024, from NASA's Terra satellite${prov ? `: ${prov.cells} map squares × ${prov.months} months` : haveCells ? `: ${state.cells.length} map squares` : " (area averages)"}`],
      ["Choosing the right tests", intent === "trend_acceleration" ? "Long-term change · earlier years against recent years" : "Long-term change · one place against another · how strong the evidence is"],
      ["Double-checking the first answer", "Making sure the pattern is real, not just the biggest number or a fluke"],
      ["Preparing the result", "Checked evidence, ready to show on a chart and the map"],
    ];
    box.hidden = false; box.className = "answer engine";
    box.innerHTML = `<p class="eng-label">Your question</p><p class="answer-q">${esc(question)}</p>
      <ol class="eng-flow" aria-label="Investigation workflow">${["Find", "Investigate", "Double-check", "Explain"].map((x) => `<li>${x}</li>`).join("")}</ol>
      <ul class="eng-stages" id="eng-stages" aria-live="polite"></ul><div id="eng-out"></div>`;
    box.scrollIntoView({behavior: reduceMotion ? "auto" : "smooth", block: "start"});
    setAskBusy(true);
    const work = investigate(intent).catch((err) => ({error: err.message || String(err)}));
    for (let i = 0; i < stages.length; i++) {
      if (run !== engineRun) return;
      $("eng-stages").insertAdjacentHTML("beforeend", `<li><b>${i + 1}. ${esc(stages[i][0])}</b><span>${esc(stages[i][1])}</span></li>`);
      box.querySelectorAll(".eng-flow li").forEach((li, k) => li.classList.toggle("on", k <= Math.min(3, Math.floor(i * 0.9))));
      if (!reduceMotion) await new Promise((r) => setTimeout(r, 260));
    }
    const out = await work;
    setAskBusy(false);
    if (run !== engineRun) return;
    if (out.error) { $("eng-out").innerHTML = `<p class="det-info">We could not finish this investigation (${esc(out.error)}). Please try again.</p>`; return; }
    const n = out.cells.length;
    $("eng-out").innerHTML = `
      ${out.notice ? `<p class="eng-notice">${esc(out.notice)}</p>` : ""}
      ${out.hypothesis ? `<p class="eng-label">The idea we are testing</p><p class="eng-hyp">${esc(out.hypothesis)}</p>` : ""}
      ${out.viz ? `<figure class="eng-viz">${out.viz}</figure>` : ""}
      ${out.stats.length ? `<div class="answer-stats">${out.stats.map((s, i) => `<div class="tile t${i}"><span class="tile-label">${esc(s[0])}</span><b class="tile-value">${esc(s[1])}</b><span class="tile-sub">${esc(s[2])}</span></div>`).join("")}</div>` : ""}
      <dl class="eng-report">
        <dt>What we found</dt><dd class="eng-lead">${esc(out.discovery)}</dd>
        <dt>The evidence</dt><dd><ul>${out.evidence.map((e) => `<li>${esc(e)}</li>`).join("")}</ul></dd>
        <dt>A reason for caution</dt><dd>${esc(out.challenge)}</dd>
        <dt>How sure are we?</dt><dd><span class="badge ${esc(out.verdict[1])}">${esc(out.verdict[0])}</span></dd>
        <dt>Why it matters</dt><dd>${esc(out.why)}</dd>
      </dl>
      <div class="answer-foot">${n || out.mapRegion ? `<button type="button" class="primary small" id="eng-map">${out.mapRegion ? `Show ${esc(areaName(out.mapRegion))} on the map` : `Show ${n === 1 ? "this square" : `these ${n} squares`} on the map`}</button>` : ""}</div>
      ${(out.technical || []).length ? `<details class="eng-more"><summary>Technical evidence</summary><ul class="eng-tech">${out.technical.map((e) => `<li>${esc(e)}</li>`).join("")}</ul></details>` : ""}
      <details class="eng-more"><summary>Where the data came from</summary><dl class="eng-facts">${out.retrieved.map(([k, v]) => `<div><dt>${esc(k)}</dt><dd>${esc(v)}</dd></div>`).join("")}</dl></details>
      <details class="eng-more"><summary>Tools the investigation used</summary><p class="note">The AI chooses which checks to run. The maths is done by tested analysis code, never guessed by a language model.</p>
        <ul class="eng-tools">${out.tools.map(([t, d]) => `<li><code>${esc(t)}</code><span>${esc(d)}</span></li>`).join("")}</ul>
        <p class="eng-arch">User question → interpretation → scientific retrieval → NASA observations → statistical analysis tools → evidence validation → explanation → map / chart discovery</p></details>
      <p class="answer-meta">Prototype: these four investigations follow fixed steps to show how the planned AI system would work. No vector database or language model runs here. Every number comes from the project's real results.</p>`;
    $("eng-map")?.addEventListener("click", () => {
      if (out.mapRegion) selectRegion(out.mapRegion);
      else setState({finding: out.mapFinding || null, cell: out.mapCell || null, region: "all"});
      window.scrollTo({top: 0, behavior: reduceMotion ? "auto" : "smooth"});
    });
  }
  // One entry point for the question box: a supported investigation, or the question engine for anything else.
  function ask(q) {
    const intent = state.regions ? detectDemoIntent(q) : "unsupported";
    $("ask-input").value = q;
    if (intent === "unsupported") { engineRun++; askAI(q); } else runInvestigation(intent, q);
  }

  function buildDiscoveries() {
    const d = state.discoveries, host = $("discovery-list");
    $("ask-chips").innerHTML = INVESTIGATIONS.map(([id, label, q]) => `<button type="button" class="chip inv" data-q="${esc(q)}" data-intent="${id}">${esc(label)}</button>`).join("")
      + EXAMPLES.map((q) => `<button type="button" class="chip" data-q="${esc(q)}">${esc(q)}</button>`).join("");
    $("ask-chips").querySelectorAll(".chip").forEach((b) => b.addEventListener("click", () => (b.dataset.intent ? ($("ask-input").value = b.dataset.q, runInvestigation(b.dataset.intent, b.dataset.q)) : askAgain(b.dataset.q))));
    $("ask").addEventListener("submit", (ev) => { ev.preventDefault(); const q = $("ask-input").value.trim(); if (q) ask(q); });
    if (!d) {
      host.innerHTML = '<p class="det-info">The AI findings are unavailable right now. The map still works.</p>';
      $("finding-wrap").hidden = true; $("discover").disabled = true; return;
    }
    const sel = $("finding");
    for (const f of d.findings.filter((x) => x.cells.length)) {
      const o = document.createElement("option");
      o.value = f.id; o.textContent = `${f.title} (${STATUS[f.status].toLowerCase()})`;
      sel.appendChild(o);
    }
    sel.addEventListener("change", () => setState({finding: sel.value || null}));
    host.innerHTML = d.findings.map((f, i) => `
      <article class="disc ${esc(f.status)} hue-${i % 6}" data-id="${esc(f.id)}">
        <span class="badge ${esc(f.status)}">${esc(STATUS[f.status])}</span>
        <h3>${esc(f.title)}</h3>
        <p class="disc-obs">${esc(f.summary || f.observation)}</p>
        <div class="disc-actions">${f.cells.length ? `<button type="button" class="ghost" data-finding="${esc(f.id)}">Show on map</button>` : ""}
          <button type="button" class="link" data-ask="${esc(f.next_question)}">Ask: ${esc(f.next_question)}</button></div>
        <details><summary>Technical evidence</summary><dl class="disc-fields">
          <dt>Where</dt><dd>${esc(f.location)}</dd>
          <dt>Evidence</dt><dd>${esc(f.evidence_text)}</dd>
          <dt>Method</dt><dd>${esc(f.method)}</dd>
          <dt>Caveat</dt><dd>${esc(f.limitations)}</dd>
        </dl></details>
      </article>`).join("");
    host.querySelectorAll("button[data-finding]").forEach((b) => b.addEventListener("click", () => showDiscovery(b.dataset.finding)));
    host.querySelectorAll("button[data-ask]").forEach((b) => b.addEventListener("click", () => {
      $("ask").scrollIntoView({behavior: reduceMotion ? "auto" : "smooth", block: "center"});
      ask(b.dataset.ask);
    }));
    // "Surprise me": show three of the findings at a time and shuffle to a different three.
    // Only which cards are visible changes: the findings themselves, and the map state, are untouched.
    const SHOW = Math.min(3, d.findings.length), btn = $("discover");
    const pick = () => {   // Fisher-Yates: every finding has the same chance, no repeats within a draw
      const ids = d.findings.map((f) => f.id);
      for (let i = ids.length - 1; i > 0; i--) { const j = Math.floor(Math.random() * (i + 1)); [ids[i], ids[j]] = [ids[j], ids[i]]; }
      return ids.slice(0, SHOW);
    };
    const apply = (ids) => {
      state.discShown = ids;
      for (const card of host.querySelectorAll(".disc")) card.classList.toggle("off", !ids.includes(card.dataset.id));
      ids.forEach((id) => host.appendChild(host.querySelector(`.disc[data-id="${id}"]`)));   // shown cards, in drawn order
    };
    const initial = () => {
      const family = (f) => f.id.split("-")[0], seen = new Set(), out = [];
      const ranked = [...d.findings].sort((a, b) => (a.status === "supported" ? 0 : 1) - (b.status === "supported" ? 0 : 1));   // stable: backend order within a status
      for (const f of ranked) { if (out.length < SHOW && !seen.has(family(f))) { seen.add(family(f)); out.push(f.id); } }
      for (const f of ranked) { if (out.length < SHOW && !out.includes(f.id)) out.push(f.id); }
      return out;
    };
    apply(initial());
    btn.disabled = d.findings.length <= SHOW;
    let shuffling = false;
    btn.addEventListener("click", () => {
      if (shuffling || d.findings.length <= SHOW) return;
      shuffling = true; btn.disabled = true;
      const before = [...state.discShown].sort().join();
      let ids = pick();
      for (let tries = 0; tries < 20 && [...ids].sort().join() === before; tries++) ids = pick();   // always a different three
      const swap = () => { apply(ids); host.classList.remove("swapping"); setTimeout(() => { shuffling = false; btn.disabled = false; }, reduceMotion ? 0 : 180); };
      if (reduceMotion) swap(); else { host.classList.add("swapping"); setTimeout(swap, 170); }
    });
    $("discovery-caveats").innerHTML = d.caveats.map((c) => `<li>${esc(c)}</li>`).join("");
    const p = d.provenance;
    $("discovery-prov").textContent = `${d.engine}. Data: ${p.cells} grid cells × ${p.months} months (${p.period[0]} to ${p.period[1]}), ${p.data_version}, grid_cells.csv sha256 ${p.sha256.slice(0, 12)}…`;
  }

  function buildFindings() {
    const stats = state.regionStats?.regions || {};
    const rows = [...state.regions].sort((a, b) => (a.region_id === "phoenix_study_area" ? -1 : b.region_id === "phoenix_study_area" ? 1 : b.trend.slope - a.trend.slope));
    const fastest = rows.filter((r) => r.region_id !== "phoenix_study_area")[0];
    const months = state.series[rows[0].region_id]?.times.length || 264, years = months / 12;
    $("findings-body").innerHTML = rows.map((r) => {
      const t = r.trend, st = stats[r.region_id] || {};
      return `<tr class="${r === fastest ? "fastest" : ""}"><td>${esc(r.region_id === state.quarterIds.whole ? "Whole study area" : QUARTERS[quarterOfRegion(r.region_id)]?.name || r.region)}</td><td>${t.p < 0.05 ? (t.trend === "increasing" ? "getting warmer" : t.trend === "decreasing" ? "getting cooler" : "no clear change") : "no clear change"}</td>
        <td class="num">${signed(t.slope * 12, 3)} °C</td><td class="num">${st.ci_low_per_year != null ? `${signed(st.ci_low_per_year, 3)} to ${signed(st.ci_high_per_year, 3)}` : "—"}</td>
        <td class="num">≈ ${signed(t.slope * months, 1)} °C</td><td>${esc(sureShort(t.p))}</td><td class="num">${t.tau.toFixed(2)}</td><td class="num">${pText(t.p)}</td><td class="num">${st.valid_months ?? "—"}</td></tr>`;
    }).join("");
    const allUp = rows.every((r) => r.trend.trend === "increasing" && r.trend.p < 0.05), whole = rows[0], wst = stats[whole.region_id] || {};
    $("findings-title").textContent = allUp ? "Every part of Phoenix warmed" : "Results by area";
    $("findings-lede").textContent = allUp
      ? `From ${whole.period.start.slice(0, 4)} to ${whole.period.end.slice(0, 4)}, the ground at night got warmer across the whole study area and in all four parts of it. The evidence is strong everywhere. Across the whole area the ground warmed by about ${signed(whole.trend.slope * 12, 3)} °C each year${wst.ci_low_per_year != null ? ` (most likely between ${signed(wst.ci_low_per_year, 3)} and ${signed(wst.ci_high_per_year, 3)})` : ""}, or roughly ${signed(whole.trend.slope * months, 1)} °C over ${years} years. ${areaName(quarterOfRegion(fastest.region_id))} warmed fastest.`
      : "How each part of the study area changed.";
    $("data-period").textContent = `${whole.period.start} to ${whole.period.end}, ${months} months`;
  }
  function buildMethodFigure() {
    const a = state.quarterIds.whole && state.anomaly[state.quarterIds.whole], svg = $("method-svg");
    if (!a) { svg.innerHTML = ""; return; }
    const years = [...new Set(a.times.map((t) => t.slice(0, 4)))];
    const x0 = 34, y0 = 10, dx = (360 - x0 - 8) / years.length, dy = (230 - y0 - 22) / 12;
    let html = "";
    MONTHS.forEach((m, mi) => {
      const y = y0 + mi * dy + dy / 2, hl = mi === 6;
      if (hl) html += `<rect x="${x0 - 4}" y="${y - dy / 2 + 1}" width="${360 - x0 - 4}" height="${dy - 2}" rx="4" fill="rgba(106,75,214,.09)" stroke="rgba(106,75,214,.45)"/>`;
      html += `<text x="${x0 - 8}" y="${y + 3.5}" text-anchor="end" font-size="9.5" fill="${hl ? "#b3261e" : "#9c927d"}" font-family="Courier Prime, monospace">${m}</text>`;
      years.forEach((yr, yi) => {
        const i = a.times.indexOf(`${yr}-${String(mi + 1).padStart(2, "0")}`), v = i < 0 ? null : a.values[i];
        const fill = v == null ? "#1c1d21" : v >= 0 ? `rgba(200,55,45,${0.25 + 0.75 * Math.min(1, v / 3)})` : `rgba(90,130,170,${0.25 + 0.75 * Math.min(1, -v / 3)})`;
        html += `<circle cx="${x0 + yi * dx + dx / 2}" cy="${y}" r="${Math.min(dx, dy) * 0.36}" fill="${fill}" stroke="${v == null ? "#4a463e" : "none"}"><title>${m} ${yr}: ${v == null ? "missing" : signed(v, 2) + " °C vs usual"}</title></circle>`;
      });
    });
    html += `<text x="${x0}" y="222" font-size="9.5" fill="#9c927d" font-family="Courier Prime, monospace">${years[0]}</text><text x="352" y="222" text-anchor="end" font-size="9.5" fill="#9c927d" font-family="Courier Prime, monospace">${years[years.length - 1]}</text>`;
    html += `<text x="${x0}" y="240" font-size="9.5" fill="#9c927d" font-family="Courier Prime, monospace">Blue: cooler, red: warmer than that month's usual</text>`;
    svg.innerHTML = html;
    if (state.baseline) {
      const means = state.baseline.map((b) => b.mean);
      $("swing").textContent = `${Math.round(Math.max(...means) - Math.min(...means))} °C`;
    }
  }

  function buildProvenance() {
    const d = state.discoveries?.provenance, st = state.mapStatic;
    const rows = [
      ["Product", "NASA Terra MODIS Land Surface Temperature, MOD11C3 version 6.1 (monthly), variable LST_Night_CMG"],
      ["Archive", '<a href="https://doi.org/10.5067/MODIS/MOD11C3.061">NASA LP DAAC, doi:10.5067/MODIS/MOD11C3.061</a>'],
      ["Grid", `0.05° cells (about 5 km); 16 × 12 = ${state.cells?.length ?? 192} cells, 112.4°–111.6° W, 33.2°–33.8° N`],
      ["Period", st ? `${st.period[0]} to ${st.period[1]}` : "2003-01 to 2024-12"],
      ["Quality control", "Good-quality flags and estimated error under 1 K only; failed months stay missing, never filled"],
      ["Data version", d ? `<span class="mono">${esc(d.data_version)}</span>` : "phoenix-qc-v1.0"],
      ["Cell file fingerprint", d ? `<span class="mono">grid_cells.csv sha256 ${esc(d.sha256.slice(0, 16))}…</span>` : "—"],
      ["Statistics", "pymannkendall seasonal Mann-Kendall and Sen's slope; Sen's slope 95% CI (Gilbert 1987); Benjamini-Hochberg FDR"],
      ["Map outline", "Natural Earth urban areas (public domain, MODIS c. 2002–2003): visual only"],
    ];
    $("provenance").innerHTML = rows.map(([k, v]) => `<div><dt>${esc(k)}</dt><dd>${v}</dd></div>`).join("");
  }
  // ---------- data loading ----------
  async function load() {
    Object.assign(state, readUrl());
    try {
      const fw = await getJSON("assets/phoenix_freeways.json", true).catch(() => null);
      if (fw) for (const q of ORDER) freeways[q] = fw.paths.flatMap((p) => clipPolyline(p.path, QUARTERS[q].b));
      const ua = await getJSON("assets/phoenix_urban_area.json", true).catch(() => null);
      if (ua) { urban.parts = ua.quarters; urban.inside = new Set(ua.inside_cells); }
      const regions = (await getJSON(`${API}/regions`)).regions;
      state.regions = regions;
      state.quarterIds.whole = regions.find((r) => r.region_id.endsWith("_study_area"))?.region_id;
      for (const q of ORDER) {
        const r = regions.find((x) => x.region_id.endsWith("_" + QUARTERS[q].name.toLowerCase()));
        if (r) state.quarterIds[q] = r.region_id;
      }
      const ids = regions.map((r) => r.region_id);
      const [series, anomalies, stats, discoveries, mapStatic] = await Promise.all([
        Promise.all(ids.map((id) => getJSON(`${API}/series?region=${encodeURIComponent(id)}`))),
        Promise.all(ids.map((id) => getJSON(`${API}/anomaly?region=${encodeURIComponent(id)}`, true).catch(() => null))),
        getJSON(`${API}/region-stats`, true).catch(() => null),
        getJSON(`${API}/discoveries`, true).catch(() => null),
        getJSON(`${API}/map-static`).catch((err) => { state.cellsError = err.message; return null; }),
      ]);
      series.forEach((s) => { state.series[s.region_id] = {times: s.series.map((p) => p.time), values: s.series.map((p) => p.value)}; });
      anomalies.forEach((a) => {
        if (!a) return;
        state.anomaly[a.region_id] = {times: a.series.map((p) => p.time), values: a.series.map((p) => p.value)};
        if (a.region_id === state.quarterIds.whole) state.baseline = a.baseline;
      });
      state.regionStats = stats; state.discoveries = discoveries;
      if (mapStatic) {
        state.mapStatic = mapStatic;
        state.cells = mapStatic.cells;
        state.cellIndex = Object.fromEntries(mapStatic.cells.map((c) => [c.id, c]));
      }
      if (state.cell && !state.cellIndex[state.cell]) state.cell = null;
      const times = state.series[state.quarterIds.whole || ids[0]].times;
      const years = [...new Set(times.map((t) => +t.slice(0, 4)))];
      buildControls(years); buildCompareControls(years); buildPanels(); buildFindings(); buildMethodFigure(); buildProvenance();
      buildDiscoveries(); renderCoverage(); setupReveal();
      await showPeriod();
      renderCompare(); renderRegionTest();
      if (state.finding) setState({finding: state.finding});
    } catch (err) {
      state.error = err.message || String(err);
    }
    writeUrl();
    renderAll();
  }

  function setupReveal() {
    if (reduceMotion || !("IntersectionObserver" in window)) return;
    const groups = [...document.querySelectorAll("#story .block-head, #story .ask-box, #story .chips, #story .disc-bar, #story .disc, #story .det-how, #story .foot")];
    const io = new IntersectionObserver((entries) => {
      for (const en of entries) {
        if (en.isIntersecting) en.target.classList.add("in");
        else if (en.boundingClientRect.top > 0) en.target.classList.remove("in");   // fades again when you scroll back up
      }
    }, {rootMargin: "0px 0px -8% 0px", threshold: 0.05});
    groups.forEach((el, i) => {
      el.classList.add("reveal");
      if (el.classList.contains("disc")) el.style.transitionDelay = `${([...el.parentNode.children].indexOf(el) % 3) * 70}ms`;
      io.observe(el);
    });
    setTimeout(() => document.documentElement.classList.add("reveal-ready"), 0);
  }

  window.addEventListener("scroll", onScroll, {passive: true});
  window.addEventListener("resize", () => { deckgl.setProps({initialViewState: fitView()}); computeTargets(); renderAll(); });
  window.addEventListener("hashchange", () => { const s = readUrl(); Object.assign(state, s); showPeriod(); renderAll(); });
  computeTargets();
  onScroll();
  renderAll();
  load();
})();

// Phone: start with the control panel collapsed to the title, period and timeline.
(function setupControlToggle() {
  const panel = document.getElementById("controls");
  const btn = document.getElementById("ctl-toggle");
  if (!panel || !btn) return;
  const apply = (collapsed) => {
    panel.classList.toggle("collapsed", collapsed);
    btn.setAttribute("aria-expanded", String(!collapsed));
    btn.textContent = collapsed ? "More controls" : "Hide controls";
  };
  apply(window.matchMedia("(max-width: 640px)").matches);
  btn.addEventListener("click", () => apply(!panel.classList.contains("collapsed")));
})();
