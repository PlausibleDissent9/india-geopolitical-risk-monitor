# igrm.R -- single-file R client for the India Geopolitical Risk Monitor.
# Data CC BY 4.0; construct: press salience, not risk; no forecasts.
# Citation: Krishna, Ishan (2026). India Geopolitical Risk Monitor. https://igrm.in/
# Field stability: https://igrm.in/data/api_contract.json

igrm_history <- function() {
  # Daily composite + five channel percentiles (0-100, trailing-730d rank).
  utils::read.csv("https://igrm.in/data/history.csv", stringsAsFactors = FALSE)
}

igrm_latest <- function() {
  # Today's scores incl. the 7-day headline fields (composite7/score7).
  jsonlite::fromJSON("https://igrm.in/data/latest.json")
}

igrm_episodes <- function() {
  # Detected coverage episodes under the frozen 2-sigma/90-day rule.
  utils::read.csv("https://igrm.in/data/episodes.csv", stringsAsFactors = FALSE)
}

igrm_alerts <- function() {
  # Registered alert events (band-separated moves, threshold crossings,
  # the morning contract's own misses). Poll model, stable ids.
  jsonlite::fromJSON("https://igrm.in/data/alerts.json")
}
