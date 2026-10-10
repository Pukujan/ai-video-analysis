"""Versioned analysis profiles: the config/control layer.

The harness core is game- and creator-agnostic. Everything specific to one
creator or one game — the measurement thresholds and the declared vocabulary of
entities, motifs and HUD slots — lives in a versioned profile rather than in
code, so a new domain is a data change, not a code change. A run records the
``profile_id``, ``profile_version`` and ``config_hash`` that produced it, so the
same bytes measured under two profiles stay distinguishable in the store.

This is the Application Profile pattern: a frozen base plus versioned per-domain
extensions. ``config/base.toml`` reproduces the historical deterministic pass
exactly; a profile overlays it key-by-key (tables merge, scalars and lists
replace). The ``ext:<slug>`` slots in :mod:`harness.vocab` are where a profile's
own terms are allowed to enter — the core vocabularies stay closed.

Strictness lives here, at load time: an unknown key, a bad schema version, an
out-of-range threshold or a bare (non-``ext:``) term raises :class:`ConfigError`
rather than being silently stored.
"""

from __future__ import annotations

import hashlib
import json
import re
import tomllib
from enum import StrEnum
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator, model_validator

from harness import vocab
from harness.vocab import EntityKind, is_extension_token, validate_vocab

__all__ = [
    "AnalysisProfile",
    "CONFIG_SCHEMA_VERSION",
    "DEFAULT_CONFIG_DIR",
    "ConfigError",
    "load_profile",
]

CONFIG_SCHEMA_VERSION = "1.0.0"
DEFAULT_CONFIG_DIR = Path(__file__).resolve().parents[2] / "config"

_ID_RE = re.compile(r"^[a-z0-9_]+$")
_VERSION_RE = re.compile(r"^\d+\.\d+\.\d+$")


class ConfigError(RuntimeError):
    """Raised when a profile config is missing, malformed or inconsistent."""


class _StrictConfig(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, str_strip_whitespace=True)


class ProfileIdentity(_StrictConfig):
    """Which (creator, game) domain a run belongs to."""

    id: str
    version: str
    creator_id: str | None = None
    game_id: str | None = None
    game_label: str | None = None

    @field_validator("id")
    @classmethod
    def _check_id(cls, value: str) -> str:
        if not _ID_RE.match(value):
            raise ValueError(f"profile id {value!r} must match ^[a-z0-9_]+$")
        return value

    @field_validator("version")
    @classmethod
    def _check_version(cls, value: str) -> str:
        if not _VERSION_RE.match(value):
            raise ValueError(f"profile version {value!r} must be MAJOR.MINOR.PATCH")
        return value


class PolicyConfig(_StrictConfig):
    id: str = "det-v1"


class WindowingConfig(_StrictConfig):
    window_ms: int = Field(gt=0)
    overlap_ms: int = Field(ge=0)

    @model_validator(mode="after")
    def _check(self) -> WindowingConfig:
        if self.overlap_ms >= self.window_ms:
            raise ValueError("overlap_ms must be smaller than window_ms")
        return self


class SilenceConfig(_StrictConfig):
    noise_db: float = Field(lt=0)
    min_s: float = Field(gt=0)


class SceneConfig(_StrictConfig):
    threshold: float = Field(gt=0, lt=1)
    cut_score_threshold: float = Field(gt=0, lt=1)

    @model_validator(mode="after")
    def _check(self) -> SceneConfig:
        if self.cut_score_threshold < self.threshold:
            raise ValueError("cut_score_threshold must be >= threshold")
        return self


class ToolingConfig(_StrictConfig):
    ffmpeg_version: str


class EntityDecl(_StrictConfig):
    """A declared recurring target in the profile's game (a boss, an enemy)."""

    id: str
    kind: str
    label: str | None = None
    aliases: list[str] = Field(default_factory=list)

    @field_validator("kind")
    @classmethod
    def _check_kind(cls, value: str) -> str:
        return validate_vocab(value, EntityKind, "kind")


class MotifDecl(_StrictConfig):
    """A declared recurring visual or editorial motif of the profile's creator."""

    id: str
    label: str
    note: str | None = None


class HudRegionDecl(_StrictConfig):
    """A declared on-screen HUD slot (health, stamina, Estus, souls).

    Coordinates are optional and declared, not consumed: the deterministic pass
    reads no pixels, so a rectangle here is a name for a region, not a measured
    fact. The coordinate convention arrives with the reader that consumes them.
    """

    id: str
    label: str | None = None
    x: int | None = Field(default=None, ge=0)
    y: int | None = Field(default=None, ge=0)
    w: int | None = Field(default=None, gt=0)
    h: int | None = Field(default=None, gt=0)

    @model_validator(mode="after")
    def _check_coords(self) -> HudRegionDecl:
        coords = (self.x, self.y, self.w, self.h)
        if any(c is not None for c in coords) and any(c is None for c in coords):
            raise ValueError("hud region coordinates must be all present or all absent")
        return self


def _core_vocab_values() -> set[str]:
    """Every member value across the closed vocabularies in :mod:`harness.vocab`."""
    values: set[str] = set()
    for name in vocab.__all__:
        member = getattr(vocab, name)
        if isinstance(member, type) and issubclass(member, StrEnum):
            values.update(item.value for item in member)
    return values


class VocabularyConfig(_StrictConfig):
    """The profile's declared terms, entities, motifs and HUD slots.

    ``terms`` are ``ext:<slug>`` tokens the profile adds; they may not be bare
    strings (a typo would enter silently) and may not shadow a core member.
    """

    terms: list[str] = Field(default_factory=list)
    entities: list[EntityDecl] = Field(default_factory=list)
    motifs: list[MotifDecl] = Field(default_factory=list)
    hud_regions: list[HudRegionDecl] = Field(default_factory=list)

    @field_validator("terms")
    @classmethod
    def _check_terms(cls, value: list[str]) -> list[str]:
        core = _core_vocab_values()
        for term in value:
            if not is_extension_token(term):
                raise ValueError(f"profile term {term!r} must be an ext:<slug> token")
            if term[len("ext:") :] in core:
                raise ValueError(f"profile term {term!r} shadows a core vocabulary member")
        return value

    @model_validator(mode="after")
    def _check_unique_ids(self) -> VocabularyConfig:
        groups = {
            "entities": [entity.id for entity in self.entities],
            "motifs": [motif.id for motif in self.motifs],
            "hud_regions": [region.id for region in self.hud_regions],
        }
        for name, ids in groups.items():
            if len(set(ids)) != len(ids):
                raise ValueError(f"duplicate ids in {name}")
        return self


class AnalysisProfile(_StrictConfig):
    """A fully-resolved profile: the base config with one overlay merged in."""

    schema_version: str = CONFIG_SCHEMA_VERSION
    profile: ProfileIdentity
    policy: PolicyConfig
    windowing: WindowingConfig
    silence: SilenceConfig
    scene: SceneConfig
    tooling: ToolingConfig
    vocabulary: VocabularyConfig = Field(default_factory=VocabularyConfig)

    @model_validator(mode="after")
    def _check_schema(self) -> AnalysisProfile:
        if self.schema_version != CONFIG_SCHEMA_VERSION:
            raise ValueError(
                f"config schema_version {self.schema_version!r} is not "
                f"{CONFIG_SCHEMA_VERSION!r}"
            )
        return self

    def policy_string(self) -> str:
        """The human-readable policy line that is hashed into ``prompt_hash``."""
        return (
            f"{self.policy.id}:ebur128=peak;"
            f"silencedetect={self.silence.noise_db:g}dB/{self.silence.min_s:g}s;"
            f"scene>{self.scene.threshold:g}"
        )

    def silence_method(self) -> str:
        """The recorded extraction method for a silence span."""
        return (
            f"ffmpeg {self.tooling.ffmpeg_version} "
            f"silencedetect=noise={self.silence.noise_db:g}dB:d={self.silence.min_s:g}"
        )

    def run_id_tag(self) -> str:
        """The run-id suffix: ``det_v1`` for base, ``det_v1_<profile>`` otherwise."""
        return "det_v1" if self.profile.id == "base" else f"det_v1_{self.profile.id}"

    def run_id(self, digest: str) -> str:
        return f"run_{digest[:12]}_{self.run_id_tag()}"

    def config_hash(self) -> str:
        """A stable hash of the resolved profile, for the run's reproducibility envelope."""
        blob = json.dumps(self.model_dump(mode="json"), sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(blob.encode("utf-8")).hexdigest()


def _read_toml(path: Path) -> dict[str, Any]:
    try:
        with path.open("rb") as handle:
            return tomllib.load(handle)
    except FileNotFoundError as exc:
        raise ConfigError(f"config file not found: {path}") from exc
    except tomllib.TOMLDecodeError as exc:
        raise ConfigError(f"invalid TOML in {path}: {exc}") from exc


def _merge(base: dict[str, Any], overlay: dict[str, Any]) -> dict[str, Any]:
    """Deep-merge ``overlay`` onto ``base``: tables merge, everything else replaces."""
    merged = dict(base)
    for key, value in overlay.items():
        existing = merged.get(key)
        if isinstance(value, dict) and isinstance(existing, dict):
            merged[key] = _merge(existing, value)
        else:
            merged[key] = value
    return merged


def load_profile(
    profile_id: str | None = None, config_dir: Path | None = None
) -> AnalysisProfile:
    """Load ``base.toml`` and, when named, overlay ``profiles/<id>.toml`` on top.

    ``profile_id=None`` or ``"base"`` yields the base profile alone.
    """
    root = config_dir if config_dir is not None else DEFAULT_CONFIG_DIR
    data = _read_toml(root / "base.toml")
    if profile_id is not None and profile_id != "base":
        overlay = _read_toml(root / "profiles" / f"{profile_id}.toml")
        data = _merge(data, overlay)
    try:
        return AnalysisProfile.model_validate(data)
    except ValidationError as exc:
        raise ConfigError(f"invalid profile config ({profile_id or 'base'}): {exc}") from exc
