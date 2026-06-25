// inject.js — runs in the page MAIN world.
// The isolated content script cannot read YouTube's player JS object, so this
// thin bridge reads the live player response and answers on-demand requests.
(function () {
  function reply(cmd, reqId, payload) {
    window.postMessage(
      Object.assign({ __azdub: "res", cmd: cmd, reqId: reqId }, payload),
      "*"
    );
  }

  window.addEventListener("message", function (e) {
    if (e.source !== window) return;
    const d = e.data;
    if (!d || d.__azdub !== "req") return;

    // --- Force the player to load a caption track so YouTube fetches it ---
    if (d.cmd === "enableCaptions") {
      let ok = false;
      try {
        const mp = document.getElementById("movie_player");
        if (mp) {
          try { mp.loadModule && mp.loadModule("captions"); } catch (_) {}
          let tracklist = [];
          try { tracklist = mp.getOption("captions", "tracklist") || []; } catch (_) {}
          let responseTracks = [];
          try {
            const resp = mp.getPlayerResponse && mp.getPlayerResponse();
            const cap =
              resp && resp.captions && resp.captions.playerCaptionsTracklistRenderer;
            responseTracks = (cap && cap.captionTracks) || [];
          } catch (_) {}
          const wanted = (d.lang || "").toLowerCase();

          function trackTextName(t) {
            const n = t && t.name;
            if (!n) return "";
            if (typeof n === "string") return n;
            if (n.simpleText) return n.simpleText;
            if (n.runs) return n.runs.map((r) => r.text).join("");
            return "";
          }

          function normalizeTrack(t) {
            if (!t) return null;
            const out = Object.assign({}, t);
            if (out.vssId && !out.vss_id) out.vss_id = out.vssId;
            out.name = trackTextName(t);
            if (out.kind === "asr" && out.languageCode && !out.vss_id) {
              out.vss_id = "a." + out.languageCode;
            }
            return out;
          }

          function scoreTrack(t) {
            const lang = String((t && t.languageCode) || "").toLowerCase();
            if (!lang) return -1;
            let score = 0;
            if (wanted && lang === wanted) score += 40;
            else if (wanted && lang.startsWith(wanted)) score += 30;
            else if (!wanted) score += 5;
            if (t.kind === "asr" || String(t.vssId || t.vss_id || "").startsWith("a.")) {
              score += 20;
            }
            if (t.is_servable === true) score += 10;
            if (t.is_servable === false) score -= 5;
            return score;
          }

          const candidates = responseTracks.concat(tracklist);
          const track =
            candidates
              .filter((t) => scoreTrack(t) >= 0)
              .sort((a, b) => scoreTrack(b) - scoreTrack(a))[0] ||
            candidates.find((t) => t && t.is_servable !== false) ||
            candidates[0];
          try { mp.setOption("captions", "reload", true); } catch (_) {}
          try {
            mp.setOption(
              "captions",
              "track",
              normalizeTrack(track) || { languageCode: d.lang || "en" }
            );
            ok = true;
          } catch (_) {}
          if (!ok && mp.toggleSubtitles) { try { mp.toggleSubtitles(); ok = true; } catch (_) {} }
        }
      } catch (_) {}
      reply("enableCaptions", d.reqId, { ok: ok });
      return;
    }

    if (d.cmd === "disableCaptions") {
      try {
        const mp = document.getElementById("movie_player");
        if (mp) mp.setOption("captions", "track", {});
      } catch (_) {}
      reply("disableCaptions", d.reqId, { ok: true });
      return;
    }

    // Mute/unmute via the player API (sticks better than video.muted alone).
    if (d.cmd === "setMute") {
      let ok = false;
      try {
        const mp = document.getElementById("movie_player");
        if (mp) {
          if (d.mute) { mp.mute && mp.mute(); }
          else { mp.unMute && mp.unMute(); }
          ok = true;
        }
      } catch (_) {}
      reply("setMute", d.reqId, { ok: ok });
      return;
    }

    if (d.cmd !== "getPlayerInfo") return;

    let info = null;
    try {
      const mp = document.getElementById("movie_player");
      const resp =
        (mp && mp.getPlayerResponse && mp.getPlayerResponse()) ||
        window.ytInitialPlayerResponse ||
        null;

      if (resp) {
        const cap =
          resp.captions && resp.captions.playerCaptionsTracklistRenderer;
        const tracks = (cap && cap.captionTracks) || [];
        info = {
          videoId: (resp.videoDetails && resp.videoDetails.videoId) || null,
          duration:
            (resp.videoDetails && Number(resp.videoDetails.lengthSeconds)) ||
            null,
          tracks: tracks.map(function (t) {
            return {
              baseUrl: t.baseUrl,
              lang: t.languageCode || "",
              kind: t.kind || "",
              vssId: t.vssId || "",
              name:
                (t.name &&
                  (t.name.simpleText ||
                    (t.name.runs &&
                      t.name.runs.map((r) => r.text).join("")))) ||
                "",
            };
          }),
        };
      }
    } catch (err) {
      info = { error: String(err) };
    }

    window.postMessage(
      { __azdub: "res", cmd: "getPlayerInfo", reqId: d.reqId, info: info },
      "*"
    );
  });
})();
