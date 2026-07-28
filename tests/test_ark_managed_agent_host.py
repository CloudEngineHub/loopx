from __future__ import annotations

from pathlib import Path
import shutil

from loopx.agent_onboarding import (
    REQUIRED_HOST_SKILL_IDS,
    _skill_delivery_contract,
)
from loopx.doctor import collect_doctor
from loopx.heartbeat_prompt import build_heartbeat_prompt
from loopx.host_loop_activation import (
    agent_type_uses_host_managed_skills,
    build_host_loop_activation_packet,
)
from loopx.skill_install_readback import (
    inspect_skill_install_readback,
    write_skill_install_readback,
)


REPO_ROOT = Path(__file__).resolve().parents[1]


def _materialize_workflow_skills(skills_dir: Path) -> None:
    for skill_id in REQUIRED_HOST_SKILL_IDS:
        shutil.copytree(REPO_ROOT / "skills" / skill_id, skills_dir / skill_id)
    write_skill_install_readback(
        skills_dir=skills_dir,
        skill_ids=REQUIRED_HOST_SKILL_IDS,
        source_root=REPO_ROOT,
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


def test_host_requires_host_managed_loopx_skill_delivery(monkeypatch) -> None:
    monkeypatch.delenv("LOOPX_SKILLS_DIR", raising=False)
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
    assert contract["fixed_installer_skill_ids"] == REQUIRED_HOST_SKILL_IDS
    assert contract["filesystem_readback"]["status"] == "skills_dir_not_configured"
    assert agent_type_uses_host_managed_skills("ark-managed-agent") is True


def test_doctor_checks_host_installation_readback_instead_of_codex_skill_root(
    tmp_path: Path,
    monkeypatch,
) -> None:
    skills_dir = tmp_path / "workspace" / ".agents" / "skills"
    _materialize_workflow_skills(skills_dir)
    monkeypatch.setenv("LOOPX_SKILLS_DIR", str(skills_dir))

    payload = collect_doctor(agent_type="ark-managed-agent")

    assert payload["skill_delivery"]["mode"] == "host_managed"
    assert payload["skill_delivery"]["owner"] == "loopx_install_script"
    assert payload["skill_delivery"]["codex_skills_root_applicable"] is False
    readback = payload["skill_delivery"]["filesystem_readback"]
    assert readback["status"] == "ready_for_host_load"
    assert readback["ready"] is True
    assert readback["source_revision"]
    skill_checks = {
        item["id"]: item for item in payload["checks"] if item["id"].startswith("installed_")
    }
    assert skill_checks
    assert all(item["applicable"] is False for item in skill_checks.values())
    host_check = next(
        item
        for item in payload["checks"]
        if item["id"] == "host_skill_installation_readback"
    )
    assert host_check["ok"] is True
    assert host_check["required"] is False


def test_onboarding_projects_verified_filesystem_readback(
    tmp_path: Path,
) -> None:
    skills_dir = tmp_path / ".agents" / "skills"
    _materialize_workflow_skills(skills_dir)

    contract = _skill_delivery_contract(
        "ark-managed-agent",
        host_skills_dir=skills_dir,
    )

    assert contract["status"] == "ready_for_host_load"
    assert contract["filesystem_readback"]["ready"] is True
    assert contract["host_readback_required"] is True


def test_skill_readback_rejects_content_changed_after_install(tmp_path: Path) -> None:
    skills_dir = tmp_path / ".agents" / "skills"
    _materialize_workflow_skills(skills_dir)
    skill_path = skills_dir / REQUIRED_HOST_SKILL_IDS[0] / "SKILL.md"
    skill_path.write_text(
        skill_path.read_text(encoding="utf-8") + "\npost-install mutation\n",
        encoding="utf-8",
    )

    readback = inspect_skill_install_readback(
        skills_dir=skills_dir,
        required_skill_ids=REQUIRED_HOST_SKILL_IDS,
    )

    assert readback["ready"] is False
    assert readback["status"] == "skill_digest_mismatch"
    assert readback["digest_mismatches"] == [REQUIRED_HOST_SKILL_IDS[0]]
