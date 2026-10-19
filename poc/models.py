"""Shared data types and small helpers used by every agent."""
from __future__ import annotations

import re
import time
from dataclasses import dataclass, field
from typing import Any, Callable

SLOTS = ["front", "rear", "left", "right", "dash", "interior", "seats", "tyre", "rc", "service"]
DOCUMENT_SLOTS = ["rc", "service"]
EXTERIOR = ["front", "rear", "left", "right"]
SLOT_LABELS = {
    "front": "Front view",
    "rear": "Rear view with badges",
    "left": "Left side",
    "right": "Right side",
    "dash": "Dashboard with engine on (odometer)",
    "interior": "Cabin and infotainment",
    "seats": "Front seats and headrests",
    "tyre": "Tyre close-up",
    "rc": "Registration certificate (RC)",
    "service": "Service booklet or invoice",
}
PANELS = [
    "front_bumper", "bonnet", "windshield", "roof", "boot", "rear_bumper",
    "left_front_fender", "left_front_door", "left_rear_door", "left_quarter",
    "right_front_fender", "right_front_door", "right_rear_door", "right_quarter", "other",
]
SEVERITIES = ["minor", "moderate", "major"]


@dataclass
class Photo:
    slot: str
    data: bytes
    mime: str
    sample_ref: str | None = None  # "<sample_id>:<slot>" when picked from the sample photos


@dataclass
class Job:
    rc_number: str
    model_id: str
    year: int
    declared_variant: str
    km_band: tuple[int, int]
    photos: dict[str, Photo]


@dataclass
class AgentOutput:
    agent: str
    engine: str
    status: str = "ok"  # ok | skipped | error
    data: dict[str, Any] = field(default_factory=dict)
    summary: str = ""
    error: str | None = None
    ms: int = 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "agent": self.agent, "engine": self.engine, "status": self.status,
            "summary": self.summary, "error": self.error, "ms": self.ms, "data": self.data,
        }


def guard(agent: str, engine: str, fn: Callable[[], AgentOutput]) -> AgentOutput:
    """Run one agent, time it, and turn any exception into an error result instead of a crash."""
    start = time.perf_counter()
    try:
        out = fn()
    except Exception as exc:  # noqa: BLE001 - one failing agent must never stop the others
        out = AgentOutput(agent=agent, engine=engine, status="error", error=f"{type(exc).__name__}: {exc}",
                          summary="Agent failed; its checks are left to the inspector.")
    out.ms = int((time.perf_counter() - start) * 1000)
    return out


def conf(value: Any) -> float:
    try:
        v = float(value)
    except (TypeError, ValueError):
        return 0.0
    return max(0.0, min(1.0, v))


def as_int(value: Any) -> int | None:
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return int(value)
    digits = re.sub(r"[^\d]", "", str(value))
    return int(digits) if digits else None


def norm_plate(text: Any) -> str:
    return re.sub(r"[^A-Z0-9]", "", str(text or "").upper())


def inr(n: float) -> str:
    """Indian digit grouping: 380459 -> ₹3,80,459."""
    n = int(round(n))
    sign = "-" if n < 0 else ""
    s = str(abs(n))
    if len(s) > 3:
        head, tail = s[:-3], s[-3:]
        groups = []
        while len(head) > 2:
            groups.insert(0, head[-2:])
            head = head[:-2]
        if head:
            groups.insert(0, head)
        s = ",".join(groups + [tail])
    return f"{sign}₹{s}"
