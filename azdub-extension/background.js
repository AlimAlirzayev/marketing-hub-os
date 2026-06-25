// background.js — service worker
// Responsibilities (kept here to avoid page CORS / CSP restrictions):
//   1. translate text -> Azerbaijani via the free Google Translate endpoint
//   2. synthesize Azerbaijani speech via Microsoft Edge Neural TTS (WebSocket)
// The content script orchestrates timing and plays the returned audio.

const TRUSTED_CLIENT_TOKEN = "6A5AA1D4EAFF4E9FB37E23D68491D6F4";
const WIN_EPOCH = 11644473600; // seconds between 1601-01-01 and 1970-01-01
const S_TO_NS = 1e9;
const SEC_MS_GEC_VERSION = "1-143.0.3650.75"; // must track edge-tts upstream
const WSS_URL_BASE =
  "wss://speech.platform.bing.com/consumer/speech/synthesize/readaloud/edge/v1";

// ---------------------------------------------------------------------------
// Edge TTS DRM token (Sec-MS-GEC)
// IMPORTANT: must replicate edge-tts EXACTLY, including IEEE-double arithmetic
// and `:.0f`-style formatting (via toFixed). Using BigInt produces a different
// integer than edge-tts/Microsoft expect, which yields a 403 and no audio.
// Ref: rany2/edge-tts src/edge_tts/drm.py
// ---------------------------------------------------------------------------
async function generateSecMsGec() {
  let ticks = Date.now() / 1000; // float unix seconds, like Python time.time()
  ticks += WIN_EPOCH;
  ticks -= ticks % 300; // round down to a 5-minute boundary
  ticks *= S_TO_NS / 100; // seconds -> 100-nanosecond intervals (×1e7)
  const strToHash = ticks.toFixed(0) + TRUSTED_CLIENT_TOKEN;
  const digest = await crypto.subtle.digest(
    "SHA-256",
    new TextEncoder().encode(strToHash)
  );
  return [...new Uint8Array(digest)]
    .map((b) => b.toString(16).padStart(2, "0"))
    .join("")
    .toUpperCase();
}

function xmlEscape(s) {
  return s
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&apos;");
}

function buildSSML(text, voice, rate, pitch) {
  return (
    `<speak version='1.0' xmlns='http://www.w3.org/2001/10/synthesis' xml:lang='az-AZ'>` +
    `<voice name='${voice}'>` +
    `<prosody pitch='${pitch}' rate='${rate}' volume='+0%'>` +
    `${xmlEscape(text)}</prosody></voice></speak>`
  );
}

function nowStr() {
  return new Date().toString();
}
function uuid() {
  return crypto.randomUUID().replace(/-/g, "");
}

function uint8ToBase64(u8) {
  let binary = "";
  const chunk = 0x8000;
  for (let i = 0; i < u8.length; i += chunk) {
    binary += String.fromCharCode.apply(null, u8.subarray(i, i + chunk));
  }
  return btoa(binary);
}

async function edgeTTS(text, voice, rate, pitch) {
  const sec = await generateSecMsGec();
  const connId = uuid();
  const url =
    `${WSS_URL_BASE}?TrustedClientToken=${TRUSTED_CLIENT_TOKEN}` +
    `&Sec-MS-GEC=${sec}&Sec-MS-GEC-Version=${SEC_MS_GEC_VERSION}` +
    `&ConnectionId=${connId}`;

  return new Promise((resolve, reject) => {
    let ws;
    try {
      ws = new WebSocket(url);
    } catch (e) {
      return reject(e);
    }
    ws.binaryType = "arraybuffer";
    const chunks = [];
    const reqId = uuid();
    let gotAudio = false;

    const timeout = setTimeout(() => {
      try { ws.close(); } catch (_) {}
      reject(new Error("TTS timeout"));
    }, 20000);

    ws.onopen = () => {
      const config =
        `X-Timestamp:${nowStr()}\r\n` +
        `Content-Type:application/json; charset=utf-8\r\n` +
        `Path:speech.config\r\n\r\n` +
        `{"context":{"synthesis":{"audio":{"metadataoptions":` +
        `{"sentenceBoundaryEnabled":"false","wordBoundaryEnabled":"false"},` +
        `"outputFormat":"audio-24khz-48kbitrate-mono-mp3"}}}}`;
      ws.send(config);

      const ssml = buildSSML(text, voice, rate, pitch);
      const msg =
        `X-RequestId:${reqId}\r\n` +
        `Content-Type:application/ssml+xml\r\n` +
        `X-Timestamp:${nowStr()}Z\r\n` +
        `Path:ssml\r\n\r\n${ssml}`;
      ws.send(msg);
    };

    ws.onmessage = (ev) => {
      if (typeof ev.data === "string") {
        if (ev.data.includes("Path:turn.end")) {
          clearTimeout(timeout);
          try { ws.close(); } catch (_) {}
          if (!chunks.length) return reject(new Error("no audio"));
          let total = 0;
          chunks.forEach((c) => (total += c.length));
          const out = new Uint8Array(total);
          let off = 0;
          chunks.forEach((c) => {
            out.set(c, off);
            off += c.length;
          });
          resolve(uint8ToBase64(out));
        }
      } else {
        // Binary frame: [2-byte big-endian header length][header][audio bytes]
        const dv = new DataView(ev.data);
        const headerLen = dv.getUint16(0);
        const audio = new Uint8Array(ev.data, 2 + headerLen);
        if (audio.length) {
          chunks.push(audio);
          gotAudio = true;
        }
      }
    };

    ws.onerror = () => {
      clearTimeout(timeout);
      console.warn("[AZDUB-bg] TTS WebSocket error");
      reject(new Error("WebSocket error"));
    };
    ws.onclose = (ev) => {
      clearTimeout(timeout);
      if (!gotAudio) {
        console.warn("[AZDUB-bg] TTS closed before audio, code=", ev && ev.code);
        reject(new Error("closed before audio (code " + (ev && ev.code) + ")"));
      }
    };
  });
}

// ---------------------------------------------------------------------------
// TTS via a self-hosted edge-tts HTTPS proxy (e.g. a Hugging Face Space).
// This is the reliable path: edge-tts runs server-side where the WebSocket
// works, and we just fetch an MP3 over plain HTTPS.
// ---------------------------------------------------------------------------
async function ttsViaProxy(proxy, text, voice, rate, pitch) {
  const base = proxy.replace(/\/+$/, "");
  const url =
    base +
    "/tts?text=" +
    encodeURIComponent(text) +
    "&voice=" +
    encodeURIComponent(voice) +
    "&rate=" +
    encodeURIComponent(rate) +
    "&pitch=" +
    encodeURIComponent(pitch);
  const res = await fetch(url);
  if (!res.ok) throw new Error("proxy HTTP " + res.status);
  const buf = await res.arrayBuffer();
  if (!buf.byteLength) throw new Error("proxy empty audio");
  const mime = res.headers.get("X-AZDUB-TTS-Mime") || res.headers.get("Content-Type") || "audio/mpeg";
  return { audio: uint8ToBase64(new Uint8Array(buf)), mime: mime.split(";")[0] };
}

// ---------------------------------------------------------------------------
// Translation (free gtx endpoint, no API key)
// ---------------------------------------------------------------------------
function sleep(ms) {
  return new Promise((r) => setTimeout(r, ms));
}

async function translateGtx(host, text, targetLang) {
  const url =
    "https://" +
    host +
    "/translate_a/single?client=gtx&sl=auto&tl=" +
    encodeURIComponent(targetLang) +
    "&dt=t&q=" +
    encodeURIComponent(text);
  const res = await fetch(url);
  if (!res.ok) throw new Error("HTTP " + res.status);
  const data = await res.json();
  let out = "";
  if (Array.isArray(data[0])) {
    for (const seg of data[0]) if (seg && seg[0]) out += seg[0];
  }
  if (!out) throw new Error("empty translation");
  return { text: out, detected: data[2] || null };
}

async function translateMyMemory(text, targetLang, source) {
  const url =
    "https://api.mymemory.translated.net/get?q=" +
    encodeURIComponent(text) +
    "&langpair=" +
    encodeURIComponent((source || "en") + "|" + targetLang);
  const res = await fetch(url);
  if (!res.ok) throw new Error("HTTP " + res.status);
  const data = await res.json();
  const out = data && data.responseData && data.responseData.translatedText;
  if (!out) throw new Error("empty translation");
  return { text: out, detected: source || null };
}

async function translate(text, targetLang, source) {
  // Try Google gtx on two hosts, then MyMemory as an independent fallback.
  const providers = [
    () => translateGtx("translate.googleapis.com", text, targetLang),
    () => translateMyMemory(text, targetLang, source),
  ];
  let lastErr;
  for (const p of providers) {
    for (let attempt = 0; attempt < 2; attempt++) {
      try {
        return await p();
      } catch (e) {
        lastErr = e;
        await sleep(250 * (attempt + 1));
      }
    }
  }
  console.warn("[AZDUB-bg] translate failed:", String(lastErr));
  throw lastErr || new Error("translate failed");
}

// ---------------------------------------------------------------------------
// Capture YouTube's own timedtext request URL (it carries a valid `pot` token
// that the player-response baseUrl lacks). We re-fetch that exact URL ourselves.
// ---------------------------------------------------------------------------
const timedtextByTab = {};
try {
  chrome.webRequest.onBeforeRequest.addListener(
    (details) => {
      if (details.tabId >= 0 && /\/api\/timedtext/.test(details.url)) {
        timedtextByTab[details.tabId] = { url: details.url, t: Date.now() };
      }
    },
    { urls: ["*://www.youtube.com/api/timedtext*"] }
  );
} catch (e) {
  // webRequest unavailable; content script will fall back to the raw baseUrl
}

// ---------------------------------------------------------------------------
// Message router
// ---------------------------------------------------------------------------
chrome.runtime.onMessage.addListener((msg, sender, sendResponse) => {
  if (msg && msg.type === "getCaptionUrl") {
    const tabId = sender.tab && sender.tab.id;
    const rec = tabId != null ? timedtextByTab[tabId] : null;
    const fresh = rec && Date.now() - rec.t < 60000;
    sendResponse({ ok: true, url: fresh ? rec.url : null });
    return; // synchronous
  }
  if (msg && msg.type === "clearCaptionUrl") {
    const tabId = sender.tab && sender.tab.id;
    if (tabId != null) delete timedtextByTab[tabId];
    sendResponse({ ok: true });
    return;
  }
  if (msg && msg.type === "translate") {
    translate(msg.text, msg.target || "az", msg.source)
      .then((r) => sendResponse({ ok: true, ...r }))
      .catch((e) => sendResponse({ ok: false, error: String(e) }));
    return true;
  }
  if (msg && msg.type === "tts") {
    const voice = msg.voice || "az-AZ-BabekNeural";
    const rate = msg.rate || "+0%";
    const pitch = msg.pitch || "+0Hz";
    (async () => {
      // 1) self-hosted HTTPS proxy (preferred, corporate-friendly)
      if (msg.proxy) {
        try {
          const r = await ttsViaProxy(msg.proxy, msg.text, voice, rate, pitch);
          return sendResponse({ ok: true, audio: r.audio, mime: r.mime, via: "proxy" });
        } catch (e) {
          console.warn("[AZDUB-bg] proxy TTS failed:", String(e));
        }
      }
      // 2) direct Edge WebSocket (works off corporate networks)
      try {
        const b64 = await edgeTTS(msg.text, voice, rate, pitch);
        sendResponse({ ok: true, audio: b64, mime: "audio/mpeg", via: "wss" });
      } catch (e) {
        sendResponse({ ok: false, error: String(e) });
      }
    })();
    return true;
  }
});
