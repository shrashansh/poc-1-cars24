"""Pricing agent: deterministic rules on top of a REAL price reference. No language model sets a price.

- The starting band is a real quote for this model, year and variant (price_references.json).
  If none exists, no rupee band is produced; the findings are still reported.
- Verified facts narrow the band. Visible damage is listed for Cars24's deduction table to price;
  this POC does not invent rupee deductions.
"""
from __future__ import annotations

from typing import Any

from ..config import MIN_CONFIDENCE
from ..models import AgentOutput, Job, inr

PANEL_NAMES = {
    "front_bumper": "Front bumper", "bonnet": "Bonnet", "windshield": "Windshield", "roof": "Roof",
    "boot": "Boot lid", "rear_bumper": "Rear bumper", "left_front_fender": "Left front fender",
    "left_front_door": "Left front door", "left_rear_door": "Left rear door", "left_quarter": "Left rear quarter",
    "right_front_fender": "Right front fender", "right_front_door": "Right front door",
    "right_rear_door": "Right rear door", "right_quarter": "Right rear quarter", "other": "Other panel",
}


def find_reference(refs: dict[str, Any], model_id: str, year: int, variant: str) -> dict[str, Any] | None:
    return ((refs.get(model_id) or {}).get(str(year)) or {}).get(variant)


def run(job: Job, refs: dict[str, Any], variant: dict, cross: dict, damage: dict, capture: dict) -> AgentOutput:
    rules = refs["band_rules"]
    rate = refs["km_rate_per_km"]
    verified: list[str] = []
    pending: list[dict[str, str]] = []  # findings with a price effect that Cars24's tables must value
    flags: list[str] = []
    notes: list[str] = []

    # Which variant to price: the declared one, unless the photos confidently show another
    priced_variant = job.declared_variant
    detected, vconf = variant.get("detected"), variant.get("confidence", 0)
    if detected not in (None, "unknown") and vconf >= MIN_CONFIDENCE:
        verified.append(f"Variant {detected}")
        if detected != job.declared_variant:
            priced_variant = detected
            notes.append(f"Re-quoted at the {detected} variant seen in the photos (declared {job.declared_variant}).")
    else:
        flags.append("Variant not confirmed from photos")

    ref = find_reference(refs, job.model_id, job.year, priced_variant)
    declared_ref = find_reference(refs, job.model_id, job.year, job.declared_variant)
    if priced_variant != job.declared_variant and ref is None:
        pending.append({"item": f"Variant correction {job.declared_variant} → {priced_variant}",
                        "effect": "re-quote needed", "why": "no real reference for the detected variant"})
        ref = declared_ref

    # Odometer
    km_note = None
    if cross.get("km_verified"):
        verified.append(f"Odometer {cross['effective_km']:,} km")
    elif cross.get("rollback_suspected"):
        flags.append("Odometer rollback suspected: inspector to verify cluster and service records")
    else:
        flags.append("Odometer not verified from photos")

    # Visible damage and non-original parts: listed, never given an invented rupee value
    for d in damage.get("damages", []):
        name = PANEL_NAMES.get(d["panel"], "Panel")
        if d["confidence"] >= MIN_CONFIDENCE:
            verified.append(f"{name} condition")
            pending.append({"item": f"{name}: {d['issue']}", "effect": "deduction", "why": f"{d['severity']} damage"})
        else:
            flags.append(f"{name}: {d['issue']} ({d['confidence']:.0%} confidence)")
    for o in damage.get("observations", []):
        if o.get("confidence", 0) >= MIN_CONFIDENCE:
            pending.append({"item": o["item"], "effect": "possible deduction", "why": "non-original part; inspector confirms"})
    tyres = damage.get("tyres", {})
    if tyres.get("confidence", 0) >= MIN_CONFIDENCE:
        verified.append("Tyre condition")
        if tyres.get("worn_count"):
            pending.append({"item": f"{tyres['worn_count']} tyre(s) look worn", "effect": "deduction", "why": "tyre wear"})
    elif tyres.get("worn_count"):
        flags.append(f"{tyres['worn_count']} tyre(s) may be worn: measure tread")
    if cross.get("service_regular"):
        verified.append("Regular service history")

    data: dict[str, Any] = {"currency": "INR", "reference": None, "verified_band": None,
                            "verified_facts": verified, "pending_price_items": pending,
                            "flags": flags, "notes": notes, "band_rules_note": rules.get("_note")}

    if ref is None:
        data["summary_reason"] = "No real price reference for this model, year and variant."
        return AgentOutput(agent="Pricing", engine="rules", data=data,
                           summary="No real price reference for this car, so no rupee band; findings are listed for pricing.")

    low, high = ref["low"], ref["high"]
    mid, half = (low + high) / 2, (high - low) / 2
    base = {"low": low, "high": high, "source": ref["source"], "variant": priced_variant}

    # A km correction only when the reference states the km it was quoted at
    if cross.get("km_verified") and ref.get("km") is not None:
        delta = -(cross["effective_km"] - ref["km"]) * rate
        mid += delta
        km_note = f"Odometer {cross['effective_km']:,} km vs {ref['km']:,} km in the reference: {'+' if delta >= 0 else '−'}{inr(abs(delta))}"
    elif cross.get("rollback_suspected") and ref.get("km") is not None:
        delta = -(cross["effective_km"] - ref["km"]) * rate
        mid += delta
        km_note = f"Priced at the higher service-record reading ({cross['effective_km']:,} km) until resolved"

    # Narrow for what is verified; widen if the odometer is disputed
    if detected not in (None, "unknown") and vconf >= MIN_CONFIDENCE:
        half *= rules["narrow_variant_verified"]
    if cross.get("km_verified"):
        half *= rules["narrow_odometer_verified"]
    if capture.get("exterior_ok", 0) >= 3:
        half *= rules["narrow_exterior_coverage"]
    if cross.get("service_regular"):
        half *= rules["narrow_service_regular"]
    if cross.get("rollback_suspected"):
        half *= rules["widen_on_rollback"]
    half = max(half, mid * rules["floor_pct"])

    new_low, new_high = mid - half, mid + half
    change = 1 - (new_high - new_low) / (high - low)
    data.update({
        "reference": base,
        "verified_band": {"low": round(new_low), "high": round(new_high), "mid": round(mid)},
        "band_width_change_pct": round(change * 100, 1),
        "km_note": km_note,
    })
    summary = (f"{inr(new_low)}–{inr(new_high)} vs reference {inr(low)}–{inr(high)} "
               f"({abs(change):.0%} {'narrower' if change >= 0 else 'wider'}); "
               f"{len(pending)} item(s) left for Cars24's deduction table.")
    return AgentOutput(agent="Pricing", engine="rules", data=data, summary=summary)
