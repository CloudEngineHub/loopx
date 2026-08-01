from loopx.control_plane.work_items.repair_delta import validate_repair_delta_claims


def _summary(*items: dict) -> dict:
    return {"items": list(items)}


def _validate(
    kind: str,
    *,
    items: tuple[dict, ...],
    advancement_policy: str = "as_needed",
) -> tuple[list[str], list[dict], list[dict]]:
    return validate_repair_delta_claims(
        [kind],
        agent_todo_summary=_summary(*items),
        agent_id="quality-agent",
        advancement_policy=advancement_policy,
        next_action_changed=False,
        vision_patch_written=False,
    )


def test_runnable_todo_claim_requires_scoped_advancement() -> None:
    accepted, evidence, rejected = _validate(
        "runnable_todo_set",
        items=(
            {
                "todo_id": "todo_123456789abc",
                "status": "open",
                "task_class": "advancement_task",
                "claimed_by": "other-agent",
            },
            {
                "todo_id": "todo_deferred12345",
                "status": "open",
                "task_class": "advancement_task",
                "claimed_by": "quality-agent",
                "resume_when": "todo_done:todo_dependency123",
                "resume_ready": False,
            },
        ),
    )

    assert accepted == []
    assert evidence == []
    assert rejected[0]["reason"] == "no scoped open advancement todo exists"


def test_runnable_todo_claim_records_todo_evidence() -> None:
    accepted, evidence, rejected = _validate(
        "runnable_todo_set",
        items=(
            {
                "todo_id": "todo_123456789abc",
                "status": "open",
                "task_class": "advancement_task",
                "claimed_by": "quality-agent",
            },
        ),
    )

    assert accepted == ["runnable_todo_set"]
    assert evidence[0]["todo_ids"] == ["todo_123456789abc"]
    assert rejected == []


def test_watch_claim_requires_bounded_schedule() -> None:
    accepted, evidence, rejected = _validate(
        "watch_lane_continuation",
        items=(
            {
                "todo_id": "todo_123456789abc",
                "status": "open",
                "task_class": "continuous_monitor",
                "claimed_by": "quality-agent",
                "target_key": "review",
                "cadence": "30m",
                "next_due_at": "2026-08-01T13:00:00Z",
            },
        ),
    )

    assert accepted == []
    assert evidence == []
    assert "expiry or resume condition" in rejected[0]["reason"]


def test_watch_claim_requires_non_repeating_vision_and_records_evidence() -> None:
    monitor = {
        "todo_id": "todo_123456789abc",
        "status": "open",
        "task_class": "continuous_monitor",
        "claimed_by": "quality-agent",
        "target_key": "review",
        "cadence": "30m",
        "next_due_at": "2026-08-01T13:00:00Z",
        "expires_at": "2026-08-02T13:00:00Z",
    }

    accepted, evidence, rejected = _validate(
        "watch_lane_continuation",
        items=(monitor,),
    )
    repeat_accepted, _, repeat_rejected = _validate(
        "watch_lane_continuation",
        items=(monitor,),
        advancement_policy="repeat_until_closed",
    )

    assert accepted == ["watch_lane_continuation"]
    assert evidence[0]["todo_ids"] == ["todo_123456789abc"]
    assert rejected == []
    assert repeat_accepted == []
    assert repeat_rejected[0]["reason"] == (
        "repeat_until_closed vision requires advancement"
    )
