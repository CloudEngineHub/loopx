from __future__ import annotations

from pathlib import Path

from loopx.heartbeat_prompt import build_heartbeat_prompt
from loopx.host_loop_activation import build_host_loop_activation_packet


def _goal_prompt() -> dict:
    return build_heartbeat_prompt(
        goal_id="managed-agent-fixture",
        active_state=Path("/workspace/ACTIVE_GOAL_STATE.md"),
        thin=True,
        runtime_profile="ark_managed_agent_goal",
    )


def test_goal_prompt_is_one_transport_independent_activation() -> None:
    local_development = _goal_prompt()
    cloud = _goal_prompt()
    normalized = " ".join(local_development["task_body"].split())

    assert local_development["task_body"] == cloud["task_body"]
    assert len(local_development["task_body"]) <= 4_000
    assert "in one Goal activation" in normalized
    assert "Goal runtime owns continuation and inner iterations" in normalized
    assert "goal loop, not automation" in normalized
    assert "invoke LoopX Turn" in normalized
    assert "choose the highest-priority in-scope unblocked agent todo" in normalized
    assert "Honor claims/leases, blocker-push and recovery obligations" in normalized
    assert "Spend exactly once after validated writeback" in normalized


def test_goal_prompt_projects_goal_only_host_contract() -> None:
    payload = _goal_prompt()

    assert payload["runtime_profile"] == "ark_managed_agent_goal"
    assert payload["host_contract"] == {
        "schema_version": "loopx_ark_managed_agent_goal_host_v0",
        "host_kind": "ark-managed-agent",
        "activation_mode": "goal_once",
        "prompt_family": "loopx_goal_prompt_v0",
        "policy_source": "quota_should_run.interaction_contract",
        "transport_contract": "goal_prompt_v0",
        "goal_runtime_owns_continuation": True,
        "loopx_turn_driver_required": False,
        "session_state_authoritative": False,
    }
    assert "--runtime-profile ark_managed_agent_goal" in payload["task_body"]


def test_host_activation_submits_one_goal_without_turn_or_automation() -> None:
    packet = build_host_loop_activation_packet(
        agent_type="ark-managed-agent",
        goal_id="managed-agent-fixture",
        agent_id="managed-agent",
        registered_agents=["managed-agent"],
    )

    assert packet["activation_method"] == "submit_goal_once"
    assert packet["host_surface"] == "ark_managed_agent_goal_mode"
    assert packet["host_mutation"]["transport_contract"] == "goal_prompt_v0"
    assert packet["host_mutation"]["prompt_field"] == "task_body"
    assert packet["commands"]["heartbeat_prompt"].endswith(
        "--runtime-profile ark_managed_agent_goal"
    )
    assert "automation_update" not in str(packet)
    assert "loopx turn run-once" not in str(packet).lower()
