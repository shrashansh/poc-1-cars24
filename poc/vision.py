"""OpenAI vision client: sends photos over HTTPS and asks for one JSON object back."""
from __future__ import annotations

import base64
import io
import json
import time
from typing import Any

import requests
from PIL import Image, ImageOps

from . import config
from .models import SLOT_LABELS, Photo

SYSTEM_PROMPT = (
    "You are a used-car pre-inspection assistant for an Indian used-car marketplace. "
    "You look at seller photos before any inspector visits. Be strictly honest: report only "
    "what is visible, give low confidence when unsure, never invent a number you cannot read, "
    "and reply with a single JSON object exactly in the shape requested."
)


class VisionError(RuntimeError):
    pass


def to_data_url(photo: Photo, max_side: int = 1280) -> str:
    """Downscale and re-encode as JPEG so uploads stay small and phone metadata (GPS) is stripped."""
    img = Image.open(io.BytesIO(photo.data))
    img = ImageOps.exif_transpose(img).convert("RGB")
    img.thumbnail((max_side, max_side))
    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=85)
    return "data:image/jpeg;base64," + base64.b64encode(buf.getvalue()).decode("ascii")


class OpenAIVision:
    name = "openai"

    def __init__(self, api_key: str | None = None, model: str | None = None,
                 base_url: str | None = None, timeout: float | None = None) -> None:
        self.api_key = api_key or config.OPENAI_API_KEY
        self.model = model or config.OPENAI_MODEL
        self.base_url = (base_url or config.OPENAI_BASE_URL).rstrip("/")
        self.timeout = timeout or config.OPENAI_TIMEOUT

    def _post(self, messages: list[dict[str, Any]], json_mode: bool) -> str:
        payload: dict[str, Any] = {"model": self.model, "messages": messages}
        if json_mode:
            payload["response_format"] = {"type": "json_object"}
        last_error = ""
        for attempt in range(2):  # one retry on rate limits and server errors
            try:
                resp = requests.post(
                    f"{self.base_url}/chat/completions",
                    headers={"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json"},
                    json=payload, timeout=self.timeout,
                )
            except requests.RequestException as exc:
                raise VisionError(f"Could not reach OpenAI: {exc}") from exc
            if resp.status_code == 200:
                return resp.json()["choices"][0]["message"]["content"] or ""
            last_error = f"OpenAI returned {resp.status_code}: {_error_text(resp)}"
            if resp.status_code in (429, 500, 502, 503) and attempt == 0:
                time.sleep(2)
                continue
            break
        raise VisionError(last_error)

    def ask(self, task: str, prompt: str, photos: list[Photo]) -> dict[str, Any]:
        content: list[dict[str, Any]] = [{"type": "text", "text": prompt}]
        for i, p in enumerate(photos, 1):
            content.append({"type": "text", "text": f"Image {i}: {SLOT_LABELS.get(p.slot, p.slot)}"})
            content.append({"type": "image_url", "image_url": {"url": to_data_url(p), "detail": "high"}})
        text = self._post([{"role": "system", "content": SYSTEM_PROMPT},
                           {"role": "user", "content": content}], json_mode=True)
        try:
            data = json.loads(text)
        except json.JSONDecodeError as exc:
            raise VisionError("The model did not return valid JSON.") from exc
        if not isinstance(data, dict):
            raise VisionError("The model returned JSON that is not an object.")
        return data

    def write(self, prompt: str) -> str | None:
        return self._post([{"role": "user", "content": prompt}], json_mode=False).strip() or None


def _error_text(resp: requests.Response) -> str:
    try:
        return resp.json().get("error", {}).get("message", "")[:300]
    except ValueError:
        return resp.text[:300]
