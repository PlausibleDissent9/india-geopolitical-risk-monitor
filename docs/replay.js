(function () {
  "use strict";

  var payload = null;
  var buttons = Array.prototype.slice.call(document.querySelectorAll("[data-replay-mode]"));
  var load = document.getElementById("replay-load");
  var result = document.getElementById("replay-result");

  function text(selector, value) {
    var node = document.querySelector(selector);
    if (node) node.textContent = value;
  }

  function list(values) {
    return values.length ? values.join(", ") : "None";
  }

  function render(mode) {
    if (!payload) return;
    var replay = mode === "after"
      ? payload.after_correction_receipt
      : payload.before_correction_receipt;
    var record = replay.records[0];
    buttons.forEach(function (button) {
      var selected = button.getAttribute("data-replay-mode") === mode;
      button.classList.toggle("on", selected);
      button.setAttribute("aria-pressed", selected ? "true" : "false");
    });
    text("[data-replay-valid]", replay.query.valid_on);
    text("[data-replay-cutoff]", replay.query.knowledge_cutoff);
    text("[data-replay-release]", replay.selected_release.release_id);
    text("[data-replay-receipt]", replay.selected_release.available_at);
    text("[data-replay-revision]", "Revision " + record.lifecycle_revision);
    text("[data-replay-object]", record.object_id);
    text("[data-replay-status]", record.record_status);
    text("[data-replay-added]", list(replay.changes.added_ids));
    text("[data-replay-removed]", list(replay.changes.removed_ids));
    text("[data-replay-changed]", list(replay.changes.same_id_changed_ids));
    load.hidden = true;
    result.hidden = false;
  }

  buttons.forEach(function (button) {
    button.addEventListener("click", function () {
      render(button.getAttribute("data-replay-mode"));
    });
  });

  fetch("data/knowledge_replay_demo.json")
    .then(function (response) {
      if (!response.ok) throw new Error("HTTP " + response.status);
      return response.json();
    })
    .then(function (document) {
      if (document.demo_class !== "synthetic_test_vector_only" ||
          document.assertions.production_release !== false) {
        throw new Error("demo boundary mismatch");
      }
      payload = document;
      render("before");
    })
    .catch(function () {
      load.textContent = "The replay demonstration refused to render because its payload was unavailable or invalid.";
    });
}());
