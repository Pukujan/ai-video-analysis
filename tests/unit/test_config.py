"""Tests for the versioned profile config layer."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from harness.config import (
    CONFIG_SCHEMA_VERSION,
    DEFAULT_CONFIG_DIR,
    AnalysisProfile,
    ConfigError,
    load_profile,
)

_FIXTURES = Path(__file__).resolve().parent / "fixtures"
_REAL_BASE = (DEFAULT_CONFIG_DIR / "base.toml").read_text(encoding="utf-8")


def _config_dir(tmp_path: Path, base: str, profiles: dict[str, str] | None = None) -> Path:
    (tmp_path / "profiles").mkdir(parents=True, exist_ok=True)
    (tmp_path / "base.toml").write_text(base, encoding="utf-8")
    for name, text in (profiles or {}).items():
        (tmp_path / "profiles" / f"{name}.toml").write_text(text, encoding="utf-8")
    return tmp_path


# --------------------------------------------------------------------------
# The base profile reproduces the historical constants byte-for-byte
# --------------------------------------------------------------------------


def test_base_profile_reproduces_the_historical_constants(
    base_profile: AnalysisProfile,
) -> None:
    assert base_profile.schema_version == CONFIG_SCHEMA_VERSION
    assert base_profile.profile.id == "base"
    assert base_profile.policy.id == "det-v1"
    assert base_profile.windowing.window_ms == 25_000
    assert base_profile.windowing.overlap_ms == 5_000
    assert base_profile.scene.threshold == 0.4
    assert base_profile.scene.cut_score_threshold == 0.6
    assert base_profile.silence.noise_db == -32.0
    assert base_profile.silence.min_s == 0.4
    assert base_profile.tooling.ffmpeg_version == "8.1.1"


def test_policy_string_matches_the_old_constant(base_profile: AnalysisProfile) -> None:
    assert (
        base_profile.policy_string()
        == "det-v1:ebur128=peak;silencedetect=-32dB/0.4s;scene>0.4"
    )


def test_silence_method_matches_the_old_constant(base_profile: AnalysisProfile) -> None:
    assert base_profile.silence_method() == "ffmpeg 8.1.1 silencedetect=noise=-32dB:d=0.4"


def test_base_run_id_is_unchanged(base_profile: AnalysisProfile) -> None:
    assert base_profile.run_id_tag() == "det_v1"
    assert base_profile.run_id("a" * 64) == "run_" + "a" * 12 + "_det_v1"


def test_policy_hash_reproduces_the_golden_prompt_hash(base_profile: AnalysisProfile) -> None:
    # The golden fixture was captured before the constants moved to config, so
    # its prompt_hash is the contract this refactor must not break.
    line = (_FIXTURES / "analyze_build_golden.jsonl").read_text(encoding="utf-8").splitlines()[2]
    golden = json.loads(line)
    assert golden["record_type"] == "analysis_run"
    expected = golden["data"]["prompt_hash"]
    actual = hashlib.sha256(base_profile.policy_string().encode("utf-8")).hexdigest()[:16]
    assert actual == expected == "4549e2f18465579f"


# --------------------------------------------------------------------------
# Overlay behaviour
# --------------------------------------------------------------------------


def test_ds3_overlay_changes_identity_and_vocabulary_only() -> None:
    base = load_profile()
    ds3 = load_profile("ds3")
    assert ds3.profile.id == "ds3"
    assert ds3.profile.game_id == "dark_souls_3"
    assert ds3.profile.game_label == "Dark Souls III"
    # No threshold moves in v0.1.0: identity and vocabulary change, measurement does not.
    assert ds3.windowing == base.windowing
    assert ds3.silence == base.silence
    assert ds3.scene == base.scene
    assert ds3.tooling == base.tooling
    assert ds3.policy == base.policy
    assert ds3.vocabulary.terms != base.vocabulary.terms
    assert ds3.config_hash() != base.config_hash()


def test_ds3_run_id_is_namespaced() -> None:
    assert load_profile("ds3").run_id("b" * 64) == "run_" + "b" * 12 + "_det_v1_ds3"


def test_ds3_terms_are_extension_tokens() -> None:
    ds3 = load_profile("ds3")
    assert ds3.vocabulary.terms
    assert all(term.startswith("ext:") for term in ds3.vocabulary.terms)
    assert {entity.kind for entity in ds3.vocabulary.entities} == {"boss"}


def test_config_hash_is_stable_across_reloads(base_profile: AnalysisProfile) -> None:
    assert base_profile.config_hash() == load_profile().config_hash()
    assert len(base_profile.config_hash()) == 64


def test_config_hash_changes_when_a_threshold_changes(tmp_path: Path) -> None:
    changed = _REAL_BASE.replace("threshold = 0.4", "threshold = 0.5")
    assert changed != _REAL_BASE
    root = _config_dir(tmp_path, changed)
    assert load_profile(config_dir=root).config_hash() != load_profile().config_hash()


# --------------------------------------------------------------------------
# Rejections: strictness lives at load time
# --------------------------------------------------------------------------


def test_unknown_key_is_rejected(tmp_path: Path) -> None:
    root = _config_dir(tmp_path, _REAL_BASE + '\n[bogus]\nx = 1\n')
    with pytest.raises(ConfigError):
        load_profile(config_dir=root)


def test_bad_schema_version_is_rejected(tmp_path: Path) -> None:
    root = _config_dir(tmp_path, _REAL_BASE.replace('"1.0.0"', '"9.9.9"', 1))
    with pytest.raises(ConfigError):
        load_profile(config_dir=root)


def test_overlap_not_smaller_than_window_is_rejected(tmp_path: Path) -> None:
    root = _config_dir(tmp_path, _REAL_BASE.replace("overlap_ms = 5000", "overlap_ms = 25000"))
    with pytest.raises(ConfigError):
        load_profile(config_dir=root)


def test_cut_score_below_scene_threshold_is_rejected(tmp_path: Path) -> None:
    root = _config_dir(
        tmp_path, _REAL_BASE.replace("cut_score_threshold = 0.6", "cut_score_threshold = 0.3")
    )
    with pytest.raises(ConfigError):
        load_profile(config_dir=root)


def test_missing_profile_file_is_rejected(tmp_path: Path) -> None:
    root = _config_dir(tmp_path, _REAL_BASE)
    with pytest.raises(ConfigError):
        load_profile("does_not_exist", config_dir=root)


def test_bare_term_is_rejected(tmp_path: Path) -> None:
    overlay = '[profile]\nid = "x"\nversion = "0.1.0"\n\n[vocabulary]\nterms = ["you_died"]\n'
    root = _config_dir(tmp_path, _REAL_BASE, {"x": overlay})
    with pytest.raises(ConfigError):
        load_profile("x", config_dir=root)


def test_term_shadowing_a_core_member_is_rejected(tmp_path: Path) -> None:
    overlay = '[profile]\nid = "x"\nversion = "0.1.0"\n\n[vocabulary]\nterms = ["ext:cut"]\n'
    root = _config_dir(tmp_path, _REAL_BASE, {"x": overlay})
    with pytest.raises(ConfigError):
        load_profile("x", config_dir=root)


def test_profile_id_must_be_a_slug(tmp_path: Path) -> None:
    overlay = '[profile]\nid = "Not A Slug"\nversion = "0.1.0"\n'
    root = _config_dir(tmp_path, _REAL_BASE, {"x": overlay})
    with pytest.raises(ConfigError):
        load_profile("x", config_dir=root)


def test_half_specified_hud_region_is_rejected(tmp_path: Path) -> None:
    overlay = (
        '[profile]\nid = "x"\nversion = "0.1.0"\n\n'
        "[[vocabulary.hud_regions]]\nid = \"health\"\nx = 4\n"
    )
    root = _config_dir(tmp_path, _REAL_BASE, {"x": overlay})
    with pytest.raises(ConfigError):
        load_profile("x", config_dir=root)
