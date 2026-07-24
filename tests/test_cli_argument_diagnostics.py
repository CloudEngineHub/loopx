from __future__ import annotations

import json

import pytest

from loopx.cli import main


@pytest.mark.parametrize(
    "argv",
    [
        ["status", "--goal-id", "example-goal", "--project", "."],
        ["quota", "should-run", "--goal-id", "example-goal", "--project", "."],
    ],
)
def test_unsupported_project_option_is_not_misparsed_as_projection_cache_ttl(
    argv: list[str],
    capsys: pytest.CaptureFixture[str],
) -> None:
    with pytest.raises(SystemExit) as exc_info:
        main(argv)

    assert exc_info.value.code == 2
    stderr = capsys.readouterr().err
    assert "unrecognized arguments: --project ." in stderr
    assert "projection-cache-ttl-seconds" not in stderr
    assert "invalid int value" not in stderr


def test_quota_include_detail_rejects_unknown_section(
    capsys: pytest.CaptureFixture[str],
) -> None:
    with pytest.raises(SystemExit) as exc_info:
        main(
            [
                "quota",
                "should-run",
                "--goal-id",
                "example-goal",
                "--include-detail",
                "unknown",
            ]
        )

    assert exc_info.value.code == 2
    stderr = capsys.readouterr().err
    assert "invalid choice: 'unknown'" in stderr
    assert "--include-detail" in stderr


def test_quota_include_detail_rejects_non_should_run_command(
    capsys: pytest.CaptureFixture[str],
) -> None:
    exit_code = main(
        [
            "--format",
            "json",
            "quota",
            "status",
            "--include-detail",
            "scheduler",
        ]
    )

    assert exit_code == 1
    payload = json.loads(capsys.readouterr().out)
    assert payload["ok"] is False
    assert payload["error"] == (
        "--include-detail is only valid with `quota should-run`"
    )
