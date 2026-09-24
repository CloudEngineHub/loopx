"""Execute the shipped DCO shell step against disposable Git repositories."""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[1]
SIGNOFF = "Signed-off-by: Test Contributor <contributor@example.invalid>"


@pytest.fixture
def git_env() -> dict[str, str]:
    return {
        **{key: value for key, value in os.environ.items() if not key.startswith("GIT_")},
        "GIT_CONFIG_NOSYSTEM": "1",
        "GIT_CONFIG_GLOBAL": os.devnull,
        "GIT_AUTHOR_NAME": "Test Contributor",
        "GIT_AUTHOR_EMAIL": "contributor@example.invalid",
        "GIT_COMMITTER_NAME": "Test Contributor",
        "GIT_COMMITTER_EMAIL": "contributor@example.invalid",
        "GIT_TERMINAL_PROMPT": "0",
    }


def git(repo: Path, env: dict[str, str], *args: str) -> str:
    return subprocess.run(
        ["git", *args], cwd=repo, env=env, check=True,
        capture_output=True, text=True, timeout=15,
    ).stdout.strip()


def commit(repo: Path, env: dict[str, str], message: str, *, signed: bool = True) -> str:
    if signed:
        message += f"\n\n{SIGNOFF}"
    git(repo, env, "commit", "--allow-empty", "-m", message)
    return git(repo, env, "rev-parse", "HEAD")


@pytest.fixture
def history(tmp_path: Path, git_env: dict[str, str]):
    """The runner knows the PR history but retains an outdated base tracking ref."""
    remote = tmp_path / "upstream.git"
    source = tmp_path / "source"
    runner = tmp_path / "runner"
    source.mkdir()
    git(tmp_path, git_env, "init", "--bare", str(remote))
    git(source, git_env, "init", "-b", "release/next")
    old_base = commit(source, git_env, "Old upstream base")
    git(source, git_env, "remote", "add", "origin", str(remote))
    git(source, git_env, "push", "origin", "release/next")
    git(tmp_path, git_env, "clone", "--branch", "release/next", str(remote), str(runner))

    upstream = commit(source, git_env, "Already upstream, without a trailer", signed=False)
    git(source, git_env, "push", "origin", "release/next")
    # Fetch the object without refreshing origin/release/next, as when a runner
    # obtains a PR ref whose history includes newer upstream commits.
    git(runner, git_env, "fetch", "origin", upstream)
    git(runner, git_env, "checkout", "-b", "contribution", "FETCH_HEAD")
    assert git(runner, git_env, "rev-parse", "origin/release/next") == old_base
    return runner, old_base, upstream


def check_dco(
    repo: Path, env: dict[str, str], old_base: str, head: str,
    *, base_ref: str = "release/next",
) -> subprocess.CompletedProcess[str]:
    workflow = yaml.safe_load((ROOT / ".github/workflows/dco.yml").read_text(encoding="utf-8"))
    event_values = {
        "${{ github.event.pull_request.base.sha }}": old_base,
        "${{ github.event.pull_request.base.ref }}": base_ref,
        "${{ github.event.pull_request.head.sha }}": head,
    }
    steps = [step for step in workflow["jobs"]["signoff"]["steps"] if "run" in step]
    for step in steps:
        step_env = {key: event_values[value] for key, value in step.get("env", {}).items()}
        result = subprocess.run(
            ["bash", "--noprofile", "--norc", "-e", "-o", "pipefail", "-c", step["run"]],
            cwd=repo, env={**env, **step_env}, check=False,
            capture_output=True, text=True, timeout=15,
        )
        if result.returncode:
            return result
    return result


@pytest.mark.parametrize("change", ["code", "docs"])
def test_signed_pr_excludes_newer_upstream_commits(history, git_env, change):
    runner, old_base, upstream = history
    filename = "example.py" if change == "code" else "README.md"
    (runner / filename).write_text("# Synthetic contribution\n", encoding="utf-8")
    git(runner, git_env, "add", filename)
    head = commit(runner, git_env, "Signed contribution")
    result = check_dco(runner, git_env, old_base, head)
    assert result.returncode == 0, result.stdout + result.stderr
    assert f"Commit {upstream} is missing" not in result.stdout


def test_unsigned_pr_commit_still_fails(history, git_env):
    runner, old_base, upstream = history
    head = commit(runner, git_env, "Unsigned contribution", signed=False)
    result = check_dco(runner, git_env, old_base, head)
    assert result.returncode != 0
    assert f"Commit {head} is missing" in result.stdout
    assert f"Commit {upstream} is missing" not in result.stdout


@pytest.mark.parametrize("signed", [False, True])
def test_pr_merge_requires_its_own_signoff(history, git_env, signed):
    runner, old_base, upstream = history
    git(runner, git_env, "checkout", "-b", "topic")
    commit(runner, git_env, "Signed topic")
    git(runner, git_env, "checkout", "contribution")
    commit(runner, git_env, "Signed mainline")
    message = f"PR merge\n\n{SIGNOFF}" if signed else "Unsigned PR merge"
    git(runner, git_env, "merge", "--no-ff", "topic", "-m", message)
    head = git(runner, git_env, "rev-parse", "HEAD")
    result = check_dco(runner, git_env, old_base, head)
    assert (result.returncode == 0) == signed, result.stdout + result.stderr
    if not signed:
        assert f"Commit {head} is missing" in result.stdout
    assert f"Commit {upstream} is missing" not in result.stdout


def test_runner_merge_is_not_part_of_pr(history, git_env):
    runner, old_base, _ = history
    head = commit(runner, git_env, "Signed contribution")
    git(runner, git_env, "checkout", "-b", "runner-merge", old_base)
    git(runner, git_env, "merge", "--no-ff", "contribution", "-m", "Runner merge")
    result = check_dco(runner, git_env, old_base, head)
    assert result.returncode == 0, result.stdout + result.stderr


@pytest.mark.parametrize("failure", ["missing-base", "unavailable-remote", "missing-head"])
def test_unreadable_history_fails_closed(history, git_env, failure):
    runner, old_base, _ = history
    head = commit(runner, git_env, "Signed contribution")
    base_ref = "release/next"
    if failure == "missing-base":
        base_ref = "deleted-branch"
    elif failure == "unavailable-remote":
        git(runner, git_env, "remote", "set-url", "origin", str(runner / "missing.git"))
    else:
        head = "0" * 40
    result = check_dco(runner, git_env, old_base, head, base_ref=base_ref)
    assert result.returncode != 0, result.stdout + result.stderr


def test_empty_pr_range_passes(history, git_env):
    runner, old_base, upstream = history
    result = check_dco(runner, git_env, old_base, upstream)
    assert result.returncode == 0, result.stdout + result.stderr


def test_signed_pr_with_current_event_base_passes(history, git_env):
    runner, _, upstream = history
    head = commit(runner, git_env, "Signed contribution")
    result = check_dco(runner, git_env, upstream, head)
    assert result.returncode == 0, result.stdout + result.stderr
