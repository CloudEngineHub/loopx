"""Shared publication/readback shape checks; length does not prove review quality."""

from __future__ import annotations

import re
from collections.abc import Iterator
from typing import Any

REQUIRED_FINAL_SECTIONS = ["动机", "改动思路", "具体改动", "对主干的风险", "我的整体评价"]


def review_body_requirements(*, behavior_bearing: bool) -> dict[str, int]:
    # Count letters/numbers in explanatory prose, not Markdown, URLs or code.
    # Documentation-only fixes need less space than an executable contract.
    return dict(zip(REQUIRED_FINAL_SECTIONS,
                    (40, 80, 180, 120, 60) if behavior_bearing else (20, 30, 50, 30, 20)))


def english_review_verdict(body: str) -> str | None:
    verdicts = _english_verdicts(body)
    return verdicts[0] if len(verdicts) == 1 else None


def _english_verdicts(body: str) -> list[str]:
    verdicts: list[str] = []
    for line in _visible_lines(body):
        match = re.match(r"(?i)^english verdict\s*:\s*(APPROVE|REQUEST_CHANGES)\b",
                         line.strip().replace("**", ""))
        if match:
            verdicts.append(match.group(1).upper())
    return verdicts


def _visible_lines(body: str) -> Iterator[str]:
    fence: str | None = None
    for line in body.splitlines():
        stripped = line.strip()
        if stripped.startswith(("```", "~~~")):
            marker = stripped[:3]
            if fence is None:
                fence = marker
            elif fence == marker:
                fence = None
            continue
        if fence is None:
            yield line


def _prose_size(lines: list[str]) -> int:
    prose = "\n".join(dict.fromkeys(lines))
    prose = re.sub(r"!?\[([^\]]*)\]\([^)]*\)", r"\1", prose)
    prose = re.sub(r"https?://\S+|\b[0-9a-fA-F]{40,64}\b", "", prose)
    return sum(char.isalnum() for char in prose)


def check_review_body(body: str, *, head_oid: str, behavior_bearing: bool) -> dict[str, Any]:
    floors = review_body_requirements(behavior_bearing=behavior_bearing)
    sections: dict[str, list[str]] = {}
    current: str | None = None
    section_level = 0
    reasons: list[str] = []
    visible_lines = list(_visible_lines(body))
    for line in visible_lines:
        stripped = line.strip()
        heading = re.match(r"^(#{1,6})\s+(.+?)\s*#*\s*$", stripped)
        if heading:
            level, label = len(heading[1]), heading[2]
            if label in floors:
                if label in sections:
                    reasons.append(f"duplicate_section:{label}")
                sections.setdefault(label, [])
                current, section_level = label, level
            elif level <= section_level:
                current = None
            continue
        if english_review_verdict(line):
            continue
        if current and stripped:
            sections[current].append(stripped)
    sizes = {label: _prose_size(lines) for label, lines in sections.items()}
    for label, floor in floors.items():
        if label not in sections:
            reasons.append(f"missing_section:{label}")
        elif sizes[label] < floor:
            reasons.append(f"section_too_short:{label}:{sizes[label]}<{floor}")
    if not head_oid or head_oid.casefold() not in "\n".join(visible_lines).casefold():
        reasons.append("missing_exact_head")
    verdicts = _english_verdicts(body)
    verdict = verdicts[0] if len(verdicts) == 1 else None
    if len(verdicts) > 1:
        reasons.append("ambiguous_english_verdict")
    elif verdict is None:
        reasons.append("missing_english_verdict")
    return {"valid": not reasons, "invalid_reasons": reasons,
            "section_lengths": sizes, "minimum_prose_characters": floors,
            "verdict": verdict, "evidence_truth_verified": False}
