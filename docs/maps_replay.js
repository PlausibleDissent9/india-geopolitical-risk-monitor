(function (root) {
  "use strict";

  var CHANNELS = ["pakistan_west", "china_east", "gulf_energy", "us_trade", "shipping"];
  var ISO_DAY = /^\d{4}-\d{2}-\d{2}$/;

  function isoDay(value) {
    var text = String(value || "");
    if (!ISO_DAY.test(text)) return false;
    var parsed = new Date(text + "T00:00:00Z");
    return !Number.isNaN(parsed.getTime()) && parsed.toISOString().slice(0, 10) === text;
  }

  function exactKeys(value, keys) {
    return value && typeof value === "object" && !Array.isArray(value) &&
      Object.keys(value).sort().join("|") === keys.slice().sort().join("|");
  }

  function validScore(value) {
    return value == null || (typeof value === "number" && Number.isFinite(value) && value >= 0 && value <= 100);
  }

  function validHistory(payload) {
    if (!payload || typeof payload !== "object" || Array.isArray(payload) || !payload._meta ||
        payload._meta.partial === true || !isoDay(payload._meta.generated) ||
        !Array.isArray(payload.dates) || payload.dates.length < 2 ||
        !Array.isArray(payload.composite) || payload.composite.length !== payload.dates.length ||
        !exactKeys(payload.channels, CHANNELS) || !exactKeys(payload.labels, CHANNELS)) return false;
    var seen = new Set();
    var prior = null;
    for (var index = 0; index < payload.dates.length; index += 1) {
      var day = payload.dates[index];
      if (!isoDay(day) || seen.has(day) || (prior && day <= prior) || !validScore(payload.composite[index])) return false;
      seen.add(day);
      prior = day;
    }
    if (payload.dates[payload.dates.length - 1] > payload._meta.generated) return false;
    return CHANNELS.every(function (channel) {
      return typeof payload.labels[channel] === "string" && Boolean(payload.labels[channel].trim()) &&
        Array.isArray(payload.channels[channel]) && payload.channels[channel].length === payload.dates.length &&
        payload.channels[channel].every(validScore);
    });
  }

  function validEpisodes(payload, history) {
    if (!validHistory(history) || !Array.isArray(payload)) return false;
    var first = history.dates[0];
    var cutoff = history.dates[history.dates.length - 1];
    var domain = new Set(history.dates);
    return payload.every(function (episode) {
      if (!episode || typeof episode !== "object" || !CHANNELS.includes(episode.channel) ||
          typeof episode.label !== "string" || !episode.label.trim() ||
          !isoDay(episode.start) || !isoDay(episode.end) || !isoDay(episode.peak_date) ||
          episode.start > episode.end || episode.peak_date < episode.start || episode.peak_date > episode.end ||
          !Number.isInteger(episode.n_spike_days) || episode.n_spike_days < 1 || episode.end > cutoff) return false;
      if (episode.end < first) return true;
      return domain.has(episode.start) && domain.has(episode.end) && domain.has(episode.peak_date);
    });
  }

  function sameDomain(actual, expected) {
    return Array.isArray(actual) && Array.isArray(expected) && actual.length === 2 && expected.length === 2 &&
      actual.every(function (value, index) { return Number(value) === Number(expected[index]); });
  }

  function validAnchors(payload, world, history) {
    if (!validHistory(history) || !payload || typeof payload !== "object" || !payload._meta ||
        payload._meta.partial !== false || !isoDay(payload._meta.generated) ||
        !world || typeof world !== "object" || !world._meta ||
        payload._meta.projection_id !== world._meta.projection_id ||
        payload._meta.world_geometry_reference !== "geo/world.json" ||
        payload._meta.world_view_box !== world.viewBox ||
        !sameDomain(payload._meta.longitude_domain, world._meta.longitude_domain) ||
        !sameDomain(payload._meta.latitude_domain, world._meta.latitude_domain) ||
        !exactKeys(payload.channels, CHANNELS)) return false;
    var lon = payload._meta.longitude_domain.map(Number);
    var lat = payload._meta.latitude_domain.map(Number);
    return CHANNELS.every(function (channel) {
      var point = payload.channels[channel];
      return point && point.label === history.labels[channel] &&
        Number.isFinite(Number(point.longitude)) && Number(point.longitude) >= lon[0] && Number(point.longitude) <= lon[1] &&
        Number.isFinite(Number(point.latitude)) && Number(point.latitude) >= lat[0] && Number(point.latitude) <= lat[1];
    });
  }

  function validReceiptsArchive(payload) {
    if (!payload || typeof payload !== "object" || !payload._meta || payload._meta.partial === true ||
        !Array.isArray(payload._meta.days) || !exactKeys(payload.channels, CHANNELS)) return false;
    var dates = new Set();
    if (!payload._meta.days.every(function (day) {
      if (!isoDay(day) || dates.has(day)) return false;
      dates.add(day);
      return true;
    })) return false;
    return CHANNELS.every(function (channel) {
      var block = payload.channels[channel];
      if (!block || typeof block !== "object" || !block.days || typeof block.days !== "object") return false;
      return Object.entries(block.days).every(function (entry) {
        var row = entry[1];
        return dates.has(entry[0]) && row && Number.isInteger(row.n_matched) && row.n_matched >= 0 &&
          Array.isArray(row.articles) && row.articles.length <= row.n_matched;
      });
    });
  }

  function resolveDeepLink(history, requestedDate, requestedChannel) {
    if (!validHistory(history)) return { ok: false, errors: ["history_invalid"], date: null, channel: null };
    var errors = [];
    var cutoff = history.dates[history.dates.length - 1];
    var date = requestedDate || cutoff;
    var channel = requestedChannel || CHANNELS[0];
    if (!history.dates.includes(date)) {
      errors.push("date_outside_published_history");
      date = cutoff;
    }
    if (!CHANNELS.includes(channel)) {
      errors.push("channel_not_registered");
      channel = CHANNELS[0];
    }
    return { ok: errors.length === 0, errors: errors, date: date, channel: channel, cutoff: cutoff };
  }

  function observation(history, date, channel) {
    if (!validHistory(history) || !CHANNELS.includes(channel)) return null;
    var index = history.dates.indexOf(date);
    if (index < 0) return null;
    return {
      date: date,
      index: index,
      composite: history.composite[index],
      value: history.channels[channel][index],
      isGap: history.channels[channel][index] == null
    };
  }

  function activeEpisodes(episodes, date) {
    if (!Array.isArray(episodes) || !isoDay(date)) return [];
    return episodes.filter(function (episode) {
      return episode.start <= date && date <= episode.end;
    }).slice().sort(function (a, b) {
      return a.channel.localeCompare(b.channel) || a.start.localeCompare(b.start);
    });
  }

  function receiptEvidence(payload, channel, date) {
    if (!validReceiptsArchive(payload) || !CHANNELS.includes(channel)) return { available: false };
    var row = payload.channels[channel].days[date];
    return row ? { available: true, nMatched: row.n_matched, nShown: row.articles.length } : { available: false };
  }

  function presentation(date, playbackActive) {
    if (!isoDay(date)) {
      return {
        available: false,
        canvasDescription: "Attention Replay unavailable. No dated replay state is rendered; current analytical layers remain withheld.",
        statusText: "Attention Replay unavailable · source bundle refused",
        hideCurrentContext: true,
        provenanceMode: "unavailable"
      };
    }
    return {
      available: true,
      canvasDescription: "Daily Attention Replay for " + date +
        ". Five interface anchors show published channel scores or explicit gaps. " +
        "They are not event locations, routes, or exposure paths.",
      statusText: playbackActive ? null : "Replay " + date + " · published daily index",
      hideCurrentContext: true,
      provenanceMode: "daily_history"
    };
  }

  function workspaceVisibility(replayMode, bundleAvailable) {
    return {
      hideCurrentContext: Boolean(replayMode),
      showReplaySurface: Boolean(replayMode && bundleAvailable)
    };
  }

  function rangeState(history, date) {
    if (!validHistory(history)) return null;
    var index = history.dates.indexOf(date);
    if (index < 0) return null;
    return {
      min: 0,
      max: history.dates.length - 1,
      value: index,
      valueText: date
    };
  }

  root.IGRM_ATLAS_REPLAY = Object.freeze({
    CHANNELS: Object.freeze(CHANNELS.slice()),
    validHistory: validHistory,
    validEpisodes: validEpisodes,
    validAnchors: validAnchors,
    validReceiptsArchive: validReceiptsArchive,
    resolveDeepLink: resolveDeepLink,
    observation: observation,
    activeEpisodes: activeEpisodes,
    receiptEvidence: receiptEvidence,
    presentation: presentation,
    workspaceVisibility: workspaceVisibility,
    rangeState: rangeState
  });
})(typeof globalThis === "undefined" ? window : globalThis);
