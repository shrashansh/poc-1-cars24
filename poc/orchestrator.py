"""Orchestrator: runs the agents in order, the evidence agents in parallel, and builds one report."""
from __future__ import annotations

import json
import time
from concurrent.futures import ThreadPoolExecutor
from functools import lru_cache
from typing import Any

from . import config
from .agents import capture_qa, cross_check, damage, document, explainer, identity, odometer, pricing, variant
from .models import AgentOutput, Job, guard
from .vision import OpenAIVision


@lru_cache(maxsize=None)
def load(name: str) -> Any:
    return json.loads((config.DATA_DIR / name).read_text(encoding="utf-8"))


def make_engine():
    if not config.openai_enabled():
        raise ValueError("Add OPENAI_API_KEY to the .env file and restart the server.")
    return OpenAIVision()


def inspect(job: Job, engine=None) -> dict[str, Any]:
    started = time.perf_counter()
    engine = engine or make_engine()
    vehicles, refs = load("vehicles.json"), load("price_references.json")
    vehicle = vehicles["models"][job.model_id]
    registry = load("rc_registry.json")

    # 1. Capture QA (local). Undecodable files are dropped before any AI call.
    qa = guard("Capture QA", "local", lambda: capture_qa.run(job))
    slots = qa.data.get("slots", {})
    usable = {s: p for s, p in job.photos.items() if slots.get(s, {}).get("decodable", True)}

    # 2. Evidence agents in parallel.
    tasks = {
        "identity": ("Identity", lambda: identity.run(job, usable, engine, registry)),
        "variant": ("Variant", lambda: variant.run(job, usable, engine, vehicle)),
        "odometer": ("Odometer", lambda: odometer.run(job, usable, engine)),
        "damage": ("Damage", lambda: damage.run(job, usable, engine)),
        "document": ("Document", lambda: document.run(job, usable, engine)),
    }
    with ThreadPoolExecutor(max_workers=len(tasks)) as pool:
        futures = {key: pool.submit(guard, name, engine.name, fn) for key, (name, fn) in tasks.items()}
        ev: dict[str, AgentOutput] = {key: f.result() for key, f in futures.items()}

    def data(key: str) -> dict:
        return ev[key].data if ev[key].status != "error" else {}

    # 3. Rules: reconcile, then price.
    cc = guard("Cross-check", "rules", lambda: cross_check.run(
        job, data("identity"), data("variant"), data("odometer"), data("document"), data("damage")))
    pr = guard("Pricing", "rules", lambda: pricing.run(job, refs, data("variant"), cc.data, data("damage"), qa.data))

    # 4. Explain.
    ex = guard("Explainer", "template", lambda: explainer.run(
        engine, pr.data, cc.data, data("variant"), data("odometer"), data("damage"), data("document")))

    agents = [qa, *ev.values(), cc, pr, ex]
    return {
        "job": {
            "rc_number": job.rc_number, "model_id": job.model_id, "model_label": vehicle["label"],
            "year": job.year, "declared_variant": job.declared_variant, "km_band": list(job.km_band),
            "engine": engine.name, "model_used": getattr(engine, "model", None),
            "photos": {s: {"source": "sample" if p.sample_ref else "upload"} for s, p in job.photos.items()},
        },
        "trace": [{k: v for k, v in a.to_dict().items() if k != "data"} for a in agents],
        "agents": {a.agent: a.to_dict() for a in agents},
        "elapsed_ms": int((time.perf_counter() - started) * 1000),
    }
