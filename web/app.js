/* Earth System Trend Detective — map explorer.
 *
 * Data rules (same as the rest of the project):
 *  - Every number comes from the backend (/regions, /series, /anomaly) or from
 *    data/grid.json, which is built from the Data layer's per-cell export
 *    (scripts/build_grid_json.py). Nothing is interpolated or estimated.
 *  - A missing month stays missing. An annual average needs all 12 months.
 *  - Without grid.json the map shows each quarter's real regional average,
 *    labelled as such, never pretend per-cell values.
 * The camera never moves. Scrolling only moves the four quarter pieces.
 */
(() => {
  "use strict";
  const {Deck, ColumnLayer, PolygonLayer, PathLayer, TextLayer, TileLayer, BitmapLayer,
         WebMercatorViewport} = deck;

  // Study window and quarter split (docs/data_card.md).
  const W = -112.4, S = 33.2, E = -111.6, N = 33.8, MID_LON = -112.0, MID_LAT = 33.5, CELL = 0.05;
  const QUARTERS = {
    NW: {name: "Northwest", b: [W, MID_LAT, MID_LON, N], dir: [-1, 1]},
    NE: {name: "Northeast", b: [MID_LON, MID_LAT, E, N], dir: [1, 1]},
    SW: {name: "Southwest", b: [W, S, MID_LON, MID_LAT], dir: [-1, -1]},
    SE: {name: "Southeast", b: [MID_LON, S, E, MID_LAT], dir: [1, -1]},
  };
  const ORDER = ["NW", "NE", "SW", "SE"];
  const MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];
  const PLACES = [["Downtown Phoenix", -112.074, 33.4484], ["Tempe", -111.94, 33.4255],
                  ["Glendale", -112.186, 33.5387], ["Scottsdale", -111.926, 33.4942]];
  const T_MIN = 0, T_MAX = 40;               // one fixed colour/height scale for every view
  const METRES_PER_DEG_C = 95;               // column height scale (34 °C ≈ 3.2 km on a 5 km cell)
  const PITCH = 42;
  const reduceMotion = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
  const params = new URLSearchParams(location.search);
  const API = (params.get("api") || (location.pathname.startsWith("/app") ? "" : "http://127.0.0.1:8000"))
    .replace(/\/$/, "");
  const CHARS = " ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789.,:+-()°·–/".split("");

  const state = {
    regions: null, series: {}, anomaly: {}, baseline: null, grid: null,
    year: 2024, month: 7, progress: 0, eased: 0, quarterIds: {}, view: null, error: null, targets: {},
  };

  // ---------- small helpers ----------
  const $ = (id) => document.getElementById(id);
  const clamp = (x, a = 0, b = 1) => Math.min(b, Math.max(a, x));
  const easeInOut = (t) => (t < 0.5 ? 4 * t * t * t : 1 - Math.pow(-2 * t + 2, 3) / 2);
  const fmt = (x, d = 1) => (x == null ? "—" : x.toFixed(d));
  const signed = (x, d) => (x >= 0 ? "+" : "−") + Math.abs(x).toFixed(d);
  const pText = (p) => (p < 0.001 ? "p < 0.001" : `p = ${p.toPrecision(2)}`);
  const esc = (s) => String(s).replace(/[&<>"']/g, (c) => ({"&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;"}[c]));

  // Cool-to-hot scale (ColorBrewer RdYlBu, reversed), fixed 0–40 °C.
  const STOPS = [[49, 54, 149], [69, 117, 180], [116, 173, 209], [171, 217, 233], [254, 224, 144],
                 [253, 174, 97], [244, 109, 67], [215, 48, 39], [165, 0, 38]];
  function tempColor(t, alpha = 235) {
    const x = clamp((t - T_MIN) / (T_MAX - T_MIN)) * (STOPS.length - 1);
    const i = Math.min(STOPS.length - 2, Math.floor(x)), f = x - i, a = STOPS[i], b = STOPS[i + 1];
    return [a[0] + (b[0] - a[0]) * f, a[1] + (b[1] - a[1]) * f, a[2] + (b[2] - a[2]) * f, alpha];
  }

  async function getJSON(path, optional = false) {
    const res = await fetch(path, {cache: "no-store"});
    if (!res.ok) {
      if (optional) return null;
      throw new Error(`${path} answered HTTP ${res.status}`);
    }
    return res.json();
  }

  // ---------- value lookups (no estimation anywhere) ----------
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
  const periodLabel = () => (state.month === "avg" ? `${state.year} annual average` : `${MONTHS[state.month - 1]} ${state.year}`);

  // ---------- geometry for the split ----------
  function pieceTransform(q, e) {
    const [w, s, ea, n] = QUARTERS[q].b;
    const cx = (w + ea) / 2, cy = (s + n) / 2;
    const t = state.targets[q] || {lon: cx, lat: cy, k: 1};
    const k = 1 + (t.k - 1) * e;
    const tx = cx + (t.lon - cx) * e, ty = cy + (t.lat - cy) * e;
    return {k, f: ([x, y]) => [tx + k * (x - cx), ty + k * (y - cy)]};
  }

  // Where each piece lands, chosen in screen space for this window size, then converted to
  // map coordinates once. Every piece ends further out in its own direction than it starts.
  function layoutMode() {
    const w = window.innerWidth, h = window.innerHeight;
    return w >= 900 && w / h >= 1.15 ? "wide" : "tall";
  }
  function computeTargets() {
    const w = $("map").clientWidth, h = $("map").clientHeight;
    const vp = new WebMercatorViewport({...state.view, width: w, height: h});
    const wide = layoutMode() === "wide";
    const spec = wide
      ? {xs: {W: 0.165, E: 0.835}, ys: {N: 0.25, S: 0.76}, width: 0.29}
      : {xs: {W: 0.255, E: 0.745}, ys: {N: 0.13, S: 0.6}, width: 0.45};
    state.targets = {};
    for (const q of ORDER) {
      const [bw, bs, be, bn] = QUARTERS[q].b;
      const cx = (bw + be) / 2, cy = (bs + bn) / 2;
      const [lon, lat] = vp.unproject([spec.xs[q[1]] * w, spec.ys[q[0]] * h]);
      // Size: measure the piece's projected width at its target spot, then scale to fit.
      const corners = [[bw, bs], [be, bs], [be, bn], [bw, bn]].map(([x, y]) => vp.project([lon + x - cx, lat + y - cy]));
      const pw = Math.max(...corners.map((c) => c[0])) - Math.min(...corners.map((c) => c[0]));
      state.targets[q] = {lon, lat, k: Math.min(1, (spec.width * w) / pw)};
    }
  }
  const rect = (w, s, e, n) => [[w, s], [e, s], [e, n], [w, n], [w, s]];

  function clipPolyline(path, [w, s, e, n]) {
    // Liang–Barsky per segment, joining consecutive inside pieces.
    const out = []; let cur = null;
    for (let i = 0; i < path.length - 1; i++) {
      let [x0, y0] = path[i], [x1, y1] = path[i + 1], t0 = 0, t1 = 1;
      const dx = x1 - x0, dy = y1 - y0, p = [-dx, dx, -dy, dy], qv = [x0 - w, e - x0, y0 - s, n - y0];
      let ok = true;
      for (let j = 0; j < 4 && ok; j++) {
        if (p[j] === 0) { if (qv[j] < 0) ok = false; }
        else { const r = qv[j] / p[j]; if (p[j] < 0) t0 = Math.max(t0, r); else t1 = Math.min(t1, r); }
      }
      if (!ok || t0 > t1) { cur = null; continue; }
      const a = [x0 + t0 * dx, y0 + t0 * dy], b = [x0 + t1 * dx, y0 + t1 * dy];
      if (cur && t0 === 0) cur.push(b); else { cur = [a, b]; out.push(cur); }
      if (t1 < 1) cur = null;
    }
    return out;
  }

  // Static geometry: cell footprints per quarter (known grid, no values) and clipped freeways.
  const cellsByQuarter = {NW: [], NE: [], SW: [], SE: []};
  for (let r = 0; r < Math.round((N - S) / CELL); r++) {
    for (let c = 0; c < Math.round((E - W) / CELL); c++) {
      const lon = W + (c + 0.5) * CELL, lat = N - (r + 0.5) * CELL;
      const q = (lat >= MID_LAT ? "N" : "S") + (lon < MID_LON ? "W" : "E");
      cellsByQuarter[q].push({lon, lat, id: `r${String(r).padStart(2, "0")}_c${String(c).padStart(2, "0")}`});
    }
  }
  let freeways = {NW: [], NE: [], SW: [], SE: []};

  // ---------- deck ----------
  const deckgl = new Deck({
    parent: $("map"),
    controller: false,                       // the camera is fixed: no pan, zoom or rotate
    initialViewState: fitView(),
    getTooltip,
    layers: [],
    useDevicePixels: Math.min(window.devicePixelRatio || 1, 2),
    onError: (err) => console.warn("deck.gl:", err),
  });

  function fitView() {
    const el = $("map"), w = el.clientWidth || window.innerWidth, h = el.clientHeight || window.innerHeight;
    const phone = w < 640;
    // Fit the study window so the map fills most of the screen. Computed once per window
    // size; the camera never moves after that.
    // Keep the map clear of the controls: beside them on wide screens, below them otherwise.
    const ctlBottom = ($("controls").getBoundingClientRect().bottom || 300) + 12;
    const brandH = w < 900 ? (document.querySelector(".brand").offsetHeight || 120) + 70 : 70;
    const pad = w > 1100 ? {top: 70, bottom: 70, left: 340, right: 40}
      : {top: ctlBottom, bottom: brandH, left: phone ? 6 : 24, right: phone ? 6 : 24};
    const vp = new WebMercatorViewport({width: w, height: h}).fitBounds([[W, S], [E, N]], {padding: pad});
    state.view = {longitude: vp.longitude, latitude: vp.latitude + 0.03, zoom: vp.zoom + 0.02,
                  pitch: PITCH, bearing: 0, maxPitch: 60};
    return state.view;
  }

  function getTooltip({object, layer}) {
    if (!object || !layer) return null;
    const style = {backgroundColor: "#fff", color: "#141a2b", border: "1px solid #cfd4e2", borderRadius: "8px",
                   fontSize: "12px", boxShadow: "0 6px 16px rgba(20,26,43,.12)", padding: "8px 10px"};
    if (object.kind === "cell") {
      const v = object.value;
      return {style, html: `<b>Grid cell ${esc(object.id)}</b><br>${object.lat.toFixed(3)}° N, ${Math.abs(object.lon).toFixed(3)}° W<br>${esc(periodLabel())}: <b>${v == null ? "no valid measurement" : fmt(v, 2) + " °C"}</b>`};
    }
    if (object.kind === "quarter") {
      const v = object.value;
      return {style, html: `<b>${esc(object.label)}</b><br>Quarter average, ${esc(periodLabel())}: <b>${v == null ? "no valid value" : fmt(v, 2) + " °C"}</b><br><span style="color:#7a839c">Cell-level values not loaded</span>`};
    }
    return null;
  }

  function buildLayers() {
    const e = state.eased, grid = state.grid, layers = [];
    const transitions = reduceMotion ? {} : {
      getElevation: {duration: 520, easing: easeInOut}, getFillColor: {duration: 520, easing: easeInOut}};

    layers.push(new TileLayer({
      id: "basemap", minZoom: 0, maxZoom: 16, tileSize: 256, opacity: 1 - 0.9 * e,
      data: "https://basemaps.cartocdn.com/light_nolabels/{z}/{x}/{y}@2x.png",
      onTileError: () => {}, maxRequests: 8,
      renderSubLayers: (props) => {
        const {boundingBox} = props.tile;
        return new BitmapLayer(props, {data: null, image: props.data,
          bounds: [boundingBox[0][0], boundingBox[0][1], boundingBox[1][0], boundingBox[1][1]]});
      },
    }));

    for (const q of ORDER) {
      const {k, f} = pieceTransform(q, e);
      const [w, s, ea, n] = QUARTERS[q].b;
      const rid = state.quarterIds[q];
      layers.push(new PolygonLayer({
        id: `piece-${q}`, data: [{poly: rect(w, s, ea, n)}], getPolygon: (d) => d.poly.map(f),
        getFillColor: [255, 255, 255, Math.round(70 + 170 * e)], getLineColor: [120, 132, 168, 200],
        lineWidthUnits: "pixels", getLineWidth: 1, stroked: true, filled: true,
        updateTriggers: {getPolygon: e, getFillColor: e},
      }));
      layers.push(new PathLayer({
        id: `roads-${q}`, data: freeways[q], getPath: (d) => d.map(f), getColor: [96, 108, 140, 150],
        widthUnits: "pixels", getWidth: 1.2, updateTriggers: {getPath: e},
      }));

      if (grid) {
        const cells = grid.byQuarter[q].map((cell) => ({kind: "cell", ...cell,
          value: periodValue(grid.months, cell.values, state.year, state.month)}));
        layers.push(new PolygonLayer({   // footprints for missing cells: visible, never filled with a value
          id: `missing-${q}`, data: cells.filter((c) => c.value == null), pickable: true,
          getPolygon: (c) => rect(c.lon - CELL * 0.42, c.lat - CELL * 0.42, c.lon + CELL * 0.42, c.lat + CELL * 0.42).map(f),
          getFillColor: [255, 255, 255, 0], getLineColor: [150, 158, 184, 220], lineWidthUnits: "pixels",
          getLineWidth: 1, stroked: true, filled: true, updateTriggers: {getPolygon: [e, state.year, state.month]},
        }));
        layers.push(new ColumnLayer({
          id: `cells-${q}`, data: cells.filter((c) => c.value != null), pickable: true, extruded: true,
          diskResolution: 4, angle: 45, radius: CELL * 0.3 * 111320 * Math.SQRT2 * Math.cos(33.5 * Math.PI / 180) * k,
          getPosition: (c) => f([c.lon, c.lat]), getElevation: (c) => Math.max(0, c.value) * METRES_PER_DEG_C,
          elevationScale: k, getFillColor: (c) => tempColor(c.value), autoHighlight: true,
          highlightColor: [106, 75, 214, 160], material: {ambient: 0.55, diffuse: 0.55, shininess: 24},
          transitions, updateTriggers: {getPosition: e, getElevation: [state.year, state.month],
                                        getFillColor: [state.year, state.month]},
        }));
      } else {
        const ser = rid && state.series[rid];
        const value = ser ? periodValue(ser.times, ser.values, state.year, state.month) : null;
        layers.push(new PolygonLayer({
          id: `quarter-${q}`, data: [{kind: "quarter", label: QUARTERS[q].name, value}],
          pickable: true, getPolygon: () => rect(w, s, ea, n).map(f),
          getFillColor: value == null ? [255, 255, 255, 0] : tempColor(value, 120), stroked: false, filled: true,
          transitions: reduceMotion ? {} : {getFillColor: {duration: 520, easing: easeInOut}},
          updateTriggers: {getPolygon: e, getFillColor: [state.year, state.month, value]},
        }));
        layers.push(new PolygonLayer({   // the known 0.05° grid, shown as outlines only
          id: `grid-${q}`, data: cellsByQuarter[q],
          getPolygon: (c) => rect(c.lon - CELL / 2, c.lat - CELL / 2, c.lon + CELL / 2, c.lat + CELL / 2).map(f),
          filled: false, stroked: true, getLineColor: [255, 255, 255, 150], lineWidthUnits: "pixels",
          getLineWidth: 0.8, updateTriggers: {getPolygon: e},
        }));
        layers.push(new TextLayer({
          id: `qval-${q}`, data: [{t: value == null ? "no value" : `${fmt(value)} °C`}], characterSet: CHARS,
          getPosition: () => f([(w + ea) / 2, (s + n) / 2]), getText: (d) => d.t, getSize: 15,
          getColor: [20, 26, 43, 235], fontWeight: 700, fontFamily: "system-ui, -apple-system, Segoe UI, Arial",
          outlineWidth: 3, outlineColor: [255, 255, 255, 230], fontSettings: {sdf: true}, parameters: {depthTest: false},
          updateTriggers: {getPosition: e, getText: [state.year, state.month]},
        }));
      }
      layers.push(new TextLayer({
        id: `qname-${q}`, data: [{t: QUARTERS[q].name.toUpperCase()}], characterSet: CHARS,
        getPosition: () => f([q.endsWith("W") ? w + 0.012 : ea - 0.012, n - 0.012]),
        getTextAnchor: q.endsWith("W") ? "start" : "end", getAlignmentBaseline: "top",
        getText: (d) => d.t, getSize: 11, getColor: [74, 84, 112, 230], fontWeight: 700,
        fontFamily: "system-ui, -apple-system, Segoe UI, Arial", parameters: {depthTest: false},
        updateTriggers: {getPosition: e},
      }));
    }
    const placeAlpha = Math.round(230 * (1 - clamp(e * 3)));
    layers.push(new TextLayer({
      id: "places", data: PLACES, characterSet: CHARS, getPosition: (d) => [d[1], d[2], 900],
      getText: (d) => d[0], getSize: 12, getColor: [20, 26, 43, placeAlpha], fontWeight: 600,
      fontFamily: "system-ui, -apple-system, Segoe UI, Arial", outlineWidth: 3,
      outlineColor: [255, 255, 255, placeAlpha], fontSettings: {sdf: true}, visible: placeAlpha > 4,
      parameters: {depthTest: false},
      updateTriggers: {getColor: placeAlpha},
    }));
    return layers;
  }

  // ---------- scroll ----------
  function onScroll() {
    const stage = $("stage"), vh = window.innerHeight;
    const travelled = -stage.getBoundingClientRect().top;
    const raw = clamp((travelled - 0.3 * vh) / (1.5 * vh));
    const p = reduceMotion ? (raw > 0.5 ? 1 : 0) : raw;
    if (p === state.progress) return;
    state.progress = p;
    state.eased = reduceMotion ? p : easeInOut(p);
    render();
  }

  let frame = 0;
  function render() {
    if (frame) return;
    frame = requestAnimationFrame(() => {
      frame = 0;
      const e = state.eased;
      deckgl.setProps({layers: buildLayers()});
      $("hint").style.opacity = String(1 - clamp(e * 4));
      document.querySelector(".brand").style.opacity = String(1 - clamp(e * 2.5));
      const ctl = $("controls");
      ctl.style.opacity = String(1 - clamp((e - 0.15) * 3));
      ctl.style.pointerEvents = e > 0.4 ? "none" : "auto";
      ctl.setAttribute("aria-hidden", e > 0.4 ? "true" : "false");
      placePanels();
    });
  }

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
        // Tall screens: the card sits directly under its own piece, same width.
        width = Math.max(150, right - left);
        el.style.width = `${width}px`;
        x = left; y = bottom + 8;
      } else {
        // Wide screens: the card sits in the open middle, beside its own piece.
        const gap = 16, half = window.innerWidth / 2;
        width = Math.min(300, Math.max(200, (q.endsWith("W") ? half - right : left - half) - 1.5 * gap));
        el.style.width = `${width}px`;
        const h = el.offsetHeight || 200;
        x = q.endsWith("W") ? right + gap : left - gap - width;
        y = q.startsWith("N") ? top : bottom - h;
      }
      const h = el.offsetHeight || 200;
      y = clamp(y, 8, window.innerHeight - h - 8);
      x = clamp(x, 8, window.innerWidth - width - 8);
      el.style.left = `${x}px`; el.style.top = `${y}px`;
      el.style.opacity = String(o);
      el.style.transform = `translateY(${(1 - o) * 6}px)`;
      el.style.visibility = o > 0.01 ? "visible" : "hidden";
      el.setAttribute("aria-hidden", o > 0.5 ? "false" : "true");
    }
  }

  function yearlyAnomalyMeans(rid) {
    const a = state.anomaly[rid];
    if (!a) return [];
    const years = [...new Set(a.times.map((t) => t.slice(0, 4)))];
    return years.map((y) => ({y, v: periodValue(a.times, a.values, y, "avg")}));
  }

  function sparkSVG(rid) {
    const bars = yearlyAnomalyMeans(rid);
    if (!bars.length) return "";
    const W2 = 240, H2 = 44, max = Math.max(0.5, ...bars.map((b) => Math.abs(b.v || 0)));
    const bw = W2 / bars.length;
    const mid = H2 / 2;
    const rects = bars.map((b, i) => {
      if (b.v == null) return `<rect x="${i * bw + bw * 0.2}" y="${mid - 0.5}" width="${bw * 0.6}" height="1" fill="#cfd4e2"><title>${b.y}: incomplete year</title></rect>`;
      const h = (Math.abs(b.v) / max) * (mid - 2);
      const y = b.v >= 0 ? mid - h : mid;
      return `<rect x="${i * bw + bw * 0.15}" y="${y}" width="${bw * 0.7}" height="${Math.max(h, 0.8)}" fill="${b.v >= 0 ? "#d9603b" : "#4575b4"}"><title>${b.y}: ${signed(b.v, 2)} °C vs average</title></rect>`;
    }).join("");
    return `<svg viewBox="0 0 ${W2} ${H2}" preserveAspectRatio="none" role="img" aria-label="Yearly mean anomaly bars, 2003 to 2024"><line x1="0" x2="${W2}" y1="${mid}" y2="${mid}" stroke="#cfd4e2" stroke-width="1"/>${rects}</svg>`;
  }

  function buildPanels() {
    const host = $("panels");
    host.innerHTML = "";
    const quarterTrends = ORDER.map((q) => state.regions.find((r) => r.region_id === state.quarterIds[q])).filter(Boolean);
    const fastest = quarterTrends.reduce((a, b) => (b.trend.slope > a.trend.slope ? b : a), quarterTrends[0]);
    for (const q of ORDER) {
      const r = state.regions.find((x) => x.region_id === state.quarterIds[q]);
      if (!r) continue;
      const t = r.trend, perYear = t.slope * 12, sig = t.p < 0.05;
      const isFastest = r === fastest && t.slope > 0 && sig;
      const el = document.createElement("article");
      el.className = "panel" + (isFastest ? " fastest" : "");
      el.id = `panel-${q}`;
      el.setAttribute("aria-label", `${QUARTERS[q].name} quarter`);
      el.innerHTML = `
        <div class="panel-head"><h3>${QUARTERS[q].name}</h3>${isFastest ? '<span class="tag">Fastest warming</span>' : ""}</div>
        <p class="rate${perYear < 0 ? " cool" : ""}">${signed(perYear, 3)} °C<small>per year (slope × 12)</small></p>
        <p class="sig">${sig ? "Statistically significant" : "Not statistically significant"} · ${pText(t.p)} · τ ${t.tau.toFixed(2)}</p>
        ${sparkSVG(r.region_id)}
        <div class="spark-cap"><span>2003</span><span>yearly mean vs average (full years)</span><span>2024</span></div>
        <dl><dt id="pl-${q}">—</dt><dd id="pv-${q}">—</dd><dt>Warmest month</dt><dd id="pw-${q}">—</dd></dl>`;
      host.appendChild(el);
      const s = state.series[r.region_id];
      if (s) {
        let best = -1;
        s.values.forEach((v, i) => { if (v != null && (best < 0 || v > s.values[best])) best = i; });
        if (best >= 0) {
          const [yy, mm] = s.times[best].split("-");
          document.getElementById(`pw-${q}`).textContent = `${fmt(s.values[best])} °C · ${MONTHS[+mm - 1]} ${yy}`;
        }
      }
    }
    updatePanelPeriod();
  }

  function updatePanelPeriod() {
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
    state.year = Math.min(state.year, +yr.max);
    yr.value = state.year; yr.disabled = false;
    $("year-min").textContent = yr.min; $("year-max").textContent = yr.max;
    yr.addEventListener("input", () => { state.year = +yr.value; onPeriodChange(); });
    const host = $("months");
    const opts = [["avg", "Annual avg"], ...MONTHS.map((m, i) => [i + 1, m])];
    for (const [val, label] of opts) {
      const b = document.createElement("button");
      b.type = "button"; b.textContent = label; b.dataset.value = val;
      b.setAttribute("role", "radio");
      if (val === "avg") b.className = "avg";
      b.addEventListener("click", () => { state.month = val === "avg" ? "avg" : +val; onPeriodChange(); });
      host.appendChild(b);
    }
    host.addEventListener("keydown", (ev) => {   // arrow keys move through the radio group
      if (!["ArrowLeft", "ArrowRight", "ArrowUp", "ArrowDown"].includes(ev.key)) return;
      const btns = [...host.querySelectorAll("button")];
      const i = btns.indexOf(document.activeElement);
      if (i < 0) return;
      ev.preventDefault();
      const next = btns[(i + (ev.key === "ArrowLeft" || ev.key === "ArrowUp" ? -1 : 1) + btns.length) % btns.length];
      next.focus(); next.click();
    });
    syncControls();
  }

  function syncControls() {
    $("year-out").textContent = state.year;
    $("period-label").textContent = periodLabel();
    for (const b of $("months").querySelectorAll("button")) {
      const on = String(b.dataset.value) === String(state.month);
      b.setAttribute("aria-checked", on ? "true" : "false");
      b.tabIndex = on ? 0 : -1;
    }
  }

  function onPeriodChange() {
    syncControls();
    updatePanelPeriod();
    updateStatus();
    render();
  }

  function updateStatus() {
    const el = $("data-status");
    el.classList.remove("warn");
    if (state.error) {
      el.classList.add("warn");
      el.innerHTML = `Could not load NASA results (${esc(state.error)}). <button type="button" id="retry">Retry</button>`;
      $("retry").addEventListener("click", () => location.reload());
      return;
    }
    if (state.grid) {
      const all = state.grid.cells, shown = all.filter((c) => periodValue(state.grid.months, c.values, state.year, state.month) != null).length;
      el.innerHTML = `<b>${shown} of ${all.length}</b> grid cells have a valid measurement for ${esc(periodLabel())}. Outlined squares have none; nothing is filled in.`;
    } else {
      el.classList.add("warn");
      el.innerHTML = `<b>Showing quarter averages.</b> Per-cell NASA values are not loaded yet, so each quarter is shaded by its real regional average. No cell values are estimated.`;
    }
  }

  // ---------- story sections ----------
  function buildFindings() {
    const rows = [...state.regions].sort((a, b) => (a.region_id === "phoenix_study_area" ? -1 : b.region_id === "phoenix_study_area" ? 1 : b.trend.slope - a.trend.slope));
    const quarterRegions = rows.filter((r) => r.region_id !== "phoenix_study_area");
    const fastest = quarterRegions[0];
    const months = state.series[rows[0].region_id]?.times.length || 264;
    $("findings-body").innerHTML = rows.map((r) => {
      const t = r.trend;
      return `<tr class="${r === fastest ? "fastest" : ""}"><td>${esc(r.region)}</td><td>${esc(t.trend)}${t.p < 0.05 ? ", significant" : ", not significant"}</td>
        <td class="num">${signed(t.slope * 12, 3)} °C</td><td class="num">≈ ${signed(t.slope * months, 1)} °C</td>
        <td class="num">${t.tau.toFixed(2)}</td><td class="num">${pText(t.p)}</td></tr>`;
    }).join("");
    const allUp = rows.every((r) => r.trend.trend === "increasing" && r.trend.p < 0.05);
    const whole = rows[0];
    $("findings-title").textContent = allUp ? "Every part of Phoenix warmed" : "Results by area";
    $("findings-lede").textContent = allUp
      ? `From ${whole.period.start} to ${whole.period.end}, nighttime land surface temperature rose in the whole study area and in all four quarters, and every trend is statistically significant. Across the whole area the trend is ${signed(whole.trend.slope * 12, 3)} °C per year, roughly ${signed(whole.trend.slope * months, 1)} °C over the period. The ${fastest.region.replace("Phoenix study area ", "")} quarter warmed fastest.`
      : "Trend results for the whole study area and each quarter.";
    $("data-period").textContent = `${whole.period.start} to ${whole.period.end}, ${months} months`;
  }

  function buildMethodFigure() {
    const rid = state.quarterIds.whole;
    const a = rid && state.anomaly[rid];
    const svg = $("method-svg");
    if (!a) { svg.innerHTML = ""; return; }
    const years = [...new Set(a.times.map((t) => t.slice(0, 4)))];
    const x0 = 34, y0 = 10, dx = (360 - x0 - 8) / years.length, dy = (230 - y0 - 22) / 12;
    let html = "";
    MONTHS.forEach((m, mi) => {
      const y = y0 + mi * dy + dy / 2;
      const hl = mi === 6;
      if (hl) html += `<rect x="${x0 - 4}" y="${y - dy / 2 + 1}" width="${360 - x0 - 4}" height="${dy - 2}" rx="4" fill="rgba(106,75,214,.09)" stroke="rgba(106,75,214,.45)"/>`;
      html += `<text x="${x0 - 8}" y="${y + 3.5}" text-anchor="end" font-size="9.5" fill="${hl ? "#6a4bd6" : "#7a839c"}" font-family="system-ui">${m}</text>`;
      years.forEach((yr, yi) => {
        const i = a.times.indexOf(`${yr}-${String(mi + 1).padStart(2, "0")}`);
        const v = i < 0 ? null : a.values[i];
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

  // ---------- data ----------
  async function loadGrid() {
    const g = await getJSON("data/grid.json", true).catch(() => null);
    if (!g || !Array.isArray(g.cells) || !Array.isArray(g.months)) return null;
    const byQuarter = {NW: [], NE: [], SW: [], SE: []};
    for (const c of g.cells) {
      if (!byQuarter[c.quarter] || c.values.length !== g.months.length) return null;
      byQuarter[c.quarter].push({id: c.id, lon: c.lon, lat: c.lat, values: c.values});
    }
    return {months: g.months, cells: g.cells, byQuarter, source: g.source};
  }

  async function load() {
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
      const [series, anomalies, grid] = await Promise.all([
        Promise.all(ids.map((id) => getJSON(`${API}/series?region=${encodeURIComponent(id)}`))),
        Promise.all(ids.map((id) => getJSON(`${API}/anomaly?region=${encodeURIComponent(id)}`, true).catch(() => null))),
        loadGrid(),
      ]);
      series.forEach((s) => { state.series[s.region_id] = {times: s.series.map((p) => p.time), values: s.series.map((p) => p.value)}; });
      anomalies.forEach((a) => {
        if (!a) return;
        state.anomaly[a.region_id] = {times: a.series.map((p) => p.time), values: a.series.map((p) => p.value)};
        if (a.region_id === state.quarterIds.whole) state.baseline = a.baseline;
      });
      state.grid = grid;
      const times = state.series[state.quarterIds.whole || ids[0]].times;
      const years = [...new Set(times.map((t) => +t.slice(0, 4)))];
      buildControls(years);
      buildPanels();
      buildFindings();
      buildMethodFigure();
    } catch (err) {
      state.error = err.message || String(err);
    }
    updateStatus();
    render();
  }

  window.addEventListener("scroll", onScroll, {passive: true});
  window.addEventListener("resize", () => {
    deckgl.setProps({initialViewState: fitView()}); computeTargets(); render();
  });
  computeTargets();
  onScroll();
  render();
  load();
})();
