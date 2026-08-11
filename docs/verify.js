"use strict";

const IGRM_API_BYTE_VERIFIER = (() => {
  const MANIFEST_URL = "data/public_api_byte_manifest.json";
  const MANIFEST_MAX_BYTES = 1024 * 1024;
  const ENTRY_MAX_BYTES = 4 * 1024 * 1024;
  const TOTAL_MAX_BYTES = 12 * 1024 * 1024;
  const MAX_ENTRIES = 512;
  const CONCURRENCY = 4;
  const FETCH_TIMEOUT_MS = 20000;
  const SHA256_RE = /^[0-9a-f]{64}$/;
  const PATH_RE = /^[A-Za-z0-9._/-]+$/;
  const TOP_LEVEL_KEYS = [
    "_meta", "api_contract", "claim_boundary", "entries",
    "excluded_entries", "integrity", "object_type", "profile",
    "schema_version", "totals", "universe",
  ];
  const ENTRY_KEYS = [
    "bytes", "format", "git_mode", "path", "repository_path", "sha256",
  ];

  function refuse(code, detail = "") {
    const error = new Error(code);
    error.code = code;
    error.detail = detail;
    throw error;
  }

  function exactKeys(value, expected, code) {
    if (!value || typeof value !== "object" || Array.isArray(value)) refuse(code);
    const actual = Object.keys(value).sort();
    const wanted = [...expected].sort();
    if (actual.length !== wanted.length || actual.some((key, i) => key !== wanted[i])) {
      refuse(code, "keys");
    }
  }

  function safePath(value) {
    if (
      typeof value !== "string" || !value || !PATH_RE.test(value) ||
      value.includes("\\") || value.includes(":") || value.includes("\0") ||
      value.normalize("NFC") !== value || value.startsWith("/") ||
      value.endsWith("/") || value.includes("//")
    ) refuse("manifest_path_invalid", String(value));
    const parts = value.split("/");
    if (parts.some((part) => !part || part === "." || part === "..")) {
      refuse("manifest_path_invalid", value);
    }
    return value;
  }

  function validateManifest(value) {
    exactKeys(value, TOP_LEVEL_KEYS, "manifest_shape_invalid");
    if (
      value.object_type !== "igrm.public_api_byte_manifest" ||
      value.schema_version !== "0.1.0" ||
      !Array.isArray(value.entries) || value.entries.length > MAX_ENTRIES ||
      !Array.isArray(value.excluded_entries) || value.excluded_entries.length !== 1 ||
      typeof value.claim_boundary !== "string" || !value.claim_boundary
    ) refuse("manifest_shape_invalid");

    const excluded = value.excluded_entries[0];
    if (
      !excluded || excluded.path !== MANIFEST_URL ||
      excluded.repository_path !== `docs/${MANIFEST_URL}` ||
      excluded.reason !== "self_exclusion_avoids_recursive_digest"
    ) refuse("manifest_self_exclusion_invalid");

    const totals = value.totals;
    const universe = value.universe;
    const integrity = value.integrity;
    if (
      !totals || totals.max_entry_bytes !== ENTRY_MAX_BYTES ||
      totals.max_hashed_bytes !== TOTAL_MAX_BYTES ||
      !Number.isSafeInteger(totals.hashed_entries) ||
      !Number.isSafeInteger(totals.hashed_bytes) ||
      !universe || universe.basis !== "api_contract.endpoints" ||
      universe.order !== "public_path_utf8_byte_ascending" ||
      universe.excluded_endpoint_denominator !== 1 ||
      universe.hashed_endpoint_denominator !== value.entries.length ||
      universe.endpoint_denominator !== value.entries.length + 1 ||
      !integrity || integrity.algorithm !== "SHA-256" ||
      integrity.external_manifest_digest_required !== true ||
      integrity.signed !== false || integrity.authenticated_deployment !== false ||
      integrity.atomic_hosted_snapshot !== false
    ) refuse("manifest_boundary_invalid");

    const paths = new Set();
    const folded = new Set();
    let bytes = 0;
    let previous = "";
    for (const entry of value.entries) {
      exactKeys(entry, ENTRY_KEYS, "manifest_entry_invalid");
      const path = safePath(entry.path);
      const fold = path.toLowerCase();
      if (paths.has(path) || folded.has(fold) || (previous && previous >= path)) {
        refuse("manifest_entry_order_invalid", path);
      }
      if (
        entry.repository_path !== `docs/${path}` || entry.git_mode !== "100644" ||
        !["json", "csv", "rss"].includes(entry.format) ||
        !Number.isSafeInteger(entry.bytes) || entry.bytes < 0 ||
        entry.bytes > ENTRY_MAX_BYTES || !SHA256_RE.test(entry.sha256)
      ) refuse("manifest_entry_invalid", path);
      paths.add(path);
      folded.add(fold);
      previous = path;
      bytes += entry.bytes;
      if (bytes > TOTAL_MAX_BYTES) refuse("manifest_total_size_invalid");
    }
    if (
      totals.hashed_entries !== value.entries.length || totals.hashed_bytes !== bytes ||
      value.api_contract.endpoint_denominator !== value.entries.length + 1
    ) refuse("manifest_denominator_invalid");
    return value;
  }

  function bytesEqual(left, right) {
    if (!(left instanceof Uint8Array) || !(right instanceof Uint8Array)) return false;
    if (left.byteLength !== right.byteLength) return false;
    let difference = 0;
    for (let i = 0; i < left.byteLength; i += 1) difference |= left[i] ^ right[i];
    return difference === 0;
  }

  async function digestBytes(bytes) {
    if (!globalThis.crypto || !globalThis.crypto.subtle) refuse("webcrypto_unsupported");
    const view = bytes instanceof Uint8Array ? bytes : new Uint8Array(bytes);
    const digest = await globalThis.crypto.subtle.digest("SHA-256", view);
    return Array.from(new Uint8Array(digest), (byte) => byte.toString(16).padStart(2, "0")).join("");
  }

  async function readBounded(response, maximum) {
    const announced = response.headers.get("content-length");
    if (announced !== null) {
      const parsed = Number(announced);
      if (!Number.isSafeInteger(parsed) || parsed < 0 || parsed > maximum) {
        refuse("response_size_limit_exceeded", announced);
      }
    }
    if (!response.body || typeof response.body.getReader !== "function") {
      const raw = new Uint8Array(await response.arrayBuffer());
      if (raw.byteLength > maximum) refuse("response_size_limit_exceeded");
      return raw;
    }
    const reader = response.body.getReader();
    const chunks = [];
    let length = 0;
    while (true) {
      const { done, value } = await reader.read();
      if (done) break;
      length += value.byteLength;
      if (length > maximum) {
        await reader.cancel("response_size_limit_exceeded");
        refuse("response_size_limit_exceeded");
      }
      chunks.push(value);
    }
    const out = new Uint8Array(length);
    let cursor = 0;
    for (const chunk of chunks) {
      out.set(chunk, cursor);
      cursor += chunk.byteLength;
    }
    return out;
  }

  async function fetchBytes(url, maximum, fetchImpl = globalThis.fetch) {
    if (typeof fetchImpl !== "function") refuse("fetch_unsupported");
    const controller = new AbortController();
    const timer = setTimeout(() => controller.abort("timeout"), FETCH_TIMEOUT_MS);
    try {
      const response = await fetchImpl(url, {
        cache: "no-store", credentials: "omit", redirect: "error", signal: controller.signal,
      });
      if (!response.ok) {
        const error = new Error(response.status === 404 ? "response_missing" : "response_http_error");
        error.code = response.status === 404 ? "response_missing" : "response_http_error";
        error.status = response.status;
        throw error;
      }
      return await readBounded(response, maximum);
    } finally {
      clearTimeout(timer);
    }
  }

  function endpointURL(path, baseURL) {
    const safe = safePath(path);
    const base = new URL(baseURL);
    const url = new URL(safe, base);
    if (url.origin !== base.origin || url.username || url.password) {
      refuse("endpoint_origin_invalid", safe);
    }
    return url.href;
  }

  async function verifyEntry(entry, baseURL, fetchImpl) {
    try {
      // The expected length is also the per-response transfer ceiling.  With
      // the validated manifest total this bounds actual aggregate endpoint
      // bytes, rather than merely trusting an announced aggregate.
      const raw = await fetchBytes(endpointURL(entry.path, baseURL), entry.bytes, fetchImpl);
      if (raw.byteLength !== entry.bytes) {
        return { path: entry.path, status: "mismatch", detail: `bytes ${raw.byteLength}/${entry.bytes}` };
      }
      const actual = await digestBytes(raw);
      if (actual !== entry.sha256) {
        return { path: entry.path, status: "mismatch", detail: `sha256 ${actual}` };
      }
      return { path: entry.path, status: "matched", detail: `${raw.byteLength} bytes` };
    } catch (error) {
      const code = error && error.code ? error.code : "network_error";
      if (code === "response_missing") return { path: entry.path, status: "missing", detail: code };
      if (code === "webcrypto_unsupported" || code === "fetch_unsupported") {
        return { path: entry.path, status: "unsupported", detail: code };
      }
      if (code === "response_size_limit_exceeded") {
        return { path: entry.path, status: "mismatch", detail: code };
      }
      return { path: entry.path, status: "indeterminate", detail: code };
    }
  }

  async function verifyEntries(entries, baseURL, fetchImpl, onResult = () => {}) {
    const results = new Array(entries.length);
    let cursor = 0;
    async function worker() {
      while (true) {
        const index = cursor;
        cursor += 1;
        if (index >= entries.length) return;
        const result = await verifyEntry(entries[index], baseURL, fetchImpl);
        results[index] = result;
        onResult(result, index, results.filter(Boolean).length);
      }
    }
    await Promise.all(Array.from({ length: Math.min(CONCURRENCY, entries.length) }, worker));
    return results;
  }

  function expectedDigestFromHash(hash) {
    const value = String(hash || "").replace(/^#/, "");
    if (!value) return "";
    if (SHA256_RE.test(value.toLowerCase())) return value.toLowerCase();
    const parsed = new URLSearchParams(value).get("sha256") || "";
    return parsed.toLowerCase();
  }

  function formatBytes(value) {
    if (value < 1024) return `${value} B`;
    if (value < 1024 * 1024) return `${(value / 1024).toFixed(1)} KiB`;
    return `${(value / (1024 * 1024)).toFixed(2)} MiB`;
  }

  async function startBrowser() {
    const byId = (id) => document.getElementById(id);
    const state = { manifest: null, raw: null, digest: "" };
    const input = byId("expected-manifest-sha");
    const button = byId("verify-api-bytes");
    const override = byId("bandwidth-override");
    const lowBandwidth = Boolean(
      (navigator.connection && navigator.connection.saveData) ||
      (globalThis.matchMedia && matchMedia("(prefers-reduced-data: reduce)").matches)
    );
    input.value = expectedDigestFromHash(location.hash);
    byId("low-bandwidth-warning").hidden = !lowBandwidth;

    function updateButton() {
      button.disabled = !state.manifest || (lowBandwidth && !override.checked);
    }
    override.addEventListener("change", updateButton);

    try {
      byId("manifest-status").textContent = "Loading the manifest only; endpoint files have not been requested.";
      const raw = await fetchBytes(new URL(MANIFEST_URL, location.href).href, MANIFEST_MAX_BYTES);
      const parsed = validateManifest(JSON.parse(new TextDecoder("utf-8", { fatal: true }).decode(raw)));
      state.raw = raw;
      state.manifest = parsed;
      state.digest = await digestBytes(raw);
      byId("manifest-raw-sha").textContent = state.digest;
      byId("manifest-count").textContent = String(parsed.entries.length);
      byId("manifest-bytes").textContent = formatBytes(parsed.totals.hashed_bytes);
      byId("manifest-status").textContent = "Manifest loaded. No endpoint artifact has been fetched.";
      updateButton();
    } catch (error) {
      byId("manifest-status").textContent = `Manifest unavailable or invalid: ${error.code || "manifest_load_failed"}.`;
      button.disabled = true;
      return;
    }

    button.addEventListener("click", async () => {
      button.disabled = true;
      const expected = input.value.trim().toLowerCase();
      const status = byId("verification-status");
      const progress = byId("verification-progress");
      const table = byId("verification-results");
      const body = table.querySelector("tbody");
      body.replaceChildren();
      table.hidden = false;

      if (expected && !SHA256_RE.test(expected)) {
        status.textContent = "Expected digest is invalid; no endpoint artifact was fetched.";
        button.disabled = false;
        return;
      }
      if (expected && expected !== state.digest) {
        status.textContent = "manifest_digest_mismatch — the supplied external digest does not match; no endpoint artifact was fetched.";
        button.disabled = false;
        return;
      }

      const rows = new Map();
      for (const entry of state.manifest.entries) {
        const row = document.createElement("tr");
        for (const text of [entry.path, formatBytes(entry.bytes), "pending", "not fetched"]) {
          const cell = document.createElement("td");
          cell.textContent = text;
          row.appendChild(cell);
        }
        body.appendChild(row);
        rows.set(entry.path, row);
      }
      status.textContent = expected
        ? "External manifest digest matched. Checking endpoint bytes…"
        : "No external digest supplied. Checking same-origin consistency only…";

      const results = await verifyEntries(
        state.manifest.entries,
        location.href,
        globalThis.fetch,
        (result, _index, completed) => {
          const row = rows.get(result.path);
          row.children[2].textContent = result.status;
          row.children[3].textContent = result.detail;
          progress.textContent = `${completed}/${state.manifest.entries.length} checked`;
        },
      );

      let second;
      try {
        second = await fetchBytes(new URL(MANIFEST_URL, location.href).href, MANIFEST_MAX_BYTES);
      } catch (error) {
        status.textContent = `release_recheck_indeterminate — ${error.code || "network_error"}; no final verdict.`;
        button.disabled = false;
        return;
      }
      if (!bytesEqual(state.raw, second)) {
        status.textContent = "release_changed_during_verification — manifest M2 differs from M1; no final verdict.";
        button.disabled = false;
        return;
      }

      const counts = Object.fromEntries(
        ["matched", "mismatch", "missing", "indeterminate", "unsupported"].map((key) => [
          key, results.filter((row) => row.status === key).length,
        ]),
      );
      if (counts.mismatch || counts.missing) {
        status.textContent = `endpoint_bytes_mismatch — ${counts.matched} matched, ${counts.mismatch} mismatched, ${counts.missing} missing.`;
      } else if (counts.indeterminate || counts.unsupported) {
        status.textContent = `verification_indeterminate — ${counts.matched} matched, ${counts.indeterminate} network-indeterminate, ${counts.unsupported} unsupported.`;
      } else if (expected) {
        status.textContent = "caller_supplied_manifest_digest_and_endpoint_bytes_match";
      } else {
        status.textContent = "same_origin_bytes_match_unanchored_manifest";
      }
      button.disabled = false;
    });
  }

  const api = {
    CONCURRENCY, ENTRY_MAX_BYTES, TOTAL_MAX_BYTES, MANIFEST_MAX_BYTES,
    bytesEqual, digestBytes, endpointURL, expectedDigestFromHash,
    fetchBytes, formatBytes, safePath, validateManifest, verifyEntries, verifyEntry,
  };
  if (typeof module !== "undefined" && module.exports) module.exports = api;
  if (typeof window !== "undefined") window.IGRM_API_BYTE_VERIFIER = api;
  if (typeof document !== "undefined") document.addEventListener("DOMContentLoaded", startBrowser);
  return api;
})();
