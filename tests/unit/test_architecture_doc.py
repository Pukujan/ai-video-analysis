"""The architecture map must stay true to the code.

ARCHITECTURE.md is tables of backticked tokens. This test parses them and
proves: every `built` symbol is importable, every `proposed` row claims no
module, every named spec file exists, and the emitted record types account for
all of ``RECORD_TYPES``. A cell that gains prose, or a row that falls out of
sync with the code, fails here rather than rotting silently.
"""

from __future__ import annotations

import importlib
import re
from pathlib import Path

from harness.records import RECORD_TYPES

_DOC = Path(__file__).resolve().parents[2] / "managed" / "design" / "ARCHITECTURE.md"
_REPO = Path(__file__).resolve().parents[2]
_TOKEN_RE = re.compile(r"`([^`]+)`")

_LAYER_HEADER = ["Layer", "Status", "Module", "Symbols", "Emits", "Spec"]
_RECORD_HEADER = ["Record type", "Family", "Layer", "Status"]


def _tables() -> list[list[list[str]]]:
    tables: list[list[list[str]]] = []
    current: list[list[str]] = []
    for line in _DOC.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if stripped.startswith("|") and stripped.endswith("|"):
            cells = [cell.strip() for cell in stripped.strip("|").split("|")]
            if all(set(cell) <= set("-: ") and cell for cell in cells):
                continue  # separator row
            current.append(cells)
        elif current:
            tables.append(current)
            current = []
    if current:
        tables.append(current)
    return tables


def _table_with_header(header: list[str]) -> list[list[str]]:
    for table in _tables():
        if table and table[0] == header:
            return table[1:]
    raise AssertionError(f"no table with header {header} in {_DOC.name}")


def _tokens(cell: str) -> list[str]:
    return _TOKEN_RE.findall(cell)


def _module_name(path: str) -> str:
    assert path.startswith("src/") and path.endswith(".py"), path
    return path[len("src/") : -len(".py")].replace("/", ".")


def _layers() -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    for cells in _table_with_header(_LAYER_HEADER):
        assert len(cells) == len(_LAYER_HEADER), cells
        rows.append(
            {
                "layer": cells[0],
                "status": cells[1],
                "modules": _tokens(cells[2]),
                "symbols": _tokens(cells[3]),
                "emits": _tokens(cells[4]),
                "spec": _tokens(cells[5]),
            }
        )
    return rows


_LAYERS = _layers()


def test_both_tables_are_present_and_well_formed() -> None:
    assert _LAYERS, "layers table is empty"
    assert _table_with_header(_RECORD_HEADER), "record-type table is empty"


def test_layer_status_is_known() -> None:
    for row in _LAYERS:
        assert row["status"] in {"built", "proposed"}, row


def test_every_built_symbol_is_importable() -> None:
    for row in _LAYERS:
        if row["status"] != "built":
            continue
        modules = row["modules"]
        symbols = row["symbols"]
        assert modules and symbols, f"built layer names no module/symbol: {row['layer']}"
        available: set[str] = set()
        for path in modules:
            module = importlib.import_module(_module_name(path))
            available.update(dir(module))
        for symbol in symbols:
            assert symbol in available, f"{symbol} not importable for layer {row['layer']}"


def test_every_proposed_row_claims_no_module() -> None:
    for row in _LAYERS:
        if row["status"] == "proposed":
            assert row["modules"] == [], f"proposed layer names a module: {row['layer']}"
            assert row["symbols"] == [], f"proposed layer names a symbol: {row['layer']}"


def test_every_named_spec_file_exists() -> None:
    for row in _LAYERS:
        for path in row["spec"]:
            assert (_REPO / path).is_file(), f"missing spec {path} for layer {row['layer']}"


def test_emitted_record_types_account_for_every_type() -> None:
    emitted: set[str] = set()
    for row in _LAYERS:
        emitted.update(row["emits"])
    assert emitted == set(RECORD_TYPES), (
        f"unaccounted: {sorted(set(RECORD_TYPES) - emitted)}; "
        f"unknown: {sorted(emitted - set(RECORD_TYPES))}"
    )


def test_record_table_covers_every_type_once() -> None:
    rows = _table_with_header(_RECORD_HEADER)
    names = [row[0] for row in rows]
    assert [name for name in names if _TOKEN_RE.findall(name)]  # every row is backticked
    listed = [token for name in names for token in _TOKEN_RE.findall(name)]
    assert len(listed) == len(set(listed)), "a record type is listed twice"
    assert set(listed) == set(RECORD_TYPES)


def test_record_table_agrees_with_layer_table() -> None:
    by_name = {row["layer"]: row for row in _LAYERS}
    for cells in _table_with_header(_RECORD_HEADER):
        record_type = _TOKEN_RE.findall(cells[0])[0]
        layer_name = _TOKEN_RE.findall(cells[2])[0]
        status = cells[3]
        assert layer_name in by_name, f"{record_type} names unknown layer {layer_name}"
        layer = by_name[layer_name]
        assert status == layer["status"], (
            f"{record_type} is {status} but its layer {layer_name} is {layer['status']}"
        )
        assert record_type in layer["emits"], (
            f"{record_type} is assigned to {layer_name}, which does not list it in Emits"
        )
