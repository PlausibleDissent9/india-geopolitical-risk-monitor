(function () {
  "use strict";

  var DATA_URL = "data/world_state.json";
  var GEO_URL = "geo/world.json";
  var STATES = [
    "observed",
    "unavailable_member_not_observed",
    "unavailable_layer_not_published"
  ];
  var dom = {
    denominatorCopy: document.getElementById("world-denominator-copy"),
    vintage: document.getElementById("world-vintage"),
    kpiMembers: document.getElementById("world-kpi-members"),
    kpiLayers: document.getElementById("world-kpi-layers"),
    kpiCells: document.getElementById("world-kpi-cells"),
    kpiObserved: document.getElementById("world-kpi-observed"),
    layerCount: document.getElementById("world-layer-count"),
    layerList: document.getElementById("world-layer-list"),
    family: document.getElementById("world-family"),
    layerTitle: document.getElementById("world-layer-title"),
    layerConstruct: document.getElementById("world-layer-construct"),
    search: document.getElementById("world-search"),
    map: document.getElementById("world-map"),
    mapLayer: document.getElementById("world-map-layer"),
    mapStatus: document.getElementById("world-map-status"),
    observed: document.getElementById("world-observed"),
    unavailable: document.getElementById("world-unavailable"),
    coverage: document.getElementById("world-coverage"),
    registryState: document.getElementById("world-registry-state"),
    resultCount: document.getElementById("world-result-count"),
    tableBody: document.getElementById("world-table-body"),
    memberState: document.getElementById("world-member-state"),
    inspectorTitle: document.getElementById("world-inspector-title"),
    memberSummary: document.getElementById("world-member-summary"),
    memberFacts: document.getElementById("world-member-facts"),
    domainProfile: document.getElementById("world-domain-profile"),
    claimBoundary: document.getElementById("world-claim-boundary"),
    sourceLink: document.getElementById("world-source-link")
  };
  if (!dom.denominatorCopy || !dom.layerList || !dom.mapLayer || !dom.tableBody) return;

  var params = new URLSearchParams(window.location.search);
  var state = {
    payload: null,
    geometry: null,
    layers: new Map(),
    members: new Map(),
    paths: new Map(),
    selectedLayer: params.get("layer") || "india_partner_event_context",
    selectedArea: params.get("area") || "PAK",
    query: ""
  };

  function fail(message) {
    throw new Error(message);
  }

  function object(value) {
    return value && typeof value === "object" && !Array.isArray(value);
  }

  function exactKeys(value, expected) {
    if (!object(value)) return false;
    var actual = Object.keys(value).sort();
    var wanted = expected.slice().sort();
    return actual.length === wanted.length && actual.every(function (key, index) {
      return key === wanted[index];
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

  function labelState(value) {
    if (value === "observed") return "Observed";
    if (value === "unavailable_member_not_observed") return "No published observation";
    return "Layer not published";
  }

  function el(tag, className, text) {
    var node = document.createElement(tag);
    if (className) node.className = className;
    if (text != null) node.textContent = text;
    return node;
  }

  function svgEl(tag, attributes) {
    var node = document.createElementNS("http://www.w3.org/2000/svg", tag);
    Object.entries(attributes || {}).forEach(function (entry) {
      node.setAttribute(entry[0], String(entry[1]));
    });
    return node;
  }

  function validate(payload, geometry) {
    if (!object(payload) || !object(payload._meta) || payload._meta.partial !== false) {
      fail("Matrix metadata or completeness state is invalid");
    }
    if (!object(payload.denominator) || payload.denominator.single_world_score !== "prohibited") {
      fail("Matrix composition boundary is invalid");
    }
    if (!Array.isArray(payload.layers) || !Array.isArray(payload.members) || !object(payload.observations)) {
      fail("Matrix collections are invalid");
    }
    if (payload.layers.length !== payload.denominator.country_level_layers ||
        payload.members.length !== payload.denominator.geometry_members ||
        payload.denominator.cells !== payload.layers.length * payload.members.length) {
      fail("Matrix denominator does not reconcile");
    }
    var layerIds = payload.layers.map(function (row) { return row.layer_id; });
    var memberIds = payload.members.map(function (row) { return row.area_id; });
    if (new Set(layerIds).size !== layerIds.length || new Set(memberIds).size !== memberIds.length) {
      fail("Matrix identifiers are not unique");
    }
    payload.layers.forEach(function (row) {
      if (!object(row) || typeof row.label !== "string" || typeof row.construct !== "string" ||
          !Number.isInteger(row.observed_members) || !Number.isInteger(row.unavailable_members) ||
          row.observed_members + row.unavailable_members !== payload.members.length) {
        fail("Layer coverage does not reconcile");
      }
    });
    payload.members.forEach(function (row) {
      if (!object(row) || typeof row.name !== "string" || !exactKeys(row.layer_states, layerIds) ||
          Object.values(row.layer_states).some(function (value) { return !STATES.includes(value); })) {
        fail("Member cell partition is invalid");
      }
    });
    if (!object(geometry) || typeof geometry.viewBox !== "string" || !object(geometry.countries) ||
        !exactKeys(geometry.countries, memberIds)) {
      fail("Map geometry and matrix denominator differ");
    }
    var observations = payload.observations.india_partner_event_context;
    if (!object(observations)) fail("Published observation map is missing");
    Object.keys(observations).forEach(function (areaId) {
      var member = payload.members.find(function (row) { return row.area_id === areaId; });
      if (!member || member.layer_states.india_partner_event_context !== "observed") {
        fail("Observation exists outside an observed matrix cell");
      }
    });
  }

  function updateUrl() {
    var next = new URLSearchParams();
    next.set("layer", state.selectedLayer);
    if (state.selectedArea) next.set("area", state.selectedArea);
    history.replaceState(null, "", "?" + next.toString());
  }

  function currentLayer() {
    return state.layers.get(state.selectedLayer) || Array.from(state.layers.values())[0];
  }

  function currentMember() {
    return state.members.get(state.selectedArea) || null;
  }

  function observation(areaId) {
    if (state.selectedLayer !== "india_partner_event_context") return null;
    return state.payload.observations.india_partner_event_context[areaId] || null;
  }

  function renderLayers() {
    var buttons = [];
    state.payload.layers.forEach(function (layer) {
      var button = el("button", "world-layer-button" + (layer.observed_members ? " live" : ""));
      button.type = "button";
      button.setAttribute("role", "option");
      button.setAttribute("aria-selected", layer.layer_id === state.selectedLayer ? "true" : "false");
      button.dataset.layer = layer.layer_id;
      button.appendChild(el("strong", "", layer.label));
      var meta = el("span");
      meta.appendChild(el("i"));
      meta.appendChild(document.createTextNode(
        layer.observed_members
          ? layer.observed_members + "/" + layer.denominator_members + " observed"
          : "Registered · unavailable"
      ));
      button.appendChild(meta);
      button.addEventListener("click", function () {
        state.selectedLayer = layer.layer_id;
        renderAll();
        updateUrl();
      });
      buttons.push(button);
    });
    dom.layerList.replaceChildren.apply(dom.layerList, buttons);
    dom.layerCount.textContent = String(buttons.length);
  }

  function renderMap() {
    var layer = currentLayer();
    var query = state.query.toLowerCase();
    state.paths.forEach(function (path, areaId) {
      var member = state.members.get(areaId);
      var status = member.layer_states[layer.layer_id];
      path.setAttribute("class", [
        "world-geometry",
        status === "observed" ? "observed" : "missing",
        areaId === state.selectedArea ? "selected" : "",
        query && !member.name.toLowerCase().includes(query) && !areaId.toLowerCase().includes(query)
          ? "filtered-out"
          : ""
      ].filter(Boolean).join(" "));
    });
    dom.mapStatus.textContent = layer.observed_members
      ? layer.observed_members + " observed · " + layer.unavailable_members + " unavailable · status map, not a score"
      : "No public observations in this domain · all " + layer.denominator_members + " cells remain explicit";
    document.getElementById("world-map-title").textContent = layer.label + " coverage map";
    document.getElementById("world-map-desc").textContent =
      layer.observed_members + " observed and " + layer.unavailable_members +
      " unavailable country or area cells. Color encodes availability only.";
  }

  function renderTable() {
    var layer = currentLayer();
    var query = state.query.toLowerCase();
    var rows = state.payload.members.filter(function (member) {
      return !query || member.name.toLowerCase().includes(query) || member.area_id.toLowerCase().includes(query);
    });
    var nodes = rows.map(function (member) {
      var status = member.layer_states[layer.layer_id];
      var obs = observation(member.area_id);
      var tr = document.createElement("tr");
      if (member.area_id === state.selectedArea) tr.className = "selected";
      var nameCell = document.createElement("td");
      var button = el("button", "world-row-button", member.name + " · " + member.area_id);
      button.type = "button";
      button.addEventListener("click", function () { selectArea(member.area_id, true); });
      nameCell.appendChild(button);
      tr.appendChild(nameCell);
      var statusCell = document.createElement("td");
      statusCell.appendChild(el("span", "world-state-pill " + (status === "observed" ? "observed" : ""), labelState(status)));
      tr.appendChild(statusCell);
      [
        obs && obs.event_count_all_time,
        obs && obs.event_count_recent_window,
        obs && obs.conflict_share_recent_window
      ].forEach(function (value, index) {
        var td = el("td", "num", index === 2 ? percent(value) : number(value));
        tr.appendChild(td);
      });
      return tr;
    });
    if (!nodes.length) {
      var empty = document.createElement("tr");
      var cell = el("td", "", "No country or area matches this search.");
      cell.colSpan = 5;
      empty.appendChild(cell);
      nodes.push(empty);
    }
    dom.tableBody.replaceChildren.apply(dom.tableBody, nodes);
    dom.resultCount.textContent = rows.length + " of " + state.payload.members.length + " members";
  }

  function fact(term, value) {
    var row = document.createElement("div");
    row.appendChild(el("dt", "", term));
    row.appendChild(el("dd", "", value));
    return row;
  }

  function renderInspector() {
    var member = currentMember();
    var layer = currentLayer();
    if (!member) return;
    var status = member.layer_states[layer.layer_id];
    var obs = observation(member.area_id);
    dom.memberState.textContent = labelState(status) + " in selected domain";
    dom.inspectorTitle.textContent = member.name;
    dom.memberSummary.textContent = status === "observed"
      ? "A published India-partner event aggregate exists for this area. It is press-recorded context, not an event census, bilateral tension score, exposure or causal effect."
      : status === "unavailable_member_not_observed"
        ? "This domain is published, but no matching observation exists for this geometry. The cell remains unavailable rather than being set to zero."
        : "This domain is registered but has not cleared its construct, source and rights gates for public country observations.";
    var facts = [fact("Geometry ID", member.area_id), fact("Selected domain", layer.label)];
    if (obs) {
      facts.push(fact("All-time events", number(obs.event_count_all_time)));
      facts.push(fact("Recent events", number(obs.event_count_recent_window)));
      facts.push(fact("All-time conflict share", percent(obs.conflict_share_all_time)));
      facts.push(fact("Recent conflict share", percent(obs.conflict_share_recent_window)));
      facts.push(fact("Goldstein mean", decimal(obs.goldstein_mean_all_time)));
    }
    dom.memberFacts.replaceChildren.apply(dom.memberFacts, facts);
    var profile = state.payload.layers.map(function (row) {
      var value = member.layer_states[row.layer_id];
      var li = el("li", value === "observed" ? "observed" : "");
      var copy = document.createElement("span");
      copy.appendChild(el("strong", "", row.label));
      copy.appendChild(el("small", "", labelState(value)));
      li.appendChild(copy);
      return li;
    });
    dom.domainProfile.replaceChildren.apply(dom.domainProfile, profile);
    dom.claimBoundary.textContent = layer.prohibited_interpretation + " " + layer.safety_rule;
    dom.sourceLink.href = layer.source_payload || DATA_URL;
    dom.sourceLink.firstChild.textContent = layer.source_payload ? "Inspect source payload " : "Inspect matrix payload ";
  }

  function renderLayerHeader() {
    var layer = currentLayer();
    dom.family.textContent = layer.family + " · " + layer.kind;
    dom.layerTitle.textContent = layer.label;
    dom.layerConstruct.textContent = layer.construct;
    dom.observed.textContent = number(layer.observed_members);
    dom.unavailable.textContent = number(layer.unavailable_members);
    dom.coverage.textContent = percent(layer.coverage_share);
    dom.registryState.textContent = String(layer.registry_state).replaceAll("_", " ");
    dom.kpiObserved.textContent = number(layer.observed_members);
  }

  function selectArea(areaId, focus) {
    if (!state.members.has(areaId)) return;
    state.selectedArea = areaId;
    renderMap();
    renderTable();
    renderInspector();
    updateUrl();
    if (focus) dom.inspectorTitle.focus({ preventScroll: false });
  }

  function renderAll() {
    if (!state.layers.has(state.selectedLayer)) state.selectedLayer = state.payload.layers[0].layer_id;
    renderLayers();
    renderLayerHeader();
    renderMap();
    renderTable();
    renderInspector();
  }

  function buildGeometry() {
    dom.map.setAttribute("viewBox", state.geometry.viewBox);
    var paths = state.payload.members.map(function (member) {
      var geo = state.geometry.countries[member.area_id];
      if (!object(geo) || typeof geo.d !== "string" || !geo.d.startsWith("M")) {
        fail("A registered geometry path is invalid");
      }
      var path = svgEl("path", {
        d: geo.d,
        "data-area": member.area_id,
        "aria-label": member.name
      });
      var title = svgEl("title");
      title.textContent = member.name;
      path.appendChild(title);
      path.addEventListener("click", function () { selectArea(member.area_id, false); });
      state.paths.set(member.area_id, path);
      return path;
    });
    dom.mapLayer.replaceChildren.apply(dom.mapLayer, paths);
  }

  Promise.all([
    fetch(DATA_URL, { cache: "no-store" }).then(function (response) {
      if (!response.ok) fail("World State Matrix request failed");
      return response.json();
    }),
    fetch(GEO_URL, { cache: "no-store" }).then(function (response) {
      if (!response.ok) fail("World geometry request failed");
      return response.json();
    })
  ]).then(function (values) {
    validate(values[0], values[1]);
    state.payload = values[0];
    state.geometry = values[1];
    state.payload.layers.forEach(function (row) { state.layers.set(row.layer_id, row); });
    state.payload.members.forEach(function (row) { state.members.set(row.area_id, row); });
    if (!state.members.has(state.selectedArea)) state.selectedArea = "PAK";
    if (dom.vintage) {
      dom.vintage.textContent = state.payload._meta.observation_vintage + " observations";
    }
    dom.kpiMembers.textContent = number(state.payload.denominator.geometry_members);
    dom.kpiLayers.textContent = number(state.payload.denominator.country_level_layers);
    dom.kpiCells.textContent = number(state.payload.denominator.cells);
    dom.search.placeholder = "Search " + number(state.payload.denominator.geometry_members) + " members";
    dom.denominatorCopy.textContent = (
      "This validated release contains " + number(state.payload.denominator.cells) +
      " explicit geometry-layer cells. An unavailable cell is a published limitation—" +
      "not a zero, a safe condition or a hidden estimate. No single world score is calculated."
    );
    buildGeometry();
    renderAll();
    updateUrl();
  }).catch(function (error) {
    dom.mapStatus.textContent = "Matrix refused: " + error.message;
    dom.tableBody.replaceChildren();
    var row = document.createElement("tr");
    var cell = el("td", "", "The matrix could not be verified. No partial view was rendered.");
    cell.colSpan = 5;
    row.appendChild(cell);
    dom.tableBody.appendChild(row);
  });

  dom.search.addEventListener("input", function () {
    state.query = dom.search.value.trim();
    renderMap();
    renderTable();
  });
}());
