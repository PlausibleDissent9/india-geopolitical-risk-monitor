(function () {
  "use strict";

  var SVG_NS = "http://www.w3.org/2000/svg";
  var COLORS = {
    missing: "#27313a",
    low: "#1c3440",
    calm: "#247d70",
    mid: "#d7a43b",
    high: "#e05d52",
    positive: "#4cba9b",
    base: "#101b24"
  };
  var SCOPE = {
    world: {
      geometryKey: "countries",
      dataKey: "partners",
      title: "World partner view",
      kicker: "India-partner event aggregates",
      dataUrl: "data/map_relations.json",
      geometryUrl: "geo/world.json",
      availableMetrics: ["conflict", "volume", "tone"],
      defaultEntity: "PAK"
    },
    india: {
      geometryKey: "states",
      dataKey: "states",
      title: "Indian state view",
      kicker: "Located event aggregates inside India",
      dataUrl: "data/map_states.json",
      geometryUrl: "geo/india.json",
      availableMetrics: ["conflict", "volume", "protest"],
      defaultEntity: "IN07"
    }
  };
  var METRIC_LABEL = {
    conflict: "Conflict share",
    volume: "Event volume",
    tone: "Goldstein mean",
    protest: "Protest share"
  };

  var dom = {
    svg: document.getElementById("atlas-map"),
    layer: document.getElementById("map-feature-layer"),
    shell: document.getElementById("map-canvas-shell"),
    tooltip: document.getElementById("map-tooltip"),
    status: document.getElementById("map-status"),
    title: document.getElementById("map-canvas-title"),
    kicker: document.getElementById("map-stage-kicker"),
    search: document.getElementById("map-search"),
    searchOptions: document.getElementById("map-search-options"),
    inspectorState: document.getElementById("map-inspector-state"),
    inspectorTitle: document.getElementById("map-inspector-title"),
    inspectorSummary: document.getElementById("map-inspector-summary"),
    facts: {
      events: document.getElementById("map-fact-events"),
      conflict: document.getElementById("map-fact-conflict"),
      thirdLabel: document.getElementById("map-fact-third-label"),
      third: document.getElementById("map-fact-third"),
      coverage: document.getElementById("map-fact-coverage")
    },
    dataLink: document.getElementById("map-data-link"),
    evidence: document.getElementById("map-evidence-note"),
    rankingBody: document.getElementById("map-ranking-body"),
    rankingTitle: document.getElementById("map-ranking-title"),
    rankingNote: document.getElementById("map-ranking-note"),
    legendLow: document.getElementById("map-legend-low"),
    legendHigh: document.getElementById("map-legend-high"),
    legendNote: document.getElementById("map-legend-note"),
    provenance: document.getElementById("map-provenance-line"),
    share: document.getElementById("map-share")
  };

  if (!dom.svg || !dom.layer || !dom.shell) return;

  var params = new URLSearchParams(window.location.search);
  var state = {
    scope: params.get("scope") === "india" ? "india" : "world",
    metric: params.get("metric") || "conflict",
    window: params.get("window") === "all" ? "all" : "recent",
    selected: params.get("entity") || null,
    payloads: {},
    geometries: {},
    features: new Map(),
    order: [],
    baseViewBox: null,
    viewBox: null,
    drag: null,
    moved: false
  };

  function escapeHtml(value) {
    return String(value).replace(/[&<>"']/g, function (char) {
      return { "&": "&amp;", "<": "&lt;", ">": "&gt;", "\"": "&quot;", "'": "&#39;" }[char];
    });
  }

  function number(value) {
    return value == null || !Number.isFinite(Number(value))
      ? "—"
      : Number(value).toLocaleString("en-IN");
  }

  function decimal(value) {
    return value == null || !Number.isFinite(Number(value))
      ? "—"
      : Number(value).toFixed(2);
  }

  function percent(value) {
    return value == null || !Number.isFinite(Number(value))
      ? "—"
      : (Number(value) * 100).toFixed(1) + "%";
  }

  function clamp(value, low, high) {
    return Math.min(high, Math.max(low, value));
  }

  function hexToRgb(hex) {
    var value = hex.replace("#", "");
    return [0, 2, 4].map(function (index) {
      return parseInt(value.slice(index, index + 2), 16);
    });
  }

  function mix(first, second, amount) {
    var a = hexToRgb(first);
    var b = hexToRgb(second);
    var t = clamp(amount, 0, 1);
    return "rgb(" + a.map(function (value, index) {
      return Math.round(value + (b[index] - value) * t);
    }).join(",") + ")";
  }

  function svgElement(name, attributes) {
    var element = document.createElementNS(SVG_NS, name);
    Object.entries(attributes || {}).forEach(function (entry) {
      element.setAttribute(entry[0], String(entry[1]));
    });
    return element;
  }

  function parseViewBox(raw) {
    var values = String(raw || "").trim().split(/\s+/).map(Number);
    if (values.length !== 4 || values.some(function (value) { return !Number.isFinite(value); })) {
      throw new Error("Registered geometry has no valid viewBox");
    }
    return { x: values[0], y: values[1], width: values[2], height: values[3] };
  }

  function setStatus(text, mode) {
    dom.status.textContent = text;
    dom.status.classList.remove("ready", "error");
    if (mode) dom.status.classList.add(mode);
  }

  function setPublishedStatus() {
    var meta = (currentPayload() || {})._meta || {};
    setStatus("Published " + meta.generated, "ready");
  }

  function currentConfig() {
    return SCOPE[state.scope];
  }

  function currentPayload() {
    return state.payloads[state.scope];
  }

  function currentRows() {
    var payload = currentPayload();
    return payload ? payload[currentConfig().dataKey] : {};
  }

  function validMetric() {
    if (!currentConfig().availableMetrics.includes(state.metric)) state.metric = "conflict";
    if ((state.metric === "tone" || state.metric === "protest") && state.window === "recent") {
      state.window = "all";
    }
  }

  function eventValue(row) {
    return state.window === "recent" ? row.recent_n : row.n;
  }

  function metricValue(row) {
    if (!row) return null;
    if (state.metric === "volume") return eventValue(row);
    if (state.metric === "conflict") {
      return state.window === "recent" ? row.recent_conflict_share : row.conflict_share;
    }
    if (state.metric === "tone") return row.goldstein_mean;
    if (state.metric === "protest") return row.protest_share;
    return null;
  }

  function metricText(row) {
    var value = metricValue(row);
    if (state.metric === "volume") return number(value);
    if (state.metric === "tone") return decimal(value);
    return percent(value);
  }

  function scaleContext() {
    var values = Object.values(currentRows()).map(metricValue).filter(function (value) {
      return value != null && Number.isFinite(Number(value));
    }).map(Number);
    var max = values.length ? Math.max.apply(null, values) : 1;
    if (state.metric === "conflict") {
      return { low: 0, high: 0.5, lowLabel: "0%", highLabel: "50%+", note: "Grey marks missing data or fewer than 50 recent events." };
    }
    if (state.metric === "protest") {
      return { low: 0, high: Math.max(0.06, max), lowLabel: "0%", highLabel: percent(Math.max(0.06, max)), note: "2017–present located-event share; no trailing-window protest field is published." };
    }
    if (state.metric === "tone") {
      return { low: -3, high: 3, lowLabel: "Conflictual", highLabel: "Cooperative", note: "Goldstein mean, clipped visually at −3 and +3; values remain exact in the inspector." };
    }
    return { low: 0, high: Math.max(1, max), lowLabel: "Lower", highLabel: number(max), note: "Log-scaled event counts within the selected published window." };
  }

  function fillFor(code) {
    var row = currentRows()[code];
    var value = metricValue(row);
    if (value == null || !Number.isFinite(Number(value))) return COLORS.missing;
    if (state.window === "recent" && row.recent_n < 50) return COLORS.missing;
    var scale = scaleContext();
    if (state.metric === "tone") {
      if (value < 0) return mix(COLORS.mid, COLORS.high, Math.abs(value) / Math.abs(scale.low));
      return mix(COLORS.mid, COLORS.positive, value / scale.high);
    }
    if (state.metric === "volume") {
      var volumeT = Math.log1p(Math.max(0, value)) / Math.log1p(scale.high);
      return mix(COLORS.low, COLORS.mid, volumeT);
    }
    return mix(COLORS.calm, COLORS.high, value / scale.high);
  }

  function updateLegend() {
    var scale = scaleContext();
    dom.legendLow.textContent = scale.lowLabel;
    dom.legendHigh.textContent = scale.highLabel;
    dom.legendNote.textContent = scale.note;
    var ramp = document.querySelector(".map-legend-ramp");
    if (ramp) {
      ramp.style.background = state.metric === "tone"
        ? "linear-gradient(90deg, " + COLORS.high + ", " + COLORS.mid + ", " + COLORS.positive + ")"
        : state.metric === "volume"
          ? "linear-gradient(90deg, " + COLORS.low + ", " + COLORS.mid + ")"
          : "linear-gradient(90deg, " + COLORS.calm + ", " + COLORS.high + ")";
    }
  }

  function setViewBox(next) {
    var base = state.baseViewBox;
    if (!base) return;
    var width = clamp(next.width, base.width / 8, base.width);
    var height = width * base.height / base.width;
    if (height > base.height) {
      height = base.height;
      width = height * base.width / base.height;
    }
    var x = clamp(next.x, base.x, base.x + base.width - width);
    var y = clamp(next.y, base.y, base.y + base.height - height);
    state.viewBox = { x: x, y: y, width: width, height: height };
    dom.svg.setAttribute("viewBox", [x, y, width, height].join(" "));
  }

  function resetViewBox() {
    if (!state.baseViewBox) return;
    setViewBox(Object.assign({}, state.baseViewBox));
  }

  function zoom(factor, anchorX, anchorY) {
    if (!state.viewBox) return;
    var box = state.viewBox;
    var ax = anchorX == null ? 0.5 : anchorX;
    var ay = anchorY == null ? 0.5 : anchorY;
    var width = box.width / factor;
    var height = box.height / factor;
    setViewBox({
      x: box.x + (box.width - width) * ax,
      y: box.y + (box.height - height) * ay,
      width: width,
      height: height
    });
  }

  function zoomToFeature(element) {
    if (!element || !state.baseViewBox) return;
    try {
      var box = element.getBBox();
      var padding = Math.max(box.width, box.height) * 1.8 + 12;
      var width = Math.min(state.baseViewBox.width, Math.max(box.width + padding, state.baseViewBox.width / 5));
      var height = width * state.baseViewBox.height / state.baseViewBox.width;
      setViewBox({
        x: box.x + box.width / 2 - width / 2,
        y: box.y + box.height / 2 - height / 2,
        width: width,
        height: height
      });
    } catch (_error) {
      resetViewBox();
    }
  }

  function setSelected(code, options) {
    var row = currentRows()[code];
    var geometry = state.geometries[state.scope][currentConfig().geometryKey][code];
    if (!row || !geometry) return;
    state.selected = code;
    state.features.forEach(function (element, featureCode) {
      var active = featureCode === code;
      element.classList.toggle("is-selected", active);
      element.setAttribute("aria-pressed", active ? "true" : "false");
      element.setAttribute("tabindex", active ? "0" : "-1");
    });
    var element = state.features.get(code);
    if (options && options.focus && element) element.focus();
    if (options && options.zoom) zoomToFeature(element);
    renderInspector(code, row, geometry.name || row.name || code);
    setPublishedStatus();
    updateUrl();
  }

  function renderInspector(code, row, name) {
    var recent = state.window === "recent";
    dom.inspectorState.textContent = "Published aggregate · " + code;
    dom.inspectorTitle.textContent = name;
    dom.inspectorSummary.textContent = recent
      ? "Trailing 365-day values from the latest published map payload."
      : "Cumulative values from the published 2017–present map payload.";
    dom.facts.events.textContent = number(eventValue(row));
    dom.facts.conflict.textContent = percent(recent ? row.recent_conflict_share : row.conflict_share);
    if (state.scope === "world") {
      dom.facts.thirdLabel.textContent = "Goldstein mean";
      dom.facts.third.textContent = decimal(row.goldstein_mean);
      dom.facts.coverage.textContent = recent && row.recent_n < 50 ? "Below 50-event display floor" : "Partner events in source stream";
      dom.evidence.textContent = "Partner-country counts and CAMEO classifications from the GDELT Events v1 stream. Association, not causation; not an event census or exposure measure.";
    } else {
      dom.facts.thirdLabel.textContent = "Protest share, 2017–";
      dom.facts.third.textContent = percent(row.protest_share);
      dom.facts.coverage.textContent = "Source-geocoded located events";
      dom.evidence.textContent = "State counts depend on the source's administrative geocoding vintage. Telangana, Ladakh and Goa retain documented boundary limitations.";
    }
    dom.dataLink.href = currentConfig().dataUrl;
  }

  function updateUrl() {
    var next = new URL(window.location.href);
    next.searchParams.set("scope", state.scope);
    next.searchParams.set("metric", state.metric);
    next.searchParams.set("window", state.window);
    if (state.selected) next.searchParams.set("entity", state.selected);
    else next.searchParams.delete("entity");
    window.history.replaceState(null, "", next.pathname + "?" + next.searchParams.toString());
  }

  function renderRanking() {
    var rows = Object.entries(currentRows()).filter(function (entry) {
      return metricValue(entry[1]) != null &&
        (state.window !== "recent" || eventValue(entry[1]) >= 50);
    }).sort(function (a, b) {
      return Number(metricValue(b[1])) - Number(metricValue(a[1]));
    }).slice(0, 12);
    dom.rankingTitle.textContent = state.metric === "tone"
      ? "Most cooperative published balance"
      : "Highest " + METRIC_LABEL[state.metric].toLowerCase();
    dom.rankingNote.textContent = "Sorted by " + METRIC_LABEL[state.metric] + " for " +
      (state.window === "recent" ? "the trailing 365 days" : "2017–present") + ". Not a risk league table.";
    dom.rankingBody.replaceChildren();
    rows.forEach(function (entry) {
      var code = entry[0];
      var row = entry[1];
      var tr = document.createElement("tr");
      var nameCell = document.createElement("td");
      var button = document.createElement("button");
      button.type = "button";
      button.textContent = row.name || code;
      button.addEventListener("click", function () { setSelected(code, { zoom: true, focus: true }); });
      nameCell.appendChild(button);
      var eventsCell = document.createElement("td");
      eventsCell.className = "num";
      eventsCell.textContent = number(eventValue(row));
      var metricCell = document.createElement("td");
      metricCell.className = "num";
      metricCell.textContent = metricText(row);
      tr.append(nameCell, eventsCell, metricCell);
      dom.rankingBody.appendChild(tr);
    });
  }

  function tooltipText(code) {
    var row = currentRows()[code];
    var geometry = state.geometries[state.scope][currentConfig().geometryKey][code];
    var name = (row && row.name) || (geometry && geometry.name) || code;
    if (!row) return "<strong>" + escapeHtml(name) + "</strong>No published aggregate";
    return "<strong>" + escapeHtml(name) + "</strong>" + escapeHtml(METRIC_LABEL[state.metric]) + ": " + escapeHtml(metricText(row));
  }

  function showTooltip(event, code) {
    dom.tooltip.innerHTML = tooltipText(code);
    dom.tooltip.hidden = false;
    var shell = dom.shell.getBoundingClientRect();
    var left = clamp(event.clientX - shell.left + 12, 8, shell.width - 250);
    var top = clamp(event.clientY - shell.top + 12, 8, shell.height - 80);
    dom.tooltip.style.left = left + "px";
    dom.tooltip.style.top = top + "px";
  }

  function renderGeometry() {
    validMetric();
    var config = currentConfig();
    var geometry = state.geometries[state.scope];
    var geometries = geometry[config.geometryKey];
    state.baseViewBox = parseViewBox(geometry.viewBox);
    state.viewBox = Object.assign({}, state.baseViewBox);
    dom.layer.replaceChildren();
    state.features = new Map();
    state.order = [];

    if (geometry.national_outline) {
      dom.layer.appendChild(svgElement("path", {
        d: geometry.national_outline,
        fill: COLORS.base,
        stroke: "none"
      }));
    }

    Object.entries(geometries).forEach(function (entry) {
      var code = entry[0];
      var shape = entry[1];
      var element;
      if (shape.d) element = svgElement("path", { d: shape.d });
      else if (shape.pt) element = svgElement("circle", { cx: shape.pt[0], cy: shape.pt[1], r: 3.4 });
      else return;
      var row = currentRows()[code];
      var name = (row && row.name) || shape.name || code;
      element.classList.add("map-feature");
      element.dataset.code = code;
      element.setAttribute("fill", fillFor(code));
      element.setAttribute("role", "button");
      element.setAttribute("aria-label", name + ", " + METRIC_LABEL[state.metric] + " " + (row ? metricText(row) : "not available"));
      element.setAttribute("aria-pressed", "false");
      element.setAttribute("tabindex", "-1");
      var title = svgElement("title");
      title.textContent = name + ": " + (row ? metricText(row) : "no published aggregate");
      element.appendChild(title);
      element.addEventListener("pointerenter", function (event) { showTooltip(event, code); });
      element.addEventListener("pointermove", function (event) { showTooltip(event, code); });
      element.addEventListener("pointerleave", function () { dom.tooltip.hidden = true; });
      element.addEventListener("click", function () {
        if (!state.moved && row) setSelected(code, { focus: true });
      });
      element.addEventListener("keydown", function (event) {
        if (event.key === "Enter" || event.key === " ") {
          event.preventDefault();
          if (row) setSelected(code, { focus: true });
        }
        if (event.key === "ArrowRight" || event.key === "ArrowDown" || event.key === "ArrowLeft" || event.key === "ArrowUp") {
          event.preventDefault();
          var direction = event.key === "ArrowRight" || event.key === "ArrowDown" ? 1 : -1;
          var index = state.order.indexOf(code);
          var next = state.order[(index + direction + state.order.length) % state.order.length];
          if (next) setSelected(next, { focus: true });
        }
      });
      dom.layer.appendChild(element);
      if (row) {
        state.features.set(code, element);
        state.order.push(code);
      }
    });

    if (geometry.national_outline) {
      dom.layer.appendChild(svgElement("path", {
        d: geometry.national_outline,
        class: "map-national-outline"
      }));
    }
    resetViewBox();
    dom.title.textContent = config.title;
    dom.kicker.textContent = config.kicker;
    dom.dataLink.href = config.dataUrl;
    populateSearch();
    updateControls();
    updateLegend();
    renderRanking();
    var selected = state.selected && state.features.has(state.selected)
      ? state.selected
      : config.defaultEntity;
    if (!state.features.has(selected)) selected = state.order[0];
    if (selected) setSelected(selected, {});
  }

  function updateFeatureStyles() {
    validMetric();
    state.features.forEach(function (element, code) {
      var row = currentRows()[code];
      element.setAttribute("fill", fillFor(code));
      element.setAttribute("aria-label", ((row && row.name) || code) + ", " + METRIC_LABEL[state.metric] + " " + metricText(row));
      var title = element.querySelector("title");
      if (title) title.textContent = ((row && row.name) || code) + ": " + metricText(row);
    });
    updateControls();
    updateLegend();
    renderRanking();
    if (state.selected && currentRows()[state.selected]) {
      var geometry = state.geometries[state.scope][currentConfig().geometryKey][state.selected];
      renderInspector(state.selected, currentRows()[state.selected], geometry.name || currentRows()[state.selected].name || state.selected);
    }
    updateUrl();
  }

  function updateControls() {
    document.querySelectorAll("[data-map-scope]").forEach(function (button) {
      var active = button.dataset.mapScope === state.scope;
      button.setAttribute("aria-selected", active ? "true" : "false");
      button.tabIndex = active ? 0 : -1;
    });
    document.querySelectorAll("[data-map-metric]").forEach(function (button) {
      var available = currentConfig().availableMetrics.includes(button.dataset.mapMetric);
      button.hidden = !available;
      button.setAttribute("aria-pressed", button.dataset.mapMetric === state.metric ? "true" : "false");
    });
    document.querySelectorAll("[data-map-window]").forEach(function (button) {
      var restricted = (state.metric === "tone" || state.metric === "protest") && button.dataset.mapWindow === "recent";
      button.disabled = restricted;
      button.title = restricted ? "This measure is published only for 2017–present" : "";
      button.setAttribute("aria-pressed", button.dataset.mapWindow === state.window ? "true" : "false");
    });
  }

  function populateSearch() {
    dom.searchOptions.replaceChildren();
    Object.entries(currentRows()).sort(function (a, b) {
      return String(a[1].name).localeCompare(String(b[1].name));
    }).forEach(function (entry) {
      var option = document.createElement("option");
      option.value = entry[1].name || entry[0];
      option.label = entry[0];
      dom.searchOptions.appendChild(option);
    });
    dom.search.value = "";
  }

  function findSearchValue(value) {
    var needle = value.trim().toLowerCase();
    if (!needle) return null;
    var exact = Object.entries(currentRows()).find(function (entry) {
      return entry[0].toLowerCase() === needle || String(entry[1].name).toLowerCase() === needle;
    });
    if (exact) return exact[0];
    var partial = Object.entries(currentRows()).find(function (entry) {
      return String(entry[1].name).toLowerCase().includes(needle);
    });
    return partial ? partial[0] : null;
  }

  function bindControls() {
    document.querySelectorAll("[data-map-scope]").forEach(function (button) {
      button.addEventListener("click", function () {
        var scope = button.dataset.mapScope;
        if (!SCOPE[scope] || scope === state.scope) return;
        state.scope = scope;
        state.metric = "conflict";
        state.window = "recent";
        state.selected = null;
        renderGeometry();
      });
    });
    document.querySelectorAll("[data-map-metric]").forEach(function (button) {
      button.addEventListener("click", function () {
        if (!currentConfig().availableMetrics.includes(button.dataset.mapMetric)) return;
        state.metric = button.dataset.mapMetric;
        updateFeatureStyles();
      });
    });
    document.querySelectorAll("[data-map-window]").forEach(function (button) {
      button.addEventListener("click", function () {
        if (button.disabled) return;
        state.window = button.dataset.mapWindow;
        updateFeatureStyles();
      });
    });
    dom.search.addEventListener("change", function () {
      var code = findSearchValue(dom.search.value);
      if (code) setSelected(code, { zoom: true, focus: true });
      else setStatus("No matching published place", "error");
    });
    dom.search.addEventListener("keydown", function (event) {
      if (event.key === "Enter") {
        event.preventDefault();
        dom.search.dispatchEvent(new Event("change"));
      }
    });
    document.querySelectorAll("[data-map-zoom]").forEach(function (button) {
      button.addEventListener("click", function () {
        if (button.dataset.mapZoom === "in") zoom(1.45);
        else if (button.dataset.mapZoom === "out") zoom(1 / 1.45);
        else resetViewBox();
      });
    });
    dom.share.addEventListener("click", async function () {
      updateUrl();
      try {
        await navigator.clipboard.writeText(window.location.href);
        dom.share.textContent = "Link copied";
      } catch (_error) {
        dom.share.textContent = "Copy URL from address bar";
      }
      window.setTimeout(function () { dom.share.textContent = "Copy view link"; }, 1800);
    });

    dom.svg.addEventListener("wheel", function (event) {
      event.preventDefault();
      var rect = dom.svg.getBoundingClientRect();
      zoom(event.deltaY < 0 ? 1.22 : 1 / 1.22,
        clamp((event.clientX - rect.left) / rect.width, 0, 1),
        clamp((event.clientY - rect.top) / rect.height, 0, 1));
    }, { passive: false });
    dom.svg.addEventListener("pointerdown", function (event) {
      if (event.button !== 0 || !state.viewBox) return;
      state.drag = { x: event.clientX, y: event.clientY, box: Object.assign({}, state.viewBox) };
      state.moved = false;
      dom.svg.classList.add("is-dragging");
      dom.svg.setPointerCapture(event.pointerId);
    });
    dom.svg.addEventListener("pointermove", function (event) {
      if (!state.drag) return;
      var rect = dom.svg.getBoundingClientRect();
      var dx = event.clientX - state.drag.x;
      var dy = event.clientY - state.drag.y;
      if (Math.abs(dx) + Math.abs(dy) > 3) state.moved = true;
      setViewBox({
        x: state.drag.box.x - dx * state.drag.box.width / rect.width,
        y: state.drag.box.y - dy * state.drag.box.height / rect.height,
        width: state.drag.box.width,
        height: state.drag.box.height
      });
    });
    function endDrag(event) {
      if (!state.drag) return;
      state.drag = null;
      dom.svg.classList.remove("is-dragging");
      if (dom.svg.hasPointerCapture(event.pointerId)) dom.svg.releasePointerCapture(event.pointerId);
      window.setTimeout(function () { state.moved = false; }, 0);
    }
    dom.svg.addEventListener("pointerup", endDrag);
    dom.svg.addEventListener("pointercancel", endDrag);
  }

  async function getJson(url) {
    var response = await fetch(url, { credentials: "same-origin" });
    if (!response.ok) throw new Error(url + " returned HTTP " + response.status);
    return response.json();
  }

  function validShare(value) {
    return value == null || (Number.isFinite(Number(value)) && Number(value) >= 0 && Number(value) <= 1);
  }

  function validateResource(scope, payload, geometry) {
    var config = SCOPE[scope];
    if (!payload || typeof payload !== "object" || !geometry || typeof geometry !== "object") {
      throw new Error("Published map payload shape is invalid for " + scope);
    }
    var rows = payload[config.dataKey];
    var shapes = geometry[config.geometryKey];
    if (!rows || typeof rows !== "object" || Array.isArray(rows) || !Object.keys(rows).length ||
        !shapes || typeof shapes !== "object" || Array.isArray(shapes) || !Object.keys(shapes).length) {
      throw new Error("Published map payload shape is invalid for " + scope);
    }
    var meta = payload._meta;
    if (!meta || meta.partial !== false || !/^\d{4}-\d{2}-\d{2}$/.test(String(meta.generated || "")) ||
        meta.recent_window_days !== 365 || !Number.isInteger(meta.days_missing) || meta.days_missing < 0) {
      throw new Error("Published " + scope + " map metadata is missing or invalid");
    }
    parseViewBox(geometry.viewBox);
    Object.entries(rows).forEach(function (entry) {
      var code = entry[0];
      var row = entry[1];
      if (!row || typeof row !== "object" || Array.isArray(row) ||
          typeof row.name !== "string" || !row.name.trim() || !shapes[code]) {
        throw new Error("Published " + scope + " map row has no registered geometry: " + code);
      }
      if (!Number.isInteger(row.n) || row.n < 0 || !Number.isInteger(row.recent_n) ||
          row.recent_n < 0 || row.recent_n > row.n ||
          !validShare(row.conflict_share) || !validShare(row.recent_conflict_share) ||
          (scope === "india" && !validShare(row.protest_share)) ||
          (scope === "world" && row.goldstein_mean != null && !Number.isFinite(Number(row.goldstein_mean)))) {
        throw new Error("Published " + scope + " map row has invalid values: " + code);
      }
    });
  }

  async function initialize() {
    bindControls();
    try {
      var resources = await Promise.all([
        getJson(SCOPE.world.geometryUrl),
        getJson(SCOPE.world.dataUrl),
        getJson(SCOPE.india.geometryUrl),
        getJson(SCOPE.india.dataUrl)
      ]);
      state.geometries.world = resources[0];
      state.payloads.world = resources[1];
      state.geometries.india = resources[2];
      state.payloads.india = resources[3];
      ["world", "india"].forEach(function (scope) {
        validateResource(scope, state.payloads[scope], state.geometries[scope]);
      });
      validMetric();
      renderGeometry();
      var meta = currentPayload()._meta || {};
      setPublishedStatus();
      dom.provenance.textContent = "Payload generated " + (meta.generated || "unknown") +
        " · " + Object.keys(state.payloads.world.partners).length + " partner aggregates · " +
        Object.keys(state.payloads.india.states).length + " state aggregates · " +
        number(meta.days_missing || 0) + " missing source days in the published build.";
    } catch (error) {
      setStatus("Map unavailable · payload refused", "error");
      dom.inspectorTitle.textContent = "Map data refused";
      dom.inspectorSummary.textContent = error instanceof Error ? error.message : "The published map payload could not be validated.";
      dom.rankingBody.innerHTML = "<tr><td colspan=\"3\">No map ranking is rendered when a required payload fails.</td></tr>";
      console.error("atlas map:", error);
    }
  }

  initialize();
})();
