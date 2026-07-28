/* Shared display names: raw keys never reach a reader's eyes. */
window.IGRM_LABELS = {
  pakistan_west: "Pakistan / Western Border",
  china_east: "China / Eastern Border",
  gulf_energy: "Gulf & Energy Security",
  us_trade: "US & Trade Policy",
  shipping: "Shipping & Chokepoints",
  composite: "Composite",
  nifty_minus_em: "Nifty − Emerging Markets",
  defence_minus_nifty: "Defence basket − Nifty",
  usdinr_minus_dxy: "Rupee − Dollar index",
  brent_ret: "Brent (descriptive)",
  gold_ret: "Gold (descriptive)",
};
window.igrmLabel = (k) => window.IGRM_LABELS[k] || k;
