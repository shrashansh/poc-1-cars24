"""Document agent: reads the RC and the service record.

Two separate calls, because they answer different questions:
the RC proves what the car is; the service record shows how it was kept and what the km were.
"""
from __future__ import annotations

import re
from typing import Any

from ..models import AgentOutput, Job, Photo, as_int, conf

RC_PROMPT = """This photo shows an Indian vehicle registration certificate (RC, Form 23 or smart card).
Some personal fields may be blacked out; ignore those.
Read only these fields if they are visible, and return null for anything you cannot read:

Reply with only this JSON:
{"found": true, "confidence": 0.0,
 "registration": "e.g. UP78HS3132",
 "maker_classification": "model and variant as printed",
 "fuel": "string", "colour": "string",
 "registration_date": "YYYY-MM-DD", "manufacture_month_year": "MM/YYYY",
 "owner_serial": 1, "hypothecation": true, "hypothecation_bank": "string or null"}"""

SERVICE_PROMPT = """This photo shows a car service record: a service booklet page, an invoice or a workshop printout.
It may be handwritten, stamped, faded, folded or photographed at an angle.
Extract every service entry you can read: date (YYYY-MM), odometer km at that service, workshop, work done.
Note anything that suggests tampering: overwritten digits, a km figure that breaks the sequence,
mismatched ink or handwriting within one entry, missing stamps.
If it is not a service record, set documents_found to false.

Reply with only this JSON:
{"documents_found": true, "confidence": 0.0,
 "registration": "plate printed on the document or null",
 "entries": [{"date": "YYYY-MM", "km": 0, "workshop": "string", "work": "string"}],
 "tamper_signals": ["..."]}"""


def _read_rc(photo: Photo, engine: Any) -> dict[str, Any]:
    read = engine.ask("rc_document", RC_PROMPT, [photo])
    return {
        "found": bool(read.get("found")), "confidence": conf(read.get("confidence")),
        "registration": read.get("registration"), "maker_classification": read.get("maker_classification"),
        "fuel": read.get("fuel"), "colour": read.get("colour"),
        "registration_date": read.get("registration_date"), "manufacture_month_year": read.get("manufacture_month_year"),
        "owner_serial": as_int(read.get("owner_serial")), "hypothecation": read.get("hypothecation"),
        "hypothecation_bank": read.get("hypothecation_bank"),
    }


def _read_service(photo: Photo, engine: Any) -> dict[str, Any]:
    read = engine.ask("document", SERVICE_PROMPT, [photo])
    entries = []
    for e in read.get("entries") or []:
        if not isinstance(e, dict):
            continue
        m = re.match(r"(\d{4})-(\d{1,2})", str(e.get("date") or ""))
        entries.append({"date": f"{m.group(1)}-{int(m.group(2)):02d}" if m else None, "km": as_int(e.get("km")),
                        "workshop": str(e.get("workshop") or ""), "work": str(e.get("work") or "")})
    entries.sort(key=lambda x: x["date"] or "")
    return {"documents_found": bool(read.get("documents_found")) and bool(entries),
            "confidence": conf(read.get("confidence")), "registration": read.get("registration"),
            "entries": entries, "tamper_signals": [str(x) for x in read.get("tamper_signals") or []]}


def run(job: Job, photos: dict[str, Photo], engine: Any) -> AgentOutput:
    if "rc" not in photos and "service" not in photos:
        return AgentOutput(agent="Document", engine=engine.name, status="skipped",
                           data={"rc": None, "documents_found": False, "entries": [], "confidence": 0, "tamper_signals": []},
                           summary="No RC or service record provided.")

    rc = _read_rc(photos["rc"], engine) if "rc" in photos else None
    service = _read_service(photos["service"], engine) if "service" in photos else \
        {"documents_found": False, "entries": [], "confidence": 0, "tamper_signals": [], "registration": None}

    parts = []
    if rc:
        parts.append(f"RC read: {rc.get('maker_classification') or 'model not legible'}" if rc["found"] else "RC not legible")
    if service["documents_found"]:
        last = service["entries"][-1]
        parts.append(f"{len(service['entries'])} service entries, latest {last['date']}"
                     + (f" at {last['km']:,} km" if last["km"] is not None else ""))
    elif "service" in photos:
        parts.append("service record not legible")
    else:
        parts.append("no service record provided")
    if service["tamper_signals"]:
        parts.append("possible tampering noted")
    return AgentOutput(agent="Document", engine=engine.name, data={"rc": rc, **service}, summary="; ".join(parts) + ".")
