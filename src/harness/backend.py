"""The BYOK backend seam: one provider-shaped adapter behind a Protocol.

Everything model-backed goes through :class:`Backend`. The seam knows about
providers, HTTP, media encoding and the provider's content gate; it knows
nothing about comedy, transcripts or records. A lens builds a
:class:`Request` (prompt + media + schema) and gets back a
:class:`Completion`; swapping providers is a router-map entry, not a rewrite.

The content gate is the reason the retry policy lives here rather than in a
lens. The provider's gate is *probabilistic* — the identical profane window
was rejected once and accepted on the next three runs — so a single rejection
is not a fact about the media. We retry a gate trip up to three attempts, with
no sleep, and only then raise :class:`GateTripped` carrying the provider's
reason. Non-gate failures (auth, 5xx, timeout, malformed JSON) are not retried.

Keys are read from the user's config files and are never printed, logged, or
interpolated into an exception.
"""

from __future__ import annotations

import base64
import json
import urllib.error
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol

__all__ = [
    "Backend",
    "BackendError",
    "Completion",
    "GateTripped",
    "InferHubBackend",
    "MalformedReply",
    "MediaRef",
    "Request",
    "get_backend",
    "load_keys",
]

_ENV_FILE = Path("C:/Users/pujan/Desktop/configs/.env")
_CREDENTIALS_FILE = Path.home() / ".dsh" / ".credentials.yaml"
_TIMEOUT_S = 180
_MAX_ATTEMPTS = 3

# InferHub's content gate, on the input side. This string lives here and
# nowhere else: only the backend is allowed to know how the provider refuses.
_GATE_TRIP_MARKER = "DataInspectionFailed"
# The mirror-image refusal, seen when a call routes through a provider that
# gates the model's *output* rather than its input.
_OUTPUT_GATE_MARKERS = ("inappropriate content",)

_PROVIDERS = ("inferhub", "openrouter")


class BackendError(RuntimeError):
    """An unrecoverable backend failure: auth, transport, or malformed reply."""


class MalformedReply(BackendError):
    """The model replied, but not with a JSON object.

    A reply-shape failure, not a transport failure: it is the same class as a
    missing field or an unknown label, so a lens re-asks it once rather than
    failing the window. Transport and HTTP errors stay plain
    :class:`BackendError` and are never retried.
    """


class GateTripped(Exception):
    """The provider's content gate rejected the input after every retry."""

    def __init__(self, reason: str, attempts: int = _MAX_ATTEMPTS) -> None:
        super().__init__(reason)
        self.reason = reason
        self.attempts = attempts


@dataclass(frozen=True, slots=True)
class MediaRef:
    """One piece of media attached to a request."""

    kind: str  # "video" | "audio" | "image"
    path: Path


@dataclass(frozen=True, slots=True)
class Request:
    """A single model call: prompt, media, and the JSON shape we expect back."""

    model: str
    prompt: str
    media: tuple[MediaRef, ...] = ()
    schema: dict[str, Any] | None = None


@dataclass(frozen=True, slots=True)
class Completion:
    """The model's structured answer plus the envelope needed to record it."""

    content: dict[str, Any]
    model: str
    usage: dict[str, Any]
    attempts: int


class Backend(Protocol):
    """The seam every provider implements."""

    def complete(self, request: Request) -> Completion: ...


def _parse_env_file(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        values[key.strip()] = value.strip().strip('"').strip("'")
    return values


def _find_key(node: object, wanted: str) -> str | None:
    """Depth-first search for ``wanted`` anywhere in a parsed YAML tree."""
    if isinstance(node, dict):
        for key, value in node.items():
            if key == wanted and isinstance(value, str):
                return value
            found = _find_key(value, wanted)
            if found is not None:
                return found
    elif isinstance(node, list):
        for item in node:
            found = _find_key(item, wanted)
            if found is not None:
                return found
    return None


def load_keys() -> dict[str, str]:
    """Read provider keys from the user's config files. Never printed."""
    if _ENV_FILE.is_file():
        values = _parse_env_file(_ENV_FILE)
        if values.get("INFERHUB_API_KEY"):
            return values

    if _CREDENTIALS_FILE.is_file():
        import yaml

        tree = yaml.safe_load(_CREDENTIALS_FILE.read_text(encoding="utf-8")) or {}
        key = _find_key(tree, "INFERHUB_API_KEY")
        url = _find_key(tree, "INFERHUB_API_URL")
        if key:
            return {"INFERHUB_API_KEY": key, "INFERHUB_API_URL": url or ""}

    raise BackendError(
        "INFERHUB_API_KEY not found in the config env file or the credentials file"
    )


def _data_uri(path: Path, kind: str) -> str:
    mime = {
        "video": "video/mp4",
        "audio": "audio/wav",
        "image": "image/jpeg",
    }[kind]
    encoded = base64.b64encode(path.read_bytes()).decode("ascii")
    return f"data:{mime};base64,{encoded}"


def _content_blocks(request: Request) -> list[dict[str, Any]]:
    prompt = request.prompt
    if request.schema is not None:
        prompt = (
            f"{prompt}\n\nReturn ONLY a JSON object matching this schema:\n"
            f"{json.dumps(request.schema, indent=2)}"
        )
    blocks: list[dict[str, Any]] = [{"type": "text", "text": prompt}]
    for ref in request.media:
        uri = _data_uri(ref.path, ref.kind)
        if ref.kind == "video":
            blocks.append({"type": "video_url", "video_url": {"url": uri}})
        elif ref.kind == "image":
            blocks.append({"type": "image_url", "image_url": {"url": uri}})
        else:
            bare = uri.split("base64,", 1)[1]
            blocks.append({"type": "input_audio", "input_audio": {"data": bare, "format": "wav"}})
    return blocks


def _extract_json(text: str) -> dict[str, Any]:
    """Parse the model's reply as JSON, tolerating a fenced code block."""
    cleaned = text.strip()
    if cleaned.startswith("```"):
        cleaned = cleaned.split("```", 2)[1]
        if cleaned.startswith("json"):
            cleaned = cleaned[len("json") :]
        cleaned = cleaned.strip()
    try:
        parsed = json.loads(cleaned)
    except json.JSONDecodeError as exc:
        raise MalformedReply(f"model reply was not JSON: {exc}") from exc
    if not isinstance(parsed, dict):
        raise MalformedReply("model reply was not a JSON object")
    return parsed


class InferHubBackend:
    """InferHub's [OI]-compatible endpoint, primary route for this slice."""

    def __init__(self, api_url: str, api_key: str) -> None:
        self.api_url = api_url.rstrip("/")
        self._api_key = api_key

    def _post(self, body: dict[str, Any]) -> tuple[dict[str, Any] | None, str]:
        """POST one request. Returns ``(payload, "")`` or ``(None, error_text)``."""
        request = urllib.request.Request(
            f"{self.api_url}/chat/completions",
            data=json.dumps(body).encode("utf-8"),
            headers={
                "Authorization": f"Bearer {self._api_key}",
                "Content-Type": "application/json",
            },
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=_TIMEOUT_S) as response:
                return json.loads(response.read().decode("utf-8")), ""
        except urllib.error.HTTPError as exc:
            return None, exc.read().decode("utf-8", "replace")
        except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as exc:
            return None, f"{type(exc).__name__}: {exc}"

    def _build_payload(self, request: Request) -> dict[str, Any]:
        return {
            "model": request.model,
            "messages": [{"role": "user", "content": _content_blocks(request)}],
            "response_format": {"type": "json_object"},
            "max_tokens": 2500,
        }

    def complete(self, request: Request) -> Completion:
        body = self._build_payload(request)
        last_reason = ""
        for attempt in range(1, _MAX_ATTEMPTS + 1):
            payload, error = self._post(body)
            if error:
                if _is_gate_trip(error):
                    last_reason = error
                    continue
                raise BackendError(f"inferhub request failed: {error[:400]}")
            assert payload is not None
            choices = payload.get("choices") or []
            if not choices:
                # A 200 carrying only ``{"error": {...}}``. Whether this is the
                # gate is decided by its text, never assumed from its shape.
                reason = json.dumps(payload.get("error") or payload)
                if _is_gate_trip(reason):
                    last_reason = reason
                    continue
                raise BackendError(f"inferhub returned no choices: {reason[:400]}")
            message = choices[0].get("message") or {}
            content = message.get("content")
            if content is None:
                # No usable content. Retry only a *gate trip*: a genuine provider
                # error must neither be retried nor recorded as ``content_gate``.
                reason = json.dumps(choices[0].get("error") or payload)
                if _is_gate_trip(reason):
                    last_reason = reason
                    continue
                raise BackendError(f"inferhub returned no content: {reason[:400]}")
            return Completion(
                content=_extract_json(content),
                model=payload.get("model", request.model),
                usage=payload.get("usage") or {},
                attempts=attempt,
            )
        raise GateTripped(last_reason or "content gate rejected the input")


def _is_gate_trip(text: str) -> bool:
    if _GATE_TRIP_MARKER in text:
        return True
    lowered = text.lower()
    return any(marker in lowered for marker in _OUTPUT_GATE_MARKERS)


def get_backend(provider_id: str) -> Backend:
    """Resolve a provider id to a backend. Only ``inferhub`` is wired today."""
    if provider_id == "inferhub":
        keys = load_keys()
        return InferHubBackend(
            keys.get("INFERHUB_API_URL") or "https://api.inferhub.dev/v1",
            keys["INFERHUB_API_KEY"],
        )
    if provider_id == "openrouter":
        raise BackendError("provider 'openrouter' is named but not wired; available: inferhub")
    raise BackendError(f"unknown provider {provider_id!r}; available: {', '.join(_PROVIDERS)}")
