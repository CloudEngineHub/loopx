from __future__ import annotations

from loopx.bootstrap import render_state_markdown
from loopx.control_plane.goals.goal_frontier import (
    build_goal_frontier_projection_from_summaries,
    goal_frontier_is_terminal_no_followup,
)
from loopx.control_plane.todos.active_state_todo_parser import (
    parse_active_state_todos,
)
from loopx.control_plane.todos.quota_summary import summarize_user_todos_for_quota


def _terminal_projection(state_text: str) -> dict[str, object]:
    parsed = parse_active_state_todos(state_text)
    user_todos = summarize_user_todos_for_quota(parsed.get("user_todos"))
    agent_todos = summarize_user_todos_for_quota(parsed.get("agent_todos"))
    return build_goal_frontier_projection_from_summaries(
        goal_id="goal-terminal-test",
        agent_id=None,
        user_todo_summary=user_todos,
        agent_todo_summary=agent_todos,
        work_lane_contract=None,
        replan_obligation=None,
    )


def test_bootstrap_declares_both_todo_sources(tmp_path) -> None:
    state_text = render_state_markdown(
        project=tmp_path,
        goal_id="goal-terminal-test",
        adapter_kind="issue_fix_workflow_v0",
        objective="Fix the issue.",
        updated_at="2026-07-29T00:00:00+08:00",
        goal_doc=None,
        execution_profile=None,
    )

    parsed = parse_active_state_todos(state_text)

    assert parsed["user_todos"]["total_count"] == 0
    assert parsed["user_todos"]["source_proof"]["derived"] is True
    assert parsed["agent_todos"]["total_count"] == 0
    assert parsed["agent_todos"]["source_proof"]["derived"] is True


def test_agent_only_no_followup_closes_explicit_empty_user_source() -> None:
    state_text = """\
## User Todo / Owner Review Reading Queue

## Agent Todo

- [x] [P0] Fix and validate the issue.
  <!-- loopx:todo todo_id=todo_fix status=done task_class=advancement_task no_followup=true note=Validated. -->
"""

    projection = _terminal_projection(state_text)

    assert projection["source_completeness"] == {
        "schema_version": "goal_terminal_source_completeness_v0",
        "user_todos": "valid",
        "agent_todos": "valid",
    }
    assert goal_frontier_is_terminal_no_followup(projection=projection) is True


def test_agent_only_no_followup_fails_closed_when_user_source_is_missing() -> None:
    state_text = """\
## Agent Todo

- [x] [P0] Fix and validate the issue.
  <!-- loopx:todo todo_id=todo_fix status=done task_class=advancement_task no_followup=true note=Validated. -->
"""

    projection = _terminal_projection(state_text)

    assert "terminal_state" not in projection
    assert goal_frontier_is_terminal_no_followup(projection=projection) is False
