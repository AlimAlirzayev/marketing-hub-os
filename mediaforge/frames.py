"""Keyframes-first stage: storyboard beats -> directed still frames.

This is the professional step between the script and the video spend: every
beat gets 1..N cheap keyframe stills (Seedream v3, ~28 credits each) rendered
in ONE style bible, so the human approves the LOOK while it still costs cents.
The approved frames then drive the free local animatic and the paid beat
animation.

Artifacts inside the package folder:
    frames/beat{i}_v{j}.png      generated keyframes
    frames/frames_plan.json      specs + prompts + run metadata
    frames/selection.json        chosen variant per beat
    frames/contact-sheet.html    visual picker (radio per beat -> pick command)
"""

from __future__ import annotations

import html
import json
import re
import time
import urllib.request
from pathlib import Path
from typing import Any

from . import knowledge

DEFAULT_IMAGE_MODEL = "t2i-seedream-v3"      # 28 cr, native 9:16
IMAGE_MODEL_CREDITS = {"t2i-seedream-v3": 28, "t2i-flux-2-turbo": 9, "t2i-flux-2": 10}

_TIME_RE = re.compile(r"(\d+(?:\.\d+)?)\s*-\s*(\d+(?:\.\d+)?)")


def parse_beat_seconds(storyboard: list[dict[str, Any]]) -> list[float]:
    """Beat 'time' strings ('0.0-1.5s') -> per-beat durations in seconds."""
    durations: list[float] = []
    for beat in storyboard:
        m = _TIME_RE.search(str(beat.get("time", "")))
        if m:
            start, end = float(m.group(1)), float(m.group(2))
            durations.append(max(0.5, end - start))
        else:
            durations.append(2.5)
    return durations


def plan_frames(pkg: dict[str, Any], *, variants: int = 2,
                model: str = DEFAULT_IMAGE_MODEL) -> dict[str, Any]:
    """Build the keyframe generation plan (no network, no spend)."""
    brief = pkg["brief"]
    category = pkg["request"]["category"]
    # Optional per-campaign character override (brief["character_direction"]) —
    # lets non-protagonist concepts (giant hand, mascot, product-as-hero) veto
    # the style bible's default human character.
    character = brief.get("character_direction")
    shots = ["hero wide establishing shot", "medium shot, handheld intimacy",
             "close-up on the human moment", "medium-wide, stable settled framing"]
    beats = []
    for i, beat in enumerate(brief["storyboard"]):
        prompt = knowledge.compose_keyframe_prompt(
            category, beat["visual"], wide_or_close=shots[i % len(shots)],
            character=character,
        )
        beats.append({
            "index": i,
            "beat": beat["beat"],
            "time": beat["time"],
            "prompt": prompt,
            "variants": variants,
        })
    per_image = IMAGE_MODEL_CREDITS.get(model, 30)
    return {
        "model": model,
        "params": {"aspect_ratio": "9:16"},
        "beats": beats,
        "total_images": len(beats) * variants,
        "estimated_credits": len(beats) * variants * per_image,
        "style_bible": knowledge.style_bible_for(category)["name"],
        "character": character or knowledge.character_block(category),
    }


def generate_frames(pkg: dict[str, Any], folder: Path, *, variants: int = 2,
                    model: str = DEFAULT_IMAGE_MODEL) -> dict[str, Any]:
    """Generate all keyframes on FLORA (PAID — caller holds the cost gate)."""
    from .flora_client import FloraMCP

    plan = plan_frames(pkg, variants=variants, model=model)
    frames_dir = folder / "frames"
    frames_dir.mkdir(parents=True, exist_ok=True)

    flora = FloraMCP()
    results: list[dict[str, Any]] = []
    total_cost = 0.0
    try:
        ws = flora.default_workspace_id()
        proj = flora.ensure_project(ws, f"Media Studio — {pkg['brief']['campaign']['name']}"[:60])
        project_id = proj["project_id"]

        runs: list[dict[str, Any]] = []
        for spec in plan["beats"]:
            for v in range(1, spec["variants"] + 1):
                gen = flora.generate_media(
                    media_type="image", workspace_id=ws, project_id=project_id,
                    model=model, prompt=spec["prompt"], params=dict(plan["params"]),
                )
                total_cost += float(gen.get("charged_cost") or 0)
                runs.append({"beat": spec["index"], "variant": v,
                             "run_id": gen.get("run_id"), "beat_name": spec["beat"]})

        for r in runs:
            url = _wait_for_output(flora, r["run_id"], want_type="imageUrl")
            r["ok"] = bool(url)
            if url:
                dest = frames_dir / f"beat{r['beat']}_v{r['variant']}.png"
                urllib.request.urlretrieve(url, dest)
                r["file"] = dest.name
            results.append(r)
    finally:
        flora.close()

    plan_out = {**plan, "runs": results, "charged_cost_usd": round(total_cost, 4),
                "generated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())}
    (frames_dir / "frames_plan.json").write_text(
        json.dumps(plan_out, ensure_ascii=False, indent=2), encoding="utf-8")

    default_sel = {str(spec["index"]): 1 for spec in plan["beats"]}
    sel_path = frames_dir / "selection.json"
    if not sel_path.exists():
        sel_path.write_text(json.dumps(default_sel, indent=2), encoding="utf-8")

    (frames_dir / "contact-sheet.html").write_text(
        render_contact_sheet(pkg, plan_out), encoding="utf-8")
    return plan_out


def _wait_for_output(flora, run_id: str, *, want_type: str, timeout_s: float = 420) -> str | None:
    deadline = time.time() + timeout_s
    while time.time() < deadline:
        run_obj = flora.get_run(run_id)
        status = (run_obj.get("status") or "").lower()
        outs = run_obj.get("outputs") or []
        if isinstance(outs, dict):
            outs = [outs]
        for o in outs:
            if o.get("type") == want_type and o.get("url"):
                return o["url"]
        if status in {"failed", "error"}:
            return None
        if status in {"completed", "succeeded", "done"}:
            return None
        time.sleep(6)
    return None


def load_selection(folder: Path, storyboard_len: int) -> dict[int, int]:
    sel_path = folder / "frames" / "selection.json"
    sel = {i: 1 for i in range(storyboard_len)}
    if sel_path.exists():
        try:
            raw = json.loads(sel_path.read_text(encoding="utf-8"))
            for k, v in raw.items():
                sel[int(k)] = int(v)
        except (ValueError, KeyError):
            pass
    return sel


def apply_picks(folder: Path, picks: str) -> dict[int, int]:
    """--pick '1=2,3=1' (1-based beat=variant) -> update selection.json."""
    frames_dir = folder / "frames"
    frames_dir.mkdir(parents=True, exist_ok=True)
    sel_path = frames_dir / "selection.json"
    sel: dict[str, int] = {}
    if sel_path.exists():
        sel = json.loads(sel_path.read_text(encoding="utf-8"))
    for part in picks.split(","):
        if "=" in part:
            beat, variant = part.split("=", 1)
            sel[str(int(beat) - 1)] = int(variant)
    sel_path.write_text(json.dumps(sel, indent=2), encoding="utf-8")
    return {int(k): v for k, v in sel.items()}


def selected_frame_paths(folder: Path, storyboard_len: int) -> list[Path | None]:
    sel = load_selection(folder, storyboard_len)
    out: list[Path | None] = []
    for i in range(storyboard_len):
        p = folder / "frames" / f"beat{i}_v{sel.get(i, 1)}.png"
        out.append(p if p.exists() else None)
    return out


def render_contact_sheet(pkg: dict[str, Any], plan: dict[str, Any]) -> str:
    """Self-contained HTML picker: radio per beat, JS builds the pick command."""
    slug = pkg["slug"]
    rows = []
    for spec in plan["beats"]:
        i = spec["index"]
        cells = []
        for v in range(1, spec["variants"] + 1):
            fname = f"beat{i}_v{v}.png"
            cells.append(f"""
        <label class="cell">
          <input type="radio" name="beat{i}" value="{v}" {'checked' if v == 1 else ''}
                 onchange="upd()">
          <img src="{fname}" loading="lazy">
          <span>v{v}</span>
        </label>""")
        rows.append(f"""
    <section>
      <h2>{i + 1}. {html.escape(spec['beat'])} <small>{html.escape(spec['time'])}</small></h2>
      <div class="row">{''.join(cells)}</div>
    </section>""")

    return f"""<!DOCTYPE html>
<html lang="az"><head><meta charset="UTF-8"><title>Contact Sheet — {html.escape(slug)}</title>
<style>
 body{{background:#0a0a0c;color:#f4f4f5;font-family:'Segoe UI',Arial;margin:0;padding:32px}}
 h1{{font-size:24px}} h2{{font-size:16px;margin:18px 0 8px}} small{{color:#7fb2ff;font-family:Consolas}}
 .row{{display:flex;gap:14px;flex-wrap:wrap}}
 .cell{{cursor:pointer;text-align:center}}
 .cell img{{width:200px;border-radius:10px;border:3px solid transparent;display:block}}
 .cell input{{display:none}}
 .cell input:checked + img{{border-color:#E31E24}}
 .cell span{{color:#a9a9b2;font-size:12px}}
 #cmd{{position:sticky;bottom:0;background:#141417;border:1px solid #2b2b31;border-radius:12px;
      padding:14px;margin-top:24px;font-family:Consolas;font-size:13px;color:#d5e5ff}}
 button{{background:#E31E24;color:#fff;border:none;border-radius:8px;padding:8px 14px;cursor:pointer;margin-left:10px}}
</style></head><body>
<h1>🎬 Keyframe seçimi — {html.escape(slug)}</h1>
<p style="color:#a9a9b2">Hər beat üçün ən yaxşı kadrı seç. Seçim Studio API-yə yazılır.</p>
{''.join(rows)}
<div id="cmd"><span id="cmdText"></span><button onclick="savePicks()">Yadda saxla</button><span id="saveStatus" style="margin-left:12px;color:#a9a9b2"></span></div>
<script>
function currentPicks(){{
  const picks = [];
  document.querySelectorAll('section').forEach((s, i) => {{
    const c = s.querySelector('input:checked');
    if (c) picks.push((i + 1) + '=' + c.value);
  }});
  return picks;
}}
function upd(){{
  document.getElementById('cmdText').innerText = 'Seçim: ' + currentPicks().join(', ');
}}
async function savePicks(){{
  const status = document.getElementById('saveStatus');
  status.innerText = 'Yazılır...';
  try {{
    const res = await fetch('/api/generate/{slug}/run', {{
      method: 'POST',
      headers: {{'Content-Type': 'application/json'}},
      body: JSON.stringify({{stage: 'pick', picks: currentPicks().join(',')}})
    }});
    const data = await res.json();
    if (!res.ok || data.error) throw new Error(data.error || 'save error');
    status.innerText = 'Yadda saxlandı. Studio-da Animatic düyməsini bas.';
  }} catch (e) {{
    status.innerText = 'Xəta: ' + e.message;
  }}
}}
upd();
</script>
</body></html>"""
