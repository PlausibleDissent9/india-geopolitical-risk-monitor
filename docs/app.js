/* IGRM frontend. Reads only what the pipeline writes into docs/data/. */

/* Series colours come from tokens.css, not from here.
 *
 * These were seven hardcoded hexes, and they were a third copy of the
 * palette after style.css and site.css -- the same duplication that
 * greyed every chart on the analysis page in July, waiting to happen
 * again. They also never changed with the theme: #12233D is the LIGHT
 * theme's ink, so the composite line was drawn in near-black on a
 * near-black ground in the default dark theme.
 *
 * And they were chosen for hue alone (#FF6B6B, #FFC94B, #31D9C2,
 * #6FA8FF, #C39BFF): five saturated pastels at almost identical
 * lightness, which merge into one grey ramp for a reader with a colour
 * vision deficiency, and in any greyscale print. The tokens separate
 * in luminance as well as hue, and a test enforces the gap.
 *
 * Read lazily, per call: the theme toggle rewrites the custom
 * properties at runtime, so a value captured once at load would be
 * stale the moment anyone switches.
 */
function seriesColor(key) {
  const token = {
    composite: "--ink",
    wikipedia: "--muted",
    pakistan_west: "--ch-pakistan-west",
    china_east: "--ch-china-east",
    gulf_energy: "--ch-gulf-energy",
    us_trade: "--ch-us-trade",
    shipping: "--ch-shipping",
  }[key];
  return token ? getCSS(token) : getCSS("--muted");
}

/* Kept as a Proxy so the ~3 existing COLORS[...] call sites keep
 * working unchanged, while every read resolves against the live theme.
 */
const COLORS = new Proxy({}, { get: (_, key) => seriesColor(String(key)) });

const state = { history: null, range: 365, on: { composite: true, daily_tape: true } };
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

function sparkline(series, color) {
  // 30-day inline trend, 90x22, no lib: the row tells its own story.
  const data = (series || []).slice(-30).filter(v => v != null);
  if (data.length < 5) return "";
  const min = Math.min(...data), max = Math.max(...data), span = (max - min) || 1;
  const pts = data.map((v, i) =>
    `${(i / (data.length - 1) * 88 + 1).toFixed(1)},${(20 - (v - min) / span * 18 + 1).toFixed(1)}`).join(" ");
  const last = data[data.length - 1], ly = (20 - (last - min) / span * 18 + 1).toFixed(1);
  return `<svg class="spark" viewBox="0 0 90 22" width="90" height="22" aria-hidden="true">` +
    `<polyline points="${pts}" fill="none" stroke="${color}" stroke-width="1.6" ` +
    `stroke-linecap="round" stroke-linejoin="round" opacity="0.85"/>` +
    `<circle cx="89" cy="${ly}" r="2.2" fill="${color}"/></svg>`;
}

function renderLatest(latest, history) {
  // Headline is the 7-day (founder-signed 2026-08-06); daily is the tape.
  const score = latest.composite7 != null ? latest.composite7 : latest.composite;
  if (score == null) return;
  document.documentElement.style.setProperty("--state", stateColor(score));
  document.getElementById("latest-date").textContent = latest.date;
  countUp(document.getElementById("composite-score"), score);
  document.getElementById("composite-delta").innerHTML =
    `${fmtDelta(history ? delta1d(history.composite7 || history.composite) : null)} <span class="flat">vs yesterday</span>`;
  document.getElementById("band-tick").style.left =
    `${Math.max(0, Math.min(100, score))}%`;

  const wrap = document.getElementById("components");
  wrap.innerHTML = "";
  for (const [key, c] of Object.entries(latest.channels || {})) {
    const d = history && (history.channels7 || history.channels) ? delta1d((history.channels7 || history.channels)[key]) : null;
    const row = document.createElement("a");
    row.className = "component-row";
    row.href = `receipts.html?channel=${encodeURIComponent(key)}`;
    row.title = "See the exact query and matched articles behind this score";
    const hist = history && history.channels ? history.channels[key] : null;
    row.innerHTML =
      `<span class="component-name">${esc(c.label)}</span>` +
      sparkline(hist, COLORS[key] || "#888") +
      `<span class="component-score">${(c.score7 != null ? esc(c.score7.toFixed(1)) : c.score == null ? "–" : esc(c.score.toFixed(1)))}</span>` +
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
      borderWidth: isComposite ? 2.4 : 1.7,
      borderDash: dashed ? [5, 4] : [],
      fill: isComposite,
      backgroundColor: isComposite ? g : "transparent",
      pointRadius: 0,
      tension: 0.2,
    });
  };
  // Composite sampling band (MI3): shaded 95% envelope on the days that
  // are sample-estimated. Drawn beneath the composite line; days without
  // a band (API-era) simply have none, never a faked one.
  if (state.on.composite && state.uncertainty && state.uncertainty.days) {
    const ud = state.uncertainty.days;
    const lo = labels.map(d => (ud[d] && ud[d].composite) ? ud[d].composite[0] : null);
    const hi = labels.map(d => (ud[d] && ud[d].composite) ? ud[d].composite[1] : null);
    if (hi.some(v => v != null)) {
      datasets.push({
        label: "95% band (sampling)", data: hi, borderWidth: 0,
        pointRadius: 0, fill: "+1", backgroundColor: ink + "2e",
        tension: 0.2, spanGaps: false,
      });
      datasets.push({
        label: "_band_lo", data: lo, borderWidth: 0, pointRadius: 0,
        fill: false, tension: 0.2, spanGaps: false,
      });
    }
  }
  addSeries("composite", h.composite7 || h.composite, "Composite (7-day)");
  if (h.composite7) addSeries("daily_tape", h.composite, "Daily tape", true);
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
      animation: { duration: 900, easing: "easeOutQuart" },
      animations: { y: { from: (ctx) => ctx.chart.scales.y.getPixelForValue(0) } },
      responsive: true,
      interaction: { mode: "index", intersect: false },
      plugins: { legend: { display: false },
        tooltip: { filter: (item) => item.dataset.label !== "_band_lo" } },
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

/* Committed dark default with a persisted light toggle (macroglide-style
   product feel; no dependence on the visitor's OS setting). */
function applyTheme(theme) {
  document.documentElement.dataset.theme = theme;
  localStorage.igrmTheme = theme;
  const btn = document.getElementById("theme-toggle");
  if (btn) btn.textContent = theme === "dark" ? "Light" : "Dark";
  const score = parseFloat(document.getElementById("composite-score").textContent);
  if (!Number.isNaN(score)) {
    document.documentElement.style.setProperty("--state", stateColor(score));
  }
  renderChart();
}
document.getElementById("theme-toggle")?.addEventListener("click", () => {
  applyTheme(document.documentElement.dataset.theme === "dark" ? "light" : "dark");
});
if (document.getElementById("theme-toggle")) {
  document.getElementById("theme-toggle").textContent =
    (localStorage.igrmTheme || "dark") === "dark" ? "Light" : "Dark";
}

/* Subscribe modal: centered, appears once after 15s of reading, fully
   automated through Buttondown (email in -> subscribed -> welcome email
   from the service). Gated on BUTTONDOWN_USER so visitors never see a
   flow that is not yet wired to a real list. */
const BUTTONDOWN_USER = "";  // buttondown.com username; empty = modal off
function initSubscribe() {
  const overlay = document.getElementById("subscribe-overlay");
  if (!overlay) return;
  const dismiss = () => {
    overlay.hidden = true; overlay.style.display = "none";
    localStorage.igrmSubDismissed = "1";
    document.removeEventListener("keydown", onKey);
  };
  const onKey = (ev) => { if (ev.key === "Escape") dismiss(); };
  // Escape hatches attach unconditionally: whatever else goes wrong,
  // this dialog must always be closable.
  overlay.addEventListener("click", (ev) => { if (ev.target === overlay) dismiss(); });
  document.getElementById("subscribe-close").addEventListener("click", dismiss);
  document.addEventListener("keydown", onKey);
  overlay.hidden = true; overlay.style.display = "none";

  const preview = new URLSearchParams(location.search).get("preview") === "subscribe";
  if (!preview) {
    if (localStorage.igrmSubscribed || localStorage.igrmSubDismissed) return;
  }

  setTimeout(() => {
    overlay.hidden = false; overlay.style.display = "flex";
    document.getElementById("subscribe-email").focus({ preventScroll: true });
    document.addEventListener("keydown", onKey);
  }, preview ? 2000 : 15000);

  document.getElementById("subscribe-form").addEventListener("submit", async (ev) => {
    ev.preventDefault();
    const email = document.getElementById("subscribe-email").value.trim();
    if (!email) return;
    // Double-clicks used to relay the same address two or three times.
    const btn = document.querySelector("#subscribe-form button");
    btn.disabled = true;
    let delivered = false;
    try {
      if (BUTTONDOWN_USER) {
        await fetch(
          `https://buttondown.com/api/emails/embed-subscribe/${BUTTONDOWN_USER}`,
          { method: "POST", mode: "no-cors", body: new URLSearchParams({ email }) }
        );
        // no-cors responses are opaque; the service's own welcome email
        // is the subscriber's receipt.
        delivered = true;
      } else {
        // No-signup relay: forwards the address to the author's inbox.
        const res = await fetch("https://formsubmit.co/ajax/ishankrishna9@gmail.com", {
          method: "POST",
          headers: { "Content-Type": "application/json", "Accept": "application/json" },
          body: JSON.stringify({ email, _subject: "New IGRM subscriber" }),
        });
        const body = res.ok ? await res.json() : null;
        delivered = !!body && (body.success === true || body.success === "true");
      }
    } catch (e) { delivered = false; }
    if (!delivered) {
      // Never claim success that didn't happen: show the mailto fallback
      // and leave the form usable (and the modal re-armed for next visit).
      btn.disabled = false;
      document.getElementById("subscribe-error").hidden = false;
      return;
    }
    document.getElementById("subscribe-form").hidden = true;
    document.querySelector(".subscribe-fine").hidden = true;
    document.getElementById("subscribe-error").hidden = true;
    document.getElementById("subscribe-done").hidden = false;
    localStorage.igrmSubscribed = "1";
    setTimeout(() => { overlay.hidden = true; overlay.style.display = "none"; }, 3500);
  });
}
initSubscribe();

/* At-a-glance strip: the biggest mover vs yesterday, in words. */
function renderGlance(history) {
  const el = document.getElementById("glance");
  if (!el || !history || !history.channels) return;
  let best = null;
  for (const [key, series] of Object.entries(history.channels)) {
    const d = delta1d(series);
    if (d != null && (!best || Math.abs(d) > Math.abs(best.d))) {
      best = { key, d };
    }
  }
  if (!best || Math.abs(best.d) < 0.05) return;
  const name = (history.labels && history.labels[best.key]) || best.key;
  const dir = best.d > 0 ? "up" : "down";
  // A big move on a thin channel can sit inside two days' sampling
  // bands; when it does, the strip says so instead of selling noise as
  // news (MI3 discipline: the band applies to every claim, not only
  // the chart).
  let caveat = "";
  const ud = state.uncertainty && state.uncertainty.days;
  if (ud) {
    const idxs = [];
    for (let i = history.dates.length - 1; i >= 0 && idxs.length < 2; i--) {
      if (history.channels[best.key][i] != null) idxs.push(i);
    }
    if (idxs.length === 2) {
      const b1 = (ud[history.dates[idxs[0]]] || {})[best.key];
      const b0 = (ud[history.dates[idxs[1]]] || {})[best.key];
      if (b0 && b1 && b1[0] <= b0[1] && b0[0] <= b1[1]) {
        caveat = ` The two days' 95% sampling bands overlap, so part of ` +
          `this move can be sampling noise.`;
      }
    }
  }
  el.innerHTML = `Today at a glance: <b>${esc(name)}</b> moved the most, ` +
    `${dir} <b>${Math.abs(best.d).toFixed(1)}</b> points vs yesterday.${caveat}`;
  el.hidden = false;
}

/* Count-up on the headline number; skipped for reduced-motion users. */
function countUp(el, target) {
  const dur = 700;
  let finished = false;
  const done = () => { finished = true; el.textContent = target.toFixed(1); };
  if (matchMedia("(prefers-reduced-motion: reduce)").matches) return done();
  const t0 = performance.now();
  const tick = (t) => {
    if (finished) return;
    const p = Math.min(1, (t - t0) / dur);
    const eased = 1 - Math.pow(1 - p, 3);
    el.textContent = (target * eased).toFixed(1);
    if (p < 1) requestAnimationFrame(tick); else finished = true;
  };
  requestAnimationFrame(tick);
  // rAF is a nicety, never a dependency: the number lands regardless.
  setTimeout(() => { if (!finished) done(); }, dur + 300);
}

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

function istTime(hhmm) {
  // "HH:MM" UTC -> "HH:MM" IST (+05:30); clock time only, freshness cue.
  const parts = String(hhmm).split(":").map(Number);
  if (parts.length !== 2 || parts.some(Number.isNaN)) return hhmm + " UTC";
  const t = (parts[0] * 60 + parts[1] + 330) % 1440;
  return `${String(Math.floor(t / 60)).padStart(2, "0")}:${String(t % 60).padStart(2, "0")}`;
}

function renderNowcast(nc) {
  // Render only a payload that is genuinely today's (UTC): a stale file
  // must vanish rather than masquerade as current. The daily score
  // above stays the number of record; this line is labeled provisional.
  if (!nc || !nc.provisional || nc.composite == null) return;
  if (nc.date !== new Date().toISOString().slice(0, 10)) return;
  const el = document.getElementById("nowcast");
  if (!el) return;
  // Per-channel provisional scores made first-class (FICCI round 2,
  // 2026-08-04: an evening event must be findable the same evening,
  // and a composite-only line hid which border was moving).
  let chips = "";
  for (const [k, c] of Object.entries(nc.channels || {})) {
    if (c.score == null) continue;
    chips += `<a class="nowcast-chip" href="receipts.html?channel=${esc(k)}">` +
      `<span class="nc-label">${esc(c.label)}</span>` +
      `<span class="nc-score">${esc(c.score)}</span></a>`;
  }
  el.innerHTML =
    `<span class="prov">Provisional</span> ${esc(nc.date)} so far: composite ` +
    `${esc(nc.composite)} as of ${esc(istTime(nc.as_of_utc))} IST, from a ` +
    `${esc(Number(nc.n_docs_sampled).toLocaleString("en-IN"))}-article ` +
    `sample. Finalized by the daily update.` +
    (chips ? `<span class="nowcast-channels">${chips}</span>` : "");
  el.hidden = false;
}

async function init() {
  bindRanges();
  let history = null;
  try {
    history = await loadJSON("data/history.json");
    state.history = history;
  } catch (e) { console.warn("history.json not available yet", e); }
  try {
    // 95% sampling bands for sample-estimated days (MI3); absence is
    // fine -- pre-ngrams days have no sampling design to band.
    state.uncertainty = await loadJSON("data/uncertainty.json");
  } catch (e) { state.uncertainty = null; }
  try {
    const latest = await loadJSON("data/latest.json");
    renderLatest(latest, history);
    if (latest.definition) {
      document.getElementById("tagline").textContent =
        latest.definition + " Final numbers by 6:00 AM IST; provisional nowcast every two hours.";
    }
  } catch (e) { console.warn("latest.json not available yet", e); }
  try {
    renderNowcast(await loadJSON("data/nowcast.json"));
  } catch (e) { /* absent nowcast is the normal state outside its hours */ }
  if (history) {
    buildToggles(history);
    renderChart();
    renderGlance(history);
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


// Masthead shrink-on-scroll (founder request 2026-08-06): the sticky
// description band yields once reading starts. Hysteresis avoids
// flicker at the threshold; rAF keeps the listener cheap.
(function () {
  const mast = document.querySelector(".masthead");
  if (!mast) return;
  let ticking = false;
  function update() {
    ticking = false;
    const y = window.scrollY;
    if (y > 80) mast.classList.add("shrunk");
    else if (y < 24) mast.classList.remove("shrunk");
  }
  window.addEventListener("scroll", () => {
    if (!ticking) { ticking = true; requestAnimationFrame(update); }
  }, { passive: true });
})();
