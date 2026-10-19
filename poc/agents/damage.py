"""Damage agent: visible body damage per panel, non-original parts, and tyre wear."""
from __future__ import annotations

from typing import Any

from ..config import MIN_CONFIDENCE
from ..models import EXTERIOR, PANELS, SEVERITIES, AgentOutput, Job, Photo, as_int, conf

PROMPT = """These are seller photos of one car (exterior views, and a tyre close-up if provided).
1. List every visible body defect: dents, scratches, swirl marks, scuffs, cracks, rust, misaligned panels,
   or a panel whose colour or finish looks different (possible repaint). Do not report dust, dirt,
   water spots or reflections as damage.
   Use panel names only from this list: {panels}.
   Severity: minor (cosmetic, polish or touch-up), moderate (dent or panel repair), major (replacement or structural).
2. List anything that looks non-original or mismatched: a wheel of a different design or colour,
   aftermarket lamps, a mismatched panel or badge.
3. Note what limits your view: dust, glare, missing angles.
4. For tyres, count visible tyres that look worn (low or uneven tread). Depth cannot be measured from a photo,
   so keep confidence modest, and low if there is no close-up.

Reply with only this JSON:
{{"damages": [{{"panel": "rear_bumper", "issue": "short description", "severity": "minor", "confidence": 0.0}}],
 "observations": [{{"item": "what looks non-original", "implication": "what the inspector should check", "confidence": 0.0}}],
 "photo_notes": ["short note"],
 "tyres": {{"worn_count": 0, "confidence": 0.0, "notes": "short sentence"}}}}"""


def run(job: Job, photos: dict[str, Photo], engine: Any) -> AgentOutput:
    used = [photos[s] for s in EXTERIOR + ["tyre"] if s in photos]
    if not used:
        return AgentOutput(agent="Damage", engine=engine.name, status="skipped",
                           data={"damages": [], "observations": [], "photo_notes": [],
                                 "tyres": {"worn_count": 0, "confidence": 0, "notes": ""}},
                           summary="No exterior photos; body condition is left to the inspector.")

    read = engine.ask("damage", PROMPT.format(panels=", ".join(PANELS)), used)
    damages = []
    for d in read.get("damages") or []:
        if not isinstance(d, dict):
            continue
        panel = d.get("panel") if d.get("panel") in PANELS else "other"
        severity = d.get("severity") if d.get("severity") in SEVERITIES else "minor"
        damages.append({"panel": panel, "issue": str(d.get("issue") or "Visible defect")[:140],
                        "severity": severity, "confidence": conf(d.get("confidence"))})
    observations = [{"item": str(o.get("item") or "")[:160], "implication": str(o.get("implication") or "")[:160],
                     "confidence": conf(o.get("confidence"))}
                    for o in read.get("observations") or [] if isinstance(o, dict) and o.get("item")]
    notes = [str(n)[:160] for n in read.get("photo_notes") or []][:5]
    t = read.get("tyres") or {}
    tyres = {"worn_count": max(0, min(4, as_int(t.get("worn_count")) or 0)),
             "confidence": conf(t.get("confidence")), "notes": str(t.get("notes") or "")}

    sure = [d for d in damages if d["confidence"] >= MIN_CONFIDENCE]
    unsure = len(damages) - len(sure)
    parts = [f"{len(sure)} defect(s) found with confidence"]
    if unsure:
        parts.append(f"{unsure} possible defect(s) flagged")
    odd = [o for o in observations if o["confidence"] >= MIN_CONFIDENCE]
    if odd:
        parts.append(f"{len(odd)} non-original part(s) suspected")
    if tyres["worn_count"]:
        parts.append(f"{tyres['worn_count']} tyre(s) look worn")
    return AgentOutput(agent="Damage", engine=engine.name,
                       data={"damages": damages, "observations": observations, "photo_notes": notes, "tyres": tyres},
                       summary="; ".join(parts) + ".")
