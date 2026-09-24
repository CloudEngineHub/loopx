"""Private, witnessed file exchange for complete local coordination snapshots.

Only transport moves here. The selected TS handler still owns validation,
source locks, operation receipts and authority. No artifact is a durable store.
"""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import stat
import tempfile
from typing import Any, NoReturn

TRANSFER_SCHEMA = "loopx_coordination_source_transfer_v0"
TRANSFER_RESULT_SCHEMA = "loopx_coordination_source_transfer_result_v0"
MAX_TRANSFER_BYTES = 16 * 1024 * 1024


def source_effect_runtime_result(method: str, request: dict[str, Any], **kwargs: Any) -> Any:
    """Keep RPC envelopes small without truncating a source or its result."""
    from ..effect_runtime import EffectRuntimeRejected, effect_runtime_result

    def reject(message: str) -> NoReturn:
        raise EffectRuntimeRejected(message, diagnostic_code="coordination_source_transfer_invalid")

    encoded = json.dumps(request, ensure_ascii=False, separators=(",", ":"), allow_nan=False).encode("utf-8")
    if len(encoded) > MAX_TRANSFER_BYTES:
        reject("coordination source transfer exceeds the 16 MiB artifact limit")
    request_digest = hashlib.sha256(encoded).hexdigest()
    # A timed-out TS handler can still hold its output open on Windows. Preserve
    # the ambiguous-operation error even when the OS cannot yet unlink that file.
    with tempfile.TemporaryDirectory(prefix="loopx-coordination-", ignore_cleanup_errors=True) as temporary:
        directory = Path(temporary).resolve()
        source = directory / "request.json"
        with source.open("xb") as writer:
            writer.write(encoded)
        result = effect_runtime_result(method, {
            "schema_version": TRANSFER_SCHEMA,
            "method": method,
            "directory": str(directory),
            "request_sha256": request_digest,
            "request_bytes": len(encoded),
        }, **kwargs)
        if (
            not isinstance(result, dict)
            or set(result) != {"schema_version", "method", "request_sha256", "result_sha256", "result_bytes"}
            or result.get("schema_version") != TRANSFER_RESULT_SCHEMA
            or result.get("method") != method
            or result.get("request_sha256") != request_digest
            or type(result.get("result_bytes")) is not int
            or not 0 < result["result_bytes"] <= MAX_TRANSFER_BYTES
        ):
            reject("coordination source transfer result does not match its request")
        target = directory / "result.json"
        before = target.lstat()
        if not stat.S_ISREG(before.st_mode) or before.st_size != result["result_bytes"]:
            reject("coordination source transfer result is not the witnessed regular file")
        descriptor = os.open(target, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0))
        with os.fdopen(descriptor, "rb") as handle:
            opened = os.fstat(handle.fileno())
            if (before.st_dev, before.st_ino) != (opened.st_dev, opened.st_ino):
                reject("coordination source transfer result changed before readback")
            data = handle.read(MAX_TRANSFER_BYTES + 1)
        if len(data) != result["result_bytes"] or hashlib.sha256(data).hexdigest() != result["result_sha256"]:
            reject("coordination source transfer result digest mismatch")
        return json.loads(data)
