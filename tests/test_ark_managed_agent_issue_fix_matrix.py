from __future__ import annotations

from pathlib import Path

import pytest

from loopx.capabilities.issue_fix.acceptance_loop import (
    build_issue_fix_acceptance_fixture_packet,
)
from loopx.capabilities.issue_fix.feasibility import (
    build_issue_fix_feasibility_packet,
)
from loopx.control_plane.scheduler.execution_context import (
    scheduler_execution_context_for_runtime_profile,
)
from loopx.control_plane.work_items.interaction_contract import (
    build_interaction_contract,
)
from loopx.heartbeat_prompt import build_heartbeat_prompt
from loopx.host_loop_activation import build_host_loop_activation_packet


@pytest.mark.parametrize(
    ("reproduction_status", "scope_class", "comment_value", "expected_route"),
    [
        ("confirmed", "bounded", "none", "fix_pr"),
        ("blocked", "uncertain", "diagnosis", "comment_only"),
        ("missing", "uncertain", "none", "triage_only"),
    ],
)
def test_representative_intake_routes_remain_public_safe_and_exclusive(
    reproduction_status: str,
    scope_class: str,
    comment_value: str,
    expected_route: str,
) -> None:
    packet = build_issue_fix_feasibility_packet(
        reproduction_status=reproduction_status,
        scope_class=scope_class,
        reproduction_label=(
            "python test_calculator.py"
            if reproduction_status in {"confirmed", "planned"}
            else None
        ),
        validation_label=(
            "python test_calculator.py"
            if reproduction_status in {"confirmed", "planned"}
            else None
        ),
        comment_value=comment_value,
    )

    assert packet["ok"] is True
    assert packet["decision"]["route"] == expected_route
    assert packet["external_writes_performed"] is False
    assert packet["issue_body_captured"] is False
    assert packet["comment_bodies_captured"] is False
    assert packet["raw_logs_captured"] is False
    assert packet["local_paths_captured"] is False


def test_validated_worker_artifact_does_not_claim_goal_host_closure() -> None:
    packet = build_issue_fix_acceptance_fixture_packet()
    artifact = packet["validated_fix_artifact"]
    review_packet = artifact["review_packet"]

    assert packet["ok"] is True
    assert artifact["repro_before"]["passed"] is False
    assert artifact["patch"]["patch_applied"] is True
    assert artifact["validation_after"]["passed"] is True
    assert artifact["fix_artifact_ready"] is True
    assert artifact["pr_review_packet_ready"] is True

    # Worker evidence and host terminal evidence have different owners. A
    # successful repair must never imply that a Goal evaluator reached
    # Satisfied or that the host reached an achieved terminal state.
    assert "goal_terminal_state" not in artifact
    assert "goal_evaluation" not in artifact

    assert review_packet["external_issue_comment_performed"] is False
    assert review_packet["external_pr_created"] is False
    assert review_packet["merge_performed"] is False


def test_one_shot_host_contract_keeps_goal_closure_with_the_host() -> None:
    prompt = build_heartbeat_prompt(
        goal_id="managed-agent-issue-fix-matrix",
        active_state=Path("/workspace/ACTIVE_GOAL_STATE.md"),
        thin=True,
        runtime_profile="ark_managed_agent_goal",
    )
    activation = build_host_loop_activation_packet(
        agent_type="ark-managed-agent",
        goal_id="managed-agent-issue-fix-matrix",
        agent_id="managed-agent",
        registered_agents=["managed-agent"],
    )

    assert prompt["host_contract"]["activation_mode"] == "goal_once"
    assert prompt["host_contract"]["goal_runtime_owns_continuation"] is True
    assert prompt["host_contract"]["loopx_turn_driver_required"] is False
    assert prompt["host_contract"]["session_state_authoritative"] is False
    assert len(prompt["task_body"]) <= 4_000
    assert "Spend exactly once after validated writeback" in prompt["task_body"]
    assert "runtime_capability_reentry_v0" not in prompt["task_body"]

    assert activation["activation_method"] == "submit_goal_once"
    assert activation["host_mutation"]["prompt_field"] == "task_body"
    assert activation["host_mutation"]["transport_contract"] == "goal_prompt_v0"
    assert any(
        "host continuation input" in step
        and "do not rewrite task_body" in step
        for step in activation["activation_steps"]
    )
    assert "loopx turn run-once" not in str(activation).lower()


def test_runtime_capability_reenters_through_host_input_not_goal_prompt() -> None:
    prompt = build_heartbeat_prompt(
        goal_id="managed-agent-issue-fix-matrix",
        active_state=Path("/workspace/ACTIVE_GOAL_STATE.md"),
        thin=True,
        runtime_profile="ark_managed_agent_goal",
    )
    decision = {
        "goal_id": "managed-agent-issue-fix-matrix",
        "agent_identity": {"agent_id": "managed-agent", "agent_model": "peer_v1"},
        "should_run": True,
        "effective_action": "capability_bridge_repair",
        "execution_obligation": {
            "must_attempt_work": True,
            "delivery_allowed": False,
        },
        "heartbeat_recommendation": {
            "recommended_mode": "repair_capability_bridge",
        },
        "capability_gate": {
            "action": "repair_bridge",
            "repair_missing": ["network"],
            "owner_missing": [],
            "resolution_bindings": [],
            "runnable_candidates": [],
        },
    }
    contract = build_interaction_contract(
        decision,
        available_capabilities=["shell"],
        scheduler_execution_context=scheduler_execution_context_for_runtime_profile(
            "ark_managed_agent_goal"
        ),
    )

    reentry = contract["cli_channel"]["runtime_capability_reentry"]
    host_contract = prompt["host_contract"]["runtime_capability_reentry"]
    assert host_contract["packet_schema_version"] == reentry["schema_version"]
    assert reentry["delivery_contract"]["primary_channel"] == "quota_tool_result"
    assert reentry["delivery_contract"]["deferred_channel"] == (
        "host_continuation_input"
    )
    assert reentry["delivery_contract"]["deferred_boundary"] == (
        "before_next_model_turn"
    )
    assert reentry["candidates"][0]["capability"] == "network"
    assert "--available-capability network" in reentry["candidates"][0]["command"]
    assert "--available-capability network" not in prompt["task_body"]
    assert "runtime_capability_reentry_v0" not in prompt["task_body"]
