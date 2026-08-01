from __future__ import annotations

import contextlib
import io
import json
from pathlib import Path

import pytest

from loopx.capabilities.issue_fix import pr_lifecycle
from loopx.capabilities.issue_fix.pr_lifecycle import (
    build_issue_fix_pr_lifecycle_monitor_packet,
)
from loopx.capabilities.issue_fix.pr_monitor_materialization import (
    materialize_issue_fix_grouped_monitors,
)
from loopx.cli import main as cli_main
from loopx.domain_packs.issue_fix import (
    upsert_issue_fix_pr_lifecycle_ledger_jsonl,
)

GOAL_ID = "issue-fix-monitor-goal"
AGENT_ID = "issue-fix-worker"


def _fixture(tmp_path: Path) -> tuple[Path, Path, Path]:
    project = tmp_path / "repo"
    state = project / "ACTIVE_GOAL_STATE.md"
    state.parent.mkdir(parents=True)
    state.write_text(
        "## User Todo / Owner Review Reading Queue\n\n"
        "## Agent Todo\n\n"
        "- [ ] [P0] Continue independent issue-fix work.\n"
        "  <!-- loopx:todo todo_id=todo_advancement status=open "
        "task_class=advancement_task claimed_by=issue-fix-worker -->\n",
        encoding="utf-8",
    )
    registry = tmp_path / "registry.global.json"
    registry.write_text(
        json.dumps(
            {
                "goals": [
                    {
                        "id": GOAL_ID,
                        "status": "active",
                        "repo": str(project),
                        "state_file": state.name,
                        "adapter": {"kind": "harness_self_improvement"},
                        "coordination": {
                            "agent_model": "peer_v1",
                            "registered_agents": [AGENT_ID],
                        },
                    }
                ]
            }
        ),
        encoding="utf-8",
    )
    return project, state, registry


def _packet(
    number: int,
    *,
    state: str = "OPEN",
    owner: str = "huangruiteng",
    repo: str = "loopx",
) -> dict:
    status_rollup = (
        [{"name": "integration", "status": "IN_PROGRESS"}]
        if state == "OPEN"
        else [{"name": "integration", "conclusion": "SUCCESS"}]
    )
    return build_issue_fix_pr_lifecycle_monitor_packet(
        url=f"https://github.com/{owner}/{repo}/pull/{number}",
        provider_payload={
            "state": state,
            "reviewDecision": "REVIEW_REQUIRED",
            "mergeStateStatus": "CLEAN",
            "statusCheckRollup": status_rollup,
        },
        generated_at="2026-08-01T16:00:00Z",
    )


def test_grouped_monitor_materialization_is_one_per_bucket_and_retires_empty_bucket(
    tmp_path: Path,
) -> None:
    project, state, registry = _fixture(tmp_path)
    ledger = tmp_path / "pr-lifecycle.jsonl"
    first = _packet(101)
    second = _packet(102)
    upsert_issue_fix_pr_lifecycle_ledger_jsonl(ledger, first)
    upsert_issue_fix_pr_lifecycle_ledger_jsonl(ledger, second)

    created = materialize_issue_fix_grouped_monitors(
        registry_path=registry,
        goal_id=GOAL_ID,
        project=project,
        ledger_path=ledger,
        claimed_by=AGENT_ID,
        cadence="30m",
        generated_at="2026-08-01T16:00:00Z",
    )

    assert created["write_performed"] is True
    assert created["active_bucket_count"] == 1
    assert created["active_member_count"] == 2
    assert created["next_due_at"] == "2026-08-02T00:30:00+08:00"
    active = state.read_text(encoding="utf-8")
    assert active.count("task_class=continuous_monitor") == 1
    assert "target_key=github-pr-state-huangruiteng--loopx-checks-pending" in active
    assert "cadence=30m" in active
    assert "next_due_at=2026-08-02T00:30:00%2B08:00" in active

    unchanged = materialize_issue_fix_grouped_monitors(
        registry_path=registry,
        goal_id=GOAL_ID,
        project=project,
        ledger_path=ledger,
        claimed_by=AGENT_ID,
        cadence="30m",
        generated_at="2026-08-01T16:01:00Z",
    )
    assert unchanged["active_bucket_count"] == 1
    assert unchanged["write_performed"] is False
    assert state.read_text(encoding="utf-8").count("task_class=continuous_monitor") == 1

    upsert_issue_fix_pr_lifecycle_ledger_jsonl(ledger, _packet(101, state="MERGED"))
    upsert_issue_fix_pr_lifecycle_ledger_jsonl(ledger, _packet(102, state="MERGED"))
    retired = materialize_issue_fix_grouped_monitors(
        registry_path=registry,
        goal_id=GOAL_ID,
        project=project,
        ledger_path=ledger,
        claimed_by=AGENT_ID,
        cadence="30m",
        generated_at="2026-08-01T16:02:00Z",
    )

    assert retired["active_bucket_count"] == 0
    assert retired["write_performed"] is True
    final_state = state.read_text(encoding="utf-8")
    assert "status=done" in final_state
    assert (
        "evidence=Issue-fix%20PR%20lifecycle%20bucket%20"
        "github-pr-state-huangruiteng--loopx-checks-pending%20is%20empty."
    ) in final_state

    upsert_issue_fix_pr_lifecycle_ledger_jsonl(ledger, _packet(103))
    reopened = materialize_issue_fix_grouped_monitors(
        registry_path=registry,
        goal_id=GOAL_ID,
        project=project,
        ledger_path=ledger,
        claimed_by=AGENT_ID,
        cadence="30m",
        generated_at="2026-08-01T16:03:00Z",
    )
    assert reopened["write_performed"] is True
    reopened_state = state.read_text(encoding="utf-8")
    assert reopened_state.count("task_class=continuous_monitor") == 1
    assert "status=open" in reopened_state
    assert "no_followup=true" not in reopened_state


def test_grouped_monitors_are_isolated_per_repository(tmp_path: Path) -> None:
    project, state, registry = _fixture(tmp_path)
    ledger = tmp_path / "pr-lifecycle.jsonl"
    upsert_issue_fix_pr_lifecycle_ledger_jsonl(ledger, _packet(101))
    upsert_issue_fix_pr_lifecycle_ledger_jsonl(
        ledger,
        _packet(202, owner="openai", repo="codex"),
    )

    result = materialize_issue_fix_grouped_monitors(
        registry_path=registry,
        goal_id=GOAL_ID,
        project=project,
        ledger_path=ledger,
        claimed_by=AGENT_ID,
        cadence="30m",
        generated_at="2026-08-01T16:00:00Z",
    )

    assert result["active_bucket_count"] == 2
    assert result["active_member_count"] == 2
    active = state.read_text(encoding="utf-8")
    assert active.count("task_class=continuous_monitor") == 2
    assert "target_key=github-pr-state-huangruiteng--loopx-checks-pending" in active
    assert "target_key=github-pr-state-openai--codex-checks-pending" in active


def test_pr_lifecycle_execute_materializes_pending_monitor_and_keeps_goal_runnable(
    tmp_path: Path,
) -> None:
    project, state, registry = _fixture(tmp_path)
    metadata = tmp_path / "pr.json"
    metadata.write_text(
        json.dumps(
            {
                "state": "OPEN",
                "reviewDecision": "REVIEW_REQUIRED",
                "mergeStateStatus": "CLEAN",
                "statusCheckRollup": [{"name": "integration", "status": "IN_PROGRESS"}],
            }
        ),
        encoding="utf-8",
    )
    output = io.StringIO()
    with contextlib.redirect_stdout(output):
        assert (
            cli_main(
                [
                    "--registry",
                    str(registry),
                    "--format",
                    "json",
                    "issue-fix",
                    "pr-lifecycle",
                    "--url",
                    "https://github.com/huangruiteng/loopx/pull/101",
                    "--metadata-json",
                    str(metadata),
                    "--goal-id",
                    GOAL_ID,
                    "--project",
                    str(project),
                    "--claimed-by",
                    AGENT_ID,
                    "--execute-transition",
                    "--generated-at",
                    "2026-08-01T16:00:00Z",
                ]
            )
            == 0
        )
    payload = json.loads(output.getvalue())

    assert payload["ok"] is True
    assert payload["transition"]["decision"] == "monitor_continuation"
    assert payload["first_screen"] == (
        payload["first_screen"]
        | {
            "agent_can_continue": True,
            "current_pr_actionable": False,
            "immediate_repoll_required": False,
        }
    )
    assert payload["grouped_monitor_writeback"] == (
        payload["grouped_monitor_writeback"]
        | {
            "write_performed": True,
            "active_bucket_count": 1,
            "active_member_count": 1,
        }
    )
    assert payload["todo_write_performed"] is True
    active = state.read_text(encoding="utf-8")
    assert active.count("task_class=continuous_monitor") == 1
    assert "target_key=github-pr-state-huangruiteng--loopx-checks-pending" in active
    assert "task_class=advancement_task" in active


def test_pr_lifecycle_execute_fetches_public_metadata_by_default(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    project, state, registry = _fixture(tmp_path)

    def fake_fetch(reference: dict, *, timeout_seconds: int) -> dict:
        assert reference["repo"] == "huangruiteng/loopx"
        assert timeout_seconds == 10
        return {
            "state": "OPEN",
            "reviewDecision": "REVIEW_REQUIRED",
            "mergeStateStatus": "CLEAN",
            "statusCheckRollup": [{"name": "integration", "status": "IN_PROGRESS"}],
        }

    monkeypatch.setattr(
        pr_lifecycle,
        "fetch_github_pr_lifecycle_payload",
        fake_fetch,
    )
    output = io.StringIO()
    with contextlib.redirect_stdout(output):
        assert (
            cli_main(
                [
                    "--registry",
                    str(registry),
                    "--format",
                    "json",
                    "issue-fix",
                    "pr-lifecycle",
                    "--url",
                    "https://github.com/huangruiteng/loopx/pull/101",
                    "--goal-id",
                    GOAL_ID,
                    "--project",
                    str(project),
                    "--claimed-by",
                    AGENT_ID,
                    "--execute-transition",
                    "--generated-at",
                    "2026-08-01T16:00:00Z",
                ]
            )
            == 0
        )

    payload = json.loads(output.getvalue())
    assert payload["ok"] is True
    assert payload["external_reads_performed"] is True
    assert state.read_text(encoding="utf-8").count("task_class=continuous_monitor") == 1
