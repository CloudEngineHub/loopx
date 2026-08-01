from __future__ import annotations

import json

import pytest

from loopx.control_plane.quota.cli_projection import (
    QUOTA_CLI_MONITOR_POLL_DECISION_DETAIL_COMMAND,
    compact_quota_monitor_poll_cli_payload,
)


def _decision(*, effective_action: str, should_run: bool) -> dict[str, object]:
    return {
        "should_run": should_run,
        "normal_delivery_allowed": should_run,
        "recovery_delivery_allowed": False,
        "effective_action": effective_action,
        "self_repair_allowed": False,
        "capability_repair_allowed": False,
        "workspace_repair_allowed": False,
        "state": "active",
        "safe_bypass_allowed": False,
        "safe_bypass_kind": None,
        "blocked_action_scope": None,
        "quota": {
            "compute": 1.0,
            "window_hours": 24,
            "slot_minutes": 30,
            "spent_slots": 2,
            "allowed_slots": 48,
        },
        "selected_todo": {"todo_id": "todo_monitor"},
        "work_lane_contract": {
            "obligation": "attempt_due_monitor",
            "diagnostic": "x" * 60_000,
        },
        "interaction_contract": {
            "mode": "DONT_NOTIFY",
            "diagnostic": "y" * 60_000,
        },
    }


@pytest.mark.parametrize(
    ("dry_run", "replayed", "ok", "has_after"),
    [
        (True, False, True, True),
        (False, False, True, True),
        (False, True, True, True),
        (True, False, False, False),
    ],
    ids=("dry-run", "execute", "replay", "failure"),
)
def test_monitor_poll_default_projection_is_bounded_and_semantically_aligned(
    dry_run: bool,
    replayed: bool,
    ok: bool,
    has_after: bool,
) -> None:
    before = _decision(effective_action="monitor_quiet_skip", should_run=False)
    after = (
        _decision(effective_action="autonomous_replan_required", should_run=True)
        if has_after
        else None
    )
    payload = {
        "ok": ok,
        "mode": "monitor-poll",
        "dry_run": dry_run,
        "replayed": replayed,
        "decision_summary": {"before": {}, "after": None},
        "before": before,
        "after": after,
    }

    projected = compact_quota_monitor_poll_cli_payload(payload)

    assert projected["before"] == projected["decision_summary"]["before"]
    assert projected["before"]["effective_action"] == "monitor_quiet_skip"
    assert "work_lane_contract" not in projected["before"]
    if has_after:
        assert projected["after"] == projected["decision_summary"]["after"]
        assert projected["after"]["effective_action"] == "autonomous_replan_required"
        assert "interaction_contract" not in projected["after"]
    else:
        assert projected["after"] is None
        assert projected["decision_summary"]["after"] is None
    detail_ref = projected["payload_compaction"]["decisions"]["detail_ref"]
    assert detail_ref["request"] == QUOTA_CLI_MONITOR_POLL_DECISION_DETAIL_COMMAND
    assert len(json.dumps(projected, ensure_ascii=False, indent=2)) < 4_000
    assert payload["before"] is before
    assert "work_lane_contract" in payload["before"]


def test_monitor_poll_explicit_cold_path_preserves_full_decisions() -> None:
    before = _decision(effective_action="monitor_quiet_skip", should_run=False)
    after = _decision(effective_action="normal_run", should_run=True)
    payload = {
        "ok": True,
        "mode": "monitor-poll",
        "decision_summary": {"before": {}, "after": {}},
        "before": before,
        "after": after,
    }

    projected = compact_quota_monitor_poll_cli_payload(
        payload,
        include_decision_detail=True,
    )

    assert projected is payload
    assert projected["before"]["work_lane_contract"]["diagnostic"] == "x" * 60_000
    assert projected["after"]["interaction_contract"]["diagnostic"] == "y" * 60_000
