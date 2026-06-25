"""Deterministic Creative Audit for Xalq Insurance Digital OS Social Studio.

This script is intentionally local and lightweight. It does not replace a
human or LLM art director; it catches measurable production risks before the
subjective review starts.
"""

from __future__ import annotations

import argparse
import json
import math
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

import numpy as np
from PIL import Image


ROOT = Path(__file__).resolve().parents[2]


@dataclass(frozen=True)
class Finding:
    severity: str
    code: str
    message: str

    def to_dict(self) -> dict[str, str]:
        return {
            "severity": self.severity,
            "code": self.code,
            "message": self.message,
        }


def clamp(value: float, low: float = 0.0, high: float = 100.0) -> float:
    return max(low, min(high, value))


def load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def resolve_path(path: str | Path) -> Path:
    p = Path(path)
    if p.is_absolute():
        return p
    return ROOT / p


def round_score(value: float) -> float:
    return round(clamp(value), 1)


def downsample_rgb(image: Image.Image, max_width: int = 512) -> np.ndarray:
    image = image.convert("RGB")
    width, height = image.size
    if width > max_width:
        new_height = max(1, int(height * (max_width / width)))
        image = image.resize((max_width, new_height), Image.Resampling.LANCZOS)
    return np.asarray(image, dtype=np.float32) / 255.0


def crop_rel(arr: np.ndarray, zone: dict[str, float]) -> np.ndarray:
    h, w = arr.shape[:2]
    x0 = int(clamp(zone.get("x0", 0), 0, 1) * w)
    y0 = int(clamp(zone.get("y0", 0), 0, 1) * h)
    x1 = int(clamp(zone.get("x1", 1), 0, 1) * w)
    y1 = int(clamp(zone.get("y1", 1), 0, 1) * h)
    return arr[y0:max(y0 + 1, y1), x0:max(x0 + 1, x1)]


def luminance(rgb: np.ndarray) -> np.ndarray:
    return (
        0.2126 * rgb[:, :, 0]
        + 0.7152 * rgb[:, :, 1]
        + 0.0722 * rgb[:, :, 2]
    )


def edge_energy(luma: np.ndarray) -> float:
    if luma.size < 4:
        return 0.0
    gx = np.abs(np.diff(luma, axis=1)).mean() if luma.shape[1] > 1 else 0.0
    gy = np.abs(np.diff(luma, axis=0)).mean() if luma.shape[0] > 1 else 0.0
    return float(gx + gy)


def zone_metrics(rgb: np.ndarray) -> dict[str, float]:
    luma = luminance(rgb)
    return {
        "luminance_mean": float(luma.mean()),
        "luminance_std": float(luma.std()),
        "edge_energy": edge_energy(luma),
    }


def red_ratio(image: Image.Image) -> float:
    small = image.convert("RGB")
    width, height = small.size
    if width > 512:
        new_height = max(1, int(height * (512 / width)))
        small = small.resize((512, new_height), Image.Resampling.LANCZOS)
    hsv = np.asarray(small.convert("HSV"), dtype=np.uint8)
    h = hsv[:, :, 0]
    s = hsv[:, :, 1]
    v = hsv[:, :, 2]
    red = ((h < 15) | (h > 240)) & (s > 70) & (v > 35)
    return float(red.mean())


def score_range(value: float, ideal_min: float, ideal_max: float, critical_max: float) -> float:
    if ideal_min <= value <= ideal_max:
        return 100.0
    if value < ideal_min:
        return 75.0 + (value / max(ideal_min, 0.0001)) * 25.0
    if value >= critical_max:
        return 0.0
    return 100.0 * (1.0 - ((value - ideal_max) / (critical_max - ideal_max)))


def audit_export(
    path: Path,
    placement: dict[str, Any],
    rules: dict[str, Any],
) -> dict[str, Any]:
    findings: list[Finding] = []

    if not path.exists():
        return {
            "path": str(path.relative_to(ROOT) if path.is_relative_to(ROOT) else path),
            "exists": False,
            "scores": {
                "production_readiness": 0.0,
                "art_direction": 0.0,
                "brand_fit": 0.0,
            },
            "findings": [
                Finding("critical", "missing_file", f"Export is missing: {path}").to_dict()
            ],
        }

    with Image.open(path) as image:
        image.load()
        width, height = image.size
        rgb = downsample_rgb(image)
        full = zone_metrics(rgb)

        footer_ratio = float(placement.get("footer_zone_ratio", 0.135))
        footer = rgb[int(rgb.shape[0] * (1.0 - footer_ratio)) :, :, :]
        footer_m = zone_metrics(footer)

        headline_zone = placement.get("headline_zone", {"x0": 0, "y0": 0, "x1": 0.55, "y1": 0.42})
        headline = crop_rel(rgb, headline_zone)
        headline_m = zone_metrics(headline)

        rr = red_ratio(image)

    expected_width = int(placement["expected_width"])
    expected_height = int(placement["expected_height"])
    dimensions_ok = width == expected_width and height == expected_height
    if not dimensions_ok:
        findings.append(
            Finding(
                "critical",
                "wrong_dimensions",
                f"{path.name} is {width}x{height}; expected {expected_width}x{expected_height}.",
            )
        )

    footer_rules = rules.get("footer_policy", {})
    max_footer_edge = float(footer_rules.get("max_edge_energy", 0.085))
    max_footer_std = float(footer_rules.get("max_luminance_std", 0.18))
    darker_by = float(footer_rules.get("prefer_footer_darker_than_full_image_by", 0.04))

    if footer_m["edge_energy"] > max_footer_edge:
        findings.append(
            Finding(
                "major",
                "footer_busy_edges",
                "Footer zone has high edge energy and may fight legal/contact text.",
            )
        )
    if footer_m["luminance_std"] > max_footer_std:
        findings.append(
            Finding(
                "major",
                "footer_busy_contrast",
                "Footer zone has high contrast variance and may reduce legal text legibility.",
            )
        )
    if footer_m["luminance_mean"] > full["luminance_mean"] - darker_by:
        findings.append(
            Finding(
                "minor",
                "footer_not_dark_enough",
                "Footer zone is not meaningfully darker than the full image average.",
            )
        )

    headline_rules = rules.get("headline_policy", {})
    max_headline_edge = float(headline_rules.get("max_edge_energy", 0.09))
    max_headline_std = float(headline_rules.get("max_luminance_std", 0.24))
    if headline_m["edge_energy"] > max_headline_edge:
        findings.append(
            Finding(
                "major",
                "headline_zone_busy_edges",
                "Upper-left headline zone has high edge energy; typography may need a stronger fade or a calmer crop.",
            )
        )
    if headline_m["luminance_std"] > max_headline_std:
        findings.append(
            Finding(
                "minor",
                "headline_zone_contrasty",
                "Upper-left headline zone has high luminance variation.",
            )
        )

    red_policy = rules.get("brand_red_policy", {})
    ideal_red_min = float(red_policy.get("ideal_red_ratio_min", 0.02))
    ideal_red_max = float(red_policy.get("ideal_red_ratio_max", 0.22))
    critical_red_max = float(red_policy.get("critical_red_ratio_max", 0.42))
    if rr > critical_red_max:
        findings.append(
            Finding(
                "major",
                "red_wash_risk",
                f"Red pixel ratio is {rr:.1%}; this risks reading as a heavy red wash.",
            )
        )
    elif rr > ideal_red_max:
        findings.append(
            Finding(
                "minor",
                "red_ratio_high",
                f"Red pixel ratio is {rr:.1%}; brand red may be too dominant.",
            )
        )

    dimension_score = 100.0 if dimensions_ok else 0.0
    footer_score = 100.0
    footer_score -= max(0.0, footer_m["edge_energy"] - max_footer_edge) * 700.0
    footer_score -= max(0.0, footer_m["luminance_std"] - max_footer_std) * 320.0
    footer_dark_delta = full["luminance_mean"] - footer_m["luminance_mean"]
    if footer_dark_delta < darker_by:
        footer_score -= (darker_by - footer_dark_delta) * 500.0

    headline_score = 100.0
    headline_score -= max(0.0, headline_m["edge_energy"] - max_headline_edge) * 650.0
    headline_score -= max(0.0, headline_m["luminance_std"] - max_headline_std) * 260.0

    brand_red_score = score_range(rr, ideal_red_min, ideal_red_max, critical_red_max)

    production_readiness = (dimension_score * 0.45) + (footer_score * 0.35) + (headline_score * 0.20)
    art_direction = (headline_score * 0.55) + (footer_score * 0.25) + (brand_red_score * 0.20)
    brand_fit = brand_red_score

    return {
        "path": str(path.relative_to(ROOT) if path.is_relative_to(ROOT) else path),
        "exists": True,
        "placement": placement["name"],
        "dimensions": {
            "width": width,
            "height": height,
            "expected_width": expected_width,
            "expected_height": expected_height,
            "ok": dimensions_ok,
        },
        "metrics": {
            "full": full,
            "footer": footer_m,
            "headline_zone": headline_m,
            "red_ratio": rr,
        },
        "scores": {
            "production_readiness": round_score(production_readiness),
            "art_direction": round_score(art_direction),
            "brand_fit": round_score(brand_fit),
        },
        "findings": [finding.to_dict() for finding in findings],
    }


def compliance_score(manifest: dict[str, Any]) -> tuple[float, list[Finding]]:
    compliance = manifest.get("compliance", {})
    findings: list[Finding] = []
    status = compliance.get("status", "")
    claim = manifest.get("copy", {}).get("regulatory_claim", "")
    if claim and status != "verified":
        findings.append(
            Finding(
                "critical",
                "regulatory_claim_unverified",
                "Regulatory claim exists but compliance status is not verified.",
            )
        )
        return 35.0, findings
    return 100.0, findings


def marketing_score(manifest: dict[str, Any]) -> tuple[float, list[Finding]]:
    copy = manifest.get("copy", {})
    findings: list[Finding] = []
    headline = copy.get("headline", "")
    subheadline = copy.get("subheadline", "")

    score = 88.0
    if not headline:
        findings.append(Finding("major", "missing_headline", "Manifest has no headline."))
        score -= 30.0
    if headline and len(headline) > 72:
        findings.append(
            Finding("minor", "headline_long", "Headline is long for fast social scanning.")
        )
        score -= 8.0
    if not subheadline:
        findings.append(Finding("minor", "missing_subheadline", "Manifest has no subheadline."))
        score -= 6.0
    if copy.get("copy_layer_mode") != "deterministic_overlay":
        findings.append(
            Finding(
                "major",
                "copy_not_deterministic",
                "Copy should be added as a deterministic overlay, not generated into the image.",
            )
        )
        score -= 20.0
    return clamp(score), findings


def creative_judgment_score(
    review: dict[str, Any] | None,
    rubric: dict[str, Any],
) -> tuple[float | None, list[Finding], dict[str, Any]]:
    findings: list[Finding] = []
    weights = rubric.get("creative_judgment_weights", {})

    if review is None:
        findings.append(
            Finding(
                "review",
                "creative_judgment_missing",
                "Automated gate passed, but no human or vision-LLM creative review was provided.",
            )
        )
        return None, findings, {
            "status": "missing",
            "score": None,
            "reviewer": None,
            "note": "Final creative approval requires a vision-capable review.",
        }

    scores = review.get("scores", {})
    blockers = review.get("blockers", [])
    if blockers:
        for blocker in blockers:
            findings.append(
                Finding("critical", "creative_blocker", str(blocker))
            )

    missing = [key for key in weights if key not in scores]
    for key in missing:
        findings.append(
            Finding(
                "major",
                "creative_score_missing",
                f"Creative review is missing score: {key}.",
            )
        )

    total_weight = 0.0
    weighted = 0.0
    normalized_scores: dict[str, float] = {}
    for key, weight in weights.items():
        if key not in scores:
            continue
        value = round_score(float(scores[key]))
        normalized_scores[key] = value
        weighted += value * float(weight)
        total_weight += float(weight)

    if total_weight <= 0:
        findings.append(
            Finding(
                "critical",
                "creative_review_invalid",
                "Creative review has no usable scores.",
            )
        )
        return 0.0, findings, {
            "status": "invalid",
            "score": 0.0,
            "reviewer": review.get("reviewer"),
            "scores": normalized_scores,
        }

    score = weighted / total_weight
    if score < 90:
        findings.append(
            Finding(
                "review",
                "creative_quality_below_approval",
                f"Creative judgment score is {score:.1f}; final approval requires 90+.",
            )
        )
    return round_score(score), findings, {
        "status": "present",
        "score": round_score(score),
        "reviewer": review.get("reviewer"),
        "scores": normalized_scores,
        "top_findings": review.get("top_findings", []),
        "revision_brief": review.get("revision_brief", []),
        "next_prompt_patch": review.get("next_prompt_patch", []),
    }


def prompt_patch(findings: list[Finding]) -> list[str]:
    codes = {finding.code for finding in findings}
    patch: list[str] = []
    if "red_wash_risk" in codes or "red_ratio_high" in codes:
        patch.append(
            "Reduce the full-frame red overlay. Keep brand red only in the suitcase, subtle reflections, small UI accents, and very soft edge atmosphere."
        )
        patch.append(
            "Avoid a saturated red wash across skin, windows, train interior, or landscape."
        )
    if "headline_zone_busy_edges" in codes or "headline_zone_contrasty" in codes:
        patch.append(
            "Make the upper-left third calmer and darker, with fewer objects, fewer bright highlights, and smoother negative space for Azerbaijani headline text."
        )
    if "footer_busy_edges" in codes or "footer_busy_contrast" in codes or "footer_not_dark_enough" in codes:
        patch.append(
            "Reserve the lower footer zone as a clean dark fade with no faces, hands, suitcase handles, documents, or high-contrast details."
        )
    if "regulatory_claim_unverified" in codes:
        patch.append(
            "Do not publish regulatory wording until the manifest contains a verified source URL, review date, and responsible owner."
        )
    if "creative_judgment_missing" in codes:
        patch.append(
            "Run a human or vision-LLM creative review before final approval; deterministic checks only validate measurable production gates."
        )
    if "creative_blocker" in codes:
        patch.append(
            "Use the creative review blockers as hard prompt constraints for the next generation."
        )
    if not patch:
        patch.append("No prompt patch required from deterministic checks.")
    return patch


def aggregate_report(
    manifest: dict[str, Any],
    rubric: dict[str, Any],
    export_reports: list[dict[str, Any]],
    creative_review: dict[str, Any] | None = None,
) -> dict[str, Any]:
    compliance, compliance_findings = compliance_score(manifest)
    marketing, marketing_findings = marketing_score(manifest)
    creative_score, creative_findings, creative_summary = creative_judgment_score(
        creative_review,
        rubric,
    )

    if export_reports:
        brand_fit = float(np.mean([r["scores"]["brand_fit"] for r in export_reports]))
        art_direction = float(np.mean([r["scores"]["art_direction"] for r in export_reports]))
        production = float(np.mean([r["scores"]["production_readiness"] for r in export_reports]))
    else:
        brand_fit = 0.0
        art_direction = 0.0
        production = 0.0

    weights = rubric.get("weights", {}) or {
        "brand_fit": 0.22,
        "art_direction": 0.22,
        "marketing_clarity": 0.18,
        "compliance_safety": 0.18,
        "production_readiness": 0.20,
    }
    automated_gate_score = (
        brand_fit * weights["brand_fit"]
        + art_direction * weights["art_direction"]
        + marketing * weights["marketing_clarity"]
        + compliance * weights["compliance_safety"]
        + production * weights["production_readiness"]
    )

    all_findings = compliance_findings + marketing_findings + creative_findings
    for report in export_reports:
        all_findings.extend(
            Finding(f["severity"], f["code"], f"{report['path']}: {f['message']}")
            for f in report.get("findings", [])
        )

    critical_count = sum(1 for f in all_findings if f.severity == "critical")
    final_score = None
    decision = "needs_creative_review"
    if creative_score is not None:
        final_weights = rubric.get("final_weights", {})
        automated_weight = float(final_weights.get("automated_gate", 0.35))
        creative_weight = float(final_weights.get("creative_judgment", 0.65))
        total_final_weight = automated_weight + creative_weight
        final_score = (
            automated_gate_score * automated_weight
            + creative_score * creative_weight
        ) / max(total_final_weight, 0.0001)

    if automated_gate_score < 55:
        decision = "reject"
    elif critical_count:
        decision = "revise"
    elif final_score is not None:
        if final_score >= 90:
            decision = "approve"
        elif final_score >= 70:
            decision = "revise"
        else:
            decision = "reject"

    return {
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "campaign": manifest.get("campaign"),
        "brand": manifest.get("brand"),
        "decision": decision,
        "automated_gate_score": round_score(automated_gate_score),
        "overall_score": None if final_score is None else round_score(final_score),
        "rubric": {
            "name": rubric.get("name", "unknown"),
            "version": rubric.get("version", "unknown"),
        },
        "score_meaning": rubric.get("score_meaning", {}),
        "scores": {
            "brand_fit": round_score(brand_fit),
            "art_direction": round_score(art_direction),
            "marketing_clarity": round_score(marketing),
            "compliance_safety": round_score(compliance),
            "production_readiness": round_score(production),
        },
        "creative_judgment": creative_summary,
        "findings": [f.to_dict() for f in all_findings],
        "prompt_patch": prompt_patch(all_findings),
        "exports": export_reports,
    }


def severity_rank(severity: str) -> int:
    return {"critical": 0, "major": 1, "review": 2, "minor": 3}.get(severity, 4)


def markdown_report(report: dict[str, Any]) -> str:
    findings = sorted(report["findings"], key=lambda f: severity_rank(f["severity"]))
    lines = [
        f"# Creative Audit - {report['campaign']}",
        "",
        f"- Brand: {report['brand']}",
        f"- Decision: {report['decision'].upper()}",
        f"- Automated gate score: {report['automated_gate_score']}/100",
        f"- Final score: {report['overall_score'] if report['overall_score'] is not None else 'pending creative review'}",
        f"- Rubric: {report['rubric']['name']} v{report['rubric']['version']}",
        f"- Generated at: {report['generated_at']}",
        "",
        "## Scorecard",
        "",
        "These are automated gate scores. They measure production safety, not final creative excellence.",
        "",
    ]
    for key, value in report["scores"].items():
        lines.append(f"- {key}: {value}/100")
    creative = report.get("creative_judgment", {})
    lines.extend(["", "## Creative Judgment", ""])
    lines.append(f"- Status: {creative.get('status')}")
    lines.append(f"- Reviewer: {creative.get('reviewer') or 'not provided'}")
    lines.append(
        f"- Score: {creative.get('score') if creative.get('score') is not None else 'pending'}"
    )
    if creative.get("scores"):
        for key, value in creative["scores"].items():
            lines.append(f"- {key}: {value}/100")
    if creative.get("top_findings"):
        lines.append("")
        lines.append("Top findings:")
        for item in creative["top_findings"]:
            lines.append(f"- {item}")
    if creative.get("revision_brief"):
        lines.append("")
        lines.append("Revision brief:")
        for item in creative["revision_brief"]:
            lines.append(f"- {item}")
    lines.extend(["", "## Findings", ""])
    if findings:
        for finding in findings:
            lines.append(
                f"- [{finding['severity']}] {finding['code']}: {finding['message']}"
            )
    else:
        lines.append("- No findings.")

    lines.extend(["", "## Export Metrics", ""])
    for export in report["exports"]:
        metrics = export.get("metrics", {})
        dims = export.get("dimensions", {})
        scores = export.get("scores", {})
        lines.append(f"### {export.get('placement')} - `{export['path']}`")
        lines.append("")
        lines.append(
            f"- Dimensions: {dims.get('width')}x{dims.get('height')} "
            f"(expected {dims.get('expected_width')}x{dims.get('expected_height')})"
        )
        lines.append(
            f"- Scores: brand {scores.get('brand_fit')}, art {scores.get('art_direction')}, "
            f"production {scores.get('production_readiness')}"
        )
        if metrics:
            lines.append(f"- Red ratio: {metrics.get('red_ratio', 0):.1%}")
            footer = metrics.get("footer", {})
            headline = metrics.get("headline_zone", {})
            lines.append(
                f"- Footer: edge {footer.get('edge_energy', math.nan):.3f}, "
                f"luma std {footer.get('luminance_std', math.nan):.3f}, "
                f"luma mean {footer.get('luminance_mean', math.nan):.3f}"
            )
            lines.append(
                f"- Headline zone: edge {headline.get('edge_energy', math.nan):.3f}, "
                f"luma std {headline.get('luminance_std', math.nan):.3f}, "
                f"luma mean {headline.get('luminance_mean', math.nan):.3f}"
            )
        lines.append("")

    lines.extend(
        [
            "## Prompt Patch",
            "",
        ]
    )
    for item in report.get("prompt_patch", []):
        lines.append(f"- {item}")
    creative_patch = report.get("creative_judgment", {}).get("next_prompt_patch", [])
    if creative_patch:
        lines.extend(["", "## Creative Prompt Patch", ""])
        for item in creative_patch:
            lines.append(f"- {item}")
    lines.append("")
    return "\n".join(lines)


def write_report(report: dict[str, Any], out_dir: Path) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "creative-audit-report.json").write_text(
        json.dumps(report, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    (out_dir / "creative-audit-report.md").write_text(
        markdown_report(report),
        encoding="utf-8",
    )


def main() -> int:
    parser = argparse.ArgumentParser(description="Run Social Studio creative audit.")
    parser.add_argument("--manifest", required=True, type=Path)
    parser.add_argument(
        "--rubric",
        default=Path("social-studio/audit/rubric.json"),
        type=Path,
    )
    parser.add_argument(
        "--creative-review",
        type=Path,
        help="Optional human or vision-LLM review JSON for final creative scoring.",
    )
    parser.add_argument("--out-dir", required=True, type=Path)
    args = parser.parse_args()

    manifest_path = resolve_path(args.manifest)
    rubric_path = resolve_path(args.rubric)
    out_dir = resolve_path(args.out_dir)
    manifest = load_json(manifest_path)
    rubric = load_json(rubric_path)
    creative_review = None
    if args.creative_review:
        creative_review = load_json(resolve_path(args.creative_review))
    rules = manifest.get("rules", {})

    export_reports: list[dict[str, Any]] = []
    for placement in manifest.get("placements", []):
        for export_path in placement.get("exports", []):
            export_reports.append(audit_export(resolve_path(export_path), placement, rules))

    report = aggregate_report(manifest, rubric, export_reports, creative_review)
    write_report(report, out_dir)

    print(f"Decision: {report['decision'].upper()}")
    print(f"Automated gate score: {report['automated_gate_score']}/100")
    if report["overall_score"] is None:
        print("Final score: pending creative review")
    else:
        print(f"Final score: {report['overall_score']}/100")
    print(f"Report: {out_dir / 'creative-audit-report.md'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
