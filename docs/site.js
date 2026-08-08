/* Shared progressive enhancement for every non-homepage public route.
 * Content, links, and the shell remain usable without JavaScript. */
(function () {
  "use strict";

  var root = document.documentElement;
  var body = document.body;
  root.classList.add("js");

  function rootPath(path) {
    var prefix = body.dataset.root || ".";
    if (prefix === "/") return "/" + path;
    if (prefix === "..") return "../" + path;
    return path;
  }

  function setThemeButton() {
    var button = document.getElementById("theme-toggle");
    if (!button) return;
    var current = root.dataset.theme || "dark";
    var target = current === "dark" ? "light" : "dark";
    button.textContent = target[0].toUpperCase() + target.slice(1);
    button.setAttribute("aria-label", "Switch to " + target + " theme");
  }

  var themeButton = document.getElementById("theme-toggle");
  setThemeButton();
  if (themeButton) {
    themeButton.addEventListener("click", function () {
      var next = root.dataset.theme === "dark" ? "light" : "dark";
      root.dataset.theme = next;
      localStorage.igrmTheme = next;
      setThemeButton();
      window.dispatchEvent(new CustomEvent("igrm:themechange", {
        detail: { theme: next },
      }));
      // Canvas pixels do not inherit new CSS variables. Reload chart pages
      // after persisting the choice so their existing scripts redraw once.
      if (document.querySelector("canvas")) window.location.reload();
    });
  }

  function markCurrentNavigation() {
    var here = new URL(window.location.href).pathname.replace(/index\.html$/, "");
    document.querySelectorAll(".mast-links a, .data-cta").forEach(function (link) {
      var there = new URL(link.href, window.location.href).pathname
        .replace(/index\.html$/, "");
      if (there === here) {
        link.classList.add("current");
        link.setAttribute("aria-current", "page");
      }
    });
  }

  function slug(text) {
    return text.toLowerCase()
      .normalize("NFKD")
      .replace(/[^a-z0-9\s-]/g, "")
      .trim()
      .replace(/[\s-]+/g, "-") || "section";
  }

  function buildTableOfContents() {
    var nav = document.querySelector("[data-page-toc]");
    var main = document.getElementById("main-content");
    if (!nav || !main) return;
    var headings = Array.from(main.querySelectorAll("h2, h3"));
    if (!headings.length) {
      nav.closest(".reading-rail").hidden = true;
      return;
    }
    var used = new Set(Array.from(document.querySelectorAll("[id]"))
      .map(function (element) { return element.id; }));
    nav.replaceChildren();
    headings.forEach(function (heading) {
      if (!heading.id) {
        var base = slug(heading.textContent || "");
        var candidate = base;
        var suffix = 2;
        while (used.has(candidate)) {
          candidate = base + "-" + suffix;
          suffix += 1;
        }
        heading.id = candidate;
        used.add(candidate);
      }
      var link = document.createElement("a");
      link.href = "#" + heading.id;
      link.textContent = heading.textContent || "Section";
      if (heading.tagName === "H3") link.className = "toc-sub";
      nav.appendChild(link);
    });
  }

  async function fillPublicationDate() {
    var targets = document.querySelectorAll("[data-latest-date]");
    if (!targets.length) return;
    targets.forEach(function (target) { target.setAttribute("aria-busy", "true"); });
    try {
      var response = await fetch(rootPath("data/latest.json"), { cache: "no-store" });
      if (!response.ok) throw new Error("latest payload unavailable");
      var latest = await response.json();
      if (!latest.date) throw new Error("latest payload has no date");
      targets.forEach(function (target) {
        var time = document.createElement("time");
        time.dateTime = latest.date;
        time.textContent = "Final data through " + latest.date;
        target.replaceChildren(time);
        target.removeAttribute("aria-busy");
      });
    } catch (error) {
      targets.forEach(function (target) {
        target.textContent = "Open status for publication date";
        target.removeAttribute("aria-busy");
      });
    }
  }

  function ensureReadingProgress() {
    if (document.querySelector(".progress")) return;
    var bar = document.createElement("div");
    bar.className = "progress";
    bar.setAttribute("aria-hidden", "true");
    document.body.appendChild(bar);
    function update() {
      var max = root.scrollHeight - window.innerHeight;
      bar.style.width = max > 0 ? (100 * root.scrollTop / max) + "%" : "0";
    }
    window.addEventListener("scroll", update, { passive: true });
    update();
  }

  function bindCompactMasthead() {
    var masthead = document.querySelector(".site-masthead");
    if (!masthead) return;
    var scheduled = false;
    function update() {
      scheduled = false;
      if (window.scrollY > 80) masthead.classList.add("shrunk");
      else if (window.scrollY < 24) masthead.classList.remove("shrunk");
    }
    window.addEventListener("scroll", function () {
      if (scheduled) return;
      scheduled = true;
      window.requestAnimationFrame(update);
    }, { passive: true });
  }

  markCurrentNavigation();
  buildTableOfContents();
  ensureReadingProgress();
  bindCompactMasthead();
  fillPublicationDate();
})();
