(function (root) {
  "use strict";

  const COLUMNS = [
    "date", "pakistan_west", "china_east", "gulf_energy",
    "us_trade", "shipping", "composite",
  ];
  const MEASURES = COLUMNS.slice(1);
  const LABELS = {
    pakistan_west: "Pakistan / western border",
    china_east: "China / eastern border",
    gulf_energy: "Gulf & energy",
    us_trade: "US & trade policy",
    shipping: "Shipping & chokepoints",
    composite: "Composite",
  };
  const COLORS = {
    pakistan_west: "#d65f5f",
    china_east: "#d69a45",
    gulf_energy: "#9e7bd8",
    us_trade: "#4b9bd7",
    shipping: "#36a887",
    composite: "var(--ink)",
  };
  const ISO_DAY = /^\d{4}-\d{2}-\d{2}$/;

  function parseHistory(text) {
    if (typeof text !== "string" || !text.trim()) {
      throw new Error("source_empty");
    }
    const lines = text.trim().split(/\r?\n/);
    const header = lines.shift().split(",");
    if (header.length !== COLUMNS.length ||
        !header.every((value, index) => value === COLUMNS[index])) {
      throw new Error("source_header_mismatch");
    }
    const rows = [];
    let previous = "";
    for (let index = 0; index < lines.length; index += 1) {
      const cells = lines[index].split(",");
      if (cells.length !== COLUMNS.length) {
        throw new Error("source_row_width_mismatch:" + (index + 2));
      }
      const day = cells[0];
      if (!ISO_DAY.test(day) || Number.isNaN(Date.parse(day + "T00:00:00Z"))) {
        throw new Error("source_date_invalid:" + (index + 2));
      }
      if (previous && day <= previous) {
        throw new Error("source_dates_not_strictly_ascending:" + (index + 2));
      }
      previous = day;
      const row = { date: day };
      MEASURES.forEach((measure, offset) => {
        const raw = cells[offset + 1];
        if (raw === "") {
          row[measure] = null;
          return;
        }
        const value = Number(raw);
        if (!Number.isFinite(value) || value < 0 || value > 100) {
          throw new Error("source_value_out_of_range:" + (index + 2) + ":" + measure);
        }
        row[measure] = value;
      });
      rows.push(row);
    }
    if (!rows.length) {
      throw new Error("source_has_no_rows");
    }
    return rows;
  }

  function validateQuery(rows, measures, from, through) {
    if (!Array.isArray(measures) || !measures.length ||
        measures.some((measure) => !MEASURES.includes(measure))) {
      throw new Error("query_measures_invalid");
    }
    if (!ISO_DAY.test(from) || !ISO_DAY.test(through) || from > through) {
      throw new Error("query_date_range_invalid");
    }
    if (from < rows[0].date || through > rows[rows.length - 1].date) {
      throw new Error("query_outside_published_range");
    }
  }

  function selectRows(rows, measures, from, through) {
    validateQuery(rows, measures, from, through);
    return rows
      .filter((row) => row.date >= from && row.date <= through)
      .map((row) => {
        const selected = { date: row.date };
        measures.forEach((measure) => { selected[measure] = row[measure]; });
        return selected;
      });
  }

  function rowsToCSV(rows, measures) {
    const header = ["date"].concat(measures);
    const body = rows.map((row) => header.map((column) => {
      const value = row[column];
      return value === null ? "" : String(value);
    }).join(","));
    return [header.join(",")].concat(body).join("\n") + "\n";
  }

  function summary(rows, measures) {
    const out = {};
    measures.forEach((measure) => {
      const values = rows.map((row) => row[measure]).filter((value) => value !== null);
      out[measure] = {
        n: values.length,
        missing: rows.length - values.length,
        mean: values.length ? values.reduce((sum, value) => sum + value, 0) / values.length : null,
        minimum: values.length ? Math.min.apply(null, values) : null,
        maximum: values.length ? Math.max.apply(null, values) : null,
      };
    });
    return out;
  }

  root.IGRM_WORKBENCH_CORE = {
    COLUMNS, MEASURES, LABELS, parseHistory, selectRows, rowsToCSV, summary,
  };
  if (typeof document === "undefined") { return; }

  const $ = (id) => document.getElementById(id);
  const SOURCE_URL = "https://igrm.in/data/history.csv";
  let sourceRows = [];
  let sourceText = "";
  let sourceHash = "";
  let current = null;

  function fail(error) {
    const box = $("workbench-error");
    box.hidden = false;
    box.textContent = "The workbench refused to continue (" + error.message + "). " +
      "No subset was produced because the published source did not pass its checks.";
    if (sourceRows.length) {
      $("result-state").textContent = "REFUSED · " + error.message;
    } else {
      $("source-state").textContent = "REFUSED";
    }
  }

  async function sha256Bytes(bytes) {
    const digest = await crypto.subtle.digest("SHA-256", bytes);
    return Array.from(new Uint8Array(digest), (byte) => byte.toString(16).padStart(2, "0")).join("");
  }

  async function sha256Hex(text) {
    return sha256Bytes(new TextEncoder().encode(text));
  }

  function esc(value) {
    return String(value).replace(/[&<>"']/g, (character) => ({
      "&": "&amp;", "<": "&lt;", ">": "&gt;", "\"": "&quot;", "'": "&#39;",
    }[character]));
  }

  function queryMeasures() {
    return Array.from(document.querySelectorAll("#channel-fields input:checked"))
      .map((input) => input.value);
  }

  function setQuery(measures, from, through) {
    const params = new URLSearchParams();
    params.set("ch", measures.join(","));
    params.set("from", from);
    params.set("to", through);
    history.replaceState(null, "", "workbench.html?" + params.toString());
  }

  function download(name, body, type) {
    const url = URL.createObjectURL(new Blob([body], { type }));
    const link = document.createElement("a");
    link.href = url;
    link.download = name;
    document.body.appendChild(link);
    link.click();
    link.remove();
    setTimeout(() => URL.revokeObjectURL(url), 0);
  }

  function buildChart(rows, measures) {
    const svg = $("workbench-chart");
    const width = 960, height = 300, left = 42, right = 12, top = 14, bottom = 34;
    const plotWidth = width - left - right, plotHeight = height - top - bottom;
    let html = "";
    [0, 25, 50, 75, 100].forEach((value) => {
      const y = top + plotHeight - (value / 100) * plotHeight;
      html += '<line x1="' + left + '" y1="' + y + '" x2="' + (width - right) +
        '" y2="' + y + '" class="wb-gridline" />';
      html += '<text x="' + (left - 8) + '" y="' + (y + 4) +
        '" text-anchor="end" class="wb-axis">' + value + "</text>";
    });
    measures.forEach((measure) => {
      let segment = [];
      const segments = [];
      rows.forEach((row, index) => {
        if (row[measure] === null) {
          if (segment.length) { segments.push(segment); segment = []; }
          return;
        }
        const x = left + (rows.length === 1 ? plotWidth / 2 : index / (rows.length - 1) * plotWidth);
        const y = top + plotHeight - row[measure] / 100 * plotHeight;
        segment.push(x.toFixed(2) + "," + y.toFixed(2));
      });
      if (segment.length) { segments.push(segment); }
      segments.forEach((points) => {
        html += '<polyline points="' + points.join(" ") + '" fill="none" stroke="' +
          COLORS[measure] + '" stroke-width="2" vector-effect="non-scaling-stroke" />';
      });
    });
    html += '<text x="' + left + '" y="' + (height - 8) + '" class="wb-axis">' +
      esc(rows[0].date) + "</text>";
    html += '<text x="' + (width - right) + '" y="' + (height - 8) +
      '" text-anchor="end" class="wb-axis">' + esc(rows[rows.length - 1].date) + "</text>";
    svg.innerHTML = html;
    svg.setAttribute("aria-label", "Daily press-salience percentiles from " + rows[0].date +
      " through " + rows[rows.length - 1].date + " for " + measures.map((m) => LABELS[m]).join(", "));
  }

  function renderPreview(rows, measures) {
    const shown = rows.length <= 20 ? rows : rows.slice(0, 10).concat(rows.slice(-10));
    const columns = ["date"].concat(measures);
    $("workbench-preview").querySelector("thead").innerHTML = "<tr>" +
      columns.map((column) => "<th>" + esc(column === "date" ? "Date" : LABELS[column]) + "</th>").join("") + "</tr>";
    $("workbench-preview").querySelector("tbody").innerHTML = shown.map((row) => "<tr>" +
      columns.map((column) => '<td class="' + (column === "date" ? "" : "num") + '">' +
        esc(row[column] === null ? "—" : row[column]) + "</td>").join("") + "</tr>").join("");
    $("preview-note").textContent = rows.length <= 20
      ? "All " + rows.length + " selected rows shown."
      : "Preview shows the first and last 10 of " + rows.length + " selected rows; downloads contain every row.";
  }

  async function build() {
    $("workbench-error").hidden = true;
    current = null;
    $("workbench-result").hidden = true;
    $("export-section").hidden = true;
    const measures = queryMeasures();
    const from = $("date-from").value;
    const through = $("date-to").value;
    const rows = selectRows(sourceRows, measures, from, through);
    if (!rows.length) { throw new Error("query_returns_no_rows"); }
    const csv = rowsToCSV(rows, measures);
    const resultHash = await sha256Hex(csv);
    const stats = summary(rows, measures);
    const accessed = new Date().toISOString().slice(0, 10);
    const citation = "Krishna, Ishan (2026). India Geopolitical Risk Monitor research subset, " +
      from + " through " + through + " (" + measures.map((m) => LABELS[m]).join("; ") +
      "). Source SHA-256 " + sourceHash + "; subset SHA-256 " + resultHash +
      "; accessed " + accessed + ". https://igrm.in/workbench.html (CC BY 4.0).";
    const manifest = {
      schema_version: "1.0.0",
      object_type: "igrm_research_subset_manifest",
      created_at: new Date().toISOString(),
      source: {
        url: SOURCE_URL,
        sha256: sourceHash,
        media_type: "text/csv",
        first_date: sourceRows[0].date,
        last_date: sourceRows[sourceRows.length - 1].date,
        n_rows: sourceRows.length,
        columns: COLUMNS,
        archive_note: "Save the source snapshot with this manifest or recover the matching public Git vintage; a hash identifies bytes but does not guarantee future URL availability.",
      },
      query: { from, through, measures },
      result: {
        sha256: resultHash,
        media_type: "text/csv",
        n_rows: rows.length,
        columns: ["date"].concat(measures),
        summary: stats,
      },
      construct: "Each value is a channel-specific percentile of press salience against that channel's own trailing 730-day history; composite is the published unweighted channel mean.",
      forbidden_interpretations: ["event probability", "severity", "economic loss", "forecast", "investment advice"],
      license: "CC BY 4.0",
      citation,
      codebook: "https://igrm.in/codebook.html",
    };
    current = { rows, measures, from, through, csv, resultHash, citation, manifest };
    setQuery(measures, from, through);
    $("workbench-empty").hidden = true;
    $("workbench-result").hidden = false;
    $("export-section").hidden = false;
    $("result-state").textContent = rows.length + " rows · SHA-256 " + resultHash.slice(0, 12) + "…";
    $("workbench-metrics").innerHTML = [
      ["Rows", rows.length.toLocaleString()],
      ["Measures", measures.length],
      ["First day", rows[0].date],
      ["Last day", rows[rows.length - 1].date],
    ].map((item) => '<div><span class="wb-eyebrow">' + esc(item[0]) + "</span><strong>" + esc(item[1]) + "</strong></div>").join("");
    $("chart-note").innerHTML = measures.map((measure) => '<span class="wb-legend"><i style="background:' +
      COLORS[measure] + '"></i>' + esc(LABELS[measure]) + "</span>").join("");
    $("citation-text").textContent = citation;
    buildChart(rows, measures);
    renderPreview(rows, measures);
  }

  function fileStem() {
    return "igrm_" + current.from + "_to_" + current.through + "_" + current.measures.join("-");
  }

  $("workbench-form").addEventListener("submit", (event) => {
    event.preventDefault();
    build().catch(fail);
  });
  $("last-year").addEventListener("click", () => {
    const through = sourceRows[sourceRows.length - 1].date;
    const date = new Date(through + "T00:00:00Z");
    date.setUTCDate(date.getUTCDate() - 364);
    $("date-from").value = date.toISOString().slice(0, 10) < sourceRows[0].date
      ? sourceRows[0].date : date.toISOString().slice(0, 10);
    $("date-to").value = through;
  });
  $("full-range").addEventListener("click", () => {
    $("date-from").value = sourceRows[0].date;
    $("date-to").value = sourceRows[sourceRows.length - 1].date;
  });
  $("download-csv").addEventListener("click", () => download(fileStem() + ".csv", current.csv, "text/csv;charset=utf-8"));
  $("download-json").addEventListener("click", () => download(fileStem() + ".json", JSON.stringify({
    _meta: current.manifest,
    data: current.rows,
  }, null, 2) + "\n", "application/json"));
  $("download-manifest").addEventListener("click", () => download(fileStem() + ".manifest.json",
    JSON.stringify(current.manifest, null, 2) + "\n", "application/json"));
  $("copy-citation").addEventListener("click", async () => {
    try {
      await navigator.clipboard.writeText(current.citation);
      $("copy-citation").textContent = "Copied";
      setTimeout(() => { $("copy-citation").textContent = "Copy citation"; }, 1500);
    } catch (_) {
      $("copy-citation").textContent = "Copy unavailable — select citation";
    }
  });

  async function boot() {
    const response = await fetch("data/history.csv", { cache: "no-store" });
    if (!response.ok) { throw new Error("source_fetch_failed:" + response.status); }
    const rawBytes = await response.arrayBuffer();
    sourceHash = await sha256Bytes(rawBytes);
    sourceText = new TextDecoder("utf-8", { fatal: true }).decode(rawBytes);
    sourceRows = parseHistory(sourceText);
    $("source-state").textContent = sourceRows.length.toLocaleString() + " rows verified · " +
      sourceRows[0].date + " to " + sourceRows[sourceRows.length - 1].date;
    $("source-hash").textContent = sourceHash;
    $("source-download").setAttribute("download", "igrm_history_" + sourceRows[sourceRows.length - 1].date + "_sha256-" + sourceHash.slice(0, 12) + ".csv");
    $("channel-fields").innerHTML = MEASURES.map((measure) => '<label class="wb-check"><input type="checkbox" value="' +
      measure + '"><span>' + esc(LABELS[measure]) + "</span></label>").join("");
    const params = new URLSearchParams(location.search);
    const requested = (params.get("ch") || "composite").split(",").filter((measure) => MEASURES.includes(measure));
    const measures = requested.length ? requested : ["composite"];
    document.querySelectorAll("#channel-fields input").forEach((input) => {
      input.checked = measures.includes(input.value);
    });
    const last = sourceRows[sourceRows.length - 1].date;
    const fallback = new Date(last + "T00:00:00Z");
    fallback.setUTCDate(fallback.getUTCDate() - 364);
    const fallbackDay = fallback.toISOString().slice(0, 10);
    const from = params.get("from") || (fallbackDay < sourceRows[0].date
      ? sourceRows[0].date : fallbackDay);
    const through = params.get("to") || last;
    $("date-from").min = sourceRows[0].date;
    $("date-from").max = last;
    $("date-to").min = sourceRows[0].date;
    $("date-to").max = last;
    $("date-from").value = from;
    $("date-to").value = through;
    await build();
  }

  boot().catch(fail);
}(typeof window === "undefined" ? globalThis : window));
