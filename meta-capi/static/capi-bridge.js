/*!
 * Meta CAPI bridge — fire every event to BOTH the browser Pixel and the CAPI
 * gateway with ONE shared event_id, so Meta deduplicates and counts it once.
 *
 * Why: the Pixel alone is client-side, so ad-blockers / ITP drop ~10-30% of
 * events — including the funnel steps and clicks you build audiences on. This
 * gives every event a server-side twin that survives those.
 *
 * Install — AFTER the Meta Pixel base code:
 *   <script src="https://YOUR-GATEWAY:8812/capi-bridge.js" data-test="0"></script>
 *   <script>
 *     capi.track('ViewContent', { content_name: 'KASKO' });
 *     // after a known user appears (login / form submit), enrich match quality:
 *     capi.identify({ email: 'a@b.az', phone: '+994501234567' });
 *     capi.track('Lead', { content_name: 'KASKO' });
 *   </script>
 *
 * The gateway URL is auto-derived from this script's own src — no build step.
 * data-test="1" routes events to Events Manager → Test Events (safe).
 */
(function () {
  var self = document.currentScript;
  var base = self ? self.src.replace(/\/capi-bridge\.js.*$/, "") : "";
  var testMode = self && self.getAttribute("data-test") === "1";

  function uuid() {
    if (window.crypto && crypto.randomUUID) return crypto.randomUUID();
    return "xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx".replace(/[xy]/g, function (c) {
      var r = (Math.random() * 16) | 0;
      return (c === "x" ? r : (r & 0x3) | 0x8).toString(16);
    });
  }

  function cookie(name) {
    var m = document.cookie.match("(^|;)\\s*" + name + "\\s*=\\s*([^;]+)");
    return m ? decodeURIComponent(m.pop()) : "";
  }

  // Identifiers known for the current visitor (set via identify()). Kept only in
  // memory for this page; merged into every event to lift match quality.
  var known = {};

  function send(name, customData, userData) {
    var eventId = uuid();

    // 1) Browser Pixel (if loaded) — same eventID is the dedup key.
    if (window.fbq) {
      try { fbq("track", name, customData || {}, { eventID: eventId }); } catch (e) {}
    }

    // 2) CAPI twin. Read first-party _fbp/_fbc cookies HERE (the gateway may be
    //    on another origin and would not receive them otherwise).
    var ud = {};
    var k;
    for (k in userData || {}) ud[k] = userData[k];
    var fbp = cookie("_fbp"); if (fbp && !ud.fbp) ud.fbp = fbp;
    var fbc = cookie("_fbc"); if (fbc && !ud.fbc) ud.fbc = fbc;

    var body = JSON.stringify({
      event_name: name,
      event_id: eventId,
      event_source_url: location.href,
      action_source: "website",
      custom_data: customData || {},
      user_data: ud,
      test: testMode || undefined
    });

    var url = base + "/collect";
    var ok = false;
    // sendBeacon keeps firing even as the page unloads (clicks that navigate).
    if (navigator.sendBeacon) {
      try { ok = navigator.sendBeacon(url, new Blob([body], { type: "application/json" })); } catch (e) {}
    }
    if (!ok) {
      fetch(url, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: body,
        keepalive: true
      }).catch(function () {});
    }
    return eventId;
  }

  function track(name, customData, userData) {
    var merged = {}, k;
    for (k in known) merged[k] = known[k];
    for (k in userData || {}) merged[k] = userData[k];
    return send(name, customData, merged);
  }

  function identify(userData) {
    for (var k in userData || {}) if (userData[k]) known[k] = userData[k];
  }

  window.capi = { track: track, identify: identify, base: base, testMode: testMode };
})();
