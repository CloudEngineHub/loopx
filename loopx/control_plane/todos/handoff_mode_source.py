"""Locked compatibility inputs for the typed handoff transition planner.

The active-state writer mutex is held by the caller. Event locks use the
append store's own lock and remain held until the mode write is durable.
"""
from __future__ import annotations

from contextlib import ExitStack, contextmanager
from collections.abc import Iterator
from pathlib import Path
from typing import Any


def _event_paths(registry_path: Path, goal_id: str, state_path: Path) -> tuple[dict[str, Any], list[Path]]:
    from ...history import load_registry
    from ...registry import find_registry_goal
    from ..status.active_state_projection import state_event_log_candidates

    goal = find_registry_goal(load_registry(registry_path), goal_id) or {"id": goal_id}
    paths = state_event_log_candidates(goal, state_path=state_path)
    return goal, sorted({path.expanduser().resolve() for path in paths}, key=str)


@contextmanager
def handoff_mode_source(
    *, registry_path: Path, goal_id: str, state_path: Path, state_text: str,
    runtime_root: Path,
) -> Iterator[dict[str, Any]]:
    from ...event_sourced_state import AppendOnlyStateEventStore, StateEventError
    from ...file_lock import exclusive_file_lock, exclusive_cross_runtime_file_lock
    from ..runtime.time import now_local_iso
    from ..work_items.task_lease import read_lease, task_lease_dir, task_lease_lock_path
    from .goal_todo_projection import project_goal_todo_items
    from .handoff_mode import HandoffModeError

    goal, paths = _event_paths(registry_path, goal_id, state_path)
    with ExitStack() as stack:
        # Same ordering for every mode writer; state -> event logs -> leases.
        # Lock absent candidates too, so the first append cannot race the scan.
        for path in paths:
            stack.enter_context(exclusive_file_lock(path, operation="handoff_mode_set"))
        stack.enter_context(exclusive_cross_runtime_file_lock(
            task_lease_lock_path(runtime_root=runtime_root, goal_id=goal_id), operation="handoff_mode_set"))
        try:
            # Display projection can warn and fall back on malformed events.
            # A safety decision must instead prove every candidate readable.
            for path in paths:
                AppendOnlyStateEventStore(path).load()
            todos = project_goal_todo_items(goal, state_text=state_text,
                state_path=state_path, rollout_events=[])
        except (OSError, StateEventError) as error:
            raise HandoffModeError("cannot establish handoff quiescence from the event sources",
                code="handoff_mode_source_unavailable") from error
        fields = ("todo_id", "done", "status", "claimed_by", "archive_state")
        leases = []
        for path in sorted(task_lease_dir(runtime_root=runtime_root, goal_id=goal_id).glob("todo_*.json")):
            lease = read_lease(path)
            if lease is not None:
                leases.append({**lease, "lease_path": str(path)})
        yield {"todos": [{key: item[key] for key in fields if key in item} for item in todos],
            "leases": leases, "observed_at": now_local_iso()}
