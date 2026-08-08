(function () {
  "use strict";

  var dimensionIds = [
    "dim:exposure.cross_border_supply",
    "dim:exposure.logistics",
    "dim:exposure.corporate_footprint",
    "dim:exposure.policy_legal",
    "dim:exposure.digital_infrastructure"
  ];
  var payload = null;
  var buttons = Array.prototype.slice.call(document.querySelectorAll("[data-dna-vintage]"));
  var load = document.getElementById("dna-load");
  var result = document.getElementById("dna-result");
  var dimensions = document.getElementById("dna-dimensions");
  var components = document.getElementById("dna-components");

  function select(selector) { return document.querySelector(selector); }
  function text(selector, value) {
    var node = select(selector);
    if (node) node.textContent = value;
  }
  function element(tag, className, value) {
    var node = document.createElement(tag);
    if (className) node.className = className;
    if (value !== undefined) node.textContent = value;
    return node;
  }
  function sameArray(left, right) {
    return left.length === right.length && left.every(function (value, index) {
      return value === right[index];
    });
  }
  function hashLike(value) { return typeof value === "string" && /^[0-9a-f]{64}$/.test(value); }
  function gapCount(gaps) {
    return (gaps.target_universe_not_declared ? 1 : 0) +
      gaps.target_universe_not_included_ids.length +
      gaps.unknown_quantification_edge_ids.length +
      gaps.stale_edge_ids.length +
      gaps.unknown_freshness_edge_ids.length +
      gaps.missing_dimension_ids.length;
  }
  function validateSnapshot(snapshot) {
    if (!snapshot || snapshot.object_type !== "exposure_dna_snapshot" ||
        !hashLike(snapshot.record_sha256) || !snapshot.result ||
        snapshot.result.scalar_score_computed !== false ||
        snapshot.result.public_claim_state !== "requires_claim_bundle" ||
        !snapshot.target || !snapshot.release || !snapshot.counts ||
        !Array.isArray(snapshot.edges) || !Array.isArray(snapshot.dimensions) ||
        !Array.isArray(snapshot.target_universes) || !snapshot.gaps ||
        snapshot.counts.direct_edges !== snapshot.edges.length ||
        snapshot.dimensions.length !== 5 ||
        !sameArray(snapshot.dimensions.map(function (row) { return row.dimension_id; }), dimensionIds)) {
      throw new Error("snapshot contract mismatch");
    }
    var partition = [];
    snapshot.dimensions.forEach(function (row) {
      if (!row.counts || row.counts.edges !== row.edge_ids.length ||
          row.counts.edges !== row.counts.quantified + row.counts.qualitative + row.counts.unknown ||
          row.counts.edges !== row.counts.current + row.counts.stale + row.counts.unknown_freshness) {
        throw new Error("dimension contract mismatch");
      }
      partition = partition.concat(row.edge_ids);
    });
    var edgeIds = snapshot.edges.map(function (edge) { return edge.edge_id; }).sort();
    if (!sameArray(partition.sort(), edgeIds)) throw new Error("dimension partition mismatch");
    snapshot.edges.forEach(function (edge) {
      if (!edge.counterpart || !edge.freshness || !edge.coverage ||
          ["current", "stale", "unknown_policy"].indexOf(edge.freshness.status) < 0 ||
          ["quantified", "qualitative", "unknown"].indexOf(edge.quantification_status) < 0 ||
          (edge.quantification_status === "quantified") !== (edge.magnitude !== null)) {
        throw new Error("component contract mismatch");
      }
    });
  }
  function validatePayload(document) {
    if (!document || !document._meta || document._meta.scope !== "synthetic_test_vector_only" ||
        document._meta.production_release !== false ||
        document._meta.real_entity_source_rights_or_exposure_claims !== false ||
        document._meta.scalar_score_computed !== false || !document.synthetic_labels) {
      throw new Error("demo boundary mismatch");
    }
    validateSnapshot(document.before_snapshot);
    validateSnapshot(document.after_snapshot);
    var delta = document.delta;
    if (!delta || delta.object_type !== "exposure_dna_delta" || !hashLike(delta.record_sha256) ||
        delta.before.snapshot_record_sha256 !== document.before_snapshot.record_sha256 ||
        delta.after.snapshot_record_sha256 !== document.after_snapshot.record_sha256 ||
        delta.result.scalar_score_computed !== false ||
        delta.result.causal_interpretation_performed !== false ||
        delta.counts.added_edges !== delta.edge_changes.added.length ||
        delta.counts.removed_edges !== delta.edge_changes.removed.length ||
        delta.counts.revised_edges !== delta.edge_changes.revised.length ||
        delta.counts.unchanged_edges !== delta.edge_changes.unchanged_edge_ids.length) {
      throw new Error("delta contract mismatch");
    }
  }
  function label(entityId) {
    return payload.synthetic_labels[entityId] || entityId;
  }
  function words(value) { return value.replace(/_/g, " "); }
  function shortHash(value) { return value.slice(0, 10) + "…" + value.slice(-8); }
  function formatMagnitude(edge) {
    if (edge.quantification_status !== "quantified") {
      return edge.quantification_status === "unknown" ? "Unknown—no value asserted" : "Qualitative—magnitude not quantified";
    }
    return edge.magnitude.value + " " + words(edge.magnitude.unit);
  }
  function statusBadge(status) {
    return element("span", "dna-badge " + status, words(status));
  }
  function renderDimension(row, index) {
    var card = element("article", "dna-dimension");
    var top = element("div", "dna-dimension-top");
    top.appendChild(element("span", "dna-dimension-index", String(index + 1).padStart(2, "0")));
    var title = element("div", "");
    title.appendChild(element("h4", "", row.label));
    title.appendChild(element("p", "", row.definition));
    top.appendChild(title);
    top.appendChild(element("strong", "dna-dimension-count", String(row.counts.edges)));
    card.appendChild(top);
    var meter = element("div", "dna-dimension-meter");
    [
      ["quantified", row.counts.quantified],
      ["qualitative", row.counts.qualitative],
      ["unknown", row.counts.unknown]
    ].forEach(function (pair) {
      if (!pair[1]) return;
      var span = element("span", pair[0]);
      span.style.width = (pair[1] / Math.max(row.counts.edges, 1) * 100) + "%";
      meter.appendChild(span);
    });
    card.appendChild(meter);
    card.appendChild(element("small", "", row.counts.quantified + " quantified · " +
      row.counts.qualitative + " qualitative · " + row.counts.unknown + " unknown"));
    return card;
  }
  function renderComponent(edge) {
    var card = element("article", "dna-component");
    var head = element("div", "dna-component-head");
    var title = element("div", "");
    title.appendChild(element("span", "dna-component-type", words(edge.edge_type)));
    title.appendChild(element("h4", "", label(edge.counterpart.entity_id)));
    title.appendChild(element("small", "", words(edge.counterpart.entity_type) + " · " + edge.orientation));
    head.appendChild(title);
    var badges = element("div", "dna-badges");
    badges.appendChild(statusBadge(edge.quantification_status));
    badges.appendChild(statusBadge(edge.freshness.status));
    head.appendChild(badges);
    card.appendChild(head);
    card.appendChild(element("strong", "dna-component-value", formatMagnitude(edge)));
    if (edge.magnitude) {
      card.appendChild(element("p", "dna-denominator", "Denominator: " + edge.magnitude.denominator));
      card.appendChild(element("p", "dna-period", "Period: " + edge.magnitude.period_start + " — " + edge.magnitude.period_end));
    }
    var foot = element("dl", "dna-component-foot");
    [
      ["Observed", edge.observed_at],
      ["Freshness rule", edge.freshness.max_current_age_days === null ? "policy unavailable" : edge.freshness.max_current_age_days + " days"],
      ["Coverage frame", edge.coverage.counts.included + "/" + edge.coverage.counts.total_eligible + " included"],
      ["Record", shortHash(edge.record_sha256)]
    ].forEach(function (pair) {
      var row = element("div", "");
      row.appendChild(element("dt", "", pair[0]));
      row.appendChild(element("dd", "", pair[1]));
      foot.appendChild(row);
    });
    card.appendChild(foot);
    return card;
  }
  function renderUniverse(snapshot) {
    var root = select("[data-dna-universe]");
    var bar = select("[data-dna-universe-bar]");
    root.replaceChildren();
    bar.replaceChildren();
    if (!snapshot.target_universes.length) {
      text("[data-dna-universe-note]", "No declared target universe is present in this release.");
      return;
    }
    var universe = snapshot.target_universes[0];
    var keys = ["included", "excluded", "unmappable", "stale"];
    keys.forEach(function (key) {
      var segment = element("span", key);
      segment.style.width = (universe.counts[key] / universe.counts.total_eligible * 100) + "%";
      segment.title = key + ": " + universe.counts[key];
      bar.appendChild(segment);
      var row = element("div", "");
      row.appendChild(element("dt", "", words(key)));
      row.appendChild(element("dd", "", universe.counts[key] + " / " + universe.counts.total_eligible));
      root.appendChild(row);
    });
    text("[data-dna-universe-note]", "Target status: " + words(universe.member_status) +
      " · reference date " + universe.reference_date + ". Coverage is limited to this declared frame.");
  }
  function renderDelta() {
    var delta = payload.delta;
    text("[data-dna-added]", String(delta.counts.added_edges));
    text("[data-dna-revised]", String(delta.counts.revised_edges));
    text("[data-dna-unchanged]", String(delta.counts.unchanged_edges));
    text("[data-dna-delta-note]", "A release difference is not proof that the real-world relationship changed, nor evidence of cause.");
    var list = select("[data-dna-delta-list]");
    list.replaceChildren();
    delta.edge_changes.added.forEach(function (row) {
      var edge = payload.after_snapshot.edges.find(function (item) { return item.edge_id === row.edge_id; });
      list.appendChild(element("li", "", "Added: " + label(edge.counterpart.entity_id) + " (" + words(edge.edge_type) + ")"));
    });
    delta.edge_changes.revised.forEach(function (row) {
      var edge = payload.after_snapshot.edges.find(function (item) { return item.edge_id === row.edge_id; });
      list.appendChild(element("li", "", "Revised: " + label(edge.counterpart.entity_id) + " · " + row.changed_aspects.map(words).join(", ")));
    });
    if (delta.gap_changes.opened.length) {
      list.appendChild(element("li", "", "Opened gap: " + words(delta.gap_changes.opened[0])));
    }
  }
  function render(vintage) {
    if (!payload) return;
    var snapshot = vintage === "before" ? payload.before_snapshot : payload.after_snapshot;
    validateSnapshot(snapshot);
    buttons.forEach(function (button) {
      var selected = button.getAttribute("data-dna-vintage") === vintage;
      button.classList.toggle("on", selected);
      button.setAttribute("aria-pressed", selected ? "true" : "false");
    });
    text("[data-dna-target]", label(snapshot.target.entity_id));
    text("[data-dna-target-type]", words(snapshot.target.entity_type) + " · synthetic test identity");
    text("[data-dna-release]", snapshot.release.release_id);
    text("[data-dna-effective]", snapshot.release.effective_date);
    text("[data-dna-hash]", shortHash(snapshot.record_sha256));
    text("[data-dna-edges]", String(snapshot.counts.direct_edges));
    text("[data-dna-orientation]", snapshot.counts.incoming_edges + " incoming · " + snapshot.counts.outgoing_edges + " outgoing");
    text("[data-dna-quantified]", snapshot.counts.quantified_edges + " quantified");
    text("[data-dna-qualitative]", snapshot.counts.qualitative_edges + " qualitative · " + snapshot.counts.unknown_edges + " unknown");
    text("[data-dna-current]", snapshot.counts.current_edges + " current");
    text("[data-dna-stale]", snapshot.counts.stale_edges + " stale · " + snapshot.counts.unknown_freshness_edges + " policy unknown");
    text("[data-dna-gaps]", String(gapCount(snapshot.gaps)));
    dimensions.replaceChildren();
    snapshot.dimensions.forEach(function (row, index) { dimensions.appendChild(renderDimension(row, index)); });
    components.replaceChildren();
    snapshot.edges.forEach(function (edge) { components.appendChild(renderComponent(edge)); });
    renderUniverse(snapshot);
    renderDelta();
    load.hidden = true;
    result.hidden = false;
  }
  function refuse() {
    result.hidden = true;
    load.hidden = false;
    load.textContent = "The fingerprint refused to render because its payload was unavailable or failed its contract.";
  }

  buttons.forEach(function (button) {
    button.addEventListener("click", function () {
      try { render(button.getAttribute("data-dna-vintage")); } catch (error) { refuse(); }
    });
  });

  fetch("data/exposure_dna_demo.json")
    .then(function (response) {
      if (!response.ok) throw new Error("HTTP " + response.status);
      return response.json();
    })
    .then(function (document) {
      validatePayload(document);
      payload = document;
      render("after");
    })
    .catch(refuse);
}());
