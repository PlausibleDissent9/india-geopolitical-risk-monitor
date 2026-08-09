(function () {
  "use strict";

  var DATA_URL = "data/event_ledger.json";
  // This trust root is deliberately independent from source-rights signers
  // and empty until a human-reviewed commit pins an exact release key.
  var TRUSTED_RELEASE_SIGNERS = Object.freeze({});
  var UNIT_IDS = [
    "aggregate_source_rows",
    "deduplicated_source_events",
    "canonical_geopolitical_events",
    "detected_salience_episodes"
  ];
  var CHANNELS = [
    ["all", "All channels"],
    ["pakistan_west", "Pakistan / West"],
    ["china_east", "China / East"],
    ["gulf_energy", "Gulf / Energy"],
    ["us_trade", "US / Trade"],
    ["shipping", "Shipping"]
  ];
  var dom = {
    boundary: document.getElementById("ledger-boundary"),
    publicationDate: document.querySelector("[data-ledger-date]"),
    days: document.getElementById("ledger-kpi-days"),
    countries: document.getElementById("ledger-kpi-countries"),
    observed: document.getElementById("ledger-kpi-observed"),
    units: document.getElementById("ledger-unit-grid"),
    chartGrid: document.getElementById("ledger-chart-grid"),
    chartLine: document.getElementById("ledger-chart-line"),
    chartDot: document.getElementById("ledger-chart-dot"),
    slider: document.getElementById("ledger-date-slider"),
    start: document.getElementById("ledger-start"),
    date: document.getElementById("ledger-date"),
    end: document.getElementById("ledger-end"),
    dayState: document.getElementById("ledger-day-state"),
    indiaRows: document.getElementById("ledger-india-rows"),
    globalRows: document.getElementById("ledger-global-rows"),
    frameCopy: document.getElementById("ledger-frame-copy"),
    countryCopy: document.getElementById("ledger-country-copy"),
    releaseId: document.getElementById("ledger-release-id"),
    stateSha: document.getElementById("ledger-state-sha"),
    rights: document.getElementById("ledger-rights"),
    episodeCount: document.getElementById("ledger-episode-count"),
    toolbar: document.getElementById("ledger-episode-toolbar"),
    episodeList: document.getElementById("ledger-episode-list"),
    more: document.getElementById("ledger-more"),
    gateList: document.getElementById("ledger-gate-list")
  };
  if (!dom.boundary || !dom.units || !dom.slider || !dom.episodeList) return;

  var state = { payload: null, channel: "all", index: 0, limit: 40 };

  function fail(message) { throw new Error(message); }
  function object(value) { return value && typeof value === "object" && !Array.isArray(value); }
  function finiteInteger(value) { return Number.isInteger(value) && value >= 0; }
  function isoDate(value) { return typeof value === "string" && /^\d{4}-\d{2}-\d{2}$/.test(value) && !Number.isNaN(Date.parse(value + "T00:00:00Z")); }
  function utcSecond(value) {
    return typeof value === "string" &&
      /^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$/.test(value) &&
      !Number.isNaN(Date.parse(value));
  }
  function sha256(value) { return typeof value === "string" && /^[0-9a-f]{64}$/.test(value); }
  function canonical(value) {
    if (Array.isArray(value)) return "[" + value.map(canonical).join(",") + "]";
    if (object(value)) return "{" + Object.keys(value).sort().map(function (key) {
      return JSON.stringify(key) + ":" + canonical(value[key]);
    }).join(",") + "}";
    return JSON.stringify(value);
  }
  function hex(bytes) {
    return Array.from(new Uint8Array(bytes)).map(function (value) {
      return value.toString(16).padStart(2, "0");
    }).join("");
  }
  function base64Bytes(value) {
    var decoded = atob(value);
    return Uint8Array.from(decoded, function (character) { return character.charCodeAt(0); });
  }
  function digest(value) {
    return crypto.subtle.digest("SHA-256", new TextEncoder().encode(canonical(value))).then(hex);
  }
  function exactKeys(value, keys) {
    if (!object(value)) return false;
    var actual = Object.keys(value).sort();
    var wanted = keys.slice().sort();
    return actual.length === wanted.length && actual.every(function (key, i) { return key === wanted[i]; });
  }
  function el(tag, className, text) {
    var node = document.createElement(tag);
    if (className) node.className = className;
    if (text != null) node.textContent = text;
    return node;
  }
  function svgEl(tag, attrs) {
    var node = document.createElementNS("http://www.w3.org/2000/svg", tag);
    Object.entries(attrs || {}).forEach(function (entry) { node.setAttribute(entry[0], String(entry[1])); });
    return node;
  }
  function count(value) { return value == null ? "Unavailable" : Number(value).toLocaleString("en-IN"); }
  function compact(value) {
    if (!Number.isFinite(Number(value))) return "Unavailable";
    var n = Number(value);
    if (n >= 1000000000) return (n / 1000000000).toFixed(2) + "B";
    if (n >= 1000000) return (n / 1000000).toFixed(2) + "M";
    if (n >= 1000) return (n / 1000).toFixed(1) + "K";
    return String(n);
  }

  function validate(payload) {
    if (!object(payload) || !object(payload._meta) ||
        payload._meta.canonical_release_state !== "unavailable_no_production_canonical_release") {
      fail("Ledger metadata or release boundary is invalid");
    }
    if (payload._meta.artifact_status === "public_release_blocked_rights_review") {
      if (payload._meta.partial !== true || payload.frame !== null ||
          payload.aggregate_historical_series !== null || payload.episodes !== null ||
          !object(payload.rights_gate) || payload.rights_gate.authorized !== false ||
          !Array.isArray(payload.rights_gate.blocked_source_ids) ||
          payload.rights_gate.blocked_source_ids.length === 0 ||
          !exactKeys(payload.count_units, UNIT_IDS) ||
          Object.values(payload.count_units).some(function (unit) {
            return !object(unit) || unit.public_available !== false || unit.value !== null;
          })) {
        fail("Rights-gated refusal artifact is invalid");
      }
      return "blocked";
    }
    if (payload._meta.artifact_status !== "public_observation_foundation" ||
        payload._meta.partial !== false || !object(payload.rights_gate) ||
        payload.rights_gate.authorized !== true) {
      fail("Authorized ledger release is invalid");
    }
    if (!object(payload.frame) || !object(payload.boundary) ||
        !exactKeys(payload.count_units, UNIT_IDS) || !object(payload.aggregate_historical_series) ||
        !Array.isArray(payload.episodes) || !object(payload.canonical_event_layer) ||
        !object(payload.release_lineage)) {
      fail("Ledger collections are invalid");
    }
    var meta = payload._meta;
    var lineage = payload.release_lineage;
    var predecessor = meta.predecessor_release_integrity_sha256;
    if (!finiteInteger(meta.vintage_number) || meta.vintage_number < 1 ||
        typeof meta.release_id !== "string" ||
        meta.release_id.indexOf("event-ledger-v" + meta.vintage_number + "-") !== 0 ||
        !sha256(meta.artifact_integrity_sha256) ||
        !sha256(meta.release_state_sha256) ||
        !sha256(meta.measurement_state_sha256) ||
        !utcSecond(meta.released_at) || !isoDate(meta.knowledge_cutoff) ||
        (predecessor !== null && !sha256(predecessor)) ||
        lineage.vintage_number !== meta.vintage_number ||
        lineage.predecessor_release_integrity_sha256 !== predecessor ||
        !object(lineage.delta) ||
        !["initial_release", "successor_release"].includes(lineage.delta.type) ||
        !Array.isArray(lineage.delta.added_dates) ||
        !Array.isArray(lineage.delta.revised_dates) ||
        !Array.isArray(lineage.delta.removed_dates) ||
        !Array.isArray(lineage.delta.added_episode_ids) ||
        !Array.isArray(lineage.delta.revised_episodes) ||
        !Array.isArray(lineage.delta.removed_episode_ids)) {
      fail("Ledger release identity or lineage is invalid");
    }
    var frame = payload.frame;
    if (!finiteInteger(frame.calendar_days) || !finiteInteger(frame.observed_aggregate_days) ||
        !finiteInteger(frame.legacy_unavailable_days) ||
        frame.calendar_days !== frame.observed_aggregate_days + frame.legacy_unavailable_days ||
        frame.calendar_partition_complete !== true || frame.aggregate_store_date_sets_equal !== true ||
        frame.global_geometry_members !== frame.eligible_external_partner_members + frame.partner_members_not_applicable_self ||
        frame.eligible_external_partner_members !== frame.partner_members_mapped + frame.partner_members_not_observed_reason_unresolved ||
        !Array.isArray(frame.legacy_unavailable_dates) ||
        frame.legacy_unavailable_dates.length !== frame.legacy_unavailable_days ||
        !Array.isArray(frame.not_observed_partner_members) ||
        frame.not_observed_partner_members.length !== frame.partner_members_not_observed_reason_unresolved ||
        frame.partner_coverage_share !== null) {
      fail("Ledger denominator does not reconcile");
    }
    var series = payload.aggregate_historical_series;
    var fields = ["dates", "states", "valid_layout_export_rows", "india_involving_rows", "india_involving_share_of_valid_layout_export_rows_pct", "verbal_conflict_rows", "material_conflict_rows", "protest_rows"];
    fields.forEach(function (field) {
      if (!Array.isArray(series[field]) || series[field].length !== frame.calendar_days) fail("Historical-series array length is invalid");
    });
    var unavailable = new Set(frame.legacy_unavailable_dates);
    series.dates.forEach(function (day, i) {
      if (!isoDate(day) || (i && day <= series.dates[i - 1])) fail("Historical-series dates are invalid");
      var gap = series.states[i] === "legacy_unavailable_without_retrieval_receipt";
      if (!gap && series.states[i] !== "observed_aggregate") fail("Historical-series state is invalid");
      if (gap !== unavailable.has(day)) fail("Historical-series gap does not match the unavailable register");
      ["valid_layout_export_rows", "india_involving_rows", "india_involving_share_of_valid_layout_export_rows_pct", "verbal_conflict_rows", "material_conflict_rows", "protest_rows"].forEach(function (field) {
        var value = series[field][i];
        var valid = field === "india_involving_share_of_valid_layout_export_rows_pct"
          ? Number.isFinite(value) && value >= 0 && value <= 100
          : finiteInteger(value);
        if (gap ? value !== null : !valid) fail("Historical-series value/gap mismatch");
      });
      if (!gap && series.india_involving_rows[i] > series.valid_layout_export_rows[i]) fail("India row count exceeds valid-layout denominator");
    });
    if (series.dates[0] !== frame.start || series.dates[series.dates.length - 1] !== frame.end) fail("Historical-series endpoints do not match frame");
    if (payload.count_units.deduplicated_source_events.public_available !== false ||
        payload.count_units.deduplicated_source_events.count !== null ||
        payload.count_units.canonical_geopolitical_events.public_available !== false ||
        payload.count_units.canonical_geopolitical_events.count !== null ||
        payload.canonical_event_layer.available !== false ||
        payload.canonical_event_layer.event_count !== null ||
        payload.canonical_event_layer.model_promotion !== "prohibited") {
      fail("Unavailable event layers were promoted");
    }
    if (payload.count_units.detected_salience_episodes.count !== payload.episodes.length) fail("Episode denominator mismatch");
    var ids = new Set();
    payload.episodes.forEach(function (episode) {
      if (!object(episode) || typeof episode.episode_id !== "string" || ids.has(episode.episode_id) ||
          episode.object_type !== "detected_salience_episode" ||
          !["detector_window_closed", "provisional_open_window"].includes(episode.lifecycle_state) || episode.canonical_event_ids !== null ||
          episode.canonical_event_link_state !== "unavailable_no_canonical_release" ||
          !isoDate(episode.start) || !isoDate(episode.end) || !isoDate(episode.peak_date)) {
        fail("Detector episode identity or boundary is invalid");
      }
      ids.add(episode.episode_id);
    });
    if (!Array.isArray(payload.canonical_event_layer.requirements) ||
        !Array.isArray(payload.canonical_event_layer.target_states) ||
        !Array.isArray(payload.boundary.prohibited_interpretations) ||
        typeof payload.release_lineage.prohibited_claim !== "string") {
      fail("Release and claim boundaries are incomplete");
    }
    return "authorized";
  }

  async function verifyAuthorizedRelease(payload) {
    var meta = payload._meta;
    var envelope = meta.release_signature;
    if (!object(envelope) || !exactKeys(envelope, [
      "schema_version", "algorithm", "signer_id", "signer_role",
      "public_key_ed25519_base64", "signed_payload_sha256",
      "signature_ed25519_base64"
    ])) fail("Authorized release signature is missing");
    var trusted = TRUSTED_RELEASE_SIGNERS[envelope.signer_id];
    if (!object(trusted) || trusted.role !== envelope.signer_role ||
        trusted.public_key_ed25519_base64 !== envelope.public_key_ed25519_base64 ||
        !isoDate(trusted.effective) || trusted.effective > meta.released_at.slice(0, 10) ||
        (trusted.revoked_on !== null &&
          (!isoDate(trusted.revoked_on) || meta.released_at.slice(0, 10) >= trusted.revoked_on))) {
      fail("Authorized release signer is not pinned by this client");
    }
    var content = JSON.parse(JSON.stringify(payload));
    delete content._meta.artifact_integrity_sha256;
    delete content._meta.release_content_sha256;
    delete content._meta.release_signature;
    if (await digest(content) !== meta.release_content_sha256) {
      fail("Authorized release content digest is invalid");
    }
    var artifact = JSON.parse(JSON.stringify(payload));
    delete artifact._meta.artifact_integrity_sha256;
    if (await digest(artifact) !== meta.artifact_integrity_sha256) {
      fail("Authorized release artifact digest is invalid");
    }
    var statement = {
      schema_version: "igrm-event-ledger-release-signature-v1",
      release_id: meta.release_id,
      vintage_number: meta.vintage_number,
      release_content_sha256: meta.release_content_sha256,
      release_state_sha256: meta.release_state_sha256,
      predecessor_release_integrity_sha256: meta.predecessor_release_integrity_sha256,
      released_at: meta.released_at,
      knowledge_cutoff: meta.knowledge_cutoff
    };
    var statementBytes = new TextEncoder().encode(canonical(statement));
    if (hex(await crypto.subtle.digest("SHA-256", statementBytes)) !== envelope.signed_payload_sha256) {
      fail("Authorized release signed-payload digest is invalid");
    }
    var key = await crypto.subtle.importKey(
      "raw", base64Bytes(envelope.public_key_ed25519_base64),
      { name: "Ed25519" }, false, ["verify"]
    );
    if (!await crypto.subtle.verify(
      { name: "Ed25519" }, key,
      base64Bytes(envelope.signature_ed25519_base64), statementBytes
    )) fail("Authorized release signature is invalid");
  }

  function renderUnits() {
    var p = state.payload;
    var definitions = [
      ["aggregate_source_rows", "Aggregate source rows", "available", compact(p.count_units.aggregate_source_rows.counts.india_involving_rows) + " India rows"],
      ["deduplicated_source_events", "Deduplicated source events", "unavailable", "Unavailable"],
      ["canonical_geopolitical_events", "Canonical geopolitical events", "unavailable", "Unavailable"],
      ["detected_salience_episodes", "Detected salience episodes", "available", count(p.count_units.detected_salience_episodes.count)]
    ];
    var cards = definitions.map(function (item) {
      var unit = p.count_units[item[0]];
      var card = el("article", "ledger-unit " + item[2]);
      card.appendChild(el("span", "ledger-state", unit.public_available ? "Published unit" : "Explicitly unavailable"));
      card.appendChild(el("strong", "", item[1]));
      card.appendChild(el("p", "", unit.definition));
      if (!unit.public_available && unit.unavailable_reason) card.appendChild(el("p", "", unit.unavailable_reason));
      card.appendChild(el("b", "", item[3]));
      return card;
    });
    dom.units.replaceChildren.apply(dom.units, cards);
  }

  function chartPath(values) {
    var width = 900, height = 220, top = 12, bottom = 15;
    var valid = values.filter(function (value) { return Number.isFinite(value); });
    var max = Math.max.apply(null, valid.concat([1]));
    var d = "";
    values.forEach(function (value, i) {
      if (!Number.isFinite(value)) return;
      var x = (i / Math.max(1, values.length - 1)) * width;
      var y = top + (1 - value / max) * (height - top - bottom);
      var previous = i > 0 ? values[i - 1] : null;
      d += (Number.isFinite(previous) ? "L" : "M") + x.toFixed(2) + " " + y.toFixed(2);
    });
    return { d: d, max: max };
  }

  function renderChart() {
    var values = state.payload.aggregate_historical_series.india_involving_share_of_valid_layout_export_rows_pct;
    var built = chartPath(values);
    dom.chartLine.setAttribute("d", built.d);
    dom.chartGrid.replaceChildren.apply(dom.chartGrid, [0.25, 0.5, 0.75].map(function (ratio) {
      return svgEl("line", { x1: 0, y1: 12 + ratio * 193, x2: 900, y2: 12 + ratio * 193, "class": "ledger-chart-grid" });
    }));
    dom.slider.max = String(values.length - 1);
    dom.slider.value = String(values.length - 1);
    state.index = values.length - 1;
    dom.start.textContent = state.payload.frame.start;
    dom.end.textContent = state.payload.frame.end;
    renderReplay();
  }

  function renderReplay() {
    var series = state.payload.aggregate_historical_series;
    var i = state.index;
    var gap = series.states[i] === "legacy_unavailable_without_retrieval_receipt";
    dom.date.textContent = series.dates[i];
    dom.dayState.textContent = gap ? "Upstream file unavailable" : "Observed aggregate";
    dom.indiaRows.textContent = gap ? "Unavailable—not zero" : count(series.india_involving_rows[i]);
    dom.globalRows.textContent = gap ? "Unavailable—not zero" : count(series.valid_layout_export_rows[i]);
    if (gap) {
      dom.chartDot.hidden = true;
    } else {
      var values = series.india_involving_share_of_valid_layout_export_rows_pct;
      var max = Math.max.apply(null, values.filter(function (value) { return Number.isFinite(value); }));
      dom.chartDot.setAttribute("cx", String((i / Math.max(1, values.length - 1)) * 900));
      dom.chartDot.setAttribute("cy", String(12 + (1 - values[i] / max) * 193));
      dom.chartDot.hidden = false;
    }
  }

  function renderToolbar() {
    if (!dom.toolbar.children.length) CHANNELS.forEach(function (row) {
      var button = el("button", "", row[1]);
      button.type = "button";
      button.dataset.channel = row[0];
      button.addEventListener("click", function () {
        state.channel = row[0];
        state.limit = 40;
        renderToolbar();
        renderEpisodes();
      });
      dom.toolbar.appendChild(button);
    });
    Array.from(dom.toolbar.children).forEach(function (button) {
      button.setAttribute("aria-pressed", button.dataset.channel === state.channel ? "true" : "false");
    });
  }

  function renderEpisodes() {
    var rows = state.payload.episodes.filter(function (episode) {
      return state.channel === "all" || episode.channel === state.channel;
    }).slice().reverse();
    var shown = Math.min(state.limit, rows.length);
    dom.episodeCount.textContent = "Showing latest " + count(shown) + " of " + count(rows.length) +
      " detector windows in this view · " + count(state.payload.episodes.length) + " total";
    var visible = rows.slice(0, shown).map(function (episode) {
      var item = el("li", "ledger-episode-row");
      var dates = el("div");
      dates.appendChild(el("strong", "", episode.start));
      dates.appendChild(el("span", "", episode.end === episode.start ? "One-day detector window" : "Through " + episode.end));
      var detail = el("div");
      detail.appendChild(el("strong", "", episode.label));
      detail.appendChild(el("small", "", "Peak " + episode.peak_date + " · " + episode.n_spike_days + " spike day(s) · not a canonical event"));
      var link = el("a", "", "Open dossier →");
      link.href = "episode.html?channel=" + encodeURIComponent(episode.channel) + "&start=" + encodeURIComponent(episode.start);
      item.appendChild(dates); item.appendChild(detail); item.appendChild(link);
      return item;
    });
    if (!visible.length) visible.push(el("li", "ledger-error", "No detector episodes match this channel."));
    dom.episodeList.replaceChildren.apply(dom.episodeList, visible);
    if (dom.more) {
      dom.more.hidden = shown >= rows.length;
      dom.more.textContent = "Show " + Math.min(40, rows.length - shown) + " more detector windows";
    }
  }

  function render() {
    var p = state.payload;
    dom.boundary.replaceChildren();
    var strong = el("b", "", "Four objects, never one inflated number. ");
    dom.boundary.appendChild(strong);
    dom.boundary.appendChild(document.createTextNode(
      "Aggregate rows and detector episodes are available; deduplicated and canonical event counts remain unavailable."
    ));
    dom.days.textContent = count(p.frame.calendar_days);
    if (dom.publicationDate) dom.publicationDate.textContent = "Aggregate frame through " + p.frame.end;
    dom.countries.textContent = count(p.frame.global_geometry_members);
    dom.observed.textContent = count(p.frame.partner_members_mapped);
    dom.frameCopy.textContent = count(p.frame.observed_aggregate_days) + " represented days + " +
      count(p.frame.legacy_unavailable_days) + " legacy missing days without retrieval receipts = " +
      count(p.frame.calendar_days) + " calendar days in the current release.";
    dom.countryCopy.textContent = count(p.frame.partner_members_mapped) + " mapped · " +
      count(p.frame.partner_members_not_observed_reason_unresolved) + " not observed / reason unresolved · " +
      count(p.frame.partner_members_not_applicable_self) + " self not applicable · " +
      count(p.frame.unmappable_provider_partner_codes.length) + " provider codes unmappable";
    dom.releaseId.textContent = p._meta.release_id;
    dom.stateSha.textContent = "Artifact-integrity SHA-256: " + p._meta.artifact_integrity_sha256;
    dom.rights.textContent = p._meta.rights_state.replaceAll("_", " ");
    dom.gateList.replaceChildren.apply(dom.gateList, p.canonical_event_layer.requirements.map(function (text) {
      return el("li", "", text);
    }));
    renderUnits(); renderChart(); renderToolbar(); renderEpisodes();
  }

  function renderBlocked() {
    var p = state.payload;
    dom.boundary.replaceChildren(
      el("b", "", "Publication refused. "),
      document.createTextNode("No source-derived value renders while any required signed rights decision is absent.")
    );
    if (dom.publicationDate) dom.publicationDate.textContent = "No authorized value release";
    dom.days.textContent = "Withheld";
    dom.countries.textContent = "Withheld";
    dom.observed.textContent = "Withheld";
    document.getElementById("ledger-kpi-release").textContent = "None";
    dom.frameCopy.textContent = "Candidate validation completed in process; public denominators are withheld.";
    dom.countryCopy.textContent = "No geometry-coverage statistic is published while the gate is blocked.";
    dom.releaseId.textContent = p._meta.status_id;
    dom.stateSha.textContent = "Refusal-state SHA-256: " + p._meta.refusal_state_sha256;
    dom.rights.textContent = "blocked · " + p.rights_gate.blocked_source_ids.length + " unsigned or unapproved sources";
    dom.gateList.replaceChildren.apply(dom.gateList, p.canonical_event_layer.requirements.map(function (text) {
      return el("li", "", text);
    }));
    dom.units.replaceChildren.apply(dom.units, UNIT_IDS.map(function (unitId) {
      var unit = p.count_units[unitId];
      var card = el("article", "ledger-unit unavailable");
      card.appendChild(el("span", "ledger-state", "Not publicly available"));
      card.appendChild(el("strong", "", unitId.replaceAll("_", " ")));
      card.appendChild(el("p", "", unit.definition));
      card.appendChild(el("b", "", "Withheld"));
      return card;
    }));
    dom.chartLine.setAttribute("d", "");
    dom.chartDot.hidden = true;
    dom.slider.disabled = true;
    dom.start.textContent = "—"; dom.date.textContent = "No release"; dom.end.textContent = "—";
    dom.dayState.textContent = "Rights gate blocked";
    dom.indiaRows.textContent = "Withheld";
    dom.globalRows.textContent = "Withheld";
    dom.episodeCount.textContent = "No detector values published";
    dom.toolbar.replaceChildren();
    dom.episodeList.replaceChildren(el("li", "ledger-error", "Detector values withheld pending signed source-rights decisions."));
    if (dom.more) dom.more.hidden = true;
  }

  dom.slider.addEventListener("input", function () {
    state.index = Number(dom.slider.value);
    renderReplay();
  });
  if (dom.more) dom.more.addEventListener("click", function () {
    state.limit += 40;
    renderEpisodes();
  });

  fetch(DATA_URL, { cache: "no-store" })
    .then(function (response) { if (!response.ok) fail("Ledger payload unavailable"); return response.json(); })
    .then(async function (payload) {
      var mode = validate(payload);
      if (mode === "authorized") await verifyAuthorizedRelease(payload);
      state.payload = payload;
      if (mode === "blocked") renderBlocked(); else render();
    })
    .catch(function (error) {
      dom.boundary.className = "ledger-error";
      dom.boundary.textContent = "Ledger refused: " + error.message + ". Use the machine artifact only after validation passes.";
      dom.units.replaceChildren(el("div", "ledger-error", "No partial or malformed ledger will render."));
    });
}());
