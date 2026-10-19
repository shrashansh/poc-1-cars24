"""Flask app: serves the web UI, the sample photos and the inspection API."""
from __future__ import annotations

from pathlib import Path

from flask import Flask, abort, jsonify, request, send_from_directory

from . import config
from .models import SLOTS, Job, Photo
from .orchestrator import inspect, load

ALLOWED_MIME = {"image/jpeg", "image/png", "image/webp"}
MAX_UPLOAD_MB = 15

app = Flask(__name__, static_folder=None)
app.json.sort_keys = False  # keep catalogue order (sample car first)
app.config["MAX_CONTENT_LENGTH"] = MAX_UPLOAD_MB * len(SLOTS) * 1024 * 1024


@app.get("/")
def index():
    return send_from_directory(config.STATIC_DIR, "index.html")


@app.get("/static/<path:name>")
def static_files(name: str):
    return send_from_directory(config.STATIC_DIR, name)


@app.get("/samples/<path:name>")
def sample_photo(name: str):
    path = _safe_path(name)
    if path is None:
        abort(404)
    return send_from_directory(path.parent, path.name)


@app.get("/api/health")
def health():
    return jsonify({"ok": True, "openai_ready": config.openai_enabled(),
                    "openai_model": config.OPENAI_MODEL if config.openai_enabled() else None})


@app.get("/api/catalog")
def catalog():
    v = load("vehicles.json")
    return jsonify({"km_bands": v["km_bands"], "slots": SLOTS,
                    "models": {k: {"label": m["label"], "years": m["years"], "variants": list(m["variants"])}
                               for k, m in v["models"].items()}})


@app.get("/api/samples")
def samples():
    cars = []
    for car in _samples()["cars"]:
        cars.append({"id": car["id"], "title": car["title"], "story": car["story"], "declared": car["declared"],
                     "photos": {slot: f"/samples/{p}" for slot, p in car["photos"].items()},
                     "alternates": {slot: f"/samples/{p}" for slot, p in car.get("alternates", {}).items()}})
    return jsonify({"cars": cars})


@app.post("/api/inspect")
def api_inspect():
    if not config.openai_enabled():
        return _error("Add OPENAI_API_KEY to .env (or the host's environment variables) and restart the server.", 400)
    form = request.form
    vehicles = load("vehicles.json")
    try:
        model_id = form["model_id"]
        model = vehicles["models"][model_id]
        year = int(form["year"])
        declared = form["declared_variant"]
        band = vehicles["km_bands"][int(form["km_band_index"])]
        rc_number = form.get("rc_number", "").strip()
    except (KeyError, ValueError, IndexError):
        return _error("Fill in model, year, variant and km band.", 400)
    if declared not in model["variants"] or year not in model["years"]:
        return _error("That variant or year is not in the catalogue for this model.", 400)

    photos: dict[str, Photo] = {}
    for slot in SLOTS:
        upload = request.files.get(f"photo_{slot}")
        sample = form.get(f"sample_{slot}")  # a sample photo path, e.g. "nexon/front.jpg"
        if upload and upload.filename:
            if upload.mimetype not in ALLOWED_MIME:
                return _error(f"{slot}: use a JPEG, PNG or WebP image.", 400)
            data = upload.read()
            if len(data) > MAX_UPLOAD_MB * 1024 * 1024:
                return _error(f"{slot}: photo is larger than {MAX_UPLOAD_MB} MB.", 400)
            photos[slot] = Photo(slot=slot, data=data, mime=upload.mimetype)
        elif sample:
            path = _safe_path(sample)
            if path is None:
                return _error(f"{slot}: unknown sample photo.", 400)
            photos[slot] = Photo(slot=slot, data=path.read_bytes(), mime="image/jpeg", sample_ref=sample)
    if not photos:
        return _error("Add at least one photo, or load the sample car.", 400)

    job = Job(rc_number=rc_number, model_id=model_id, year=year, declared_variant=declared,
              km_band=(band[0], band[1]), photos=photos)
    try:
        return jsonify(inspect(job))
    except ValueError as exc:
        return _error(str(exc), 400)


def _samples() -> dict:
    return load("samples/samples.json")


def _safe_path(name: str) -> Path | None:
    """Only files listed in samples.json can be served or used."""
    allowed = {p for car in _samples()["cars"] for p in [*car["photos"].values(), *car.get("alternates", {}).values()]}
    if name not in allowed:
        return None
    path = (config.SAMPLES_DIR / name).resolve()
    return path if path.is_file() and config.SAMPLES_DIR.resolve() in path.parents else None


def _error(message: str, status: int):
    return jsonify({"error": message}), status


@app.errorhandler(413)
def too_large(_):
    return _error(f"Upload too large. Keep each photo under {MAX_UPLOAD_MB} MB.", 413)
