"""Whole-source summary decisions precede display limits and preserve chronology."""
from loopx.control_plane.todos.todo_summary import compact_todo_group


def row(index, **fields):
    return {"todo_id": f"todo_summary_{index}", "text": f"Work {index}", "role": "agent",
            "task_class": "advancement_task", "status": "open", "index": index,
            "source_section": "Agent Todo", **fields}


def summarize(items, **kwargs):
    return compact_todo_group(items, role="agent", source_section="Agent Todo", **kwargs)


def test_recent_completions_compare_instants_not_offset_strings():
    items = [row(1, status="done", no_followup=True, completed_at="2026-01-01T10:00:00+08:00"),
             row(2, status="done", no_followup=True, completed_at="2026-01-01T03:00:00Z")]
    result = summarize(items)
    assert [item["todo_id"] for item in result["recent_completed_advancement_items"]] == [
        "todo_summary_2", "todo_summary_1"]


def test_recent_completions_preserve_microseconds_across_offsets():
    items = [row(2, status="done", no_followup=True, completed_at="2026-01-01T10:00:00.000001+08:00"),
             row(1, status="done", no_followup=True, completed_at="2026-01-01T02:00:00.000002Z")]
    result = summarize(items)
    assert [item["todo_id"] for item in result["recent_completed_advancement_items"]] == [
        "todo_summary_1", "todo_summary_2"]


def test_invalid_completion_time_does_not_displace_known_recent_work():
    result = summarize([row(1, status="done", no_followup=True, completed_at="unknown"),
                        row(2, status="done", no_followup=True, completed_at="2026-01-01T03:00:00Z")])
    assert [item["todo_id"] for item in result["recent_completed_advancement_items"]] == ["todo_summary_2"]
    assert result["advancement_done_count"] == 2  # Still retained as completed work.


def test_summary_caps_do_not_change_work_counts_or_hide_a_peer():
    items = [row(i, claimed_by="agent-a" if i < 24 else "agent-b") for i in range(32)]
    result = summarize(items, item_limit=1)
    assert len(result["items"]) == 1 and result["work_counts"]["advancement"] == 32
    assert len(result["claimed_open_items"]) == 16
    assert {item["claimed_by"] for item in result["claimed_open_items"]} == {"agent-a", "agent-b"}
    assert result["claimed_open_count"] == 32


def test_late_edit_does_not_make_an_old_completion_recent():
    result = summarize([row(1, status="done", no_followup=True,
                            completed_at="2026-01-01T00:00:00Z", updated_at="2026-09-01T00:00:00Z"),
                        row(2, status="done", no_followup=True,
                            completed_at="2026-02-01T00:00:00Z")])
    assert [item["todo_id"] for item in result["recent_completed_advancement_items"]] == [
        "todo_summary_2", "todo_summary_1"]


def test_a_selection_cannot_restore_a_lost_full_source_proof():
    from loopx.control_plane.todos.todo_summary import compact_evaluated_todo_group
    source = summarize([row(1, status="done", no_followup=True)], item_limit=None)
    result = compact_evaluated_todo_group(source["items"], source_section="Agent Todo", role="agent",
        full_selection=False, selection={"role": "agent", "status": None, "todo_id": None, "agent_id": None})
    assert "source_proof" not in result and "terminal_closure_proof" not in result
    assert result["done_count"] == 1
