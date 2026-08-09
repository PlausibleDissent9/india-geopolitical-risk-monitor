(function (root, factory) {
  "use strict";
  var api = factory();
  if (typeof module === "object" && module.exports) module.exports = api;
  root.IGRMTypedCanonical = api;
})(typeof globalThis !== "undefined" ? globalThis : this, function () {
  "use strict";

  var PROFILE = "igrm-typed-canonical-f64-v1";
  var MAX_SAFE_JSON_INTEGER = 9007199254740991;
  var encoder = new TextEncoder();

  function fail(code) { throw new Error(code); }

  function bytesHex(bytes) {
    return Array.from(bytes).map(function (value) {
      return value.toString(16).padStart(2, "0");
    }).join("");
  }

  function utf8(value) {
    for (var index = 0; index < value.length; index += 1) {
      var unit = value.charCodeAt(index);
      if (unit >= 0xd800 && unit <= 0xdbff) {
        var next = value.charCodeAt(index + 1);
        if (!(next >= 0xdc00 && next <= 0xdfff)) fail("typed_canonical_string_invalid");
        index += 1;
      } else if (unit >= 0xdc00 && unit <= 0xdfff) {
        fail("typed_canonical_string_invalid");
      }
    }
    return encoder.encode(value);
  }

  function compareBytes(left, right) {
    var limit = Math.min(left.length, right.length);
    for (var index = 0; index < limit; index += 1) {
      if (left[index] !== right[index]) return left[index] - right[index];
    }
    return left.length - right.length;
  }

  function float64Hex(value) {
    var buffer = new ArrayBuffer(8);
    new DataView(buffer).setFloat64(0, value, false);
    return bytesHex(new Uint8Array(buffer));
  }

  function encode(value) {
    if (value === null) return "n;";
    if (typeof value === "boolean") return value ? "b1;" : "b0;";
    if (typeof value === "number") {
      if (!Number.isFinite(value) || (Number.isInteger(value) && !Number.isSafeInteger(value))) {
        fail("typed_canonical_number_invalid");
      }
      return "d" + float64Hex(value) + ";";
    }
    if (typeof value === "string") {
      var encoded = utf8(value);
      return "s" + encoded.length + ":" + bytesHex(encoded) + ";";
    }
    if (Array.isArray(value)) {
      return "a" + value.length + ":" + value.map(encode).join("") + ";";
    }
    if (value && typeof value === "object") {
      var entries = Object.keys(value).map(function (key) {
        return { key: key, bytes: utf8(key) };
      }).sort(function (left, right) { return compareBytes(left.bytes, right.bytes); });
      return "o" + entries.length + ":" + entries.map(function (entry) {
        return encode(entry.key) + encode(value[entry.key]);
      }).join("") + ";";
    }
    fail("typed_canonical_type_invalid");
  }

  return Object.freeze({ profile: PROFILE, encode: encode });
});
