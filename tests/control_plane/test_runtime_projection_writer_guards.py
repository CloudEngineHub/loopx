"""Fail-closed guards on the shared compact runtime projection writer.

The happy path, the `already_current` replay and the readback success are owned
by the projection smokes that drive the shipped callers. This module pins only
what those smokes never reach: the writer must refuse before touching disk, and
it must refuse to claim a projection it cannot read back.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from loopx.control_plane.runtime import runtime_projection_writer
from loopx.control_plane.runtime.runtime_projection_writer import (
    write_compact_runtime_projection,
)

GOAL_ID = "projection-writer-guards"
MARKER_FIELD = "shared_runtime_projection"
IDENTITY_FIELDS = ("source_generated_at", "source_projection_sha256_16")


def _record(**marker_overrides: Any) -> dict[str, Any]:
    marker: dict[str, Any] = {
        "source_generated_at": "2026-09-25T09:00:00+08:00",
        "source_projection_sha256_16": "0123456789abcdef",
    }
    marker.update(marker_overrides)
    return {
        "generated_at": "2026-09-25T09:00:00+08:00",
        MARKER_FIELD: marker,
    }


def _call(tmp_path: Path, **overrides: Any) -> dict[str, Any]:
    params: dict[str, Any] = {
        "target_runtime_root": tmp_path / "runtime",
        "goal_id": GOAL_ID,
        "record": _record(),
        "index_record": {"goal_id": GOAL_ID, "kind": "projection"},
        "marker_field": MARKER_FIELD,
        "identity_fields": IDENTITY_FIELDS,
        "markdown_renderer": lambda record: "# projection\n",
        "dry_run": False,
    }
    params.update(overrides)
    return write_compact_runtime_projection(**params)


def _index_path(tmp_path: Path) -> Path:
    return tmp_path / "runtime" / "goals" / GOAL_ID / "runs" / "index.jsonl"


def test_missing_marker_rejects_before_any_write(tmp_path: Path) -> None:
    record = _record()
    del record[MARKER_FIELD]

    with pytest.raises(ValueError, match="must include object marker"):
        _call(tmp_path, record=record)

    assert not _index_path(tmp_path).exists()
    assert not (tmp_path / "runtime" / "goals").exists()


def test_non_object_marker_rejects_before_any_write(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="must include object marker"):
        _call(tmp_path, record={**_record(), MARKER_FIELD: "already-ran"})

    assert not _index_path(tmp_path).exists()


def test_blank_identity_field_rejects_before_any_write(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="is missing identity fields") as raised:
        _call(tmp_path, record=_record(source_projection_sha256_16=""))

    # The rejection names which identities the caller has to supply, so a fix is
    # not a guess about which of the tuple was empty.
    for field in IDENTITY_FIELDS:
        assert field in str(raised.value)
    assert not _index_path(tmp_path).exists()


def test_identity_rejection_precedes_the_dry_run_report(tmp_path: Path) -> None:
    record = _record()
    del record[MARKER_FIELD]

    with pytest.raises(ValueError, match="must include object marker"):
        _call(tmp_path, record=record, dry_run=True)

    assert not (tmp_path / "runtime" / "goals").exists()


def test_dry_run_reports_without_writing(tmp_path: Path) -> None:
    result = _call(tmp_path, dry_run=True)

    assert result["status"] == "would_project"
    assert result["dry_run"] is True
    assert result["readback_verified"] is False
    assert "json_path" not in result
    assert not _index_path(tmp_path).exists()


def test_readback_mismatch_fails_closed_after_append(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # The writer's own contract is "append, then prove it reads back". With the
    # read side blind, it must refuse the claim instead of reporting success.
    monkeypatch.setattr(runtime_projection_writer, "load_index", lambda path: ([], 0))

    with pytest.raises(OSError, match="did not pass index readback"):
        _call(tmp_path)

    # The guard protects the claim, not the bytes: the append already landed, so
    # a caller that retries must be prepared to meet `already_current`.
    assert _index_path(tmp_path).exists()
    assert (
        len(_index_path(tmp_path).read_text(encoding="utf-8").strip().splitlines()) == 1
    )
