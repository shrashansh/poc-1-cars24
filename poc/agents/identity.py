"""Identity agent: are these photos of the car on the RC, and of one car only?"""
from __future__ import annotations

from typing import Any

from ..config import MIN_CONFIDENCE
from ..models import EXTERIOR, AgentOutput, Job, Photo, conf, norm_plate

PROMPT = """Look at these exterior photos of one car.
1. Read the registration number plate exactly as printed (Indian format, e.g. "DL 3C AB 1234").
2. Name the body colour in one or two plain words.
3. Decide whether all photos show the same car (same colour, body, wheels, plate).

Reply with only this JSON:
{"plate": "string or null", "plate_confidence": 0.0,
 "colour": "string or null", "colour_confidence": 0.0,
 "same_car": true, "same_car_confidence": 0.0,
 "notes": "one short sentence"}"""


def run(job: Job, photos: dict[str, Photo], engine: Any, rc_registry: dict[str, Any]) -> AgentOutput:
    used = [photos[s] for s in EXTERIOR if s in photos]
    rc = rc_registry.get(norm_plate(job.rc_number))
    if not used:
        return AgentOutput(agent="Identity", engine=engine.name, status="skipped",
                           data={"rc_record": rc, "checks": {"rc_found": rc is not None}},
                           summary="No exterior photos, so plate and colour were not checked.")

    read = engine.ask("identity", PROMPT, used)
    plate_ok = conf(read.get("plate_confidence")) >= MIN_CONFIDENCE and bool(read.get("plate"))
    colour_ok = conf(read.get("colour_confidence")) >= MIN_CONFIDENCE and bool(read.get("colour"))
    same_ok = conf(read.get("same_car_confidence")) >= MIN_CONFIDENCE and read.get("same_car") is not None

    checks = {
        "rc_found": rc is not None,
        "plate_read": plate_ok,
        "plate_matches_rc": (norm_plate(read.get("plate")) == norm_plate(job.rc_number)) if plate_ok else None,
        "colour_matches_rc": _colour_match(read.get("colour"), rc.get("colour")) if (colour_ok and rc) else None,
        "same_car": bool(read.get("same_car")) if same_ok else None,
        "model_matches_rc": (rc.get("model") == job.model_id) if rc else None,
    }

    bits = []
    bits.append("RC found in registry" if rc else "RC not found in the registry lookup")
    if checks["plate_matches_rc"] is True:
        bits.append("plate matches RC")
    elif checks["plate_matches_rc"] is False:
        bits.append(f"plate reads {read.get('plate')}, not the RC entered")
    else:
        bits.append("plate not readable")
    if checks["colour_matches_rc"] is False:
        bits.append(f"colour looks {read.get('colour')}, RC says {rc.get('colour')}")
    if checks["same_car"] is False:
        bits.append("photos may show different cars")
    return AgentOutput(agent="Identity", engine=engine.name, data={"read": read, "rc_record": rc, "checks": checks},
                       summary=_sentence("; ".join(bits)))


def _sentence(text: str) -> str:
    return text[:1].upper() + text[1:] + "."


def _colour_match(seen: Any, registered: Any) -> bool:
    a, b = str(seen or "").lower(), str(registered or "").lower()
    return bool(a) and bool(b) and (a in b or b in a or bool(set(a.split()) & set(b.split())))
