# -*- coding: utf-8 -*-
# Copyright (c) 2025 relakkes@gmail.com
#
# This file is part of MediaCrawler project.
# Repository: https://github.com/NanmiCoder/MediaCrawler
# GitHub: https://github.com/NanmiCoder
# Licensed under NON-COMMERCIAL LEARNING LICENSE 1.1
#
# 声明：本代码仅供学习和研究目的使用。使用者应遵守以下原则：
# 1. 不得用于任何商业用途。
# 2. 使用时应遵守目标平台的使用条款和robots.txt规则。
# 3. 不得进行大规模爬取或对平台造成运营干扰。
# 4. 应合理控制请求频率，避免给目标平台带来不必要的负担。
# 5. 不得用于任何非法或不当的用途。
#
# 详细许可条款请参阅项目根目录下的LICENSE文件。
# 使用本代码即表示您同意遵守上述原则和LICENSE中的所有条款。

"""
Worker communication protocol via stdin / stdout NDJSON.

All I/O is done in UTF-8 binary mode to avoid Windows code-page issues.
"""

from __future__ import annotations

import json
import sys
from typing import Any, Dict, Optional

from .models import WorkerEvent, WorkerRequest

# ── Protocol constants ──────────────────────────────────────────────────

EVENT_PREFIX = "MC_AGG_EVENT"
EVENT_SEPARATOR = "\t"
_ENCODING = "utf-8"


# ── Secret sanitization ─────────────────────────────────────────────────

def _is_secret_key(key: str) -> bool:
    """Check whether a dict key names a secret field.

    Matches exact canonical forms AND suffix-based patterns:
    anything ending in _token, _secret, _cookie, _password, _key,
    or the hyphenated equivalents.
    """
    c = key.lower().replace("_", "").replace("-", "")
    # Exact canonical matches
    if c in frozenset({
        "cookie", "cookies",
        "authorization", "authorisation",
        "token", "accesstoken", "refreshtoken", "apitoken",
        "password", "passwd", "secret",
        "session", "sessionid",
        "xxsrftoken", "xcsrftoken", "setcookie",
        "xsectoken",
    }):
        return True
    # Suffix-based: any key ending with token/secret/cookie/password/key
    for suffix in ("token", "secret", "cookie", "password", "key"):
        if c.endswith(suffix):
            return True
    return False


def _sanitize(obj: any, depth: int = 10) -> any:
    """Recursively remove secret keys from nested dicts/lists.

    At depth 0, entire subtree is replaced with [REDACTED] rather than
    returned unexamined.
    """
    if depth <= 0:
        return "[REDACTED]"
    if isinstance(obj, dict):
        return {
            k: ("[REDACTED]" if _is_secret_key(k) else _sanitize(v, depth - 1))
            for k, v in obj.items()
        }
    if isinstance(obj, list):
        return [_sanitize(v, depth - 1) for v in obj]
    return obj


# ── Writing (worker side) ───────────────────────────────────────────────

def emit_event(event: WorkerEvent) -> None:
    """Emit a single protocol event on stdout in UTF-8.

    All nested dict values are sanitized to remove secrets before emission.
    """
    event.data = _sanitize(event.data)
    payload = event.model_dump_json(exclude_none=True)
    line = f"{EVENT_PREFIX}{EVENT_SEPARATOR}{payload}\n"
    sys.stdout.buffer.write(line.encode(_ENCODING))
    sys.stdout.buffer.flush()


def emit_status(
    job_id: str,
    platform: str,
    status: str,
    extra: Optional[Dict[str, Any]] = None,
) -> None:
    emit_event(
        WorkerEvent(
            event="status",
            job_id=job_id,
            platform=platform,
            data={"status": status, **(extra or {})},
        )
    )


def emit_result(job_id: str, platform: str, result: Any) -> None:
    emit_event(
        WorkerEvent(event="result", job_id=job_id, platform=platform, data=result)
    )


def emit_done(job_id: str, platform: str) -> None:
    emit_event(
        WorkerEvent(event="done", job_id=job_id, platform=platform, data=None)
    )


def emit_error(
    job_id: str,
    platform: str,
    error_type: str,
    message: str,
) -> None:
    emit_event(
        WorkerEvent(
            event="error",
            job_id=job_id,
            platform=platform,
            data={"type": error_type, "message": message},
        )
    )


# ── Reading (parent side) ───────────────────────────────────────────────

def parse_event_line(line: str) -> Optional[WorkerEvent]:
    """Attempt to parse a protocol event from a line of text."""
    if not line.startswith(EVENT_PREFIX + EVENT_SEPARATOR):
        return None

    try:
        json_str = line[len(EVENT_PREFIX) + len(EVENT_SEPARATOR):].strip()
        if not json_str:
            return None
        data = json.loads(json_str)
        return WorkerEvent(**data)
    except (json.JSONDecodeError, Exception):
        return None


# ── Reading request (worker side) ───────────────────────────────────────

def read_request() -> WorkerRequest:
    """Read a single JSON request line from stdin in UTF-8 binary mode.

    Blocks until data is available. Raises on parse error.
    """
    raw = sys.stdin.buffer.readline()
    if not raw:
        raise EOFError("Worker stdin closed before receiving a request")
    line = raw.decode(_ENCODING, errors="replace").strip()
    data = json.loads(line)
    return WorkerRequest(**data)
