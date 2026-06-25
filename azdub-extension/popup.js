const DEFAULTS = {
  enabled: true,
  targetLang: "az",
  voice: "az-AZ-BabekNeural",
  rate: "+0%",
  pitch: "+0Hz",
  skipLangs: ["az", "tr"],
  muteOriginal: true,
  duckVolume: 0.08,
  useBrowserFallback: false,
  ttsProxyUrl: "",
  ahead: 6,
};

const $ = (id) => document.getElementById(id);

function rateToNum(s) {
  const m = /(-?\d+)/.exec(s || "");
  return m ? parseInt(m[1], 10) : 0;
}
function numToRate(n) {
  return (n >= 0 ? "+" : "") + n + "%";
}

async function init() {
  const s = await chrome.storage.sync.get(DEFAULTS);

  $("enabled").checked = !!s.enabled;
  $("targetLang").value = s.targetLang || "az";
  $("voice").value = s.voice;
  const rn = rateToNum(s.rate);
  $("rate").value = rn;
  $("rateVal").textContent = (rn >= 0 ? "+" : "") + rn + "%";
  $("origMute").checked = !!s.muteOriginal;
  $("origDuck").checked = !s.muteOriginal;
  $("skip").value = (s.skipLangs || []).join(", ");
  $("fallback").checked = !!s.useBrowserFallback;
  $("proxy").value = s.ttsProxyUrl || "";

  const save = (patch) => chrome.storage.sync.set(patch);

  $("enabled").addEventListener("change", (e) =>
    save({ enabled: e.target.checked })
  );
  $("targetLang").addEventListener("change", (e) =>
    save({ targetLang: e.target.value })
  );
  $("voice").addEventListener("change", (e) => save({ voice: e.target.value }));
  $("rate").addEventListener("input", (e) => {
    const n = parseInt(e.target.value, 10);
    $("rateVal").textContent = (n >= 0 ? "+" : "") + n + "%";
    save({ rate: numToRate(n) });
  });
  $("origMute").addEventListener("change", () => save({ muteOriginal: true }));
  $("origDuck").addEventListener("change", () => save({ muteOriginal: false }));
  $("skip").addEventListener("change", (e) => {
    const langs = e.target.value
      .split(",")
      .map((x) => x.trim().toLowerCase())
      .filter(Boolean);
    save({ skipLangs: langs.length ? langs : ["az", "tr"] });
  });
  $("fallback").addEventListener("change", (e) =>
    save({ useBrowserFallback: e.target.checked })
  );
  $("proxy").addEventListener("change", (e) =>
    save({ ttsProxyUrl: e.target.value.trim().replace(/\/+$/, "") })
  );
}

init();
