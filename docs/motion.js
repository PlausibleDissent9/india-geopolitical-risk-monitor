/* Chart motion, from the same scale as everything else on the page.
 *
 * WHY THIS FILE EXISTS
 * The stylesheets were reduced to five named durations and one easing on
 * 2026-08-07, enforced by tests/test_design_tokens.py. Those tests read
 * CSS. They could not see `animation: { duration: 900, easing:
 * "easeOutQuart" }` sitting in app.js and analysis.html -- a sixth
 * duration, more than twice the longest one in the scale, and a
 * different curve, applied to the two most prominent charts on the site.
 *
 * A motion scale that the charts opt out of is not a scale. And the
 * charts were the one place motion actually ignored
 * prefers-reduced-motion, because the CSS catch-all cannot reach a
 * number passed to a canvas library.
 *
 * It is a separate file rather than six lines copied into each page
 * because this project has now been bitten four times by exactly that
 * copy: two palettes, two sets of keyframes, three copies of the chart
 * colours, and a spacing scale documented in one place and used in
 * none. Three copies of a helper about consistency would be a poor joke.
 *
 * Load before any script that builds a Chart.
 */
(function (global) {
  "use strict";

  function tokenMs(name, fallback) {
    var v = getComputedStyle(document.documentElement)
      .getPropertyValue(name).trim();
    if (!v) return fallback;
    return v.slice(-2) === "ms" ? parseFloat(v) : parseFloat(v) * 1000;
  }

  /* Chart.js takes a named easing string, not a cubic-bezier, so the CSS
   * token cannot be passed through. easeOutCubic is the nearest named
   * curve to --ease (0.2, 0, 0.2, 1): it decelerates into place and does
   * NOT overshoot. easeOutBack, easeOutElastic and easeOutBounce all
   * overshoot and are banned here for the same reason the CSS bounce was
   * removed -- on an instrument, overshoot reads as the number wobbling. */
  var EASING = "easeOutCubic";

  /* Returns a Chart.js `animation` value: an options object normally,
   * and `false` for anyone who asked their system for less motion. */
  function chartAnimation(durationToken) {
    var reduced = global.matchMedia
      && global.matchMedia("(prefers-reduced-motion: reduce)").matches;
    if (reduced) return false;
    return { duration: tokenMs(durationToken || "--dur-slow", 420),
             easing: EASING };
  }

  global.IGRM_MOTION = {
    chartAnimation: chartAnimation,
    tokenMs: tokenMs,
    EASING: EASING,
  };
})(window);
