const fs = require("node:fs");
const path = require("node:path");
const { chromium } = require(path.resolve(
  __dirname,
  "..",
  "..",
  ".audit-tools",
  "node_modules",
  "playwright"
));

const repoRoot = path.resolve(__dirname, "..", "..");
const extensionPath = path.join(repoRoot, "azdub-extension");
const userDataDir = path.join(repoRoot, ".audit-tools", "pw-azdub-profile");

const videos = {
  english: "https://www.youtube.com/watch?v=nIwU-9ZTTJc",
  turkish: "https://www.youtube.com/watch?v=oB2u8dbYQLI",
  azerbaijani: "https://www.youtube.com/watch?v=g4i6_6fMwCs",
};

async function wait(ms) {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

async function getServiceWorker(context) {
  let [worker] = context.serviceWorkers();
  if (!worker) worker = await context.waitForEvent("serviceworker", { timeout: 15000 });
  return worker;
}

async function patchBackgroundLogs(worker) {
  await worker.evaluate(() => {
    if (globalThis.__azdubAuditConsolePatched) return;
    globalThis.__azdubAuditConsolePatched = true;
    globalThis.__azdubAuditLogs = [];
    for (const level of ["log", "warn", "error"]) {
      const original = console[level].bind(console);
      console[level] = (...args) => {
        try {
          globalThis.__azdubAuditLogs.push({
            level,
            text: args.map((x) => String(x)).join(" "),
            t: Date.now(),
          });
        } catch (_) {}
        original(...args);
      };
    }
  });
}

async function setExtensionSettings(worker) {
  await worker.evaluate(
    (settings) =>
      new Promise((resolve) => {
        chrome.storage.sync.set(settings, resolve);
      }),
    {
      enabled: true,
      voice: "az-AZ-BabekNeural",
      rate: "+0%",
      pitch: "+0Hz",
      skipLangs: ["az", "tr"],
      muteOriginal: true,
      useBrowserFallback: false,
      ttsProxyUrl: "http://127.0.0.1:7860",
      ahead: 2,
    }
  );
}

async function acceptConsent(page) {
  for (const label of [
    "Accept all",
    "Reject all",
    "I agree",
    "Agree",
    "Accept",
    "Raziyam",
  ]) {
    try {
      const button = page.getByRole("button", { name: new RegExp(label, "i") });
      if (await button.first().isVisible({ timeout: 1000 })) {
        await button.first().click({ timeout: 3000 });
        await wait(1000);
        return true;
      }
    } catch (_) {}
  }
  return false;
}

async function startVideo(page) {
  await page.waitForSelector("video", { timeout: 30000 });
  await page.evaluate(() => {
    const autonav = document.querySelector(".ytp-autonav-toggle-button");
    if (autonav && autonav.getAttribute("aria-checked") === "true") {
      autonav.click();
    }
  });
  try {
    const playButton = page.locator(".ytp-play-button");
    if (await playButton.first().isVisible({ timeout: 3000 })) {
      const title = (await playButton.first().getAttribute("title")) || "";
      const label = (await playButton.first().getAttribute("aria-label")) || "";
      if (/play/i.test(title + " " + label)) {
        await playButton.first().click({ timeout: 5000 });
      }
    }
  } catch (_) {
    try {
      await page.locator("video").click({ force: true, timeout: 5000 });
    } catch (_) {}
  }
  return await page.evaluate(async () => {
    const video = document.querySelector("video");
    if (!video) return { ok: false, error: "no video" };
    try {
      await video.play();
      return { ok: true, paused: video.paused, currentTime: video.currentTime };
    } catch (e) {
      return { ok: false, error: String(e), paused: video.paused };
    }
  });
}

async function snapshot(page) {
  return await page.evaluate(() => {
    const video = document.querySelector("video");
    const mp = document.getElementById("movie_player");
    const captionContainer =
      document.querySelector(".ytp-caption-window-container") ||
      document.querySelector(".caption-window");
    return {
      url: location.href,
      title: document.title,
      status: document.querySelector("#azdub-status")?.textContent || "",
      video: video
        ? {
            muted: video.muted,
            paused: video.paused,
            currentTime: Number(video.currentTime.toFixed(2)),
            playbackRate: video.playbackRate,
            readyState: video.readyState,
            networkState: video.networkState,
            error: video.error ? video.error.message || String(video.error.code) : "",
          }
        : null,
      playerState:
        mp && mp.getPlayerState
          ? (() => {
              try {
                return mp.getPlayerState();
              } catch (_) {
                return null;
              }
            })()
          : null,
      youtubeDom: {
        hasMoviePlayer: !!mp,
        hasGetPlayerResponse: !!(mp && mp.getPlayerResponse),
        hasSetOption: !!(mp && mp.setOption),
        hasCaptionContainer: !!captionContainer,
        captionSegments: document.querySelectorAll(".ytp-caption-segment").length,
      },
    };
  });
}

async function runVideo(page, label, url, observeMs) {
  const logs = [];
  const onConsole = (msg) => {
    const text = msg.text();
    if (text.includes("[AZDUB]")) logs.push({ type: msg.type(), text });
  };
  page.on("console", onConsole);
  await page.goto(url, { waitUntil: "domcontentloaded", timeout: 60000 });
  await acceptConsent(page);
  const playResult = await startVideo(page);
  for (let i = 0; i < 10; i++) {
    await wait(1000);
    await page.evaluate(() => {
      const video = document.querySelector("video");
      if (video && video.paused) video.play().catch(() => {});
    });
  }
  await wait(observeMs);
  const state = await snapshot(page);
  page.off("console", onConsole);
  return { label, url, playResult, state, logs };
}

(async () => {
  if (fs.existsSync(userDataDir)) fs.rmSync(userDataDir, { recursive: true, force: true });
  const context = await chromium.launchPersistentContext(userDataDir, {
    headless: false,
    viewport: { width: 1280, height: 900 },
    locale: "en-US",
    args: [
      `--disable-extensions-except=${extensionPath}`,
      `--load-extension=${extensionPath}`,
      "--no-first-run",
      "--disable-features=Translate",
    ],
  });

  const page = await context.newPage();
  const worker = await getServiceWorker(context);
  await patchBackgroundLogs(worker);
  await setExtensionSettings(worker);
  const extensionId = new URL(worker.url()).hostname;

  const results = [];
  results.push(await runVideo(page, "english", videos.english, 60000));
  results.push(await runVideo(page, "turkish", videos.turkish, 12000));
  results.push(await runVideo(page, "azerbaijani", videos.azerbaijani, 12000));

  const bgLogs = await worker.evaluate(() => globalThis.__azdubAuditLogs || []);
  await context.close();

  console.log(
    JSON.stringify(
      {
        extensionId,
        videos,
        results,
        bgLogs: bgLogs.filter((l) => l.text.includes("[AZDUB-bg]")),
      },
      null,
      2
    )
  );
})().catch((err) => {
  console.error(err);
  process.exit(1);
});
