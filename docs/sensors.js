(function () {
  "use strict";

  var expectedLanes = [
    "official",
    "news",
    "coded_event",
    "physical_transmission",
    "trade_transmission",
    "energy_transmission",
    "market_transmission",
    "public_attention"
  ];
  var payload = null;
  var buttons = Array.prototype.slice.call(document.querySelectorAll("[data-sensor-mode]"));
  var load = document.getElementById("sensor-load");
  var result = document.getElementById("sensor-result");
  var laneRoot = document.getElementById("sensor-lanes");

  function text(selector, value) {
    var node = document.querySelector(selector);
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

  function validateMatrix(matrix) {
    if (!matrix || matrix.object_type !== "sensor_fusion" ||
        !matrix.query || matrix.query.join_policy !== "collate_only_never_average_or_convert" ||
        !matrix.result || matrix.result.numeric_fusion_performed !== false ||
        !matrix.counts || matrix.counts.registered_lanes !== 8 ||
        !Array.isArray(matrix.lanes) || matrix.lanes.length !== 8 ||
        !sameArray(matrix.lanes.map(function (lane) { return lane.lane_id; }), expectedLanes)) {
      throw new Error("matrix contract mismatch");
    }
    var present = matrix.lanes.filter(function (lane) { return lane.state === "present"; });
    var absent = matrix.lanes.filter(function (lane) { return lane.state === "absent"; });
    if (present.length + absent.length !== 8 ||
        matrix.counts.present_lanes !== present.length ||
        matrix.counts.absent_lanes !== absent.length ||
        matrix.coverage.fraction !== present.length / 8 ||
        !sameArray(matrix.coverage.observed_lane_ids, present.map(function (lane) { return lane.lane_id; })) ||
        !sameArray(matrix.coverage.missing_lane_ids, absent.map(function (lane) { return lane.lane_id; }))) {
      throw new Error("matrix coverage mismatch");
    }
    matrix.lanes.forEach(function (lane) {
      if (!Array.isArray(lane.observations) || lane.observation_count !== lane.observations.length ||
          lane.state !== (lane.observations.length ? "present" : "absent")) {
        throw new Error("lane contract mismatch");
      }
    });
  }

  function renderLane(lane, index) {
    var card = element("article", "sensor-lane " + lane.state);
    var head = element("div", "sensor-lane-head");
    head.appendChild(element("span", "sensor-lane-index", String(index + 1).padStart(2, "0")));
    var title = element("div", "sensor-lane-title");
    title.appendChild(element("h3", "", lane.label));
    title.appendChild(element("span", "sensor-lane-state", lane.state === "present" ? "Present" : "Absent"));
    head.appendChild(title);
    card.appendChild(head);
    card.appendChild(element("p", "sensor-lane-definition", lane.semantic_definition));
    if (lane.state === "present") {
      var observation = lane.observations[0];
      var facts = element("dl", "sensor-lane-facts");
      [
        ["Source role", observation.source_role],
        ["Evidence type", observation.evidence_type],
        ["Observed", observation.observed_at],
        ["Verification", observation.verification_status]
      ].forEach(function (pair) {
        var row = element("div", "");
        row.appendChild(element("dt", "", pair[0]));
        row.appendChild(element("dd", "", pair[1]));
        facts.appendChild(row);
      });
      card.appendChild(facts);
    } else {
      card.appendChild(element("p", "sensor-lane-empty", "No eligible event link in this signed release window."));
    }
    return card;
  }

  function render(mode) {
    if (!payload) return;
    var matrix = mode === "narrow" ? payload.narrow_window_matrix : payload.complete_matrix;
    validateMatrix(matrix);
    buttons.forEach(function (button) {
      var selected = button.getAttribute("data-sensor-mode") === mode;
      button.classList.toggle("on", selected);
      button.setAttribute("aria-pressed", selected ? "true" : "false");
    });
    laneRoot.replaceChildren();
    matrix.lanes.forEach(function (lane, index) {
      laneRoot.appendChild(renderLane(lane, index));
    });
    var present = matrix.counts.present_lanes;
    text("[data-sensor-coverage]", present + "/8 registered lanes present");
    text("[data-sensor-window]", matrix.query.window_start + " — " + matrix.query.window_end);
    text("[data-sensor-boundary]", present === 8
      ? "Matrix complete means lane coverage only—not event truth or sensor agreement."
      : (8 - present) + " lanes are explicitly absent; the engine does not backfill them.");
    text("[data-sensor-release]", matrix.release.release_id);
    text("[data-sensor-cutoff]", matrix.query.knowledge_cutoff);
    text("[data-sensor-eligible]", String(matrix.counts.eligible_observations));
    text("[data-sensor-excluded]", String(matrix.counts.excluded_observations));
    var fill = document.querySelector("[data-sensor-fill]");
    if (fill) fill.style.width = (matrix.coverage.fraction * 100) + "%";
    load.hidden = true;
    result.hidden = false;
  }

  buttons.forEach(function (button) {
    button.addEventListener("click", function () {
      try {
        render(button.getAttribute("data-sensor-mode"));
      } catch (error) {
        result.hidden = true;
        load.hidden = false;
        load.textContent = "The matrix refused to render because its contract was invalid.";
      }
    });
  });

  fetch("data/sensor_fusion_demo.json")
    .then(function (response) {
      if (!response.ok) throw new Error("HTTP " + response.status);
      return response.json();
    })
    .then(function (document) {
      if (!document._meta || document._meta.scope !== "synthetic_test_vector_only" ||
          document._meta.production_release !== false ||
          document._meta.real_source_or_rights_claims !== false ||
          document._meta.numeric_fusion_performed !== false) {
        throw new Error("demo boundary mismatch");
      }
      validateMatrix(document.complete_matrix);
      validateMatrix(document.narrow_window_matrix);
      payload = document;
      render("complete");
    })
    .catch(function () {
      result.hidden = true;
      load.hidden = false;
      load.textContent = "The matrix refused to render because its payload was unavailable or invalid.";
    });
}());
