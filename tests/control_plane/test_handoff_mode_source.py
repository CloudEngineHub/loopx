"""Real compatibility sources: complete overlays and their mutation locks."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from loopx.control_plane.todos.handoff_mode import HandoffModeError, set_goal_handoff_mode, show_goal_handoff_mode
from loopx.event_sourced_state import AppendOnlyStateEventStore, TODO_ADDED, make_state_event
from loopx.file_lock import LockAcquireTimeoutError, exclusive_file_lock


def workspace(root: Path) -> tuple[Path, Path, Path]:
    state = root / "ACTIVE_GOAL_STATE.md"
    state.write_text("---\ngoal_id: mode-source\nhandoff_mode: legacy\n---\n\n## Agent Todo\n", encoding="utf-8")
    registry = root / "registry.json"
    runtime = root / "runtime"
    registry.write_text(json.dumps({"common_runtime_root": str(runtime), "goals": [{"id": "mode-source",
        "repo": str(root), "state_file": state.name, "adapter": {"kind": "harness_self_improvement"}}]}))
    return registry, state, runtime


def append(path: Path, *, claimed: bool, todo_id: str = "todo_event") -> None:
    AppendOnlyStateEventStore(path).append(make_state_event(event_id=f"add-{todo_id}", goal_id="mode-source",
        event_type=TODO_ADDED, refs={"todo_id": todo_id}, payload={"role": "agent", "title": "Durable event task",
            "task_class": "advancement_task", **({"claimed_by": "worker"} if claimed else {})},
        recorded_at="2026-09-20T00:00:00Z", producer="mode-source-fixture"))


def switch(registry: Path, **kwargs):
    return set_goal_handoff_mode(registry_path=registry, goal_id="mode-source", mode="hard_lease", **kwargs)


@pytest.mark.parametrize("registered", [False, True])
def test_unmaterialized_claim_at_end_of_large_event_source_blocks(tmp_path: Path, registered: bool) -> None:
    registry, state, _ = workspace(tmp_path)
    path = tmp_path / ("declared-events.jsonl" if registered else "events.jsonl")
    if registered:
        value = json.loads(registry.read_text())
        value["goals"][0]["state_event_log"] = str(path)
        registry.write_text(json.dumps(value))
    events = [make_state_event(event_id=f"add-{i}", goal_id="mode-source", event_type=TODO_ADDED,
        refs={"todo_id": f"todo_event_{i}"}, payload={"role": "user" if i % 2 else "agent",
            "title": f"Task {i}", "task_class": "advancement_task", **({"claimed_by": "worker"} if i == 520 else {})},
        recorded_at="2026-09-20T00:00:00Z", producer="mode-source-fixture") for i in range(521)]
    AppendOnlyStateEventStore(path).append_many(events)
    before = state.read_bytes(), path.read_bytes()
    for dry_run in (True, False):
        with pytest.raises(HandoffModeError) as caught:
            switch(registry, dry_run=dry_run)
        assert caught.value.code == "handoff_mode_not_quiescent"
        assert [row["todo_id"] for row in caught.value.payload["claimed_todos"]] == ["todo_event_520"]
        assert (state.read_bytes(), path.read_bytes()) == before


def test_unclaimed_overlay_stays_unmaterialized_and_locked_until_durable_write(tmp_path: Path, monkeypatch) -> None:
    registry, state, _ = workspace(tmp_path)
    path = state.with_name("events.jsonl")
    append(path, claimed=False)
    from loopx.control_plane.coordination import runtime_shadow_writer_adapter as adapter
    original_write = adapter.write_captured_todo_state
    seen = []

    def locked_write(*args, **kwargs):
        with pytest.raises(LockAcquireTimeoutError):
            with exclusive_file_lock(path, timeout_seconds=0):
                pytest.fail("event append lock was released before mode write")
        seen.append(True)
        return original_write(*args, **kwargs)

    monkeypatch.setattr(adapter, "write_captured_todo_state", locked_write)
    before = path.read_bytes()
    result = switch(registry)
    assert result["changed"] is True and seen == [True]
    assert path.read_bytes() == before
    assert "todo_event" not in state.read_text()
    assert show_goal_handoff_mode(registry_path=registry, goal_id="mode-source")["handoff_mode"] == "hard_lease"
    with exclusive_file_lock(path, timeout_seconds=0):
        pass


@pytest.mark.parametrize("contents", ["not json\n", '{"schema_version":"unknown"}\n'])
def test_unreadable_event_source_is_not_quiescence(tmp_path: Path, contents: str) -> None:
    registry, state, _ = workspace(tmp_path)
    path = state.with_name("events.jsonl")
    path.write_text(contents)
    before = state.read_bytes()
    with pytest.raises(HandoffModeError) as caught:
        switch(registry)
    assert caught.value.code == "handoff_mode_source_unavailable"
    assert state.read_bytes() == before


def test_invalid_unused_event_candidate_does_not_fall_back_silently(tmp_path: Path) -> None:
    registry, state, _ = workspace(tmp_path)
    declared = tmp_path / "declared.jsonl"
    append(declared, claimed=False)
    value = json.loads(registry.read_text())
    value["goals"][0]["state_event_log"] = str(declared)
    registry.write_text(json.dumps(value))
    state.with_name("events.jsonl").write_text("corrupt fallback\n")
    with pytest.raises(HandoffModeError) as caught:
        switch(registry)
    assert caught.value.code == "handoff_mode_source_unavailable"


def test_noop_does_not_need_to_repair_or_scan_source(tmp_path: Path) -> None:
    registry, state, _ = workspace(tmp_path)
    state.write_text(state.read_text().replace("legacy", "hard_lease"))
    state.with_name("events.jsonl").write_text("corrupt unrelated event\n")
    before = state.read_bytes()
    assert switch(registry)["changed"] is False
    assert state.read_bytes() == before


@pytest.mark.parametrize("ending", [b"", b"\r\n"])
def test_public_mode_write_preserves_unrelated_bytes(tmp_path: Path, ending: bytes) -> None:
    registry, state, _ = workspace(tmp_path)
    source = '---\r\ngoal_id: mode-source\r\ntitle: "a\u2028b"\r\nhandoff_mode: legacy\r\n---\r\n\r\n## Agent Todo'.encode() + ending
    state.write_bytes(source)
    assert switch(registry)["changed"] is True
    assert state.read_bytes() == source.replace(b"handoff_mode: legacy", b"handoff_mode: hard_lease")


def test_duplicate_mode_fields_reject_without_partial_repair(tmp_path: Path) -> None:
    registry, state, _ = workspace(tmp_path)
    state.write_text(state.read_text().replace("handoff_mode: legacy", "handoff_mode: legacy\nhandoff_mode: banana"))
    before = state.read_bytes()
    with pytest.raises(HandoffModeError) as caught:
        switch(registry)
    assert caught.value.code == "handoff_mode_duplicate_field"
    assert state.read_bytes() == before


def test_large_prose_never_crosses_the_mode_plan_transport(tmp_path: Path) -> None:
    registry, state, _ = workspace(tmp_path)
    original = state.read_bytes() + b"\n## Evidence\n" + b"Unrelated durable prose.\n" * 150_000
    state.write_bytes(original)
    assert switch(registry)["changed"] is True
    assert state.read_bytes() == original.replace(b"handoff_mode: legacy", b"handoff_mode: hard_lease")
