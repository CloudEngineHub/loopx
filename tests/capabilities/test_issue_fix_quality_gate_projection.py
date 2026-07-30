"""Quality-gate projection in issue-fix workflow-plan.

Four semantic scenarios:
  1. Default packet — gate is not_configured, no blocker, validates clean.
  2. Admitted + proceed candidate — gate is projected with side-effect-free
     todo/command contract, blocker is added, validates clean.
  3. Wrong schema version — validator rejects.
  4. False side-effect claim (registry_read=True) — validator rejects.
"""

from __future__ import annotations

from loopx.capabilities.issue_fix.candidate_evidence import (
    build_public_github_candidate_preflight_input,
)
from loopx.capabilities.issue_fix.workflow_plan import (
    ISSUE_FIX_QUALITY_GATE_PLAN_SCHEMA_VERSION,
    build_issue_fix_workflow_plan_packet,
    validate_issue_fix_workflow_plan_packet,
)

GENERATED_AT = "2026-07-30T12:00:00Z"
REPO = "volcengine/OpenViking"
ISSUE = "#3305"


def _source_receipts() -> dict[str, dict[str, object]]:
    return {
        field: {
            "provider": "github_graphql",
            "observed_at": GENERATED_AT,
            "query_fingerprint": f"sha256:{field}",
            "page_count": 1,
            "result_count": 0,
            "complete": True,
            "truncated": False,
            "raw_provider_payload_captured": False,
        }
        for field in (
            "numeric_pr_evidence",
            "semantic_pr_evidence",
            "maintainer_comment_evidence",
        )
    }


def _admitted_proceed_preflight() -> dict[str, object]:
    """Canonical preflight input → admitted + proceed (no manual override)."""
    return build_public_github_candidate_preflight_input(
        repo=REPO,
        issue_ref=ISSUE,
        issue_state="OPEN",
        closing_pull_requests=[],
        cross_referenced_pull_requests=[],
        maintainer_comments=[],
        generated_at=GENERATED_AT,
        source_receipts=_source_receipts(),
    )


def _proceed_packet() -> dict[str, object]:
    return build_issue_fix_workflow_plan_packet(
        repo=REPO,
        issue_ref=ISSUE,
        candidate_preflight_input=_admitted_proceed_preflight(),
    )


def test_default_not_configured_no_blocker_valid() -> None:
    packet = build_issue_fix_workflow_plan_packet()
    gate = packet["quality_gate_plan"]
    blockers = packet["review_packet_preview"]["readiness_blockers"]

    assert gate["status"] == "not_configured"
    assert gate["gate_required"] is False
    assert gate["todo_preview"] is None
    assert gate["command_preview"] is None
    assert gate["registry_read_performed"] is False
    assert gate["external_writes_performed"] is False
    assert "quality_gate_not_run" not in blockers

    v = validate_issue_fix_workflow_plan_packet(packet)
    assert v["ok"] is True, v["errors"]


def test_admitted_proceed_projects_side_effect_free_gate() -> None:
    packet = _proceed_packet()
    gate = packet["quality_gate_plan"]
    blockers = packet["review_packet_preview"]["readiness_blockers"]
    todo = gate["todo_preview"]

    assert gate["status"] == "projected"
    assert gate["gate_required"] is True
    assert gate["schema_version"] == ISSUE_FIX_QUALITY_GATE_PLAN_SCHEMA_VERSION

    assert todo is not None
    assert todo["action_kind"] == "issue_fix_pre_pr_quality_gate"
    assert todo["priority"] == "P1"
    assert todo["would_write"] is False
    assert todo["requires_execute_flag"] is True
    assert "change-quality prepare" in todo["next_command_preview"]

    assert "change-quality prepare" in gate["command_preview"]
    assert gate["result_record_command_preview"] is not None
    assert gate["record_requires_matching_scope_fingerprint"] is True

    assert gate["registry_read_performed"] is False
    assert gate["external_writes_performed"] is False

    assert "quality_gate_not_run" in blockers

    v = validate_issue_fix_workflow_plan_packet(packet)
    assert v["ok"] is True, v["errors"]


def test_wrong_schema_fails_validation() -> None:
    packet = build_issue_fix_workflow_plan_packet()
    broken = dict(packet)
    broken["quality_gate_plan"] = dict(
        packet["quality_gate_plan"],
        schema_version="bogus_v99",
    )
    v = validate_issue_fix_workflow_plan_packet(broken)
    assert v["ok"] is False
    assert any("wrong schema" in e for e in v["errors"])


def test_false_side_effect_claim_fails_validation() -> None:
    """Validator must enforce that the plan never claims registry reads."""
    packet = _proceed_packet()
    broken = dict(packet)
    broken["quality_gate_plan"] = dict(
        packet["quality_gate_plan"],
        registry_read_performed=True,
    )
    v = validate_issue_fix_workflow_plan_packet(broken)
    assert v["ok"] is False
    assert any("registry" in e for e in v["errors"])
