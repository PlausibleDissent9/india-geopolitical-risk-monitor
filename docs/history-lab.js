/* History Lab renderer.
 *
 * Every value on screen is read from docs/data/historical_intelligence.json
 * and nothing is restated in the markup, so the page cannot drift from the
 * payload it describes. Where a value is unavailable the renderer prints the
 * REASON rather than an empty cell: a blank and a refusal look identical at a
 * glance, and only one of them is honest.
 *
 * The page is meaningful without this file. The markup ships static
 * eligibility copy, the construct warning, the limitations and links to the
 * JSON and both CSVs, so a reader with no JavaScript still gets the claims,
 * the refusals and the data.
 */
(function () {
  "use strict";

  var PAYLOAD = "data/historical_intelligence.json";

  function el(id) { return document.getElementById(id); }

  function text(node, value) {
    node.textContent = value === null || value === undefined ? "—" : String(value);
    return node;
  }

  function cell(row, value, cls) {
    var td = document.createElement("td");
    if (cls) { td.className = cls; }
    text(td, value);
    row.appendChild(td);
    return td;
  }

  /* An unavailable number prints as "unavailable" with its reason beneath,
   * never as a dash that could be mistaken for a zero or an oversight. */
  function unavailableCell(row, reason) {
    var td = document.createElement("td");
    td.className = "lab-unavailable";
    td.textContent = "unavailable";
    if (reason) {
      var why = document.createElement("span");
      why.className = "lab-reason";
      why.textContent = reason;
      td.appendChild(why);
    }
    row.appendChild(td);
    return td;
  }

  function fail(message) {
    var targets = ["baselines-body", "breaks-body", "archetypes-body", "analog-result"];
    targets.forEach(function (id) {
      var node = el(id);
      if (!node) { return; }
      node.innerHTML = "";
      var p = document.createElement("p");
      p.className = "lab-nojs";
      p.textContent = message;
      if (node.tagName === "TBODY") {
        var tr = document.createElement("tr");
        var td = document.createElement("td");
        td.colSpan = 9;
        td.appendChild(p);
        tr.appendChild(td);
        node.appendChild(tr);
      } else {
        node.appendChild(p);
      }
    });
  }

  function renderBaselines(rows) {
    var body = el("baselines-body");
    if (!body) { return; }
    body.innerHTML = "";
    rows.forEach(function (r) {
      var tr = document.createElement("tr");
      cell(tr, r.channel);
      cell(tr, r.series);
      cell(tr, r.period_label);
      cell(tr, r.n_months_in_period, "num");
      cell(tr, r.n_observed, "num");
      cell(tr, r.coverage_fraction === null ? null
        : (r.coverage_fraction * 100).toFixed(1) + "%", "num");
      if (r.available) {
        cell(tr, r.mean, "num");
        cell(tr, r.median, "num");
        cell(tr, r.p90, "num");
      } else {
        unavailableCell(tr, r.unavailable_reason);
        cell(tr, null, "num");
        cell(tr, null, "num");
      }
      body.appendChild(tr);
    });
  }

  function renderBreaks(rows) {
    var host = el("breaks-body");
    if (!host) { return; }
    host.innerHTML = "";
    rows.forEach(function (r) {
      var wrap = document.createElement("div");
      wrap.className = "lab-break";

      var h = document.createElement("h3");
      h.textContent = r.channel + " · " + r.series;
      wrap.appendChild(h);

      var p = document.createElement("p");
      p.className = "prose";
      var primary = r.primary || {};
      if (primary.available) {
        p.textContent = "Candidate break " + primary.candidate_break_month
          + " (statistic " + primary.statistic + ", p = " + primary.p_value
          + " from " + primary.n_permutations + " permutations, minimum segment "
          + primary.min_segment_months + " months).";
      } else {
        p.textContent = "No candidate reported: "
          + (primary.unavailable_reason || "unavailable");
      }
      wrap.appendChild(p);

      var stability = document.createElement("p");
      stability.className = "prose lab-emphasis";
      if (r.stable_across_all_settings) {
        stability.textContent = "Stable: every tested minimum segment length "
          + "returns the same candidate month.";
      } else {
        stability.textContent = "Not stable: the candidate moves with the "
          + "setting, returning " + r.distinct_candidates_across_settings.join(" and ")
          + " across the tested minimum segment lengths. Read it as a scan "
          + "result, not a date.";
      }
      wrap.appendChild(stability);

      var table = document.createElement("table");
      table.className = "lab-table";
      var cap = document.createElement("caption");
      cap.className = "sr-only";
      cap.textContent = "Sensitivity sweep for " + r.channel;
      table.appendChild(cap);
      table.innerHTML += "<thead><tr>"
        + "<th scope=\"col\" class=\"num\">Min segment</th>"
        + "<th scope=\"col\">Candidate</th>"
        + "<th scope=\"col\" class=\"num\">Statistic</th>"
        + "<th scope=\"col\" class=\"num\">p</th></tr></thead>";
      var tb = document.createElement("tbody");
      r.sensitivity_sweep.forEach(function (s) {
        var tr = document.createElement("tr");
        cell(tr, s.min_segment_months, "num");
        if (s.available) {
          cell(tr, s.candidate_break_month);
          cell(tr, s.statistic, "num");
          cell(tr, s.p_value, "num");
        } else {
          unavailableCell(tr, s.unavailable_reason);
          cell(tr, null, "num");
          cell(tr, null, "num");
        }
        tb.appendChild(tr);
      });
      table.appendChild(tb);

      var wrapT = document.createElement("div");
      wrapT.className = "tblwrap";
      wrapT.appendChild(table);
      wrap.appendChild(wrapT);

      var note = document.createElement("p");
      note.className = "prose role-note";
      note.textContent = r.interpretation;
      wrap.appendChild(note);

      host.appendChild(wrap);
    });
  }

  function renderArchetypes(rows) {
    var body = el("archetypes-body");
    if (!body) { return; }
    body.innerHTML = "";
    rows.forEach(function (a) {
      var tr = document.createElement("tr");
      cell(tr, a.month);
      cell(tr, a.channel);
      cell(tr, a.archetype);
      if (a.available) {
        cell(tr, "yes");
      } else {
        unavailableCell(tr, a.unavailable_reason);
      }
      body.appendChild(tr);
    });
  }

  function renderAnalogs(payload, channel, month) {
    var host = el("analog-result");
    if (!host) { return; }
    host.innerHTML = "";
    var byChannel = payload.analog_retrieval.by_channel[channel] || {};
    var entry = byChannel[month];

    if (!entry) {
      var none = document.createElement("p");
      none.className = "lab-nojs";
      none.textContent = "No entry for " + channel + " " + month + ".";
      host.appendChild(none);
      return;
    }

    var head = document.createElement("p");
    head.className = "lab-result-head";
    if (!entry.available) {
      head.innerHTML = "";
      head.textContent = "No analogs for " + month + ": " + entry.unavailable_reason
        + ". Nothing is substituted for the missing features.";
      host.appendChild(head);
      return;
    }
    head.textContent = "Nearest months to " + month + " in " + channel
      + ", by standardised distance over the registered features present for "
      + "each pair.";
    host.appendChild(head);

    var table = document.createElement("table");
    table.className = "lab-table";
    var cap = document.createElement("caption");
    cap.className = "sr-only";
    cap.textContent = "Nearest analog months for " + channel + " " + month;
    table.appendChild(cap);
    table.innerHTML += "<thead><tr>"
      + "<th scope=\"col\" class=\"num\">Rank</th>"
      + "<th scope=\"col\">Month</th>"
      + "<th scope=\"col\" class=\"num\">Distance</th>"
      + "<th scope=\"col\" class=\"num\">Features used</th>"
      + "<th scope=\"col\">Which</th>"
      + "<th scope=\"col\">Excluded as null</th></tr></thead>";
    var tb = document.createElement("tbody");
    entry.analogs.forEach(function (a, i) {
      var tr = document.createElement("tr");
      cell(tr, i + 1, "num");
      cell(tr, a.month);
      cell(tr, a.distance, "num");
      cell(tr, a.n_features_used, "num");
      cell(tr, a.features_used.join(", "));
      cell(tr, a.features_excluded_as_null.length
        ? a.features_excluded_as_null.join(", ")
        : "none");
      tb.appendChild(tr);
    });
    table.appendChild(tb);
    var wrapT = document.createElement("div");
    wrapT.className = "tblwrap";
    wrapT.appendChild(table);
    host.appendChild(wrapT);

    var why = document.createElement("p");
    why.className = "prose role-note";
    why.textContent = payload.analog_retrieval.reason_template;
    host.appendChild(why);
  }

  function populate(payload) {
    var channelSel = el("analog-channel");
    var monthSel = el("analog-month");
    if (!channelSel || !monthSel) { return; }

    var channels = Object.keys(payload.analog_retrieval.by_channel).sort();
    channels.forEach(function (c) {
      var o = document.createElement("option");
      o.value = c;
      o.textContent = c;
      channelSel.appendChild(o);
    });

    function fillMonths() {
      monthSel.innerHTML = "";
      var months = Object.keys(
        payload.analog_retrieval.by_channel[channelSel.value] || {}).sort();
      months.forEach(function (m) {
        var o = document.createElement("option");
        o.value = m;
        o.textContent = m;
        monthSel.appendChild(o);
      });
      // Default to a month with a registered human-authored archetype, so the
      // first thing a reader sees is a month someone deliberately annotated
      // rather than an arbitrary one.
      var anchored = (payload.event_archetypes.rows || []).filter(function (a) {
        return a.channel === channelSel.value && a.available;
      });
      if (anchored.length && months.indexOf(anchored[0].month) !== -1) {
        monthSel.value = anchored[0].month;
      }
    }

    function update() {
      renderAnalogs(payload, channelSel.value, monthSel.value);
    }

    channelSel.addEventListener("change", function () {
      fillMonths();
      update();
    });
    monthSel.addEventListener("change", update);

    fillMonths();
    update();
  }

  function renderProvenance(meta) {
    var map = {
      "prov-contract": meta.contract_sha256,
      "prov-source": meta.source_sha256,
      "prov-impl": meta.implementation_sha256
    };
    Object.keys(map).forEach(function (id) {
      var node = el(id);
      if (node) { text(node, map[id]); }
    });
    var cutoff = el("cutoff");
    if (cutoff && meta.knowledge_cutoff) {
      text(cutoff, meta.knowledge_cutoff.archive_end);
    }
  }

  fetch(PAYLOAD, { credentials: "same-origin" })
    .then(function (r) {
      if (!r.ok) { throw new Error("HTTP " + r.status); }
      return r.json();
    })
    .then(function (payload) {
      // A partial payload must fail loudly rather than render half a page
      // that looks complete.
      ["regime_baselines", "structural_breaks", "analog_retrieval",
        "event_archetypes", "_meta"].forEach(function (key) {
          if (!payload || !payload[key]) {
            throw new Error("payload is missing " + key);
          }
        });
      renderProvenance(payload._meta);
      renderBaselines(payload.regime_baselines.rows);
      renderBreaks(payload.structural_breaks.rows);
      renderArchetypes(payload.event_archetypes.rows);
      populate(payload);
    })
    .catch(function (err) {
      fail("The published payload could not be loaded (" + err.message
        + "). Nothing is shown rather than a partial view: use "
        + "data/historical_intelligence.json or the CSV downloads directly.");
    });
})();
