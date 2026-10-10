"""Tests for the BYOK backend seam. No network: the transport is stubbed."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from harness import backend as backend_mod
from harness.backend import (
    BackendError,
    Completion,
    GateTripped,
    InferHubBackend,
    MalformedReply,
    MediaRef,
    Request,
    _content_blocks,
    _extract_json,
    get_backend,
    load_keys,
)

_FIXTURES = Path(__file__).resolve().parent / "fixtures" / "backend"
_SUCCESS = json.loads((_FIXTURES / "success_response.json").read_text(encoding="utf-8"))
_GATE = (_FIXTURES / "gate_trip_error.txt").read_text(encoding="utf-8")


def _backend() -> InferHubBackend:
    return InferHubBackend("https://api.example.test/v1", "fixture_key")


def _request(tmp_path: Path) -> Request:
    clip = tmp_path / "clip.mp4"
    clip.write_bytes(b"\x00\x01\x02")
    return Request(
        model="ali/qwen3.8-omni-flash", prompt="analyse", media=(MediaRef("video", clip),)
    )


# --------------------------------------------------------------------------
# Key loading
# --------------------------------------------------------------------------


def test_load_keys_reads_env_file(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(backend_mod, "_ENV_FILE", _FIXTURES / "test_keys.env")
    keys = load_keys()
    assert keys["INFERHUB_API_KEY"] == "fixture_key_value"
    assert keys["INFERHUB_API_URL"] == "https://api.example.test/v1"


def test_load_keys_missing_raises_without_leaking(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(backend_mod, "_ENV_FILE", Path("does_not_exist.env"))
    monkeypatch.setattr(backend_mod, "_CREDENTIALS_FILE", Path("does_not_exist.yaml"))
    with pytest.raises(BackendError) as excinfo:
        load_keys()
    assert "INFERHUB_API_KEY" in str(excinfo.value)


# --------------------------------------------------------------------------
# Request assembly
# --------------------------------------------------------------------------


def test_content_blocks_encodes_video_and_prompt(tmp_path: Path) -> None:
    blocks = _content_blocks(_request(tmp_path))
    assert blocks[0]["type"] == "text"
    assert blocks[1]["type"] == "video_url"
    assert blocks[1]["video_url"]["url"].startswith("data:video/mp4;base64,")


def test_content_blocks_includes_schema_when_present(tmp_path: Path) -> None:
    req = Request(
        model="m", prompt="p", media=(), schema={"type": "object", "properties": {}}
    )
    assert "Return ONLY a JSON object" in _content_blocks(req)[0]["text"]


def test_extract_json_tolerates_fences() -> None:
    assert _extract_json('```json\n{"a": 1}\n```') == {"a": 1}


def test_extract_json_rejects_non_object() -> None:
    with pytest.raises(MalformedReply):
        _extract_json("[1, 2, 3]")


def test_extract_json_rejects_non_json_as_malformed_reply() -> None:
    """A non-JSON reply is a reply-shape failure, so a lens can re-ask it once.

    It used to raise plain ``BackendError``, which the lenses do not catch for a
    re-ask — so the first non-JSON reply failed the whole window.
    """
    with pytest.raises(MalformedReply) as excinfo:
        _extract_json("Sure! Here are the beats: {\"quote\": \"x\"}")
    assert isinstance(excinfo.value, BackendError)  # still a backend failure


# --------------------------------------------------------------------------
# Completion and the gate-trip retry policy
# --------------------------------------------------------------------------


def test_complete_returns_parsed_content(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    backend = _backend()
    monkeypatch.setattr(backend, "_post", lambda body: (_SUCCESS, ""))
    result = backend.complete(_request(tmp_path))
    assert isinstance(result, Completion)
    assert result.content["beats"][0]["quote"] == "this game's not that hard"
    assert result.model == "ali/qwen3.8-omni-flash"
    assert result.attempts == 1


def test_gate_trip_retries_three_times(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    backend = _backend()
    calls = {"n": 0}

    def always_gate(body: object) -> tuple[None, str]:
        calls["n"] += 1
        return None, _GATE

    monkeypatch.setattr(backend, "_post", always_gate)
    with pytest.raises(GateTripped) as excinfo:
        backend.complete(_request(tmp_path))
    assert calls["n"] == 3
    assert "DataInspectionFailed" in excinfo.value.reason


def test_gate_trip_succeeds_on_second_attempt(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    backend = _backend()
    responses = [(None, _GATE), (_SUCCESS, "")]

    def flaky(body: object) -> tuple[object, str]:
        return responses.pop(0)

    monkeypatch.setattr(backend, "_post", flaky)
    result = backend.complete(_request(tmp_path))
    assert result.attempts == 2


def test_non_gate_error_is_not_retried(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    backend = _backend()
    calls = {"n": 0}

    def server_error(body: object) -> tuple[None, str]:
        calls["n"] += 1
        return None, "HTTP 500: internal server error"

    monkeypatch.setattr(backend, "_post", server_error)
    with pytest.raises(BackendError):
        backend.complete(_request(tmp_path))
    assert calls["n"] == 1


# --------------------------------------------------------------------------
# 200 responses that are not a completion
#
# Both shapes are real (the spike saw the first), and both used to escape the
# pass: a ``KeyError`` on ``choices`` killed the whole video rather than failing
# one window, and a non-gate ``finish_reason: "error"`` was retried three times
# and then recorded as ``content_gate:``.
# --------------------------------------------------------------------------


def test_error_shaped_200_without_choices_raises_backend_error(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    backend = _backend()
    calls = {"n": 0}
    payload = {"error": {"message": "upstream unavailable", "code": 503}}

    def error_payload(body: object) -> tuple[dict[str, object], str]:
        calls["n"] += 1
        return payload, ""

    monkeypatch.setattr(backend, "_post", error_payload)
    with pytest.raises(BackendError, match="no choices"):
        backend.complete(_request(tmp_path))
    assert calls["n"] == 1


def test_non_gate_finish_error_is_not_retried(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    backend = _backend()
    calls = {"n": 0}
    payload = {"choices": [{"finish_reason": "error", "message": {"content": None}}]}

    def failed(body: object) -> tuple[dict[str, object], str]:
        calls["n"] += 1
        return payload, ""

    monkeypatch.setattr(backend, "_post", failed)
    with pytest.raises(BackendError, match="no content"):
        backend.complete(_request(tmp_path))
    assert calls["n"] == 1  # a genuine provider error is not a gate trip


def test_gated_200_without_content_is_retried(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    backend = _backend()
    calls = {"n": 0}
    payload = {
        "choices": [
            {"finish_reason": "error", "error": {"message": "DataInspectionFailed"}}
        ]
    }

    def gated(body: object) -> tuple[dict[str, object], str]:
        calls["n"] += 1
        return payload, ""

    monkeypatch.setattr(backend, "_post", gated)
    with pytest.raises(GateTripped):
        backend.complete(_request(tmp_path))
    assert calls["n"] == 3


# --------------------------------------------------------------------------
# Router
# --------------------------------------------------------------------------


def test_get_backend_inferhub_wired(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(backend_mod, "_ENV_FILE", _FIXTURES / "test_keys.env")
    assert isinstance(get_backend("inferhub"), InferHubBackend)


def test_get_backend_openrouter_named_but_unwired() -> None:
    with pytest.raises(BackendError, match="not wired"):
        get_backend("openrouter")


def test_get_backend_unknown_provider() -> None:
    with pytest.raises(BackendError, match="unknown provider"):
        get_backend("nope")
