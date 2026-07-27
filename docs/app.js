/* IGRM frontend. Reads only what the pipeline writes into docs/data/. */

const COLORS = {
  composite: "#12233D",
  wikipedia: "#8A93A6",
  pakistan_west: "#A2361F",
  china_east: "#B07C1F",
  gulf_energy: "#1E6E67",
  us_trade: "#4A5D8A",
  shipping: "#7A6A54",
};

const state = { history: null, range: 365, on: { composite: true } };
let chart = null;

function stateColor(score) {
  if (score >= 70) return getCSS("--severe");
  if (score >= 45) return getCSS("--elevated");
  return getCSS("--calm");
}
function getCSS(name) {
  return getComputedStyle(document.documentElement).getPropertyValue(name).trim();
}
function fmtDelta(d) {
  if (d == null) return '<span class="flat">&ndash;</span>';
  const cls = d > 0.05 ? "up" : d < -0.05 ? "down" : "flat";
  const arrow = d > 0.05 ? "▲" : d < -0.05 ? "▼" : "–";
  return `<span class="${cls}">${arrow} ${d >= 0 ? "+" : ""}${d.toFixed(1)}</span>`;
}
function esc(s) {
  return String(s).replace(/[&<>"']/g, (c) => ({
    "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;",
  }[c]));
}

async function loadJSON(path) {
  const r = await fetch(path, { cache: "no-store" });
  if (!r.ok) throw new Error(`${path}: ${r.status}`);
  return r.json();
}

/* Yesterday's move, computed from the history series (last two non-null). */
function delta1d(series) {
  if (!series) return null;
  const vals = [];
  for (let i = series.length - 1; i >= 0 && vals.length < 2; i--) {
    if (series[i] != null) vals.push(series[i]);
  }
  return vals.length === 2 ? vals[0] - vals[1] : null;
}

function renderLatest(latest, history) {
  const score = latest.composite;
  if (score == null) return;
  document.documentElement.style.setProperty("--state", stateColor(score));
  document.getElementById("latest-date").textContent = latest.date;
  document.getElementById("composite-score").textContent = score.toFixed(1);
  document.getElementById("composite-delta").innerHTML =
    `${fmtDelta(history ? delta1d(history.composite) : null)} <span class="flat">vs yesterday</span>`;
  document.getElementById("band-tick").style.left =
    `${Math.max(0, Math.min(100, score))}%`;

  const wrap = document.getElementById("components");
  wrap.innerHTML = "";
  for (const [key, c] of Object.entries(latest.channels || {})) {
    const d = history && history.channels ? delta1d(history.channels[key]) : null;
    const row = document.createElement("div");
    row.className = "component-row";
    row.innerHTML =
      `<span class="component-name">${esc(c.label)}</span>` +
      `<span class="component-score">${c.score == null ? "–" : esc(c.score.toFixed(1))}</span>` +
      `<span class="component-delta">${fmtDelta(d)}</span>`;
    wrap.appendChild(row);
  }
}

function sliceRange(arr, n) {
  return n === "all" ? arr : arr.slice(-n);
}

function renderChart() {
  const h = state.history;
  if (!h) return;
  const labels = sliceRange(h.dates, state.range);
  const datasets = [];
  const ink = getCSS("--ink");
  const stateCol = getCSS("--state");
  const canvas = document.getElementById("history-chart");
  const g = canvas.getContext("2d").createLinearGradient(0, 0, 0, canvas.clientHeight || 320);
  g.addColorStop(0, stateCol + "26");
  g.addColorStop(1, stateCol + "00");
  const addSeries = (key, data, label, dashed) => {
    if (!state.on[key] || !data) return;
    const isComposite = key === "composite";
    datasets.push({
      label,
      data: sliceRange(data, state.range),
      borderColor: isComposite ? ink : (COLORS[key] || "#888"),
      borderWidth: isComposite ? 2.2 : 1.2,
      borderDash: dashed ? [5, 4] : [],
      fill: isComposite,
      backgroundColor: isComposite ? g : "transparent",
      pointRadius: 0,
      tension: 0.2,
    });
  };
  addSeries("composite", h.composite, "Composite");
  for (const [key, data] of Object.entries(h.channels || {})) {
    addSeries(key, data, (h.labels && h.labels[key]) || key);
  }
  if (h.wikipedia) {
    // Demand-side second source: percentile of Wikipedia pageviews,
    // normalized independently; drawn dashed, aligned by its own dates.
    const wiki = new Map(h.wikipedia.dates.map((d, i) => [d, h.wikipedia.composite[i]]));
    addSeries("wikipedia", labels.map((d) => wiki.get(d) ?? null),
      "Composite · Wikipedia", true);
  }
  const ctx = document.getElementById("history-chart");
  if (chart) chart.destroy();
  chart = new Chart(ctx, {
    type: "line",
    data: { labels, datasets },
    options: {
      animation: false,
      responsive: true,
      interaction: { mode: "index", intersect: false },
      plugins: { legend: { display: false } },
      scales: {
        y: { min: 0, max: 100,
             grid: { color: getCSS("--rule-soft") },
             ticks: { color: getCSS("--muted") } },
        x: { ticks: { maxTicksLimit: 8, color: getCSS("--muted") },
             grid: { display: false } },
      },
    },
  });
}

/* Keep chart and state colors in sync with the OS theme. */
matchMedia("(prefers-color-scheme: dark)").addEventListener("change", () => {
  const score = parseFloat(document.getElementById("composite-score").textContent);
  if (!Number.isNaN(score)) {
    document.documentElement.style.setProperty("--state", stateColor(score));
  }
  renderChart();
});

function buildToggles(h) {
  const wrap = document.getElementById("series-toggles");
  const keys = ["composite", ...Object.keys(h.channels || {})];
  if (h.wikipedia) keys.push("wikipedia");
  for (const key of keys) {
    state.on[key] = key === "composite";
    const b = document.createElement("button");
    b.className = "toggle" + (state.on[key] ? " is-on" : "");
    b.textContent = key === "composite" ? "Composite"
      : key === "wikipedia" ? "Composite · Wikipedia"
      : (h.labels && h.labels[key]) || key;
    b.addEventListener("click", () => {
      state.on[key] = !state.on[key];
      b.classList.toggle("is-on", state.on[key]);
      renderChart();
    });
    wrap.appendChild(b);
  }
}

function bindRanges() {
  document.querySelectorAll(".range-btn").forEach((b) => {
    b.addEventListener("click", () => {
      document.querySelectorAll(".range-btn").forEach((x) =>
        x.classList.remove("is-active"));
      b.classList.add("is-active");
      const r = b.dataset.range;
      state.range = r === "all" ? "all" : parseInt(r, 10);
      renderChart();
    });
  });
}

/* Minimal markdown for the weekly note (headings, bold, lists, paras). */
function miniMarkdown(md) {
  const escd = md.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");
  const body = escd.replace(/^---[\s\S]*?---\s*/, "");
  return body
    .split(/\n{2,}/)
    .map((block) => {
      const b = block.trim();
      if (!b) return "";
      if (b.startsWith("## ")) return `<h3>${b.slice(3)}</h3>`;
      if (b.split("\n").every((l) => l.trim().startsWith("- "))) {
        const items = b.split("\n")
          .map((l) => `<li>${l.trim().slice(2)}</li>`).join("");
        return `<ul>${items}</ul>`;
      }
      return `<p>${b.replace(/\*\*(.+?)\*\*/g, "<strong>$1</strong>")
        .replace(/\n/g, "<br>")}</p>`;
    })
    .join("");
}

function renderEpisodes(episodes) {
  const tbody = document.querySelector("#episodes-table tbody");
  if (!episodes || !episodes.length) return;
  tbody.innerHTML = "";
  for (const e of episodes.slice().reverse().slice(0, 40)) {
    const href = `episode.html?channel=${encodeURIComponent(e.channel)}` +
      `&start=${encodeURIComponent(e.start)}`;
    const tr = document.createElement("tr");
    tr.innerHTML = `<td>${esc(e.start)}</td><td>${esc(e.end)}</td>` +
      `<td>${esc(e.label || e.channel)}</td>` +
      `<td>${Number(e.peak_value).toFixed(2)}</td>` +
      `<td>${esc(e.n_spike_days)}</td>` +
      `<td><a href="${href}">detail</a></td>`;
    tbody.appendChild(tr);
  }
}

function fmtCell(w) {
  if (!w) return "–";
  return `${w.mean.toFixed(2)} [${w.ci95[0].toFixed(2)}, ${w.ci95[1].toFixed(2)}]`;
}

function renderEventStudy(ev, history) {
  const tbody = document.querySelector("#evstudy-table tbody");
  if (!ev || !ev.channels || !Object.keys(ev.channels).length) return;
  tbody.innerHTML = "";
  const labels = (history && history.labels) || {};
  for (const [ch, data] of Object.entries(ev.channels)) {
    for (const [outcome, wins] of Object.entries(data.outcomes)) {
      const tag = (ev.descriptive_only || []).includes(outcome) ? " (descriptive)" : "";
      const tr = document.createElement("tr");
      tr.innerHTML = `<td>${esc(labels[ch] || ch)}</td><td>${esc(outcome + tag)}</td>` +
        `<td>${fmtCell(wins["1"])}</td><td>${fmtCell(wins["5"])}</td>` +
        `<td>${fmtCell(wins["20"])}</td><td>${esc(data.n_episodes)}</td>`;
      tbody.appendChild(tr);
    }
  }
}

async function init() {
  bindRanges();
  let history = null;
  try {
    history = await loadJSON("data/history.json");
    state.history = history;
  } catch (e) { console.warn("history.json not available yet", e); }
  try {
    const latest = await loadJSON("data/latest.json");
    renderLatest(latest, history);
    if (latest.definition) {
      document.getElementById("tagline").textContent =
        latest.definition + " Updated 18:00 IST.";
    }
  } catch (e) { console.warn("latest.json not available yet", e); }
  if (history) {
    buildToggles(history);
    renderChart();
  }
  try {
    const note = await loadJSON("data/note_latest.json");
    if (note.markdown) {
      document.getElementById("weekly-note").innerHTML = miniMarkdown(note.markdown);
    }
  } catch (e) { /* no note yet */ }
  try {
    const eps = await loadJSON("data/episodes.json");
    renderEpisodes(eps);
  } catch (e) { /* no episodes yet */ }
  try {
    const ev = await loadJSON("data/event_study.json");
    renderEventStudy(ev, history);
  } catch (e) { /* not computed yet */ }
}

init();
