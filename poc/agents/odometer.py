"""Odometer agent: read the km from the instrument cluster."""
from __future__ import annotations

from typing import Any

from ..config import MIN_CONFIDENCE
from ..models import AgentOutput, Job, Photo, as_int, conf

PROMPT = """This photo shows a car's instrument cluster.
Read the total odometer (ODO) value in kilometres. Ignore trip meters (TRIP A/B) and fuel range.
Also list any warning lights that are lit (for example check engine, airbag, ABS, battery).
If the digits are not clearly legible, return null and a low confidence.

Reply with only this JSON:
{"reading_km": 0, "confidence": 0.0, "warning_lights": ["..."], "evidence": "one short sentence"}"""


def run(job: Job, photos: dict[str, Photo], engine: Any) -> AgentOutput:
    if "dash" not in photos:
        return AgentOutput(agent="Odometer", engine=engine.name, status="skipped",
                           data={"reading_km": None, "confidence": 0, "warning_lights": []},
                           summary="No dashboard photo; the declared km band is unverified.")

    read = engine.ask("odometer", PROMPT, [photos["dash"]])
    km = as_int(read.get("reading_km"))
    c = conf(read.get("confidence")) if km is not None else 0.0
    lights = [str(x) for x in read.get("warning_lights") or []]
    a, b = job.km_band
    data = {"reading_km": km, "confidence": c, "warning_lights": lights,
            "evidence": str(read.get("evidence") or ""), "in_declared_band": (a <= km <= b) if km is not None else None}

    if km is None or c < MIN_CONFIDENCE:
        summary = "Odometer not readable with confidence."
    else:
        where = "inside" if a <= km <= b else "outside"
        summary = f"Reads {km:,} km ({c:.0%}), {where} the declared {a:,}–{b:,} km band."
    if lights:
        summary += f" Warning lights: {', '.join(lights)}."
    return AgentOutput(agent="Odometer", engine=engine.name, data=data, summary=summary)
