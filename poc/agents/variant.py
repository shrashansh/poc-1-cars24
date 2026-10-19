"""Variant agent: which trim do the visible features indicate?"""
from __future__ import annotations

from typing import Any

from ..config import MIN_CONFIDENCE
from ..models import AgentOutput, Job, Photo, conf

PROMPT = """These photos show a {year} {label}. The seller says it is the {declared} variant.
Decide which variant the visible features indicate. Variant guide (simplified):
{guide}

Look at wheels, badges, headlamps, door handles, the infotainment unit and seat trim.
If a registration certificate is included, its maker's classification often names the variant.
If the evidence is unclear, use "unknown" and a confidence below 0.5.

Reply with only this JSON:
{{"detected": "one of {options} or unknown", "confidence": 0.0,
 "evidence": ["short reason tied to a specific photo", "..."]}}"""

USE = ["rear", "front", "left", "right", "interior", "seats", "rc"]


def run(job: Job, photos: dict[str, Photo], engine: Any, vehicle: dict[str, Any]) -> AgentOutput:
    used = [photos[s] for s in USE if s in photos]
    variants: dict[str, str] = vehicle["variants"]
    if not used:
        return AgentOutput(agent="Variant", engine=engine.name, status="skipped",
                           data={"detected": "unknown", "confidence": 0, "evidence": []},
                           summary="No exterior or cabin photos to identify the variant.")

    guide = "\n".join(f"- {name}: {desc}" for name, desc in variants.items())
    prompt = PROMPT.format(year=job.year, label=vehicle["label"], declared=job.declared_variant,
                           guide=guide, options=", ".join(variants))
    read = engine.ask("variant", prompt, used)

    detected = str(read.get("detected") or "unknown").strip()
    match = next((v for v in variants if v.lower() == detected.lower()), "unknown")
    c = conf(read.get("confidence"))
    evidence = [str(e) for e in read.get("evidence") or []][:5]
    data = {"detected": match, "confidence": c, "evidence": evidence, "declared": job.declared_variant}

    if match == "unknown" or c < MIN_CONFIDENCE:
        summary = f"Variant not confirmed (best guess {match}, {c:.0%}); declared {job.declared_variant} kept."
    elif match == job.declared_variant:
        summary = f"Variant {match} confirmed ({c:.0%})."
    else:
        summary = f"Declared {job.declared_variant}, photos indicate {match} ({c:.0%})."
    return AgentOutput(agent="Variant", engine=engine.name, data=data, summary=summary)
