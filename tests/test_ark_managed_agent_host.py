from __future__ import annotations

import json
from pathlib import Path

import pytest

from loopx.agent_onboarding import (
    REQUIRED_HOST_SKILL_IDS,
    _skill_delivery_contract,
)
from loopx.ark_managed_agent_host import (
    ARK_MANAGED_AGENT_CAPABILITY_CONTINUATION_EVENT_MARKER,
    build_ark_managed_agent_capability_continuation_event_request,
    build_ark_managed_agent_capability_continuation_input,
)
from loopx.doctor import collect_doctor
from loopx.heartbeat_prompt import build_heartbeat_prompt
from loopx.host_loop_activation import (
    agent_type_uses_host_managed_skills,
    build_host_loop_activation_packet,
)


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
        "runtime_capability_reentry": {
            "source_ref": (
                "quota_should_run.interaction_contract.cli_channel."
                "runtime_capability_reentry"
            ),
            "packet_schema_version": "runtime_capability_reentry_v0",
            "verified_envelope_source_ref": (
                "quota_should_run.interaction_contract.cli_channel."
                "runtime_capability_envelope"
            ),
            "verified_envelope_schema_version": "runtime_capability_envelope_v0",
            "continuation_input_schema_version": (
                "loopx_ark_managed_agent_capability_continuation_v0"
            ),
            "delivery_channels": [
                "quota_tool_result",
                "host_continuation_input",
            ],
            "managed_agent_event_mapping": {
                "endpoint": "POST /api/v3/sessions/{session_id}/events",
                "event_types": [
                    "user.message",
                    "system.message",
                ],
                "system_message_position": "immediately_after_user_message",
                "emit_policy": "once_per_changed_packet",
            },
            "deferred_boundary": "before_next_model_turn",
            "goal_prompt_mutated": False,
            "prompt_regeneration_required": False,
            "session_scoped": True,
            "durable_grant_written": False,
        },
    }
    assert "--runtime-profile ark_managed_agent_goal" in payload["task_body"]
    assert "runtime_capability_reentry_v0" not in payload["task_body"]
    assert "host_continuation_input" not in payload["task_body"]
    assert "Before the first quota guard" not in payload["task_body"]
    assert "--available-capability <name>" not in payload["task_body"]


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
    assert any(
        "runtime_capability_reentry_v0" in step
        and "runtime_capability_envelope_v0" in step
        and "do not rewrite task_body" in step
        for step in packet["activation_steps"]
    )
    assert packet["commands"]["heartbeat_prompt"].endswith(
        "--runtime-profile ark_managed_agent_goal"
    )
    assert "automation_update" not in str(packet)
    assert "loopx turn run-once" not in str(packet).lower()


def test_host_wraps_reentry_packet_as_between_turn_input() -> None:
    reentry = {
        "schema_version": "runtime_capability_reentry_v0",
        "state": "verification_required",
        "candidates": [{"capability": "network"}],
    }

    continuation = build_ark_managed_agent_capability_continuation_input(
        {"runtime_capability_reentry": reentry}
    )

    assert continuation == {
        "schema_version": "loopx_ark_managed_agent_capability_continuation_v0",
        "channel": "host_continuation_input",
        "delivery_boundary": "before_next_model_turn",
        "goal_prompt_mutated": False,
        "packet_kind": "runtime_capability_reentry",
        "runtime_capability": reentry,
    }


def test_host_wraps_verified_envelope_from_canonical_nested_path() -> None:
    envelope = {
        "schema_version": "runtime_capability_envelope_v0",
        "state": "verified",
        "available_capabilities": ["network"],
        "cli_args": ["--available-capability", "network"],
    }

    continuation = build_ark_managed_agent_capability_continuation_input(
        {
            "interaction_contract": {
                "cli_channel": {
                    "runtime_capability_envelope": envelope,
                }
            }
        }
    )

    assert continuation is not None
    assert continuation["packet_kind"] == "runtime_capability_envelope"
    assert continuation["runtime_capability"] == envelope
    assert continuation["goal_prompt_mutated"] is False


def test_host_maps_continuation_to_managed_agent_event_request() -> None:
    prompt_before = _goal_prompt()
    envelope = {
        "schema_version": "runtime_capability_envelope_v0",
        "state": "verified",
        "available_capabilities": ["network"],
        "cli_args": ["--available-capability", "network"],
    }

    request = build_ark_managed_agent_capability_continuation_event_request(
        {"runtime_capability_envelope": envelope}
    )

    assert request is not None
    assert [event["type"] for event in request["events"]] == [
        "user.message",
        "system.message",
    ]
    user_text = request["events"][0]["content"][0]["text"]
    assert "Continue the active Goal from durable state" in user_text
    assert "not a permission grant or a replacement Goal" in user_text
    system_text = request["events"][1]["content"][0]["text"]
    marker, encoded = system_text.split("\n", maxsplit=1)
    assert marker == ARK_MANAGED_AGENT_CAPABILITY_CONTINUATION_EVENT_MARKER
    assert json.loads(encoded) == {
        "schema_version": (
            "loopx_ark_managed_agent_capability_continuation_v0"
        ),
        "channel": "host_continuation_input",
        "delivery_boundary": "before_next_model_turn",
        "goal_prompt_mutated": False,
        "packet_kind": "runtime_capability_envelope",
        "runtime_capability": envelope,
    }
    assert _goal_prompt()["task_body"] == prompt_before["task_body"]
    assert ARK_MANAGED_AGENT_CAPABILITY_CONTINUATION_EVENT_MARKER not in (
        prompt_before["task_body"]
    )


def test_host_omits_event_request_without_runtime_capability_packet() -> None:
    assert (
        build_ark_managed_agent_capability_continuation_event_request({})
        is None
    )


def test_host_capability_continuation_fails_closed_on_wrong_schema() -> None:
    with pytest.raises(
        ValueError,
        match=(
            "runtime_capability_envelope must use "
            "schema_version=runtime_capability_envelope_v0"
        ),
    ):
        build_ark_managed_agent_capability_continuation_input(
            {
                "runtime_capability_envelope": {
                    "schema_version": "runtime_capability_envelope_v9",
                }
            }
        )


def test_host_requires_host_managed_loopx_skill_delivery() -> None:
    contract = _skill_delivery_contract("ark-managed-agent")

    assert contract["mode"] == "host_managed"
    assert contract["owner"] == "loopx_install_script"
    assert contract["required_skill_ids"] == REQUIRED_HOST_SKILL_IDS
    assert contract["host_readback_required"] is True
    assert contract["codex_skills_root_required"] is False
    assert contract["preferred_delivery"] == "fixed_install_script"
    assert contract["install_script"] == "scripts/install-local.sh"
    assert contract["skills_dir_env"] == "LOOPX_SKILLS_DIR"
    assert contract["target_layout"] == "./.agents/skills"
    assert agent_type_uses_host_managed_skills("ark-managed-agent") is True


def test_doctor_checks_host_readback_instead_of_codex_skill_root() -> None:
    payload = collect_doctor(agent_type="ark-managed-agent")

    assert payload["skill_delivery"]["mode"] == "host_managed"
    assert payload["skill_delivery"]["owner"] == "loopx_install_script"
    assert payload["skill_delivery"]["codex_skills_root_applicable"] is False
    skill_checks = {
        item["id"]: item for item in payload["checks"] if item["id"].startswith("installed_")
    }
    assert skill_checks
    assert all(item["applicable"] is False for item in skill_checks.values())
