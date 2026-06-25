// content.js — isolated world orchestrator.
// Flow per watch page:
//   detect spoken language -> skip az/tr -> fetch transcript -> translate to AZ
//   -> synthesize AZ neural audio -> play it in sync while muting the original.

(function () {
  "use strict";

  const DEFAULTS = {
    enabled: true,
    targetLang: "az",
    voice: "az-AZ-BabekNeural", // or az-AZ-BanuNeural
    rate: "+0%",
    pitch: "+0Hz",
    skipLangs: ["az", "tr"],
    muteOriginal: true,
    duckVolume: 0.08,
    useBrowserFallback: false,
    ttsProxyUrl: "",
    ahead: 6,
  };

  const AZ = { settings: { ...DEFAULTS } };

  function sleep(ms) {
    return new Promise((r) => setTimeout(r, ms));
  }

  async function loadSettings() {
    const s = await chrome.storage.sync.get(DEFAULTS);
    AZ.settings = { ...DEFAULTS, ...s };
  }

  // -------------------------------------------------------------------------
  // Status badge
  // -------------------------------------------------------------------------
  function createStatusUI() {
    let el = null;
    function ensure() {
      if (el && document.documentElement.contains(el)) return el;
      el = document.createElement("div");
      el.id = "azdub-status";
      el.addEventListener("click", () => el && (el.style.display = "none"));
      (document.body || document.documentElement).appendChild(el);
      return el;
    }
    return {
      hide() {
        if (el) el.style.display = "none";
      },
      set(state, text) {
        const e = ensure();
        e.dataset.state = state;
        e.textContent = text;
        e.style.display = "flex";
      },
    };
  }
  const statusUI = createStatusUI();

  // -------------------------------------------------------------------------
  // Bridge to MAIN world (inject.js)
  // -------------------------------------------------------------------------
  function getPlayerInfo() {
    return new Promise((resolve) => {
      const reqId = Math.random().toString(36).slice(2);
      let settled = false;
      function onMsg(e) {
        if (e.source !== window) return;
        const d = e.data;
        if (
          d &&
          d.__azdub === "res" &&
          d.cmd === "getPlayerInfo" &&
          d.reqId === reqId
        ) {
          settled = true;
          window.removeEventListener("message", onMsg);
          resolve(d.info);
        }
      }
      window.addEventListener("message", onMsg);
      window.postMessage({ __azdub: "req", cmd: "getPlayerInfo", reqId }, "*");
      setTimeout(() => {
        if (!settled) {
          window.removeEventListener("message", onMsg);
          resolve(null);
        }
      }, 600);
    });
  }

  function bridge(cmd, extra) {
    return new Promise((resolve) => {
      const reqId = Math.random().toString(36).slice(2);
      let settled = false;
      function onMsg(e) {
        if (e.source !== window) return;
        const d = e.data;
        if (d && d.__azdub === "res" && d.cmd === cmd && d.reqId === reqId) {
          settled = true;
          window.removeEventListener("message", onMsg);
          resolve(d);
        }
      }
      window.addEventListener("message", onMsg);
      window.postMessage(
        Object.assign({ __azdub: "req", cmd, reqId }, extra || {}),
        "*"
      );
      setTimeout(() => {
        if (!settled) {
          window.removeEventListener("message", onMsg);
          resolve(null);
        }
      }, 1500);
    });
  }

  // Force YouTube to load a caption track, then grab the real request URL that
  // its player issued (it includes the valid `pot` token), via the background.
  async function captureCaptionUrl(vid, lang) {
    await chrome.runtime.sendMessage({ type: "clearCaptionUrl" }).catch(() => {});
    for (let attempt = 0; attempt < 3; attempt++) {
      await bridge("enableCaptions", { lang });
      for (let i = 0; i < 12; i++) {
        const r = await chrome.runtime
          .sendMessage({ type: "getCaptionUrl", vid })
          .catch(() => null);
        if (r && r.ok && r.url && r.url.includes("v=" + vid)) return r.url;
        await sleep(500);
      }
    }
    return null;
  }

  async function waitForPlayerInfo(vid) {
    for (let i = 0; i < 25; i++) {
      const info = await getPlayerInfo();
      if (info && info.videoId === vid) {
        // captions can populate slightly after the response; give them time
        if ((info.tracks && info.tracks.length) || i > 6) return info;
      }
      await sleep(400);
    }
    return await getPlayerInfo();
  }

  // -------------------------------------------------------------------------
  // Transcript
  // -------------------------------------------------------------------------
  function decodeEntities(s) {
    const t = document.createElement("textarea");
    t.innerHTML = s;
    return t.value;
  }

  function parseJson3(data) {
    const segs = [];
    for (const ev of data.events || []) {
      if (!ev.segs) continue;
      const text = ev.segs
        .map((s) => s.utf8 || "")
        .join("")
        .replace(/\s+/g, " ")
        .trim();
      if (!text) continue;
      segs.push({ startMs: ev.tStartMs || 0, durMs: ev.dDurationMs || 0, text });
    }
    return segs;
  }

  function parseXmlTranscript(xml) {
    const doc = new DOMParser().parseFromString(xml, "text/xml");
    const segs = [];
    // srv1 / ttml: <text start="1.5" dur="3.2">...</text>
    const texts = doc.querySelectorAll("text");
    if (texts.length) {
      texts.forEach((n) => {
        const startMs = Math.round(parseFloat(n.getAttribute("start") || "0") * 1000);
        const durMs = Math.round(parseFloat(n.getAttribute("dur") || "0") * 1000);
        const text = decodeEntities(n.textContent || "").replace(/\s+/g, " ").trim();
        if (text) segs.push({ startMs, durMs, text });
      });
      return segs;
    }
    // srv3: <p t="1500" d="3200"><s>word</s>...</p>
    doc.querySelectorAll("p").forEach((p) => {
      const startMs = parseInt(p.getAttribute("t") || "0", 10);
      const durMs = parseInt(p.getAttribute("d") || "0", 10);
      const text = decodeEntities(p.textContent || "").replace(/\s+/g, " ").trim();
      if (text) segs.push({ startMs, durMs, text });
    });
    return segs;
  }

  async function fetchTranscript(baseUrl) {
    const clean = baseUrl.replace(/&fmt=[^&]*/g, "");
    const attempts = [clean + "&fmt=json3", clean + "&fmt=srv3", clean];
    let lastInfo = "boş cavab";
    for (const url of attempts) {
      try {
        const res = await fetch(url, { credentials: "include" });
        const ct = res.headers.get("content-type") || "";
        const body = await res.text();
        console.log(
          "[AZDUB] timedtext status=%s ct=%s len=%s hasPot=%s hasFmt=%s\n%s",
          res.status,
          ct,
          body.length,
          /[?&]pot=/.test(url),
          /[?&]fmt=/.test(url),
          url
        );
        if (!body || !body.trim()) {
          lastInfo = "boş cavab (status " + res.status + ")";
          continue;
        }
        let segs;
        if (body.trim().startsWith("{")) {
          segs = parseJson3(JSON.parse(body));
          if (!segs.length) {
            lastInfo = "json3 boş (events yoxdur)";
            continue;
          }
        } else {
          segs = parseXmlTranscript(body);
          if (!segs.length) {
            lastInfo = "xml boş (mətn yoxdur)";
            continue;
          }
        }
        console.log("[AZDUB] transcript parsed: %s seqment", segs.length);
        return segs;
      } catch (e) {
        console.warn("[AZDUB] timedtext error", url.slice(0, 140), e);
        lastInfo = String(e && e.message ? e.message : e);
      }
    }
    throw new Error(lastInfo);
  }

  function buildPhrases(segs) {
    const phrases = [];
    let cur = null;
    const MAXLEN = 180;
    const GAP = 900; // ms between caption events that forces a phrase break
    for (const s of segs) {
      if (!cur) {
        cur = { startMs: s.startMs, endMs: s.startMs + s.durMs, text: s.text };
        continue;
      }
      const gap = s.startMs - cur.endMs;
      const endsSentence = /[.!?…][")']?$/.test(cur.text);
      if (
        endsSentence ||
        gap > GAP ||
        cur.text.length + s.text.length > MAXLEN
      ) {
        phrases.push(cur);
        cur = { startMs: s.startMs, endMs: s.startMs + s.durMs, text: s.text };
      } else {
        cur.text += " " + s.text;
        cur.endMs = s.startMs + s.durMs;
      }
    }
    if (cur) phrases.push(cur);
    return phrases;
  }

  function pickBrowserVoice() {
    const vs = (window.speechSynthesis && speechSynthesis.getVoices()) || [];
    return (
      vs.find((v) => /az/i.test(v.lang)) ||
      vs.find((v) => /tr/i.test(v.lang)) ||
      null
    );
  }

  function lastWords(s, n) {
    const a = s.split(/\s+/).filter(Boolean);
    return a.slice(Math.max(0, a.length - n)).join(" ");
  }

  // Newly-appeared words in `cur` that are not already covered by `tail`
  // (handles YouTube's rolling caption window where text scrolls upward).
  function deltaWords(tail, cur) {
    if (!tail) return cur;
    const a = tail.split(/\s+/).filter(Boolean);
    const b = cur.split(/\s+/).filter(Boolean);
    const maxk = Math.min(a.length, b.length, 30);
    for (let k = maxk; k > 0; k--) {
      if (a.slice(a.length - k).join(" ") === b.slice(0, k).join(" ")) {
        return b.slice(k).join(" ");
      }
    }
    return cur;
  }

  // -------------------------------------------------------------------------
  // Dubbing session for a single video
  // -------------------------------------------------------------------------
  class DubSession {
    constructor(video, phrases, settings) {
      this.video = video;
      this.phrases = phrases; // each gains .az/.audio/.translating/.synthesizing/.audioFailed
      this.settings = settings;
      this.dead = false;

      this.curAudio = null;
      this.curUtter = null;
      this.audioBusy = false;
      this.playingIndex = -1;
      this.nextToPlay = 0;
      this._autoPaused = false;
    }

    start() {
      this._applyMute();
      this.nextToPlay = this._indexAt(this.video.currentTime * 1000);
      this.playingIndex = this.nextToPlay - 1;

      this._onSeek = () => this._flush();
      this._onRate = () => {
        if (this.curAudio) this.curAudio.playbackRate = this.video.playbackRate;
      };
      this._onPause = () => {
        if (this._autoPaused) return; // our own pause keeps the dub running
        if (this.curAudio) this.curAudio.pause();
        if (this.curUtter && window.speechSynthesis) speechSynthesis.pause();
      };
      this._onPlay = () => {
        if (this.curAudio && this.curAudio.paused)
          this.curAudio.play().catch(() => {});
        if (window.speechSynthesis && speechSynthesis.paused)
          speechSynthesis.resume();
      };

      this.video.addEventListener("seeking", this._onSeek);
      this.video.addEventListener("ratechange", this._onRate);
      this.video.addEventListener("pause", this._onPause);
      this.video.addEventListener("play", this._onPlay);

      this._driver = setInterval(() => this._tick(), 150);
      this._pump();
      statusUI.set("active", "🔊 AZ dublyaj aktiv");
    }

    destroy() {
      this.dead = true;
      clearInterval(this._driver);
      this.video.removeEventListener("seeking", this._onSeek);
      this.video.removeEventListener("ratechange", this._onRate);
      this.video.removeEventListener("pause", this._onPause);
      this.video.removeEventListener("play", this._onPlay);
      this._stopAudio();
      if (this.settings.muteOriginal) {
        if (this._origMuted !== undefined) this.video.muted = this._origMuted;
        if (this._didMute) bridge("setMute", { mute: false });
      } else if (this._origVol !== undefined) {
        this.video.volume = this._origVol;
      }
      if (this._autoPaused) {
        this._autoPaused = false;
        if (this.video.paused) this.video.play().catch(() => {});
      }
    }

    _applyMute() {
      if (this.settings.muteOriginal) {
        this._origMuted = this.video.muted;
        this.video.muted = true;
        this._didMute = true;
        bridge("setMute", { mute: true });
      } else {
        this._origVol = this.video.volume;
        this.video.volume = this.settings.duckVolume;
      }
    }

    _indexAt(ms) {
      const ph = this.phrases;
      if (!ph.length || ms < ph[0].startMs) return 0;
      let lo = 0,
        hi = ph.length - 1,
        ans = 0;
      while (lo <= hi) {
        const mid = (lo + hi) >> 1;
        if (ph[mid].startMs <= ms) {
          ans = mid;
          lo = mid + 1;
        } else hi = mid - 1;
      }
      return ans;
    }

    // ---- preparation pipeline (stays ahead of the playhead) ----
    async _pump() {
      while (!this.dead) {
        const curIdx = this._indexAt(this.video.currentTime * 1000);
        const target = Math.min(
          this.phrases.length,
          curIdx + this.settings.ahead
        );
        let did = false;
        for (let i = Math.max(0, curIdx); i < target; i++) {
          if (this.dead) return;
          const p = this.phrases[i];
          if (!p) continue;
          if (p.az == null && !p.translating) {
            await this._translate(p);
            did = true;
          }
          if (
            p.az != null &&
            !p.audio &&
            !p.synthesizing &&
            !p.audioFailed
          ) {
            await this._synth(p);
            did = true;
          }
        }
        if (!did) await sleep(150);
      }
    }

    async _translate(p) {
      p.translating = true;
      try {
        const r = await chrome.runtime.sendMessage({
          type: "translate",
          text: p.text,
          target: this.settings.targetLang || "az",
        });
        console.log(
          "[AZDUB] tr ok=%s err=%s | '%s' -> '%s'",
          r && r.ok,
          r && r.error,
          p.text.slice(0, 50),
          r && r.text ? r.text.slice(0, 50) : ""
        );
        p.az = r && r.ok && r.text ? r.text : p.text; // fall back to original
      } catch (e) {
        console.log(
          "[AZDUB] tr ok=false err=%s | '%s' -> ''",
          String(e),
          p.text.slice(0, 50)
        );
        p.az = p.text;
      }
      p.translating = false;
    }

    async _synth(p) {
      p.synthesizing = true;
      try {
        const r = await chrome.runtime.sendMessage({
          type: "tts",
          text: p.az,
          voice: this.settings.voice,
          rate: this.settings.rate,
          pitch: this.settings.pitch,
          proxy: this.settings.ttsProxyUrl,
        });
        if (r && r.ok && r.audio) {
          p.audio = r.audio;
          p.mime = r.mime || "audio/mpeg";
        }
        else p.audioFailed = true;
        console.log(
          "[AZDUB] tts ok=%s via:\"%s\" err=%s len=%s",
          r && r.ok,
          (r && r.via) || "",
          r && r.error,
          r && r.audio ? r.audio.length : 0
        );
      } catch (e) {
        p.audioFailed = true;
        console.log("[AZDUB] tts ok=false via:\"\" err=%s len=0", String(e));
      }
      p.synthesizing = false;
    }

    _ready(p) {
      return !!(
        p.audio ||
        (p.audioFailed && this.settings.useBrowserFallback && p.az)
      );
    }
    _terminal(p) {
      // permanently unrenderable -> skip rather than stall forever
      return p.audioFailed && !(this.settings.useBrowserFallback && p.az);
    }

    // ---- playback driver ----
    _tick() {
      if (this.dead) return;
      if (this.video.paused && !this._autoPaused) return; // user paused

      const ms = this.video.currentTime * 1000;

      if (this.audioBusy) {
        // keep the picture from running ahead of an in-progress dub line
        const next = this.phrases[this.playingIndex + 1];
        if (next && ms >= next.startMs && !this.video.paused) this._autoPause();
        return;
      }

      const i = this.nextToPlay;
      if (i >= this.phrases.length) {
        if (this._autoPaused) this._resume();
        return;
      }
      const p = this.phrases[i];

      if (ms >= p.startMs) {
        if (this._ready(p)) {
          if (this._autoPaused) this._resume();
          this._play(i);
        } else if (this._terminal(p)) {
          this.nextToPlay = i + 1;
          if (this._autoPaused) this._resume();
        } else {
          if (!this.video.paused) this._autoPause();
          statusUI.set("preparing", "⏳ Dublyaj hazırlanır…");
        }
      } else if (this._autoPaused) {
        this._resume();
      }
    }

    _autoPause() {
      this._autoPaused = true;
      try { this.video.pause(); } catch (_) {}
    }
    _resume() {
      this._autoPaused = false;
      if (this.video.paused) this.video.play().catch(() => {});
    }

    _play(i) {
      const p = this.phrases[i];
      this.playingIndex = i;
      this.nextToPlay = i + 1;
      this.audioBusy = true;
      statusUI.set("active", "🔊 AZ dublyaj");

      const onDone = () => {
        this.curAudio = null;
        this.curUtter = null;
        this.audioBusy = false;
        if (this._autoPaused) this._resume();
      };

      if (p.audio) {
        const a = new Audio("data:" + (p.mime || "audio/mpeg") + ";base64," + p.audio);
        a.playbackRate = this.video.playbackRate || 1;
        this.curAudio = a;
        a.onended = onDone;
        a.onerror = onDone;
        a.play().catch(onDone);
      } else if (p.az && this.settings.useBrowserFallback && window.speechSynthesis) {
        try {
          const u = new SpeechSynthesisUtterance(p.az);
          u.lang = "az-AZ";
          const v = pickBrowserVoice();
          if (v) u.voice = v;
          u.onend = onDone;
          u.onerror = onDone;
          this.curUtter = u;
          speechSynthesis.speak(u);
        } catch (e) {
          onDone();
        }
      } else {
        onDone();
      }
    }

    _stopAudio() {
      if (this.curAudio) {
        try { this.curAudio.pause(); } catch (_) {}
        this.curAudio = null;
      }
      if (window.speechSynthesis) {
        try { speechSynthesis.cancel(); } catch (_) {}
      }
      this.curUtter = null;
      this.audioBusy = false;
    }

    _flush() {
      this._stopAudio();
      this._autoPaused = false;
      this.nextToPlay = this._indexAt(this.video.currentTime * 1000);
      this.playingIndex = this.nextToPlay - 1;
    }
  }

  // -------------------------------------------------------------------------
  // Live caption-scraping session (fallback when timedtext is empty/blocked).
  // Reads what the player renders on screen, so it works whenever subtitles
  // can be displayed at all.
  // -------------------------------------------------------------------------
  class LiveDubSession {
    constructor(video, settings, spokenLang) {
      this.video = video;
      this.settings = settings;
      this.spokenLang = spokenLang;
      this.dead = false;

      this.procQueue = []; // captured source phrases awaiting translate+synth
      this.processing = false;
      this.playQueue = []; // ready { az, audio }
      this.playing = false;
      this.curAudio = null;
      this._autoPaused = false;

      this.capturedTail = "";
      this.pending = "";
      this.lastChange = 0;
      this._anyText = false;
    }

    async start() {
      this._applyMute();
      document.documentElement.classList.add("azdub-hide-captions");
      await bridge("enableCaptions", { lang: this.spokenLang });

      this._sampler = setInterval(() => this._sample(), 220);
      this._guard = setInterval(() => this._driftGuard(), 200);
      this._onPause = () => {
        if (!this._autoPaused && this.curAudio) this.curAudio.pause();
      };
      this._onPlay = () => {
        if (this.curAudio && this.curAudio.paused)
          this.curAudio.play().catch(() => {});
      };
      this.video.addEventListener("pause", this._onPause);
      this.video.addEventListener("play", this._onPlay);

      statusUI.set("active", "🔊 AZ dublyaj (canlı)");

      this._watchdog = setTimeout(() => {
        if (!this.dead && !this._anyText) {
          statusUI.set("none", "Altyazı görünmür — bu video danışıqsız ola bilər");
          this.destroy();
        }
      }, 12000);
    }

    destroy() {
      this.dead = true;
      clearInterval(this._sampler);
      clearInterval(this._guard);
      clearTimeout(this._watchdog);
      document.documentElement.classList.remove("azdub-hide-captions");
      this.video.removeEventListener("pause", this._onPause);
      this.video.removeEventListener("play", this._onPlay);
      if (this.curAudio) {
        try { this.curAudio.pause(); } catch (_) {}
        this.curAudio = null;
      }
      if (window.speechSynthesis) {
        try { speechSynthesis.cancel(); } catch (_) {}
      }
      bridge("disableCaptions");
      if (this.settings.muteOriginal) {
        if (this._origMuted !== undefined) this.video.muted = this._origMuted;
        if (this._didMute) bridge("setMute", { mute: false });
      } else if (this._origVol !== undefined) {
        this.video.volume = this._origVol;
      }
      if (this._autoPaused) {
        this._autoPaused = false;
        if (this.video.paused) this.video.play().catch(() => {});
      }
    }

    _applyMute() {
      if (this.settings.muteOriginal) {
        this._origMuted = this.video.muted;
        this.video.muted = true;
        this._didMute = true;
        bridge("setMute", { mute: true });
      } else {
        this._origVol = this.video.volume;
        this.video.volume = this.settings.duckVolume;
      }
    }

    _visibleText() {
      const c =
        document.querySelector(".ytp-caption-window-container") ||
        document.querySelector(".caption-window");
      if (!c) return "";
      const segs = c.querySelectorAll(".ytp-caption-segment");
      let text = segs.length
        ? Array.from(segs).map((s) => s.textContent).join(" ")
        : c.textContent || "";
      return text
        .replace(/\[[^\]]*\]/g, " ") // drop [Music], [Applause], etc.
        .replace(/\s+/g, " ")
        .trim();
    }

    _sample() {
      if (this.dead || this.video.paused) return;
      const cur = this._visibleText();
      const now = performance.now();
      if (cur) {
        this._anyText = true;
        const delta = deltaWords(this.capturedTail, cur);
        if (delta) {
          this.pending = this.pending ? this.pending + " " + delta : delta;
          this.capturedTail = lastWords(
            (this.capturedTail + " " + delta).trim(),
            30
          );
          this.lastChange = now;
        }
      }
      if (this.pending) {
        const wc = this.pending.split(/\s+/).length;
        const ends = /[.!?…]["')]?$/.test(this.pending);
        const idle = now - this.lastChange > 900;
        if (ends || wc >= 12 || idle) {
          const phrase = this.pending.trim();
          this.pending = "";
          if (phrase) {
            this.procQueue.push(phrase);
            this._process();
          }
        }
      }
    }

    async _process() {
      if (this.processing) return;
      this.processing = true;
      while (!this.dead && this.procQueue.length) {
        const text = this.procQueue.shift();
        let az = text;
        const tr = await chrome.runtime
          .sendMessage({
            type: "translate",
            text,
            target: this.settings.targetLang || "az",
            source: this.spokenLang,
          })
          .catch((e) => ({ ok: false, error: String(e) }));
        console.log(
          "[AZDUB] tr ok=%s err=%s | '%s' -> '%s'",
          tr && tr.ok,
          tr && tr.error,
          text.slice(0, 50),
          tr && tr.text ? tr.text.slice(0, 50) : ""
        );
        if (tr && tr.ok && tr.text) az = tr.text;

        let audio = null;
        const ts = await chrome.runtime
          .sendMessage({
            type: "tts",
            text: az,
            voice: this.settings.voice,
            rate: this.settings.rate,
            pitch: this.settings.pitch,
            proxy: this.settings.ttsProxyUrl,
          })
          .catch((e) => ({ ok: false, error: String(e) }));
        console.log(
          "[AZDUB] tts ok=%s via:\"%s\" err=%s len=%s",
          ts && ts.ok,
          (ts && ts.via) || "",
          ts && ts.error,
          ts && ts.audio ? ts.audio.length : 0
        );
        let mime = "audio/mpeg";
        if (ts && ts.ok && ts.audio) {
          audio = ts.audio;
          mime = ts.mime || mime;
        }

        if (this.dead) break;
        this.playQueue.push({ az, audio, mime });
        this._playNext();
      }
      this.processing = false;
    }

    _playNext() {
      if (this.playing || this.dead) return;
      const item = this.playQueue.shift();
      if (!item) return;
      this.playing = true;
      const done = () => {
        this.curAudio = null;
        this.playing = false;
        this._playNext();
      };
      if (item.audio) {
        const a = new Audio("data:" + (item.mime || "audio/mpeg") + ";base64," + item.audio);
        a.playbackRate = this.video.playbackRate || 1;
        this.curAudio = a;
        a.onended = done;
        a.onerror = done;
        a.play().catch(done);
      } else if (
        item.az &&
        this.settings.useBrowserFallback &&
        window.speechSynthesis
      ) {
        try {
          const u = new SpeechSynthesisUtterance(item.az);
          u.lang = "az-AZ";
          const v = pickBrowserVoice();
          if (v) u.voice = v;
          u.onend = done;
          u.onerror = done;
          speechSynthesis.speak(u);
        } catch (e) {
          done();
        }
      } else {
        done();
      }
    }

    // Hold the picture if dubbed audio is piling up, so nothing is lost.
    _driftGuard() {
      if (this.dead) return;
      // Re-assert mute in case YouTube flipped it back during playback.
      if (this.settings.muteOriginal && !this.video.muted) this.video.muted = true;
      const backlog = this.playQueue.length + (this.playing ? 1 : 0);
      if (backlog >= 3 && !this.video.paused) {
        this._autoPaused = true;
        try { this.video.pause(); } catch (_) {}
      } else if (backlog <= 1 && this._autoPaused) {
        this._autoPaused = false;
        if (this.video.paused) this.video.play().catch(() => {});
      }
    }
  }

  // -------------------------------------------------------------------------
  // Top-level controller
  // -------------------------------------------------------------------------
  let currentSession = null;
  let currentVid = null;
  let evaluating = false;
  let pendingEvaluate = false;

  function teardown() {
    if (currentSession) {
      currentSession.destroy();
      currentSession = null;
    }
  }

  async function evaluate() {
    const vid = new URLSearchParams(location.search).get("v");
    if (!location.pathname.startsWith("/watch") || !vid) {
      if (evaluating) pendingEvaluate = true;
      teardown();
      currentVid = null;
      statusUI.hide();
      return;
    }
    if (evaluating) {
      pendingEvaluate = true;
      return;
    }
    if (vid === currentVid) return; // already handled / in progress
    evaluating = true;
    teardown();
    currentVid = vid;

    const stillOnVideo = () =>
      location.pathname.startsWith("/watch") &&
      new URLSearchParams(location.search).get("v") === vid &&
      currentVid === vid;

    try {
      if (!AZ.settings.enabled) {
        statusUI.hide();
        return;
      }

      statusUI.set("checking", "🔎 Yoxlanılır…");
      const info = await waitForPlayerInfo(vid);
      if (!stillOnVideo()) return; // navigated away while waiting
      if (!info) {
        statusUI.set("error", "Player tapılmadı");
        return;
      }
      const tracks = info.tracks || [];
      if (!tracks.length) {
        statusUI.set("none", "Altyazı yoxdur — dublyaj mümkün deyil");
        return;
      }

      console.log("[AZDUB] tracks:", tracks.map((t) => t.lang + (t.kind ? "/" + t.kind : "")).join(", "));
      const asr = tracks.find((t) => t.kind === "asr");
      const spoken = (asr ? asr.lang : tracks[0].lang || "").toLowerCase();
      const skip = (AZ.settings.skipLangs || []).map((x) =>
        String(x).toLowerCase()
      );
      if (skip.some((l) => spoken.startsWith(l))) {
        statusUI.set("skip", `Dil: ${spoken} — dublyaj keçildi`);
        return;
      }

      const src = asr || tracks[0];
      console.log("[AZDUB] spoken=%s, source track=%s", spoken, src.lang + "/" + (src.kind || "manual"));

      statusUI.set("loading", "📝 Altyazı tutulur…");
      let segs = null;
      let lastErr = "";

      // Primary path: capture YouTube's own (pot-bearing) timedtext URL.
      const captured = await captureCaptionUrl(vid, spoken);
      if (!stillOnVideo()) return;
      if (captured) {
        console.log("[AZDUB] captured timedtext url with token");
        try { segs = await fetchTranscript(captured); } catch (e) { lastErr = e.message || String(e); }
      } else {
        console.log("[AZDUB] no captured url; trying raw baseUrl");
      }

      // Fallback: the raw baseUrl (works for some manual tracks / older videos).
      if (!segs || !segs.length) {
        try { segs = await fetchTranscript(src.baseUrl); }
        catch (e) { lastErr = e.message || String(e); }
      }

      if (!stillOnVideo()) return;
      const video =
        document.querySelector("video.html5-main-video") ||
        document.querySelector("video");
      if (!video) {
        statusUI.set("error", "Video tapılmadı");
        return;
      }

      if (segs && segs.length) {
        // Fast path: full transcript with timestamps. Subtitles no longer needed.
        bridge("disableCaptions");
        console.log("[AZDUB] using timestamped transcript (%s phrases)", segs.length);
        const phrases = buildPhrases(segs);
        currentSession = new DubSession(video, phrases, AZ.settings);
        currentSession.start();
      } else {
        // Fallback: live on-screen caption scraping (keeps captions enabled).
        console.log("[AZDUB] timedtext empty (%s); falling back to live scraping", lastErr);
        statusUI.set("loading", "📝 Canlı altyazı rejimi…");
        currentSession = new LiveDubSession(video, AZ.settings, spoken);
        currentSession.start();
      }
    } finally {
      evaluating = false;
      if (pendingEvaluate) {
        pendingEvaluate = false;
        setTimeout(() => evaluate(), 0);
      }
    }
  }

  // React to popup setting changes live
  chrome.storage.onChanged.addListener((changes, area) => {
    if (area !== "sync") return;
    for (const k in changes) AZ.settings[k] = changes[k].newValue;
    const v = currentVid;
    currentVid = null;
    teardown();
    if (v) evaluate();
  });

  function init() {
    document.addEventListener("yt-navigate-finish", () => evaluate());
    document.addEventListener("yt-page-data-updated", () => evaluate());
    window.addEventListener("yt-navigate-finish", () => evaluate());

    // URL-change fallback for SPA navigations
    let lastHref = location.href;
    setInterval(() => {
      if (location.href !== lastHref) {
        lastHref = location.href;
        evaluate();
      }
    }, 1000);

    evaluate();
  }

  (async function () {
    await loadSettings();
    init();
  })();
})();
