/* Earth System Trend Detective — map explorer.
 *
 * Data rules (same as the rest of the project):
 *  - Every number comes from the backend: regional results (/regions, /series, /anomaly,
 *    /region-stats, /region-compare), one map frame at a time (/map-frame: one month's value per
 *    grid cell, never the whole dataset), per-cell trend and coverage (/map-static) and verified
 *    AI discoveries (/discoveries). Nothing is interpolated or estimated in the browser.
 *  - A missing month stays missing. An annual average needs all 12 months (enforced server-side).
 *  - One shared state object drives every view; the URL hash mirrors it for shareable links.
 * The camera never moves. Scrolling only moves the four quarter pieces.
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
  const HIGHLIGHT = {faster: [106, 75, 214], slower: [37, 99, 235], extremes: [217, 70, 39],
                     anomalies: [217, 119, 6], none: [106, 75, 214]};
  const METRES_PER_DEG_C = 95;                 // column height scale (fixed for every period)
  const PITCH = 42;
  const reduceMotion = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
  const params = new URLSearchParams(location.search);
  const API = (params.get("api") || (location.pathname.startsWith("/app") ? "" : "http://127.0.0.1:8000"))
    .replace(/\/$/, "");
  const CHARS = " ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789.,:+-()°·–/".split("");

  // ---------- layer definitions (each with its own scale, units and description) ----------
  const RAMP_TEMP = [[49, 54, 149], [69, 117, 180], [116, 173, 209], [171, 217, 233], [254, 224, 144],
                     [253, 174, 97], [244, 109, 67], [215, 48, 39], [165, 0, 38]];
  const RAMP_DIV = [[33, 102, 172], [103, 169, 207], [209, 229, 240], [247, 247, 247], [253, 219, 199],
                    [239, 138, 98], [178, 24, 43]];
  const RAMP_RATE = [[247, 244, 249], [212, 185, 218], [201, 148, 199], [223, 101, 176], [231, 41, 138],
                     [152, 0, 67]];
  const RAMP_COV = [[240, 240, 240], [189, 201, 225], [116, 169, 207], [43, 140, 190], [4, 90, 141]];
  const LAYERS = {
    temperature: {label: "Temperature", unit: "°C", min: 0, max: 40, ramp: RAMP_TEMP,
      ticks: ["0 °C", "10", "20", "30", "40 °C"],
      note: "Measured nighttime land surface temperature for the selected period. Height and colour use one fixed 0–40 °C scale; outlined squares had no valid measurement."},
    anomaly: {label: "Anomaly", unit: "°C", min: -4, max: 4, ramp: RAMP_DIV,
      ticks: ["−4 °C", "−2", "0", "+2", "+4 °C"],
      note: "Difference from the same cell's 2003–2024 average for that calendar month (annual view: its mean of complete years). Blue cooler than usual, red warmer."},
    rate: {label: "Warming rate", unit: "°C/yr", min: 0, max: 0.2, ramp: RAMP_RATE,
      ticks: ["0", "0.05", "0.10", "0.15", "0.20 °C/yr"],
      note: "Each cell's 2003–2024 trend (seasonal Sen's slope per year). Faded cells are not significant after false-discovery-rate correction. Same for every year and month."},
    coverage: {label: "Coverage", unit: "months", min: 0, max: 12, ramp: RAMP_COV,
      ticks: ["0", "3", "6", "9", "12 months"],
      note: "Valid months in the selected year for each cell (of 12), after NASA quality control. Missing months are never filled in."},
  };

  // ---------- shared state ----------
  const state = {
    // selections (mirrored in the URL)
    year: 2024, month: 7, layer: "temperature", region: "all", cell: null, finding: null,
    compA: {year: 2003, month: "avg"}, compB: {year: 2023, month: "avg"}, rtA: "phoenix_southeast", rtB: "phoenix_northeast",
    // playback / scroll
    playing: false, speed: 900, progress: 0, eased: 0,
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
    if (state.finding) p.set("finding", state.finding);
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

  // ---------- deck ----------
  const deckgl = new Deck({
    parent: $("map"), controller: false, initialViewState: fitView(), getTooltip, layers: [],
    useDevicePixels: Math.min(window.devicePixelRatio || 1, 2),
    onClick: ({object}) => { if (object && object.kind === "cell") setState({cell: object.id}); },
    onError: (err) => console.warn("deck.gl:", err),
  });

  function fitView() {
    const el = $("map"), w = el.clientWidth || window.innerWidth, h = el.clientHeight || window.innerHeight;
    const phone = w < 640;
    const ctlBottom = ($("controls").getBoundingClientRect().bottom || 300) + 12;
    const brandH = w < 900 ? (document.querySelector(".brand").offsetHeight || 120) + 70 : 70;
    const pad = w > 1100 ? {top: 70, bottom: 70, left: 360, right: 40}
      : {top: ctlBottom, bottom: brandH, left: phone ? 6 : 24, right: phone ? 6 : 24};
    const vp = new WebMercatorViewport({width: w, height: h}).fitBounds([[W, S], [E, N]], {padding: pad});
    state.view = {longitude: vp.longitude, latitude: vp.latitude + 0.03, zoom: vp.zoom + 0.02,
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
    const style = {backgroundColor: "#fff", color: "#141a2b", border: "1px solid #cfd4e2", borderRadius: "8px",
                   fontSize: "12px", boxShadow: "0 6px 16px rgba(20,26,43,.12)", padding: "8px 10px"};
    if (object.kind === "cell") {
      const v = layerValue(object), L = LAYERS[state.layer];
      const shown = v == null ? "no valid measurement" : state.layer === "rate" ? `${signed(v, 3)} °C/yr` :
        state.layer === "anomaly" ? `${signed(v, 2)} °C vs usual` : state.layer === "coverage" ? `${v} of 12 months` : `${fmt(v, 2)} °C`;
      return {style, html: `<b>Cell ${esc(object.id)}</b> · ${esc(QUARTERS[object.quarter].name)}<br>${esc(L.label)}${state.layer === "rate" ? "" : `, ${esc(periodLabel())}`}: <b>${shown}</b><br><span style="color:#7a839c">Click for details</span>`};
    }
    if (object.kind === "quarter") {
      return {style, html: `<b>${esc(object.label)}</b><br>Quarter average, ${esc(periodLabel())}: <b>${object.value == null ? "no valid value" : fmt(object.value, 2) + " °C"}</b>`};
    }
    return null;
  }

  function buildLayers() {
    const e = state.eased, layers = [];
    const trans = reduceMotion ? {} : {getElevation: {duration: 450, easing: easeInOut}, getFillColor: {duration: 450, easing: easeInOut}};
    layers.push(new TileLayer({
      // Esri World Light Gray Canvas: no API key needed.
      id: "basemap", minZoom: 0, maxZoom: 16, tileSize: 256, opacity: 1 - 0.9 * e,
      data: "https://server.arcgisonline.com/ArcGIS/rest/services/Canvas/World_Light_Gray_Base/MapServer/tile/{z}/{y}/{x}",
      onTileError: () => {}, maxRequests: 8,
      renderSubLayers: (props) => {
        const {boundingBox} = props.tile;
        return new BitmapLayer(props, {data: null, image: props.data,
          bounds: [boundingBox[0][0], boundingBox[0][1], boundingBox[1][0], boundingBox[1][1]]});
      },
    }));
    const finding = state.finding && state.discoveries?.findings.find((x) => x.id === state.finding);
    for (const q of ORDER) {
      const {k, f} = pieceTransform(q, e);
      const [w, s, ea, n] = QUARTERS[q].b;
      const dim = state.region !== "all" && state.region !== q;
      layers.push(new PolygonLayer({
        id: `piece-${q}`, data: [{poly: rect(w, s, ea, n)}], getPolygon: (d) => d.poly.map(f),
        getFillColor: [255, 255, 255, Math.round(70 + 170 * e)],
        getLineColor: state.region === q ? [106, 75, 214, 255] : [120, 132, 168, 200],
        lineWidthUnits: "pixels", getLineWidth: state.region === q ? 2.5 : 1, stroked: true, filled: true,
        updateTriggers: {getPolygon: e, getFillColor: e, getLineColor: state.region, getLineWidth: state.region},
      }));
      layers.push(new PathLayer({id: `roads-${q}`, data: freeways[q], getPath: (d) => d.map(f),
        getColor: [96, 108, 140, 150], widthUnits: "pixels", getWidth: 1.2, updateTriggers: {getPath: e}}));

      if (state.cells) {
        const recs = state.cells.filter((c) => c.quarter === q).map((c) => cellRecord(c.id));
        const alpha = dim ? 70 : 235;
        const has = recs.filter((r) => layerValue(r) != null), missing = recs.filter((r) => layerValue(r) == null);
        layers.push(new PolygonLayer({   // missing cells: outline only, never a value
          id: `missing-${q}`, data: missing, pickable: true,
          getPolygon: (c) => c.footprint.map((p) => [c.lon + (p[0] - c.lon) * 0.84, c.lat + (p[1] - c.lat) * 0.84]).map(f),
          getFillColor: [255, 255, 255, 0], getLineColor: [150, 158, 184, dim ? 90 : 220], lineWidthUnits: "pixels",
          getLineWidth: 1, stroked: true, filled: true,
          updateTriggers: {getPolygon: e, getLineColor: dim},
        }));
        const colour = (r) => {
          const a = state.layer === "rate" && !r.significant_fdr ? Math.round(alpha * 0.35) : alpha;
          return layerColor(state.layer, layerValue(r), a);
        };
        if (state.layer === "temperature") {
          layers.push(new ColumnLayer({
            id: `cells-${q}`, data: has, pickable: true, extruded: true, diskResolution: 4, angle: 45,
            radius: 0.05 * 0.3 * 111320 * Math.SQRT2 * Math.cos(33.5 * Math.PI / 180) * k,
            getPosition: (c) => f([c.lon, c.lat]), getElevation: (c) => Math.max(0, c.value) * METRES_PER_DEG_C,
            elevationScale: k, getFillColor: colour, autoHighlight: true, highlightColor: [106, 75, 214, 170],
            material: {ambient: 0.55, diffuse: 0.55, shininess: 24}, transitions: trans,
            updateTriggers: {getPosition: e, getElevation: state.frame, getFillColor: [state.frame, state.region]},
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
            getColor: [20, 26, 43, 255], widthUnits: "pixels", getWidth: 3, parameters: {depthTest: false},
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
        id: `qname-${q}`, data: [{t: QUARTERS[q].name.toUpperCase()}], characterSet: CHARS,
        getPosition: () => f([q.endsWith("W") ? w + 0.012 : ea - 0.012, n - 0.012]),
        getTextAnchor: q.endsWith("W") ? "start" : "end", getAlignmentBaseline: "top",
        getText: (d) => d.t, getSize: 11, getColor: state.region === q ? [106, 75, 214, 255] : [74, 84, 112, 230],
        fontWeight: 700, fontFamily: "system-ui, -apple-system, Segoe UI, Arial", parameters: {depthTest: false},
        updateTriggers: {getPosition: e, getColor: state.region},
      }));
    }
    const placeAlpha = Math.round(230 * (1 - clamp(e * 3)));
    layers.push(new TextLayer({
      id: "places", data: PLACES, characterSet: CHARS, getPosition: (d) => [d[1], d[2], 4200],
      getText: (d) => d[0], getSize: 12, getColor: [20, 26, 43, placeAlpha], fontWeight: 600,
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
      const e = state.eased;
      deckgl.setProps({layers: buildLayers()});
      $("hint").style.opacity = String(1 - clamp(e * 4));
      document.querySelector(".brand").style.opacity = String(1 - clamp(e * 2.5));
      const ctl = $("controls");
      ctl.style.opacity = String(1 - clamp((e - 0.15) * 3));
      ctl.style.pointerEvents = e > 0.4 ? "none" : "auto";
      ctl.setAttribute("aria-hidden", e > 0.4 ? "true" : "false");
      $("inspector").style.opacity = String(1 - clamp((e - 0.1) * 4));
      syncControls(); renderLegend(); renderInspector(); renderStatus(); placePanels(); updatePanels();
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
    const L = LAYERS[state.layer];
    const finding = state.finding && state.discoveries?.findings.find((x) => x.id === state.finding);
    $("legend").innerHTML = `<div class="legend-title">${esc(L.label)} <span>(${esc(L.unit)})</span></div>
      <div class="legend-bar" style="background:${rampCss(L.ramp)}" aria-hidden="true"></div>
      <div class="legend-scale" aria-hidden="true">${L.ticks.map((t) => `<span>${esc(t)}</span>`).join("")}</div>
      <p class="legend-note">${esc(L.note)}</p>
      ${!reduceMotion && state.layer !== "rate" ? '<p class="legend-note">Changes ease between observed frames; only the settled frame is data.</p>' : ""}
      ${finding ? `<p class="legend-note overlay"><i style="border-color:rgb(${(HIGHLIGHT[finding.highlight] || HIGHLIGHT.none).join(",")})"></i>${esc(finding.title)} (${esc(finding.status)}): ${finding.cells.length} cells outlined.</p>` : ""}`;
  }

  function renderStatus() {
    const el = $("data-status");
    el.classList.remove("warn");
    if (state.error) {
      el.classList.add("warn");
      el.innerHTML = `Could not load NASA results (${esc(state.error)}). <button type="button" id="retry">Retry</button>`;
      $("retry").onclick = () => location.reload();
      return;
    }
    if (!state.cells) {
      el.classList.add("warn");
      el.innerHTML = state.cellsError ? `Cell-level map unavailable (${esc(state.cellsError)}); showing the four quarter averages instead.` : "Loading cells…";
      return;
    }
    if (state.layer === "rate") {
      el.innerHTML = `${state.cells.filter((c) => c.significant_fdr).length} of ${state.cells.length} cells have a significant trend after correction.`;
      return;
    }
    if (!state.frame) { el.textContent = state.cellsError ? `This period could not be loaded (${state.cellsError}).` : "Loading…"; return; }
    const shown = state.frame.cells.filter((c) => c.value != null).length;
    el.innerHTML = `<b>${shown} of ${state.frame.cells.length}</b> cells have a valid measurement for ${esc(periodLabel())}.${state.month === "avg" ? " An annual average needs all 12 months." : ""}`;
  }

  function renderInspector() {
    const box = $("inspector");
    if (!state.cell || !state.cellIndex[state.cell]) { box.hidden = true; return; }
    const r = cellRecord(state.cell);
    box.hidden = false;
    $("inspector-body").innerHTML = `
      <h3>Cell ${esc(r.id)}</h3>
      <p class="ins-sub">${r.lat.toFixed(3)}° N, ${Math.abs(r.lon).toFixed(3)}° W · ${esc(QUARTERS[r.quarter].name)} quarter · 0.05° (≈5 km)</p>
      <dl>
        <dt>${esc(periodLabel())}</dt><dd>${r.value == null ? "no valid measurement" : `${fmt(r.value, 2)} °C`}</dd>
        <dt>Anomaly</dt><dd>${r.anomaly == null ? "—" : `${signed(r.anomaly, 2)} °C vs usual`}</dd>
        <dt>Valid months in ${state.year}</dt><dd>${r.validInYear ?? "—"} of 12</dd>
        <dt>Trend 2003–2024</dt><dd>${signed(r.slope_per_year, 3)} °C/yr</dd>
        <dt>95% CI</dt><dd>${signed(r.ci_low_per_year, 3)} to ${signed(r.ci_high_per_year, 3)}</dd>
        <dt>Significance</dt><dd>${r.q == null ? "—" : `${r.significant_fdr ? "significant" : "not significant"} (q = ${r.q.toPrecision(2)})`}</dd>
        <dt>Valid months overall</dt><dd>${r.valid_months} of ${r.months}</dd>
      </dl>
      <p class="ins-note">q is the p-value corrected for testing all ${state.cells.length} cells (Benjamini-Hochberg). Seasonal Mann-Kendall and Sen's slope on this cell's own QC'd months.</p>`;
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
      if (b.v == null) return `<rect x="${i * bw + bw * 0.2}" y="${mid - 0.5}" width="${bw * 0.6}" height="1" fill="#cfd4e2"><title>${b.y}: incomplete year</title></rect>`;
      const h = (Math.abs(b.v) / max) * (mid - 2), y = b.v >= 0 ? mid - h : mid;
      return `<rect x="${i * bw + bw * 0.15}" y="${y}" width="${bw * 0.7}" height="${Math.max(h, 0.8)}" fill="${b.v >= 0 ? "#d9603b" : "#4575b4"}"><title>${b.y}: ${signed(b.v, 2)} °C vs average</title></rect>`;
    }).join("");
    return `<svg viewBox="0 0 ${W2} ${H2}" preserveAspectRatio="none" role="img" aria-label="Yearly mean anomaly bars, 2003 to 2024"><line x1="0" x2="${W2}" y1="${mid}" y2="${mid}" stroke="#cfd4e2"/>${rects}</svg>`;
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
      el.className = "panel" + (isFastest ? " fastest" : "");
      el.id = `panel-${q}`;
      el.tabIndex = 0;
      el.setAttribute("aria-label", `${QUARTERS[q].name} quarter; select to focus this region`);
      el.innerHTML = `
        <div class="panel-head"><h3>${QUARTERS[q].name}</h3>${isFastest ? '<span class="tag">Fastest warming</span>' : ""}</div>
        <p class="rate${perYear < 0 ? " cool" : ""}">${signed(perYear, 3)} °C<small>per year</small></p>
        <p class="ci">${st.ci_low_per_year != null ? `95% CI ${signed(st.ci_low_per_year, 3)} to ${signed(st.ci_high_per_year, 3)}` : ""}</p>
        <p class="sig">${sig ? "Statistically significant" : "Not statistically significant"} · ${pText(t.p)} · τ ${t.tau.toFixed(2)}</p>
        ${sparkSVG(r.region_id)}
        <div class="spark-cap"><span>2003</span><span>yearly mean vs average (full years)</span><span>2024</span></div>
        <dl><dt id="pl-${q}">—</dt><dd id="pv-${q}">—</dd><dt>Valid months</dt><dd>${st.valid_months ?? "—"} of ${st.months ?? 264}</dd></dl>`;
      el.addEventListener("click", () => setState({region: state.region === q ? "all" : q}));
      el.addEventListener("keydown", (ev) => { if (ev.key === "Enter" || ev.key === " ") { ev.preventDefault(); el.click(); } });
      host.appendChild(el);
    }
  }
  function updatePanels() {
    for (const q of ORDER) {
      const rid = state.quarterIds[q], s = rid && state.series[rid];
      const l = document.getElementById(`pl-${q}`), v = document.getElementById(`pv-${q}`);
      if (!l || !s) continue;
      l.textContent = `${periodLabel()}, quarter avg`;
      const val = periodValue(s.times, s.values, state.year, state.month);
      v.textContent = val == null ? "no value" : `${fmt(val)} °C`;
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
    $("region").addEventListener("change", () => setState({region: $("region").value}));
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
    $("inspector-close").addEventListener("click", () => setState({cell: null}));
    $("share").addEventListener("click", async () => {
      writeUrl();
      try { await navigator.clipboard.writeText(location.href); $("share").textContent = "Link copied"; }
      catch { $("share").textContent = "Copy from the address bar"; }
      setTimeout(() => { $("share").textContent = "Copy link to this view"; }, 2000);
    });
    $("csv").addEventListener("click", downloadCsv);
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
      <p><b>${diffs.length}</b> cells measured in both periods; mean cell ΔT <b>${signed(mean, 2)} °C</b>. White cells lack a valid value in at least one period.</p>
      <table class="mini"><thead><tr><th>Regional average</th><th>A (°C)</th><th>B (°C)</th><th>ΔT</th></tr></thead><tbody>${regional}</tbody></table>
      <p class="note">A single-period difference mixes the long-term trend with year-to-year weather. For the trend itself see the warming-rate layer and the findings table; no significance is claimed here.</p>`;
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
      out.innerHTML = `<b>${esc(name(r.region_a))} minus ${esc(name(r.region_b))}:</b> ${signed(r.difference_slope_per_year, 3)} °C/yr (95% CI ${signed(r.ci_low_per_year, 3)} to ${signed(r.ci_high_per_year, 3)}), ${pText(r.p)}, ${r.months_used} months. <span class="badge ${r.significant ? "supported" : "not_supported"}">${r.significant ? "Trends differ significantly" : "No significant difference detected"}</span>`;
    } catch (err) {
      out.innerHTML = `<span class="det-info">The comparison could not be run (${esc(err.message)}).</span>`;
    }
  }

  // ---------- coverage ----------
  function renderCoverage() {
    if (!state.cells) { $("coverage-summary").textContent = "Cell-level coverage is unavailable right now."; return; }
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
    $("coverage-summary").innerHTML = `Across all cells, <b>${valid.toLocaleString()} of ${total.toLocaleString()}</b> cell-months passed quality control (${(100 * valid / total).toFixed(1)}%). The cell with the most gaps, ${esc(worst.id)}, still has ${worst.valid_months} of ${worst.months} months. Regional averages are left blank when less than 80% of a region's area passes; that happened in 8 quarter-months over 22 years.`;
  }

  // ---------- discovery engine ----------
  const STATUS = {supported: "Statistically supported", exploratory: "Exploratory", not_supported: "Not supported"};
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
  function buildDiscoveries() {
    const d = state.discoveries, host = $("discovery-list");
    if (!d) {
      host.innerHTML = '<p class="det-info">The Discovery Engine is unavailable right now (the cell-level analysis service did not answer). Regional results above are unaffected.</p>';
      $("finding-wrap").hidden = true; $("discover").disabled = true; return;
    }
    const sel = $("finding");
    for (const f of d.findings.filter((x) => x.cells.length)) {
      const o = document.createElement("option");
      o.value = f.id; o.textContent = `${f.title} (${STATUS[f.status].toLowerCase()})`;
      sel.appendChild(o);
    }
    sel.addEventListener("change", () => setState({finding: sel.value || null}));
    host.innerHTML = d.findings.map((f) => `
      <article class="disc ${esc(f.status)}" data-id="${esc(f.id)}">
        <div class="disc-head"><span class="badge ${esc(f.status)}">${esc(STATUS[f.status])}</span>${f.cells.length ? `<button type="button" data-finding="${esc(f.id)}">Show on map</button>` : ""}</div>
        <h3>${esc(f.title)}</h3>
        <p class="disc-obs">${esc(f.observation)}</p>
        <dl class="disc-fields">
          <dt>Location</dt><dd>${esc(f.location)}</dd>
          <dt>Period</dt><dd>${esc(f.period)}</dd>
          <dt>Data</dt><dd>${esc(f.source)}; ${esc(f.variable.toLowerCase())}</dd>
          <dt>Evidence</dt><dd>${esc(f.evidence_text)}</dd>
          <dt>Confidence</dt><dd>${esc(f.confidence)}</dd>
          <dt>Method</dt><dd>${esc(f.method)}</dd>
          <dt>Challenge</dt><dd>${esc(f.challenge)}</dd>
          <dt>Limitations</dt><dd>${esc(f.limitations)}</dd>
          <dt>Next question</dt><dd>${esc(f.next_question)}</dd>
        </dl>
      </article>`).join("");
    host.querySelectorAll("button[data-finding]").forEach((b) => b.addEventListener("click", () => showDiscovery(b.dataset.finding)));
    let next = 0;
    $("discover").addEventListener("click", () => {
      const order = [...d.findings].sort((a, b) => (a.status === "supported" ? 0 : 1) - (b.status === "supported" ? 0 : 1));
      const f = order[next++ % order.length];
      $("ask-result").hidden = false;
      $("ask-result").innerHTML = `<b>${esc(STATUS[f.status])}:</b> ${esc(f.title)}. ${f.cells.length ? "Its cells are outlined on the map." : ""} Next question: ${esc(f.next_question)}`;
      showDiscovery(f.id, false);
    });
    $("ask").addEventListener("submit", (ev) => {
      ev.preventDefault();
      const q = $("ask-input").value.toLowerCase();
      const hit = ASK_RULES.find(([re]) => re.test(q));
      $("ask-result").hidden = false;
      if (!hit) {
        $("ask-result").innerHTML = "The Discovery Engine answers questions it has a tested analysis for: faster or slower neighbourhoods, hidden spread inside averages, seasons, unusual months and how widespread the warming is. For questions about the regions, try the Climate Detective below. It never guesses beyond its tools.";
        return;
      }
      const f = d.findings.find((x) => x.id === hit[1]);
      $("ask-result").innerHTML = `<b>${esc(STATUS[f.status])}:</b> ${esc(f.observation)}`;
      showDiscovery(f.id, false);
    });
    $("discovery-caveats").innerHTML = d.caveats.map((c) => `<li>${esc(c)}</li>`).join("");
    const p = d.provenance;
    $("discovery-prov").textContent = `${d.engine}. Data: ${p.cells} grid cells × ${p.months} months (${p.period[0]} to ${p.period[1]}), ${p.data_version}, grid_cells.csv sha256 ${p.sha256.slice(0, 12)}…`;
  }

  // ---------- story: findings + method figure ----------
  function buildFindings() {
    const stats = state.regionStats?.regions || {};
    const rows = [...state.regions].sort((a, b) => (a.region_id === "phoenix_study_area" ? -1 : b.region_id === "phoenix_study_area" ? 1 : b.trend.slope - a.trend.slope));
    const fastest = rows.filter((r) => r.region_id !== "phoenix_study_area")[0];
    const months = state.series[rows[0].region_id]?.times.length || 264, years = months / 12;
    $("findings-body").innerHTML = rows.map((r) => {
      const t = r.trend, st = stats[r.region_id] || {};
      return `<tr class="${r === fastest ? "fastest" : ""}"><td>${esc(r.region)}</td><td>${esc(t.trend)}${t.p < 0.05 ? ", significant" : ", not significant"}</td>
        <td class="num">${signed(t.slope * 12, 3)} °C</td><td class="num">${st.ci_low_per_year != null ? `${signed(st.ci_low_per_year, 3)} to ${signed(st.ci_high_per_year, 3)}` : "—"}</td>
        <td class="num">≈ ${signed(t.slope * months, 1)} °C</td><td class="num">${t.tau.toFixed(2)}</td><td class="num">${pText(t.p)}</td><td class="num">${st.valid_months ?? "—"}</td></tr>`;
    }).join("");
    const allUp = rows.every((r) => r.trend.trend === "increasing" && r.trend.p < 0.05), whole = rows[0], wst = stats[whole.region_id] || {};
    $("findings-title").textContent = allUp ? "Every part of Phoenix warmed" : "Results by area";
    $("findings-lede").textContent = allUp
      ? `From ${whole.period.start} to ${whole.period.end}, nighttime land surface temperature rose in the whole study area and in all four quarters, and every trend is statistically significant. Across the whole area the trend is ${signed(whole.trend.slope * 12, 3)} °C per year${wst.ci_low_per_year != null ? ` (95% CI ${signed(wst.ci_low_per_year, 3)} to ${signed(wst.ci_high_per_year, 3)})` : ""}, roughly ${signed(whole.trend.slope * months, 1)} °C over ${years} years. The ${fastest.region.replace("Phoenix study area ", "")} quarter warmed fastest.`
      : "Trend results for the whole study area and each quarter.";
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
      html += `<text x="${x0 - 8}" y="${y + 3.5}" text-anchor="end" font-size="9.5" fill="${hl ? "#6a4bd6" : "#7a839c"}" font-family="system-ui">${m}</text>`;
      years.forEach((yr, yi) => {
        const i = a.times.indexOf(`${yr}-${String(mi + 1).padStart(2, "0")}`), v = i < 0 ? null : a.values[i];
        const fill = v == null ? "#ffffff" : v >= 0 ? `rgba(217,96,59,${0.25 + 0.75 * Math.min(1, v / 3)})` : `rgba(69,117,180,${0.25 + 0.75 * Math.min(1, -v / 3)})`;
        html += `<circle cx="${x0 + yi * dx + dx / 2}" cy="${y}" r="${Math.min(dx, dy) * 0.36}" fill="${fill}" stroke="${v == null ? "#cfd4e2" : "none"}"><title>${m} ${yr}: ${v == null ? "missing" : signed(v, 2) + " °C vs usual"}</title></circle>`;
      });
    });
    html += `<text x="${x0}" y="222" font-size="9.5" fill="#7a839c" font-family="system-ui">${years[0]}</text><text x="352" y="222" text-anchor="end" font-size="9.5" fill="#7a839c" font-family="system-ui">${years[years.length - 1]}</text>`;
    html += `<text x="${x0}" y="240" font-size="9.5" fill="#7a839c" font-family="system-ui">Blue: cooler, orange: warmer than that month's average (whole study area)</text>`;
    svg.innerHTML = html;
    if (state.baseline) {
      const means = state.baseline.map((b) => b.mean);
      $("swing").textContent = `${Math.round(Math.max(...means) - Math.min(...means))} °C`;
    }
  }

  // ---------- data loading ----------
  async function load() {
    Object.assign(state, readUrl());
    try {
      const fw = await getJSON("assets/phoenix_freeways.json", true).catch(() => null);
      if (fw) for (const q of ORDER) freeways[q] = fw.paths.flatMap((p) => clipPolyline(p.path, QUARTERS[q].b));
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
        state.cells = mapStatic.cells;
        state.cellIndex = Object.fromEntries(mapStatic.cells.map((c) => [c.id, c]));
      }
      if (state.cell && !state.cellIndex[state.cell]) state.cell = null;
      const times = state.series[state.quarterIds.whole || ids[0]].times;
      const years = [...new Set(times.map((t) => +t.slice(0, 4)))];
      buildControls(years); buildCompareControls(years); buildPanels(); buildFindings(); buildMethodFigure();
      buildDiscoveries(); renderCoverage();
      await showPeriod();
      renderCompare(); renderRegionTest();
      if (state.finding) setState({finding: state.finding});
    } catch (err) {
      state.error = err.message || String(err);
    }
    writeUrl();
    renderAll();
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
