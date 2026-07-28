/* Scroll-reveal, progressive-enhancement grade:
   - content is VISIBLE by default; this script only hides elements that
     start below the fold, so no-JS readers, reader modes, crawlers, and
     any environment where observers never fire still see everything;
   - reduced-motion users get no animation at all;
   - a failsafe reveals anything still hidden after 3s. */
(() => {
  if (matchMedia("(prefers-reduced-motion: reduce)").matches) return;
  if (!("IntersectionObserver" in window)) return;
  const candidates = document.querySelectorAll(
    "main > section, body > h2, body > .table-scroll, body > .chart-wrap, " +
    "body > table, .prose > h2, footer"
  );
  const below = [...candidates].filter(
    (t) => t.getBoundingClientRect().top > innerHeight * 0.92
  );
  if (!below.length) return;
  const io = new IntersectionObserver((entries) => {
    for (const en of entries) {
      if (en.isIntersecting) { en.target.classList.add("in"); io.unobserve(en.target); }
    }
  }, { rootMargin: "0px 0px -6% 0px" });
  for (const t of below) { t.classList.add("reveal"); io.observe(t); }
  setTimeout(() => {
    for (const t of below) t.classList.add("in");
  }, 3000);
})();

/* Reading progress bar */
(() => {
  const bar = document.createElement("div");
  bar.className = "progress";
  document.body.appendChild(bar);
  const update = () => {
    const h = document.documentElement;
    const max = h.scrollHeight - innerHeight;
    bar.style.width = max > 0 ? (100 * h.scrollTop / max) + "%" : "0";
  };
  addEventListener("scroll", update, { passive: true });
  update();
})();
