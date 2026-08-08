(function () {
  "use strict";

  var load = document.getElementById("shock-load");
  var result = document.getElementById("shock-result");
  var grid = document.getElementById("shock-grid");
  var ledger = document.getElementById("shock-ledger");
  var gaps = document.getElementById("shock-gaps");

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
  function hashLike(value) {
    return typeof value === "string" && /^[0-9a-f]{64}$/.test(value);
  }
  function close(left, right) { return Math.abs(left - right) < 0.000001; }
  function range(row, suffix) {
    return row.lower + "–" + row.upper + (suffix || "");
  }
  function shortHash(value) { return value.slice(0, 12) + "…"; }
  function label(document, id) { return document.synthetic_labels[id] || id; }
  function assumption(document, type) {
    return document.compilation.assumption_ledger.filter(function (row) {
      return row.assumption_type === type;
    })[0];
  }
  function requireContract(document) {
    if (!document || !document._meta ||
        document._meta.scope !== "synthetic_test_vector_only" ||
        document._meta.production_release !== false ||
        document._meta.real_entity_source_rights_exposure_or_disruption_claims !== false ||
        document._meta.forecast_probability_causation_advice_or_scalar_score !== false ||
        !document.scenario || !document.compilation || !document.synthetic_labels) {
      throw new Error("demo boundary mismatch");
    }
    var scenario = document.scenario;
    var compilation = document.compilation;
    var outputScenario = compilation.scenario;
    var output = compilation.result;
    var counts = compilation.counts;
    if (scenario.object_type !== "shock_scenario" || !hashLike(scenario.record_sha256) ||
        compilation.object_type !== "shock_compilation" || !hashLike(compilation.record_sha256) ||
        outputScenario.record_sha256 !== scenario.record_sha256 ||
        outputScenario.scenario_id !== scenario.scenario_id ||
        outputScenario.knowledge_cutoff !== scenario.knowledge_cutoff ||
        output.public_claim_state !== "requires_claim_bundle" ||
        output.forecast_performed !== false || output.probability_assigned !== false ||
        output.causal_attribution_performed !== false ||
        output.recommendation_generated !== false || output.scalar_score_computed !== false ||
        !Array.isArray(compilation.paths) || counts.structural_paths !== compilation.paths.length ||
        counts.bounded_paths + counts.abstained_paths !== counts.structural_paths ||
        counts.gaps !== compilation.gaps.length ||
        counts.assumptions !== compilation.assumption_ledger.length) {
      throw new Error("compilation contract mismatch");
    }
    if (compilation.paths.length !== 1 || counts.bounded_paths !== 1 || counts.gaps !== 0) {
      throw new Error("unexpected synthetic vector shape");
    }
    var path = compilation.paths[0];
    if (path.quantification_status !== "bounded_range" || path.hops.length !== 1 ||
        path.edge_ids.length !== 1 || path.entity_ids.length !== 2 ||
        path.hops[0].edge_id !== path.edge_ids[0] ||
        path.entry_entity_id !== scenario.shock_subject_entity_id ||
        path.entity_ids[1] !== scenario.target_entity_id ||
        path.sensitivity_grid.length !== 4 ||
        !path.gross_affected_share || !path.residual_affected_share ||
        !path.residual_duration) {
      throw new Error("path contract mismatch");
    }
    var hop = path.hops[0];
    var edgeRange = hop.magnitude.uncertainty;
    var shock = scenario.shock.magnitude;
    var substitution = scenario.substitutions[0].fraction_of_gross_effect;
    var duration = scenario.shock.duration;
    var buffer = scenario.buffers[0].duration_offset;
    if (edgeRange.status !== "interval" || hop.quantification_status !== "quantified" ||
        !close(path.gross_affected_share.lower, edgeRange.lower * shock.lower / 100) ||
        !close(path.gross_affected_share.upper, edgeRange.upper * shock.upper / 100) ||
        !close(path.residual_affected_share.lower,
          path.gross_affected_share.lower * (1 - substitution.upper / 100)) ||
        !close(path.residual_affected_share.upper,
          path.gross_affected_share.upper * (1 - substitution.lower / 100)) ||
        path.residual_duration.lower !== Math.max(0, duration.lower - buffer.upper) ||
        path.residual_duration.upper !== Math.max(0, duration.upper - buffer.lower) ||
        path.gross_affected_share.denominator !== hop.magnitude.denominator ||
        path.residual_affected_share.denominator !== hop.magnitude.denominator) {
      throw new Error("bounded arithmetic mismatch");
    }
    if (!assumption(document, "shock") || !assumption(document, "substitution") ||
        !assumption(document, "buffer") ||
        compilation.assumption_ledger.some(function (row) {
          return row.status !== "hypothetical" || row.origin !== "user_supplied" ||
            row.used_by_path_ids.length !== 1 || row.unused_reason !== null;
        })) {
      throw new Error("assumption ledger mismatch");
    }
  }
  function renderGrid(path) {
    grid.textContent = "";
    path.sensitivity_grid.forEach(function (cell) {
      var card = element("article", "shock-grid-cell");
      var head = element("div", "shock-grid-head");
      head.appendChild(element("strong", "", cell.shock_magnitude_percent + "%"));
      head.appendChild(element("span", "", cell.duration_days + " days"));
      card.appendChild(head);
      var values = element("dl", "");
      [
        ["Gross", range(cell.gross_affected_share, " pp")],
        ["Residual", range(cell.residual_affected_share, " pp")],
        ["Residual days", range(cell.residual_duration_days, "")]
      ].forEach(function (row) {
        var block = element("div", "");
        block.appendChild(element("dt", "", row[0]));
        block.appendChild(element("dd", "", row[1]));
        values.appendChild(block);
      });
      card.appendChild(values);
      grid.appendChild(card);
    });
  }
  function renderLedger(document, path) {
    ledger.textContent = "";
    document.compilation.assumption_ledger.forEach(function (row) {
      var item = element("li", "");
      var title = row.assumption_type.charAt(0).toUpperCase() + row.assumption_type.slice(1);
      item.appendChild(element("strong", "", title));
      item.appendChild(element("span", "", "Hypothetical · user supplied · used by " +
        row.used_by_path_ids.length + " path" + (row.used_by_path_ids.length === 1 ? "" : "s")));
      item.appendChild(element("code", "", row.assumption_id));
      ledger.appendChild(item);
    });
    gaps.textContent = "";
    if (document.compilation.gaps.length === 0) {
      var clear = element("li", "shock-gap-clear");
      clear.appendChild(element("strong", "", "No gap in this synthetic one-hop vector"));
      clear.appendChild(element("span", "", "Hostile tests separately prove stale, unsupported-unit, multi-hop, unused-assumption and no-path gaps."));
      gaps.appendChild(clear);
      return;
    }
    document.compilation.gaps.forEach(function (row) {
      var item = element("li", "");
      item.appendChild(element("strong", "", row.gap_code));
      item.appendChild(element("code", "", row.gap_id));
      gaps.appendChild(item);
    });
  }
  function render(document) {
    requireContract(document);
    var scenario = document.scenario;
    var compilation = document.compilation;
    var path = compilation.paths[0];
    var hop = path.hops[0];
    var shock = scenario.shock;
    var substitution = scenario.substitutions[0].fraction_of_gross_effect;
    var buffer = scenario.buffers[0].duration_offset;
    var coverage = hop.coverage.counts;
    text("[data-shock-scenario]", scenario.scenario_id);
    text("[data-shock-cutoff]", "Knowledge cutoff " + scenario.knowledge_cutoff);
    text("[data-shock-release]", compilation.release.release_id);
    text("[data-shock-hash]", shortHash(compilation.record_sha256));
    text("[data-shock-status]", compilation.result.status.replace(/_/g, " "));
    text("[data-shock-magnitude]", range(shock.magnitude, "%"));
    text("[data-shock-duration]", range(shock.duration, " days"));
    text("[data-shock-substitution]", range(substitution, "%"));
    text("[data-shock-buffer]", range(buffer, " days"));
    text("[data-shock-subject]", label(document, scenario.shock_subject_entity_id));
    text("[data-shock-target]", label(document, scenario.target_entity_id));
    text("[data-shock-edge]", label(document, hop.edge_id));
    text("[data-shock-edge-range]", range(hop.magnitude.uncertainty, " " + hop.magnitude.unit));
    text("[data-shock-denominator]", hop.magnitude.denominator);
    text("[data-shock-freshness]", hop.freshness.status + " · " +
      hop.freshness.observation_age_seconds + " seconds at release");
    text("[data-shock-coverage]", coverage.included + " included / " +
      coverage.total_eligible + " eligible · " + coverage.excluded + " excluded · " +
      coverage.unmappable + " unmappable");
    text("[data-shock-gross]", range(path.gross_affected_share, " pp"));
    text("[data-shock-residual]", range(path.residual_affected_share, " pp"));
    text("[data-shock-residual-days]", range(path.residual_duration, " days"));
    text("[data-shock-gross-equation]", path.gross_affected_share.equation);
    text("[data-shock-residual-equation]", path.residual_affected_share.equation);
    text("[data-shock-duration-equation]", path.residual_duration.equation);
    renderGrid(path);
    renderLedger(document, path);
    load.hidden = true;
    result.hidden = false;
  }

  fetch("data/shock_compiler_demo.json", {cache: "no-store"})
    .then(function (response) {
      if (!response.ok) throw new Error("HTTP " + response.status);
      return response.json();
    })
    .then(render)
    .catch(function () {
      load.textContent = "The synthetic compiler vector could not be verified. No scenario result is shown.";
      load.classList.add("error");
      result.hidden = true;
    });
}());
