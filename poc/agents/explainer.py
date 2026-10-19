"""Explainer agent: seller message, inspector checklist and dealer badge.

The English copy is built from the findings by template, so it can only say what the
other agents found. It also asks OpenAI for a Hindi version of the same text.
"""
from __future__ import annotations

from typing import Any

from ..config import MIN_CONFIDENCE
from ..models import AgentOutput, inr

ALWAYS_CHECK = [
    "Engine start, idle and noise",
    "Gearbox and clutch",
    "Underbody: rust, leaks, flood marks",
    "Suspension and steering",
    "Electricals and AC",
]


def run(engine: Any, pricing: dict, cross: dict, variant: dict, odometer: dict, damage: dict,
        document: dict) -> AgentOutput:
    seller: list[str] = []
    band = pricing.get("verified_band")
    if band:
        seller.append(f"Based on your photos, your car is likely to fetch {inr(band['low'])} to {inr(band['high'])}.")
    else:
        seller.append("We have checked your photos. A price range will follow from Cars24's pricing for this model.")
    seller += pricing.get("notes", [])
    if pricing.get("verified_facts"):
        seller.append("Confirmed from your photos: " + ", ".join(pricing["verified_facts"]) + ".")
    for p in pricing.get("pending_price_items", []):
        seller.append(f"The inspector will price: {p['item']}.")
    if cross.get("rollback_suspected"):
        seller.append("Your odometer reading is lower than your service records. The inspector will check this first.")
    seller.append("The final offer comes from the dealer auction after a short inspection that confirms these findings.")

    tips: list[str] = []
    if not document.get("documents_found"):
        tips.append("Add a photo of your service booklet or latest invoices: documented history narrows your price band.")
    if (damage.get("tyres") or {}).get("confidence", 0) < MIN_CONFIDENCE:
        tips.append("Add a close-up of your most worn tyre so tyre condition is known before the visit.")
    tips += damage.get("photo_notes", [])

    checklist: list[dict[str, str]] = []
    for issue in cross.get("issues", []):
        if issue["severity"] in ("critical", "warning"):
            checklist.append({"item": issue["message"], "type": "resolve", "severity": issue["severity"]})
    for f in pricing.get("flags", []):
        checklist.append({"item": f, "type": "verify", "severity": "flag"})
    already = " ".join(c["item"] for c in checklist)
    for p in pricing.get("pending_price_items", []):
        if p["item"] in already:  # already on the list as an issue to resolve
            continue
        checklist.append({"item": f"Confirm and price: {p['item']}", "type": "confirm", "severity": "ai_finding"})
    for item in ALWAYS_CHECK:
        checklist.append({"item": item, "type": "always", "severity": "routine"})

    badge = {
        "variant_verified": variant.get("detected") not in (None, "unknown") and variant.get("confidence", 0) >= MIN_CONFIDENCE,
        "odometer_verified": bool(cross.get("km_verified")),
        "rc_read": bool((document.get("rc") or {}).get("found")),
        "service_history": "regular" if cross.get("service_regular") else
                           ("partial" if document.get("documents_found") else "not provided"),
        "visible_damage_items": len([d for d in damage.get("damages", []) if d["confidence"] >= MIN_CONFIDENCE]),
        "critical_issues": len([i for i in cross.get("issues", []) if i["severity"] == "critical"]),
    }

    hindi = None
    try:
        hindi = engine.write("Translate this message for a used-car seller into simple, polite Hindi (Devanagari). "
                             "Keep all rupee amounts and numbers exactly as written. Return only the translation.\n\n"
                             + "\n".join(seller))
    except Exception:  # noqa: BLE001 - the translation is a nice-to-have
        hindi = None

    return AgentOutput(agent="Explainer", engine="template" + (" + openai (Hindi)" if hindi else ""), data={
        "seller_message": seller, "seller_message_hi": hindi, "seller_tips": tips,
        "inspector_checklist": checklist, "dealer_badge": badge,
    }, summary=f"Seller message and a {len(checklist)}-item inspector checklist prepared.")
