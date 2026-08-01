from __future__ import annotations

from collections.abc import Iterable
from typing import Any

from ..todos.contract import (
    TODO_STATUS_OPEN,
    TODO_TASK_CLASS_ADVANCEMENT,
    TODO_TASK_CLASS_MONITOR,
    normalize_todo_claimed_by,
    normalize_todo_status,
)
from ..todos.projection import todo_item_is_actionable_open, todo_item_task_class

REPAIR_DELTA_KIND_CHOICES = (
    "effective_action",
    "interaction_contract",
    "runnable_todo_set",
    "user_gate",
    "blocker",
    "successor_or_supersede",
    "capability_gate",
    "monitor_target",
    "active_state_next_action",
    "goal_vision_patch",
    "goal_boundary_projection",
    "no_followup",
    "watch_lane_continuation",
)

FRONTIER_REPLAN_ACK_DELTA_KINDS = frozenset(
    {
        "active_state_next_action",
        "blocker",
        "goal_vision_patch",
        "no_followup",
        "runnable_todo_set",
        "successor_or_supersede",
        "watch_lane_continuation",
    }
)


def normalize_repair_delta_kinds(values: Iterable[str] | None) -> list[str]:
    normalized: list[str] = []
    seen: set[str] = set()
    allowed = set(REPAIR_DELTA_KIND_CHOICES)
    for value in values or []:
        item = str(value or "").strip()
        if not item:
            continue
        if item not in allowed:
            raise ValueError(
                "repair_delta_kind must be one of: "
                + ", ".join(REPAIR_DELTA_KIND_CHOICES)
            )
        if item in seen:
            continue
        seen.add(item)
        normalized.append(item)
    return normalized


def repair_delta_kinds_have_frontier_delta(values: Iterable[str] | None) -> bool:
    return bool(
        {
            str(item or "").strip()
            for item in (values or [])
            if str(item or "").strip()
        }
        & FRONTIER_REPLAN_ACK_DELTA_KINDS
    )


def validate_repair_delta_claims(
    values: Iterable[str],
    *,
    agent_todo_summary: dict[str, Any] | None,
    agent_id: str | None,
    advancement_policy: str,
    next_action_changed: bool,
    vision_patch_written: bool,
) -> tuple[list[str], list[dict[str, Any]], list[dict[str, str]]]:
    items = (
        agent_todo_summary.get("items")
        if isinstance(agent_todo_summary, dict)
        and isinstance(agent_todo_summary.get("items"), list)
        else []
    )
    normalized_agent_id = normalize_todo_claimed_by(agent_id)
    scoped = [
        item
        for item in items
        if isinstance(item, dict)
        and (
            not normalized_agent_id
            or not normalize_todo_claimed_by(item.get("claimed_by"))
            or normalize_todo_claimed_by(item.get("claimed_by"))
            == normalized_agent_id
        )
    ]
    runnable_ids = [
        item.get("todo_id")
        for item in scoped
        if todo_item_is_actionable_open(item)
        and todo_item_task_class(item) == TODO_TASK_CLASS_ADVANCEMENT
        and item.get("todo_id")
    ]
    bounded_watch_ids = [
        item.get("todo_id")
        for item in scoped
        if item.get("done") is not True
        and (normalize_todo_status(item.get("status")) or TODO_STATUS_OPEN)
        == TODO_STATUS_OPEN
        and todo_item_task_class(item) == TODO_TASK_CLASS_MONITOR
        and str(item.get("target_key") or "").strip()
        and str(item.get("cadence") or "").strip()
        and str(item.get("next_due_at") or "").strip()
        and (
            str(item.get("expires_at") or "").strip()
            or str(item.get("resume_when") or "").strip()
        )
        and item.get("todo_id")
    ]

    accepted: list[str] = []
    evidence: list[dict[str, Any]] = []
    rejected: list[dict[str, str]] = []
    for kind in values:
        reason = ""
        todo_ids: list[str] = []
        if kind == "runnable_todo_set":
            todo_ids = runnable_ids
            reason = "no scoped open advancement todo exists"
        elif kind == "watch_lane_continuation":
            todo_ids = bounded_watch_ids
            reason = (
                "repeat_until_closed vision requires advancement"
                if advancement_policy == "repeat_until_closed"
                else (
                    "no scoped monitor has target, cadence, next due, and expiry "
                    "or resume condition"
                )
            )
            if advancement_policy == "repeat_until_closed":
                todo_ids = []
        elif kind == "active_state_next_action" and not next_action_changed:
            reason = "active-state Next Action did not change"
        elif kind == "goal_vision_patch" and not vision_patch_written:
            reason = "no vision patch was written"
        else:
            accepted.append(kind)
            continue

        if todo_ids:
            accepted.append(kind)
            evidence.append(
                {
                    "kind": kind,
                    "source": "active_state_agent_todos",
                    "todo_ids": todo_ids,
                }
            )
        else:
            rejected.append({"kind": kind, "reason": reason})
    return accepted, evidence, rejected
