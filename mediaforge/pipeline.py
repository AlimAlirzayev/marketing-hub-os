"""One-command orchestrator: sentence -> full production package.

Ties MediaForge's brain to the existing FLORA prompt compiler and campaign
folder structure. Produces everything up to the single paid generation step:
    - a schema-valid brief.json in the campaign folder
    - a compiled FLORA prompt (reusing scripts/compile_generative_ad.py)
    - a human-readable concept + storyboard
    - a visual storyboard board (SVG filmstrip) — a real artifact, no deps
    - a ready-to-fire FLORA generation command with a cost gate

It never spends credits or posts. Generation stays behind a human OAuth + cost
checkpoint, per config/agent_permissions.json (flora_ai_mcp: draft_only).
"""

from __future__ import annotations

import html
import importlib.util
import json
import time
from pathlib import Path
from typing import Any

from . import director


ROOT = Path(__file__).resolve().parent.parent
# Generated packages are regenerable runtime artifacts → keep them out of the
# tracked video-studio/generative_ads/campaigns dir (which holds hand-authored
# reference campaigns like kasko-qurban-2026). This whole tree is gitignored.
CAMPAIGNS = ROOT / "output" / "mediaforge" / "campaigns"
COMPILE_SCRIPT = ROOT / "scripts" / "compile_generative_ad.py"
RUN_LOG = ROOT / "output" / "mediaforge" / "runs.jsonl"


def _rel(path: Path) -> str:
    """Path relative to repo root when possible; otherwise the absolute path.

    Keeps output tidy in normal use but never crashes for out-of-tree paths
    (e.g. a temp dir in tests)."""
    try:
        return str(path.relative_to(ROOT))
    except ValueError:
        return str(path)


def _load_compiler():
    spec = importlib.util.spec_from_file_location("compile_generative_ad", COMPILE_SCRIPT)
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(module)
    return module


def create(sentence: str, *, use_llm: bool = True) -> dict[str, Any]:
    """Run the full pipeline for one natural-language request."""
    result = director.direct(sentence, use_llm=use_llm)
    brief = result["brief"]
    slug = brief["campaign"]["slug"]
    folder = CAMPAIGNS / slug
    (folder / "prompts").mkdir(parents=True, exist_ok=True)

    # 1. brief.json
    brief_path = folder / "brief.json"
    brief_path.write_text(json.dumps(brief, ensure_ascii=False, indent=2), encoding="utf-8")

    # 2. compiled FLORA prompt (reuse the existing compiler)
    compiled_path = folder / "prompts" / "compiled-flora-prompt.md"
    try:
        compiler = _load_compiler()
        compiled_path.write_text(compiler.compile_prompt(brief), encoding="utf-8")
        compiled_ok = True
    except Exception as exc:  # noqa: BLE001
        compiled_path.write_text(f"# Compile failed\n\n{exc}\n", encoding="utf-8")
        compiled_ok = False

    # 3. concept + storyboard (human readable)
    concept_md = _render_concept(result)
    (folder / "concept.md").write_text(concept_md, encoding="utf-8")
    storyboard_md = _render_storyboard(brief)
    (folder / "storyboard.md").write_text(storyboard_md, encoding="utf-8")

    # 4. visual storyboard board (SVG filmstrip artifact)
    board_svg = render_board_svg(result)
    board_path = folder / "storyboard-board.svg"
    board_path.write_text(board_svg, encoding="utf-8")

    # 5. ready-to-fire command + cost gate
    gen = _generation_plan(result, compiled_path)
    (folder / "ready-command.md").write_text(gen["ready_markdown"], encoding="utf-8")

    package = {
        "slug": slug,
        "sentence": sentence,
        "request": result["request"],
        "resolution": result["resolution"],
        "concept": result["concept"],
        "brief": brief,
        "meta": result["meta"],
        "generation": gen,
        "artifacts": {
            "folder": _rel(folder),
            "brief": _rel(brief_path),
            "compiled_prompt": _rel(compiled_path),
            "compiled_ok": compiled_ok,
            "concept": _rel(folder / "concept.md"),
            "storyboard": _rel(folder / "storyboard.md"),
            "board_svg": _rel(board_path),
            "ready_command": _rel(folder / "ready-command.md"),
        },
    }
    (folder / "package.json").write_text(
        json.dumps(package, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    _log_run(package)
    _remember(package)
    return package


# --------------------------------------------------------------------------- #
# Generation plan + cost gate
# --------------------------------------------------------------------------- #
def _generation_plan(result: dict[str, Any], compiled_path: Path) -> dict[str, Any]:
    res = result["resolution"]
    brief = result["brief"]
    fmt = brief["format"]
    models_list = brief["model_strategy"]["recommended"]

    cli_cmds = []
    for mid in models_list:
        cli_cmds.append(
            "flora --format json generations create "
            "--workspace-id <WORKSPACE_ID> --project-id <PROJECT_ID> "
            f"--type {'video'} --model {mid} "
            '--prompt "<PASTE compiled-flora-prompt.md>" '
            f"--params '{{\"aspect_ratio\":\"{fmt['aspect']}\",\"duration\":\"{fmt['duration_s']}\"}}'"
        )

    slug = brief["campaign"]["slug"]
    fire_command = f"python -m mediaforge.generate {slug} --pro --confirm"
    mcp_instruction = (
        f"Peşəkar yol: `python -m mediaforge.generate {slug}` planı göstərir; "
        f"`--frames --confirm` (keyframe-lər, ~qəpiklər) → contact-sheet-də seç → "
        f"`--animatic` (pulsuz) → `--beats --confirm` (beat videolar + stitch). "
        f"Hamısı bir yerdə: `{fire_command}`."
    )

    ready_md = _render_ready_command(result, cli_cmds, mcp_instruction, compiled_path, fire_command)

    return {
        "status": "ready_for_generation",
        "can_autofire": False,
        "gate_reason": (
            "FLORA generasiya real kredit xərcləyir. Governance: flora_ai_mcp = "
            "draft_only + harness ödənişli əməli bloklayır — sistem krediti avtomatik "
            f"xərcləmir. Bir əmrlə sən işə sal: `{fire_command}`."
        ),
        "cost_band": res["cost_band"],
        "credits": res.get("credits"),
        "primary_model": res["model_id"],
        "second_variant": res["partner_id"],
        "fire_command": fire_command,
        "plan_command": f"python -m mediaforge.generate {slug}",
        "mcp_instruction": mcp_instruction,
        "cli_commands": cli_cmds,
        "manual_step": "FLORA OAuth artıq tamamlanıb (token cache-də) — birbaşa fire komandası işləyir.",
        "ready_markdown": ready_md,
    }


# --------------------------------------------------------------------------- #
# Renderers
# --------------------------------------------------------------------------- #
def _render_concept(result: dict[str, Any]) -> str:
    c = result["concept"]
    r = result["resolution"]
    req = result["request"]
    meta = result["meta"]
    notes = "\n".join(f"- {n}" for n in r.get("notes", [])) or "- (yoxdur)"
    return f"""# Kreativ konsepsiya — {c.get('name', '')}

Sorğu: "{req['raw']}"

- Böyük ideya: {c.get('big_idea', '')}
- Emosional qövs: {c.get('emotional_arc', '')}
- Framework: {c.get('framework', '')}
- Niyə işləyir: {c.get('why_it_works', '')}

## Model qərarı
- Seçilən model: {r['label']} (`{r['model_id']}`), tier: {r['tier']}, xərc bandı: {r['cost_band']}
- İkinci variant: {r['partner_label']} (`{r['partner_id']}`)
- Müddət: {r['duration_s']}s (istənilən: {r['requested_duration_s']}s)
- Qeydlər:
{notes}

## Mühərrik
- Brief mühərriki: {meta['engine']}{' (' + meta['llm_model'] + ')' if meta.get('llm_model') else ''}
- Schema keçərli: {meta['valid']}
"""


def _render_storyboard(brief: dict[str, Any]) -> str:
    lines = [f"# Storyboard — {brief['campaign']['name']}", ""]
    for b in brief["storyboard"]:
        lines += [
            f"## {b['time']} — {b['beat']}",
            f"- Görüntü: {b['visual']}",
            f"- Hərəkət: {b['motion']}",
            f"- Overlay (deterministik): {b['overlay'] or '(bu beat-də mətn yoxdur)'}",
            "",
        ]
    lines += ["## Overlay mətnləri (deterministik)", ""]
    lines += [f"- {t}" for t in brief["text_policy"]["overlay_text"]]
    return "\n".join(lines) + "\n"


def _render_ready_command(result, cli_cmds, mcp_instruction, compiled_path, fire_command) -> str:
    r = result["resolution"]
    rel = _rel(compiled_path)
    cli_block = "\n".join(cli_cmds)
    slug = result["brief"]["campaign"]["slug"]
    return f"""# İşə salmağa hazır — FLORA generasiya

Model: **{r['label']}** (`{r['model_id']}`) · Müddət: {r['duration_s']}s · Xərc: {r['cost_band']}

## Peşəkar pipeline (keyframes-first)
```powershell
python -m mediaforge.generate {slug}                     # plan + bütün mərhələ xərcləri
python -m mediaforge.generate {slug} --frames --confirm  # 1) keyframe-lər (~qəpiklər)
# frames/contact-sheet.html-də kadrları seç →
python -m mediaforge.generate {slug} --pick 1=2,3=1      # 2) seçim (pulsuz)
python -m mediaforge.generate {slug} --animatic          # 3) PULSUZ animatic (vaxtlama təsdiqi)
python -m mediaforge.generate {slug} --beats --confirm   # 4) beat videolar + stitch (ödənişli)
{fire_command}   # və ya hamısı bir yerdə
```
`--confirm` real kredit xərcləyir; nəticələr paket qovluğuna enir
(`frames/`, `animatic.mp4`, `beats/`, `promo-beats-master.mp4`).

## Alternativ: xam FLORA CLI (2 variant — reference + motion)
```powershell
{cli_block}
```

Prompt mənbəyi: `{rel}`

## Qapı (cost gate)
- Sistem krediti avtomatik xərcləmir; `--confirm` sənin açıq təsdiqindir.
- Yekun: generasiyadan sonra dəqiq mətn/logo/CTA deterministik overlay kimi Video Studio-da bağlanır.
"""


# --------------------------------------------------------------------------- #
# SVG storyboard board — a real visual artifact with zero dependencies
# --------------------------------------------------------------------------- #
def _wrap(text: str, width: int) -> list[str]:
    words, lines, cur = (text or "").split(), [], ""
    for w in words:
        if len(cur) + len(w) + 1 <= width:
            cur = f"{cur} {w}".strip()
        else:
            if cur:
                lines.append(cur)
            cur = w
    if cur:
        lines.append(cur)
    return lines


def render_board_svg(result: dict[str, Any]) -> str:
    brief = result["brief"]
    beats = brief["storyboard"][:4]
    c = result["concept"]
    r = result["resolution"]

    fw, fh, gap, pad, top = 300, 534, 26, 40, 132
    W = pad * 2 + fw * 4 + gap * 3
    H = top + fh + 90
    red = "#E31E24"

    frames = []
    for i, b in enumerate(beats):
        x = pad + i * (fw + gap)
        title = html.escape(f"{i+1}. {b['beat']}")
        time_chip = html.escape(b["time"])
        visual = _wrap(b["visual"], 34)[:5]
        motion = _wrap("↳ " + b["motion"], 36)[:3]
        overlay = html.escape(b["overlay"] or "— overlay yoxdur —")

        vlines = "".join(
            f'<tspan x="{x+20}" dy="{22 if j else 0}">{html.escape(line)}</tspan>'
            for j, line in enumerate(visual)
        )
        mlines = "".join(
            f'<tspan x="{x+20}" dy="{18 if j else 0}">{html.escape(line)}</tspan>'
            for j, line in enumerate(motion)
        )
        frames.append(f"""
  <g>
    <rect x="{x}" y="{top}" width="{fw}" height="{fh}" rx="18" fill="#141417" stroke="#2b2b31"/>
    <rect x="{x}" y="{top}" width="{fw}" height="150" rx="18" fill="#1c1c22"/>
    <rect x="{x}" y="{top+120}" width="{fw}" height="30" fill="#1c1c22"/>
    <circle cx="{x+34}" cy="{top+40}" r="7" fill="{red}"/>
    <text x="{x+52}" y="{top+45}" fill="#f4f4f5" font-family="Segoe UI, Arial" font-size="16" font-weight="700">{title}</text>
    <rect x="{x+20}" y="{top+62}" width="120" height="26" rx="13" fill="#26262d"/>
    <text x="{x+32}" y="{top+79}" fill="#a9d3ff" font-family="Consolas, monospace" font-size="13">{time_chip}</text>
    <text x="{x+20}" y="{top+118}" fill="#8a8a92" font-family="Segoe UI, Arial" font-size="12" letter-spacing="1">GÖRÜNTÜ</text>
    <text y="{top+178}" fill="#dcdce0" font-family="Segoe UI, Arial" font-size="15">{vlines}</text>
    <text y="{top+330}" fill="#9aa0a6" font-family="Segoe UI, Arial" font-size="13" font-style="italic">{mlines}</text>
    <rect x="{x+16}" y="{top+fh-92}" width="{fw-32}" height="72" rx="12" fill="#0f0f12" stroke="#2b2b31"/>
    <text x="{x+28}" y="{top+fh-70}" fill="#8a8a92" font-family="Segoe UI, Arial" font-size="11" letter-spacing="1">OVERLAY (deterministik)</text>
    <text x="{x+28}" y="{top+fh-46}" fill="{red}" font-family="Segoe UI, Arial" font-size="14" font-weight="600">{overlay[:40]}</text>
  </g>""")

    subtitle = html.escape(
        f"{c.get('big_idea','')[:110]}"
    )
    header = html.escape(c.get("name", "Media Studio storyboard"))
    modeline = html.escape(f"{r['label']} · {r['duration_s']}s · {brief['format']['aspect']} · {brief['platform']['name']}")

    return f"""<svg xmlns="http://www.w3.org/2000/svg" width="{W}" height="{H}" viewBox="0 0 {W} {H}" font-family="Segoe UI, Arial">
  <rect width="{W}" height="{H}" fill="#0a0a0c"/>
  <rect x="0" y="0" width="{W}" height="6" fill="{red}"/>
  <text x="{pad}" y="52" fill="#f4f4f5" font-size="30" font-weight="800">🎬 {header}</text>
  <text x="{pad}" y="82" fill="#b6b6bd" font-size="16">{subtitle}</text>
  <text x="{pad}" y="108" fill="#7fb2ff" font-size="14" font-family="Consolas, monospace">{modeline}</text>
  {''.join(frames)}
  <text x="{pad}" y="{H-32}" fill="#5f5f66" font-size="13">Xalq Sığorta · Media Studio — motion plate; dəqiq mətn/logo deterministik overlay kimi əlavə olunur.</text>
</svg>"""


# --------------------------------------------------------------------------- #
# Logging + memory (best effort)
# --------------------------------------------------------------------------- #
def _log_run(package: dict[str, Any]) -> None:
    try:
        RUN_LOG.parent.mkdir(parents=True, exist_ok=True)
        entry = {
            "ts": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "slug": package["slug"],
            "sentence": package["sentence"],
            "model": package["resolution"]["model_id"],
            "engine": package["meta"]["engine"],
            "valid": package["meta"]["valid"],
        }
        with RUN_LOG.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(entry, ensure_ascii=False) + "\n")
    except Exception:  # noqa: BLE001
        pass


def _remember(package: dict[str, Any]) -> None:
    try:
        from brain import capture  # optional learning loop
        capture.remember(
            f"Media Studio promo package: {package['concept'].get('name','')} "
            f"({package['resolution']['model_id']}, {package['request']['category']}). "
            f"Slug {package['slug']}.",
            tags=["mediaforge", "video", package["request"]["category"]],
        )
    except Exception:  # noqa: BLE001
        pass
