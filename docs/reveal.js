/* Scroll-reveal: content rises in as the reader reaches it.
   Skipped entirely for reduced-motion users. */
(() => {
  if (matchMedia("(prefers-reduced-motion: reduce)").matches) return;
  const targets = document.querySelectorAll(
    "main > section, body > h2, body > .table-scroll, body > .chart-wrap, " +
    "body > table, .prose > h2, footer"
  );
  const io = new IntersectionObserver((entries) => {
    for (const en of entries) {
      if (en.isIntersecting) { en.target.classList.add("in"); io.unobserve(en.target); }
    }
  }, { rootMargin: "0px 0px -8% 0px" });
  for (const t of targets) { t.classList.add("reveal"); io.observe(t); }
})();
