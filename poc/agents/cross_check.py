"""Cross-check agent: deterministic rules that reconcile what the other agents found.

No AI here on purpose: these are the checks a reviewer must be able to audit line by line.
"""
from __future__ import annotations

from datetime import date
from typing import Any

from ..config import MIN_CONFIDENCE
from ..models import AgentOutput, Job, norm_plate

MAX_GAP_MONTHS = 15
MAX_GAP_KM = 15000
STALE_SERVICE_MONTHS = 18
ROLLBACK_TOLERANCE_KM = 500
HIGH_USE_KM_PER_YEAR = 35000
LOW_USE_KM_PER_YEAR = 3000


def _months(ym: str) -> int:
    y, m = ym.split("-")
    return int(y) * 12 + int(m)


def run(job: Job, identity: dict, variant: dict, odometer: dict, document: dict, damage: dict,
        today: date | None = None) -> AgentOutput:
    today = today or date.today()
    issues: list[dict[str, str]] = []

    def add(code: str, severity: str, message: str) -> None:
        issues.append({"code": code, "severity": severity, "message": message})

    # --- identity ---
    checks = identity.get("checks", {})
    rc = identity.get("rc_record")
    if not checks.get("rc_found"):
        add("RC_NOT_FOUND", "warning", "RC number not found in the registry; ownership must be checked by hand.")
    if checks.get("plate_matches_rc") is False:
        add("PLATE_MISMATCH", "critical", "The plate in the photos does not match the RC number entered.")
    if checks.get("same_car") is False:
        add("DIFFERENT_CARS", "critical", "The photos may not all show the same car.")
    if checks.get("colour_matches_rc") is False:
        add("COLOUR_MISMATCH", "warning", "Body colour differs from the RC record (repaint or wrong car).")
    if checks.get("model_matches_rc") is False:
        add("MODEL_MISMATCH", "warning", "The model selected does not match the RC record.")

    # --- the RC document itself ---
    rc_doc = document.get("rc") or {}
    if rc_doc.get("found") and rc_doc.get("confidence", 0) >= MIN_CONFIDENCE:
        doc_plate = norm_plate(rc_doc.get("registration"))
        if doc_plate and job.rc_number and doc_plate != norm_plate(job.rc_number):
            add("RC_DOC_MISMATCH", "critical", f"The RC photo shows {rc_doc.get('registration')}, not the RC number entered.")
        read_plate = norm_plate((identity.get("read") or {}).get("plate"))
        if doc_plate and read_plate and checks.get("plate_read") and doc_plate != read_plate:
            add("RC_DOC_PLATE_MISMATCH", "critical", "The plate on the car does not match the RC photo.")
        if rc_doc.get("hypothecation"):
            bank = rc_doc.get("hypothecation_bank") or "a lender"
            add("HYPOTHECATION", "info", f"RC shows a loan with {bank}: bank NOC and Form 35 needed before transfer.")
    elif "rc" in document and document.get("rc") is not None:
        add("RC_DOC_UNREADABLE", "warning", "The RC photo could not be read with confidence; retake it flat and in focus.")

    # --- non-original parts ---
    for o in damage.get("observations", []):
        if o.get("confidence", 0) >= MIN_CONFIDENCE:
            add("NON_ORIGINAL_PART", "warning", f"{o['item']}. {o.get('implication', '')}".strip())

    # --- variant ---
    if variant.get("detected") not in (None, "unknown") and variant.get("confidence", 0) >= MIN_CONFIDENCE \
            and variant["detected"] != job.declared_variant:
        add("VARIANT_MISMATCH", "warning",
            f"Declared {job.declared_variant}, photos indicate {variant['detected']}.")

    # --- odometer vs bills ---
    reading = odometer.get("reading_km") if odometer.get("confidence", 0) >= MIN_CONFIDENCE else None
    entries = [e for e in document.get("entries", []) if e.get("date") and e.get("km") is not None]
    entries.sort(key=lambda e: e["date"])
    max_bill = max(entries, key=lambda e: e["km"]) if entries else None

    rollback = bool(reading is not None and max_bill and reading < max_bill["km"] - ROLLBACK_TOLERANCE_KM)
    if rollback:
        add("ODOMETER_ROLLBACK", "critical",
            f"Dashboard shows {reading:,} km, but the service record dated {max_bill['date']} shows {max_bill['km']:,} km.")

    a, b = job.km_band
    if reading is not None and not (a <= reading <= b):
        add("KM_OUTSIDE_BAND", "warning", f"Odometer {reading:,} km is outside the declared {a:,}–{b:,} km band.")

    for prev, cur in zip(entries, entries[1:]):
        if cur["km"] < prev["km"]:
            add("BILL_KM_DECREASING", "critical",
                f"Service km fell from {prev['km']:,} ({prev['date']}) to {cur['km']:,} ({cur['date']}).")

    km_per_year = None
    reg_date = (rc or {}).get("registration_date") or (rc_doc.get("registration_date") if rc_doc.get("found") else None)
    try:
        reg = date.fromisoformat(str(reg_date)) if reg_date else None
    except ValueError:
        reg = None
    if reg:
        years = max(0.25, (today - reg).days / 365.25)
        basis = max(reading or 0, max_bill["km"] if max_bill else 0)
        if basis:
            km_per_year = round(basis / years)
            if km_per_year > HIGH_USE_KM_PER_YEAR:
                add("HIGH_USAGE", "info", f"About {km_per_year:,} km a year: heavy use (possible commercial use).")
            elif km_per_year < LOW_USE_KM_PER_YEAR:
                add("LOW_USAGE", "warning", f"Only about {km_per_year:,} km a year: unusually low, check the odometer.")

    # --- service regularity ---
    regular = False
    if entries:
        gaps_ok = all(_months(c["date"]) - _months(p["date"]) <= MAX_GAP_MONTHS and c["km"] - p["km"] <= MAX_GAP_KM
                      for p, c in zip(entries, entries[1:]))
        recent = (today.year * 12 + today.month) - _months(entries[-1]["date"]) <= STALE_SERVICE_MONTHS
        regular = len(entries) >= 2 and gaps_ok and recent and not rollback
        if not regular:
            add("SERVICE_GAPS", "info", "Service history has gaps or the last service is old.")
    if document.get("tamper_signals"):
        add("BILL_TAMPER_SIGNALS", "warning", "Possible tampering on the service document: " +
            "; ".join(document["tamper_signals"]))

    warning_lights = odometer.get("warning_lights") or []
    if warning_lights:
        add("WARNING_LIGHTS", "warning", "Warning lights on: " + ", ".join(warning_lights) + ".")

    km_verified = reading is not None and not rollback
    effective_km = max(reading or 0, max_bill["km"] if max_bill else 0) if rollback else reading

    crit = sum(1 for i in issues if i["severity"] == "critical")
    warn = sum(1 for i in issues if i["severity"] == "warning")
    summary = f"{crit} critical, {warn} warning(s)."
    if rollback:
        summary = "Odometer rollback suspected. " + summary
    return AgentOutput(agent="Cross-check", engine="rules", data={
        "issues": issues, "km_verified": km_verified, "rollback_suspected": rollback,
        "effective_km": effective_km, "service_regular": regular, "km_per_year": km_per_year,
    }, summary=summary)
