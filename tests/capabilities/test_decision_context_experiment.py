from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from loopx.capabilities.catalog import build_capability_detail_packet
from loopx.capabilities.decision_context import (
    build_decision_source_provider,
    normalize_decision_context_experiment_config,
    resolve_decision_context_experiment,
)
from loopx.cli import main

OBSERVED_AT = "2026-07-25T18:30:00+00:00"
PRIVATE_CONTENT = "private authority content"


def experiment_payload(
    authority_path: Path,
    *,
    enabled: bool = True,
    agent_id: str = "example-agent",
    adapter: str = "local-file",
) -> dict[str, Any]:
    return {
        "schema_version": "decision_context_experiment_config_v0",
        "goal_id": "example-decision-goal",
        "enabled": enabled,
        "enabled_agents": [agent_id],
        "source_provider_bindings": [
            {
                "provider_id": "local-authority",
                "adapter": adapter,
                "config": {"max_bytes": 4096},
            }
        ],
        "sources": [
            {
                "source_id": "source:authority:baseline",
                "provider_id": "local-authority",
                "source_kind": "artifact",
                "priority": "p0",
                "evidence_level": "s3",
                "objectives": ["delivery-quality", "product-adoption"],
                "scan_mode": "incremental",
                "exact_read_policy": "material_change",
                "freshness_seconds": 3 * 24 * 60 * 60,
                "private_locator": str(authority_path),
                "max_changes": 8,
                "enabled": True,
            }
        ],
        "context_provider": None,
        "automation": {
            "automatic_capture": False,
            "fail_open": True,
        },
    }


def write_config(path: Path, payload: dict[str, Any]) -> Path:
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


def test_experiment_is_default_off_without_private_config() -> None:
    status, config = resolve_decision_context_experiment(
        goal_id="example-decision-goal",
        agent_id="example-agent",
        config_path=None,
    )

    assert config is None
    assert status["status"] == "disabled"
    assert status["default_enabled"] is False
    assert status["available"] is False
    assert status["external_writes_performed"] is False


def test_available_status_and_manifest_do_not_leak_private_config(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    authority = tmp_path / "private-authority.md"
    authority.write_text(PRIVATE_CONTENT, encoding="utf-8")
    config_path = write_config(
        tmp_path / "private-config.json",
        experiment_payload(authority),
    )

    assert (
        main(
            [
                "--format",
                "json",
                "decision-context",
                "source-manifest",
                "--goal-id",
                "example-decision-goal",
                "--agent-id",
                "example-agent",
                "--config",
                str(config_path),
                "--observed-at",
                OBSERVED_AT,
            ]
        )
        == 0
    )
    payload = json.loads(capsys.readouterr().out)
    serialized = json.dumps(payload, sort_keys=True)

    assert payload["status"] == "available"
    assert payload["source_manifest"]["source_count"] == 1
    assert payload["source_manifest"]["observed_at"] == OBSERVED_AT
    for private_value in (
        str(authority),
        str(config_path),
        PRIVATE_CONTENT,
        "max_bytes",
    ):
        assert private_value not in serialized
    assert payload["private_locator_captured"] is False
    assert payload["raw_content_captured"] is False
    assert payload["credentials_captured"] is False


@pytest.mark.parametrize(
    ("goal_id", "agent_id", "adapter", "expected_status"),
    [
        (
            "another-goal",
            "example-agent",
            "local-file",
            "config_invalid",
        ),
        (
            "example-decision-goal",
            "another-agent",
            "local-file",
            "agent_not_enabled",
        ),
        (
            "example-decision-goal",
            "example-agent",
            "missing-adapter",
            "provider_unavailable",
        ),
    ],
)
def test_scope_and_provider_routes_fail_closed_without_private_leaks(
    tmp_path: Path,
    goal_id: str,
    agent_id: str,
    adapter: str,
    expected_status: str,
) -> None:
    authority = tmp_path / "private-authority.md"
    authority.write_text(PRIVATE_CONTENT, encoding="utf-8")
    config_path = write_config(
        tmp_path / "private-config.json",
        experiment_payload(authority, adapter=adapter),
    )

    status, _config = resolve_decision_context_experiment(
        goal_id=goal_id,
        agent_id=agent_id,
        config_path=config_path,
    )
    serialized = json.dumps(status, sort_keys=True)

    assert status["status"] == expected_status
    assert status["available"] is False
    assert str(authority) not in serialized
    assert str(config_path) not in serialized
    assert PRIVATE_CONTENT not in serialized


@pytest.mark.parametrize(
    ("field_name", "value", "expected_message"),
    [
        ("automatic_capture", True, "automatic capture must stay disabled"),
        ("fail_open", False, "providers must fail open"),
    ],
)
def test_experiment_rejects_unsafe_automation_modes(
    tmp_path: Path,
    field_name: str,
    value: bool,
    expected_message: str,
) -> None:
    payload = experiment_payload(tmp_path / "authority.md")
    payload["automation"][field_name] = value

    with pytest.raises(ValueError, match=expected_message):
        normalize_decision_context_experiment_config(payload)


def test_local_file_provider_supports_bounded_scan_exact_read_and_cursor(
    tmp_path: Path,
) -> None:
    authority = tmp_path / "authority.md"
    authority.write_text(PRIVATE_CONTENT, encoding="utf-8")
    config = normalize_decision_context_experiment_config(experiment_payload(authority))
    provider = build_decision_source_provider(
        config.provider_binding_map()["local-authority"]
    )
    source = config.sources[0]

    first = provider.scan(
        source=source,
        after_cursor=None,
        before="2100-01-01T00:00:00+00:00",
        limit=8,
        timeout_seconds=2,
        observed_at=OBSERVED_AT,
    )
    exact_read = provider.exact_read(
        source=source,
        item=first.items[0],
        timeout_seconds=2,
        observed_at=OBSERVED_AT,
    )
    receipt = first.public_receipt(exact_reads=[exact_read])
    second = provider.scan(
        source=source,
        after_cursor=first.cursor_after,
        before="2100-01-01T00:00:00+00:00",
        limit=8,
        timeout_seconds=2,
        observed_at=OBSERVED_AT,
    )
    serialized = json.dumps(receipt, sort_keys=True)

    assert first.status == "completed"
    assert exact_read.content == PRIVATE_CONTENT
    assert receipt["changed_count"] == 1
    assert receipt["exact_read_count"] == 1
    assert second.status == "no_change"
    assert str(authority) not in serialized
    assert PRIVATE_CONTENT not in serialized


def test_local_file_provider_rejects_oversized_authority(tmp_path: Path) -> None:
    authority = tmp_path / "authority.md"
    authority.write_text(PRIVATE_CONTENT, encoding="utf-8")
    payload = experiment_payload(authority)
    bindings = payload["source_provider_bindings"]
    assert isinstance(bindings, list)
    binding = bindings[0]
    assert isinstance(binding, dict)
    private_config = binding["config"]
    assert isinstance(private_config, dict)
    private_config["max_bytes"] = 2
    config = normalize_decision_context_experiment_config(payload)
    provider = build_decision_source_provider(
        config.provider_binding_map()["local-authority"]
    )

    with pytest.raises(ValueError, match="exceeds max_bytes"):
        provider.scan(
            source=config.sources[0],
            after_cursor=None,
            before="2100-01-01T00:00:00+00:00",
            limit=8,
            timeout_seconds=2,
            observed_at=OBSERVED_AT,
        )


def test_catalog_routes_to_default_off_experiment_status() -> None:
    capability = build_capability_detail_packet("decision-context")["capability"]
    schema_versions = {
        protocol["schema_version"] for protocol in capability["implemented_protocols"]
    }

    assert "experiment-status" in capability["entry_command"]
    assert {
        "decision_context_experiment_config_v0",
        "decision_context_experiment_status_v0",
    } <= schema_versions
