from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess
import sys
import time

import pytest

from loopx.file_lock import exclusive_file_lock


REPO_ROOT = Path(__file__).resolve().parents[2]


def _workspace(tmp_path: Path, *, goal_id: str) -> tuple[Path, Path, Path]:
    repo = tmp_path / goal_id
    repo.mkdir()
    state = repo / "ACTIVE_GOAL_STATE.md"
    state.write_text(
        "---\n"
        f"goal_id: {goal_id}\n"
        "handoff_mode: hard_lease\n"
        "updated_at: 2026-09-02T00:00:00+00:00\n"
        "---\n\n"
        "## Agent Todo\n\n",
        encoding="utf-8",
    )
    runtime_root = tmp_path / f"{goal_id}-runtime"
    registry = tmp_path / f"{goal_id}-registry.json"
    registry.write_text(
        json.dumps(
            {
                "common_runtime_root": str(runtime_root),
                "goals": [
                    {
                        "id": goal_id,
                        "status": "active",
                        "repo": str(repo),
                        "state_file": state.name,
                        "coordination": {
                            "agent_model": "peer_v1",
                            "registered_agents": ["agent-a", "agent-b"],
                        },
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    return registry, state, runtime_root


def _command(registry: Path, runtime_root: Path, *args: str) -> list[str]:
    return [
        sys.executable,
        "-m",
        "loopx.cli",
        "--registry",
        str(registry),
        "--runtime-root",
        str(runtime_root),
        "--format",
        "json",
        *args,
    ]


def _env() -> dict[str, str]:
    env = os.environ.copy()
    env["PYTHONPATH"] = str(REPO_ROOT)
    return env


def _cli(registry: Path, runtime_root: Path, *args: str) -> dict[str, object]:
    completed = subprocess.run(
        _command(registry, runtime_root, *args),
        cwd=REPO_ROOT,
        env=_env(),
        check=True,
        capture_output=True,
        text=True,
        timeout=30,
    )
    return json.loads(completed.stdout)


def _store_document(runtime_root: Path, goal_id: str) -> tuple[Path, dict[str, object]]:
    paths = list(
        (runtime_root / "authority-shadow" / "file" / goal_id).glob(
            "authority-store-*.json"
        )
    )
    assert len(paths) == 1
    return paths[0], json.loads(paths[0].read_text(encoding="utf-8"))


def _add_todo(
    registry: Path,
    runtime_root: Path,
    *,
    goal_id: str,
    text: str,
) -> dict[str, object]:
    return _cli(
        registry,
        runtime_root,
        "todo",
        "add",
        "--goal-id",
        goal_id,
        "--role",
        "agent",
        "--text",
        text,
        "--task-class",
        "advancement_task",
    )


def test_product_cli_configure_capture_readback_disable_and_default_off_parity(
    tmp_path: Path,
) -> None:
    goal_id = "shadow-cli-e2e"
    registry, _state, runtime_root = _workspace(tmp_path, goal_id=goal_id)

    preview = _cli(
        registry,
        runtime_root,
        "configure-goal",
        "--goal-id",
        goal_id,
        "--local-authority-shadow-file",
    )
    assert preview["dry_run"] is True
    assert preview["written"] is False

    enabled = _cli(
        registry,
        runtime_root,
        "configure-goal",
        "--goal-id",
        goal_id,
        "--local-authority-shadow-file",
        "--execute",
    )
    assert enabled["written"] is True

    text = "Capture one post-commit observation through the product CLI."
    observed = _add_todo(
        registry,
        runtime_root,
        goal_id=goal_id,
        text=text,
    )
    assert observed["authority_shadow"]["outcome"] == "captured"  # type: ignore[index]
    assert observed["authority_shadow"]["parity_verdict"] == "not_evaluated"  # type: ignore[index]
    lease = _cli(
        registry,
        runtime_root,
        "task-lease",
        "acquire",
        "--goal-id",
        goal_id,
        "--todo-id",
        str(observed["todo_id"]),
        "--owner",
        "agent-a",
        "--idempotency-key",
        "shadow-cli-lease",
        "--ttl-seconds",
        "120",
    )
    assert lease["acquired"] is True
    assert lease["authority_shadow"]["outcome"] == "captured"  # type: ignore[index]
    store_path, store = _store_document(runtime_root, goal_id)
    assert len(store["head"]["todos"]) == 1  # type: ignore[index]
    assert len(store["head"]["leases"]) == 1  # type: ignore[index]

    inspected = _cli(
        registry,
        runtime_root,
        "configure-goal",
        "--goal-id",
        goal_id,
    )
    assert inspected["after"]["local_authority_shadow"] == {  # type: ignore[index]
        "enabled": True,
        "mode": "file_one_way",
        "status": "enabled",
    }

    disabled = _cli(
        registry,
        runtime_root,
        "configure-goal",
        "--goal-id",
        goal_id,
        "--clear-local-authority-shadow",
        "--execute",
    )
    assert disabled["written"] is True
    candidate_before_disabled_write = store_path.read_bytes()
    after_disable = _add_todo(
        registry,
        runtime_root,
        goal_id=goal_id,
        text="This local lifecycle write must not execute the observer.",
    )
    assert after_disable["ok"] is True
    assert after_disable["added"] is True
    assert "authority_shadow" not in after_disable
    assert store_path.read_bytes() == candidate_before_disabled_write

    baseline_registry, _baseline_state, baseline_runtime = _workspace(
        tmp_path, goal_id="shadow-cli-baseline"
    )
    baseline = _add_todo(
        baseline_registry,
        baseline_runtime,
        goal_id="shadow-cli-baseline",
        text=text,
    )
    for field in (
        "ok",
        "added",
        "already_exists",
        "metadata_updated",
        "status_changed",
        "role",
        "status",
        "task_class",
        "action_kind",
        "continuation_policy",
    ):
        assert observed[field] == baseline[field]
    assert not (baseline_runtime / "authority-shadow").exists()


def test_product_cli_candidate_failure_preserves_the_primary_lifecycle_commit(
    tmp_path: Path,
) -> None:
    goal_id = "shadow-cli-failure"
    registry, state, runtime_root = _workspace(tmp_path, goal_id=goal_id)
    _cli(
        registry,
        runtime_root,
        "configure-goal",
        "--goal-id",
        goal_id,
        "--local-authority-shadow-file",
        "--execute",
    )
    runtime_root.mkdir(parents=True, exist_ok=True)
    (runtime_root / "authority-shadow").write_text("block candidate directory", encoding="utf-8")

    result = _add_todo(
        registry,
        runtime_root,
        goal_id=goal_id,
        text="The primary write survives a candidate construction failure.",
    )

    assert result["ok"] is True
    assert result["added"] is True
    assert result["authority_shadow"]["outcome"] == "failed"  # type: ignore[index]
    assert result["authority_shadow"]["reason_code"] == "shadow_observation_failed"  # type: ignore[index]
    assert str(result["todo_id"]) in state.read_text(encoding="utf-8")


@pytest.mark.skipif(os.name == "nt", reason="requires POSIX cross-process flock and SIGKILL")
def test_product_cli_crash_gap_has_no_outbox_but_later_capture_refreshes_head(
    tmp_path: Path,
) -> None:
    goal_id = "shadow-cli-crash-gap"
    registry, state, runtime_root = _workspace(tmp_path, goal_id=goal_id)
    _cli(
        registry,
        runtime_root,
        "configure-goal",
        "--goal-id",
        goal_id,
        "--local-authority-shadow-file",
        "--execute",
    )
    first_text = "Primary commit that loses its post-commit observation."
    observation_lock_target = (
        runtime_root / "authority-shadow" / "file" / goal_id / "observation"
    )

    with exclusive_file_lock(observation_lock_target, operation="e2e_crash_gap"):
        process = subprocess.Popen(
            _command(
                registry,
                runtime_root,
                "todo",
                "add",
                "--goal-id",
                goal_id,
                "--role",
                "agent",
                "--text",
                first_text,
                "--task-class",
                "advancement_task",
            ),
            cwd=REPO_ROOT,
            env=_env(),
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
        deadline = time.monotonic() + 5.0
        while first_text not in state.read_text(encoding="utf-8"):
            if time.monotonic() >= deadline:
                process.kill()
                process.communicate(timeout=5)
                raise AssertionError("primary Todo commit did not become visible")
            time.sleep(0.01)
        assert process.poll() is None
        process.kill()
        process.communicate(timeout=5)

    assert not list(
        (runtime_root / "authority-shadow" / "file" / goal_id).glob(
            "authority-store-*.json"
        )
    )

    recovered = _add_todo(
        registry,
        runtime_root,
        goal_id=goal_id,
        text="A later primary commit refreshes the current full snapshot.",
    )
    assert recovered["authority_shadow"]["outcome"] == "captured"  # type: ignore[index]
    assert recovered["authority_shadow"]["durable_source_outbox"] is False  # type: ignore[index]
    assert recovered["authority_shadow"]["source_transaction_correlated"] is False  # type: ignore[index]
    assert recovered["authority_shadow"]["parity_verdict"] == "not_evaluated"  # type: ignore[index]
    _store_path, store = _store_document(runtime_root, goal_id)
    assert len(store["head"]["todos"]) == 2  # type: ignore[index]
