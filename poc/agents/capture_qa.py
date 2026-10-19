"""Capture QA agent: local image checks, no AI.

In the production app this runs on the phone so the seller can retake a shot at once.
Here it runs on the server with the same thresholds.
"""
from __future__ import annotations

import io

from PIL import Image, ImageFilter, ImageOps, ImageStat

from ..models import DOCUMENT_SLOTS, EXTERIOR, SLOTS, AgentOutput, Job

MIN_SIDE = 480
TOO_DARK = 45
TOO_BRIGHT = 225
MIN_SHARPNESS = 25.0


def check_image(slot: str, data: bytes) -> dict:
    try:
        img = Image.open(io.BytesIO(data))
        img = ImageOps.exif_transpose(img)
        img.load()
    except Exception:  # noqa: BLE001
        return {"decodable": False, "status": "retake", "issues": ["File could not be read as an image"], "metrics": {}}

    w, h = img.size
    gray = img.convert("L")
    gray.thumbnail((512, 512))
    brightness = ImageStat.Stat(gray).mean[0]
    sharpness = ImageStat.Stat(gray.filter(ImageFilter.FIND_EDGES)).var[0]

    issues = []
    if min(w, h) < MIN_SIDE:
        issues.append(f"Low resolution ({w}×{h}); shoot at least {MIN_SIDE} px on the short side")
    if brightness < TOO_DARK:
        issues.append("Too dark; move to daylight or turn on lights")
    if brightness > TOO_BRIGHT and slot not in DOCUMENT_SLOTS:  # documents are meant to be mostly white
        issues.append("Overexposed; avoid direct sunlight on the lens")
    if sharpness < MIN_SHARPNESS:
        issues.append("Looks blurred; hold the phone steady")

    return {
        "decodable": True,
        "status": "ok" if not issues else "retake",
        "issues": issues,
        "metrics": {"width": w, "height": h, "brightness": round(brightness, 1), "sharpness": round(sharpness, 1)},
    }


def run(job: Job) -> AgentOutput:
    slots = {slot: check_image(slot, photo.data) for slot, photo in job.photos.items()}
    missing = [s for s in SLOTS if s not in job.photos]
    exterior_ok = sum(1 for s in EXTERIOR if slots.get(s, {}).get("status") == "ok")
    retakes = [s for s, r in slots.items() if r["status"] != "ok"]

    parts = [f"{len(slots)} photo(s) checked"]
    if retakes:
        parts.append(f"retake suggested: {', '.join(retakes)}")
    if missing:
        parts.append(f"missing: {', '.join(missing)}")
    return AgentOutput(
        agent="Capture QA", engine="local",
        data={"slots": slots, "missing": missing, "exterior_ok": exterior_ok},
        summary="; ".join(parts) + ".",
    )
