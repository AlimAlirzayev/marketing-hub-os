const assert = require("node:assert/strict");
const crypto = require("node:crypto");
const fs = require("node:fs");
const path = require("node:path");
const { spawnSync } = require("node:child_process");
const test = require("node:test");
const vm = require("node:vm");

const repoRoot = path.resolve(__dirname, "..", "..");
const extensionRoot = path.join(repoRoot, "azdub-extension");
const python =
  process.env.AZDUB_AUDIT_PYTHON ||
  path.join(repoRoot, ".audit-tools", "py312-venv", "Scripts", "python.exe");

function extractFunction(source, name) {
  const start = source.indexOf(`function ${name}`);
  if (start < 0) throw new Error(`missing function ${name}`);
  const brace = source.indexOf("{", start);
  let depth = 0;
  for (let i = brace; i < source.length; i++) {
    const c = source[i];
    if (c === "{") depth++;
    if (c === "}") depth--;
    if (depth === 0) return source.slice(start, i + 1);
  }
  throw new Error(`unterminated function ${name}`);
}

function extractAsyncFunction(source, name) {
  const start = source.indexOf(`async function ${name}`);
  if (start < 0) throw new Error(`missing async function ${name}`);
  const brace = source.indexOf("{", start);
  let depth = 0;
  for (let i = brace; i < source.length; i++) {
    const c = source[i];
    if (c === "{") depth++;
    if (c === "}") depth--;
    if (depth === 0) return source.slice(start, i + 1);
  }
  throw new Error(`unterminated async function ${name}`);
}

function extractConst(source, name) {
  const re = new RegExp(`const ${name} = ([^;]+);`);
  const match = source.match(re);
  if (!match) throw new Error(`missing const ${name}`);
  return `const ${name} = ${match[1]};`;
}

function loadBackgroundAt(timestampSeconds) {
  const source = fs.readFileSync(path.join(extensionRoot, "background.js"), "utf8");
  const fixedDate = class extends Date {
    static now() {
      return timestampSeconds * 1000;
    }
  };
  const context = {
    crypto: crypto.webcrypto,
    Date: fixedDate,
    TextEncoder,
  };
  vm.runInNewContext(
    [
      extractConst(source, "TRUSTED_CLIENT_TOKEN"),
      extractConst(source, "WIN_EPOCH"),
      extractConst(source, "S_TO_NS"),
      extractAsyncFunction(source, "generateSecMsGec"),
      "globalThis.__out = { generateSecMsGec };",
    ].join("\n"),
    context
  );
  return context.__out;
}

function loadContentFunctions() {
  const source = fs.readFileSync(path.join(extensionRoot, "content.js"), "utf8");
  const { DOMParser, parseHTML } = require(path.join(
    repoRoot,
    ".audit-tools",
    "node_modules",
    "linkedom"
  ));
  const { document: linkeDocument } = parseHTML(
    "<!doctype html><html><body></body></html>"
  );
  const document = {
    createElement(tag) {
      if (tag.toLowerCase() !== "textarea") return linkeDocument.createElement(tag);
      let value = "";
      return {
        set innerHTML(input) {
          value = String(input)
            .replace(/&quot;/g, '"')
            .replace(/&#39;/g, "'")
            .replace(/&apos;/g, "'")
            .replace(/&lt;/g, "<")
            .replace(/&gt;/g, ">")
            .replace(/&amp;/g, "&");
        },
        get value() {
          return value;
        },
      };
    },
  };
  const context = { DOMParser, document };
  vm.runInNewContext(
    [
      extractFunction(source, "decodeEntities"),
      extractFunction(source, "parseJson3"),
      extractFunction(source, "parseXmlTranscript"),
      extractFunction(source, "buildPhrases"),
      extractFunction(source, "lastWords"),
      extractFunction(source, "deltaWords"),
      "globalThis.__out = { parseJson3, parseXmlTranscript, buildPhrases, lastWords, deltaWords };",
    ].join("\n"),
    context
  );
  return context.__out;
}

function pythonSecMsGec(timestampSeconds) {
  const script = `
import edge_tts.drm as drm
drm.DRM.get_unix_timestamp = staticmethod(lambda: ${JSON.stringify(timestampSeconds)})
print(drm.DRM.generate_sec_ms_gec())
`;
  const result = spawnSync(python, ["-c", script], {
    encoding: "utf8",
    windowsHide: true,
  });
  if (result.status !== 0) {
    throw new Error(`python edge-tts failed: ${result.stderr || result.stdout}`);
  }
  return result.stdout.trim();
}

test("generateSecMsGec matches Python edge_tts across 5-minute boundaries", async () => {
  const timestamps = [
    1710000000.123,
    1710000299.999,
    1710000300.0,
    1710000600.456,
    1710000901.789,
  ];
  const values = [];
  for (const ts of timestamps) {
    const js = await loadBackgroundAt(ts).generateSecMsGec();
    const py = pythonSecMsGec(ts);
    values.push({ ts, js, py });
    assert.equal(js, py, `Sec-MS-GEC mismatch at ${ts}: JS=${js} PY=${py}`);
  }
  console.log("SEC_MS_GEC_PARITY_VALUES", JSON.stringify(values));
});

test("deltaWords and lastWords preserve rolling ASR captions without duplicates", () => {
  const { deltaWords, lastWords } = loadContentFunctions();
  const windows = [
    "alpha bravo charlie",
    "bravo charlie delta",
    "charlie delta echo",
    "delta echo foxtrot",
    "echo foxtrot golf",
    "foxtrot golf hotel",
    "golf hotel india",
  ];
  let tail = "";
  let captured = "";
  for (const cur of windows) {
    const delta = deltaWords(tail, cur);
    if (delta) {
      captured = (captured + " " + delta).trim();
      tail = lastWords((tail + " " + delta).trim(), 30);
    }
  }
  assert.equal(
    captured,
    "alpha bravo charlie delta echo foxtrot golf hotel india"
  );

  tail = "";
  captured = "";
  for (const cur of [
    "one two",
    "one two",
    "one two three",
    "two three four",
    "three four five",
  ]) {
    const delta = deltaWords(tail, cur);
    if (delta) {
      captured = (captured + " " + delta).trim();
      tail = lastWords((tail + " " + delta).trim(), 30);
    }
  }
  assert.equal(captured, "one two three four five");
});

test("buildPhrases splits on sentence end, large gap, and max phrase length", () => {
  const { buildPhrases } = loadContentFunctions();
  assert.deepEqual(
    JSON.parse(JSON.stringify(buildPhrases([
      { startMs: 0, durMs: 400, text: "First sentence." },
      { startMs: 500, durMs: 400, text: "Second sentence" },
    ]).map((p) => p.text))),
    ["First sentence.", "Second sentence"]
  );

  assert.deepEqual(
    JSON.parse(JSON.stringify(buildPhrases([
      { startMs: 0, durMs: 400, text: "Before gap" },
      { startMs: 1500, durMs: 300, text: "After gap" },
    ]).map((p) => p.text))),
    ["Before gap", "After gap"]
  );

  const longA = "a".repeat(100);
  const longB = "b".repeat(90);
  assert.deepEqual(
    JSON.parse(JSON.stringify(buildPhrases([
      { startMs: 0, durMs: 400, text: longA },
      { startMs: 450, durMs: 400, text: longB },
    ]).map((p) => p.text))),
    [longA, longB]
  );
});

test("parseJson3 extracts timed caption events", () => {
  const { parseJson3 } = loadContentFunctions();
  const segs = parseJson3({
    events: [
      {
        tStartMs: 1250,
        dDurationMs: 2200,
        segs: [{ utf8: "Hello" }, { utf8: "\n" }, { utf8: "world" }],
      },
      { tStartMs: 5000, dDurationMs: 1000, segs: [{ utf8: "   " }] },
      { tStartMs: 6200, segs: [{ utf8: "Next line" }] },
    ],
  });
  assert.deepEqual(JSON.parse(JSON.stringify(segs)), [
    { startMs: 1250, durMs: 2200, text: "Hello world" },
    { startMs: 6200, durMs: 0, text: "Next line" },
  ]);
});

test("parseXmlTranscript extracts srv1 and srv3 with HTML entity decoding", () => {
  const { parseXmlTranscript } = loadContentFunctions();
  const srv1 =
    '<transcript><text start="1.5" dur="2.25">Tom &amp;amp; Jerry &amp;quot;go&amp;quot;</text></transcript>';
  assert.deepEqual(JSON.parse(JSON.stringify(parseXmlTranscript(srv1))), [
    { startMs: 1500, durMs: 2250, text: 'Tom & Jerry "go"' },
  ]);

  const srv3 =
    '<timedtext><body><p t="1500" d="3200"><s>Alpha </s><s>&amp;amp; beta</s></p></body></timedtext>';
  assert.deepEqual(JSON.parse(JSON.stringify(parseXmlTranscript(srv3))), [
    { startMs: 1500, durMs: 3200, text: "Alpha & beta" },
  ]);
});
