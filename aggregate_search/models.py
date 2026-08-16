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
Unified data models for aggregate cross-platform search.

These DTOs are used by the aggregate_search layer only. MediaCrawler core
and store layers continue to use their own native data structures.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, List, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator


# ── Platform & status enums ────────────────────────────────────────────

PlatformSlug = Literal["xhs", "douyin", "bilibili", "zhihu"]

PLATFORM_SLUGS: List[PlatformSlug] = ["xhs", "douyin", "bilibili", "zhihu"]

# Mapping from aggregate-search slug → MediaCrawler core slug.
# The core uses "dy" for Douyin and "bili" for Bilibili.
_AGG_TO_CORE: Dict[str, str] = {
    "xhs": "xhs",
    "douyin": "dy",
    "bilibili": "bili",
    "zhihu": "zhihu",
}

# Reverse mapping: core slug → aggregate slug.
_CORE_TO_AGG: Dict[str, str] = {v: k for k, v in _AGG_TO_CORE.items()}


def agg_to_core_platform(agg_slug: str) -> str:
    """Convert an aggregate-search platform slug to a MediaCrawler core slug.

    >>> agg_to_core_platform("douyin")
    'dy'
    >>> agg_to_core_platform("bilibili")
    'bili'
    >>> agg_to_core_platform("xhs")
    'xhs'
    """
    return _AGG_TO_CORE.get(agg_slug, agg_slug)


def core_to_agg_platform(core_slug: str) -> str:
    """Convert a MediaCrawler core slug back to an aggregate-search slug.

    >>> core_to_agg_platform("dy")
    'douyin'
    >>> core_to_agg_platform("bili")
    'bilibili'
    """
    return _CORE_TO_AGG.get(core_slug, core_slug)


def is_valid_platform(platform: str) -> bool:
    """Check if the given platform slug is valid for aggregate search."""
    return platform in _AGG_TO_CORE

PlatformStatus = Literal[
    "pending",
    "running",
    "succeeded",
    "empty",
    "login_required",
    "rate_limited",
    "timed_out",
    "failed",
    "cancelled",
]

OverallStatus = Literal["running", "completed", "partial", "failed", "cancelling", "cancelled"]


# ── Unified search result ──────────────────────────────────────────────

class UnifiedSearchResult(BaseModel):
    """Normalized result from any supported platform."""

    platform: PlatformSlug
    content_id: str
    content_type: str = "note"  # "note", "video", "answer", "article", "zvideo"
    title: str
    author: Optional[str] = None  # public display name only
    url: str
    published_at: Optional[str] = None  # ISO 8601
    cover_url: Optional[str] = None
    metrics: Dict[str, int] = Field(default_factory=dict)
    rank: int = 0  # original platform rank (0-based)

    # Allow extra fields from adapters for internal use
    model_config = {"extra": "ignore"}


# ── Platform-specific search results (aggregate layer internal) ────────

class PlatformResult(BaseModel):
    """Container for one platform's search outcome."""

    platform: PlatformSlug
    status: PlatformStatus
    results: List[UnifiedSearchResult] = Field(default_factory=list)
    error_summary: Optional[str] = None  # safe, no stack traces or secrets


# ── Job-level models ───────────────────────────────────────────────────

class SearchJobRequest(BaseModel):
    keyword: str = Field(..., min_length=1, description="Search keyword")
    platforms: List[PlatformSlug] = Field(
        default_factory=lambda: PLATFORM_SLUGS.copy(),
        description="Platforms to search",
    )
    limit_per_platform: int = Field(default=10, ge=1, le=20)
    # Round 15: 按平台独立数量。优先于 limit_per_platform；缺失平台回退
    # limit_per_platform（默认 10）。值必须是 1–20 的严格整数。
    platform_limits: Optional[Dict[str, Any]] = Field(default=None)

    @field_validator("platform_limits")
    @classmethod
    def platform_limits_valid(cls, v: Optional[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
        if v is None:
            return v
        if not isinstance(v, dict):
            raise ValueError("platform_limits 必须是对象")
        for key, val in v.items():
            if key not in PLATFORM_SLUGS:
                raise ValueError(f"未知平台: {key}")
            if isinstance(val, bool) or not isinstance(val, int):
                raise ValueError(f"{key} 的数量必须是 1–20 的整数")
            if val < 1 or val > 20:
                raise ValueError(f"{key} 的数量必须在 1–20 之间")
        return v


class SearchJobStatus(BaseModel):
    job_id: str
    overall: OverallStatus
    keyword: str
    created_at: str
    completed_at: Optional[str] = None
    platforms: Dict[str, PlatformResult] = Field(default_factory=dict)


# ── Worker protocol models ─────────────────────────────────────────────

class WorkerRequest(BaseModel):
    """Request sent from parent process to worker via stdin."""

    # Round 16.2: 校验错误不回显输入值（model_validate 路径）—— 否则
    # ValidationError 会打印 session_snapshot 的原始输入（可能含 Cookie）。
    model_config = ConfigDict(hide_input_in_errors=True)

    job_id: str
    mode: Literal["search", "login"]
    platform: PlatformSlug
    keyword: str = ""
    limit: int = 10
    # Round 16: 内存会话快照（cookie name→value，仅经 stdin 传输，绝不
    # 进 argv/env/日志；后端重启后为 None，worker 自动回退浏览器路径）。
    # Round 16.1/16.2: repr=False —— 默认 repr 省略该字段；安全 __repr__/
    # __str__ 显式用 <redacted> 占位。model_dump_json 仍保留（唯一 stdin
    # 传输序列化）。__init__ 预检把类型错误变成普通 ValueError，避免
    # pydantic ValidationError 回显 input_value（其中可能含 Cookie）。
    session_snapshot: Optional[Dict[str, str]] = Field(default=None, repr=False)
    # Round 16: 允许无浏览器快速路径（worker 内部仍会安全回退）。
    fast_path: bool = False
    # Round 16: 用户主动重新搜索时绕过结果缓存（默认 False）。
    bypass_cache: bool = False

    def __init__(self, **data):
        snap = data.get("session_snapshot")
        if snap is not None and not isinstance(snap, dict):
            # 不回显输入值（可能含 Cookie/快照内容）。
            raise ValueError("session_snapshot must be a dict or None")
        if isinstance(snap, dict):
            for k, v in snap.items():
                if not isinstance(k, str) or not isinstance(v, str):
                    raise ValueError("session_snapshot must map str to str")
        super().__init__(**data)

    def __repr__(self) -> str:
        """安全 repr：会话快照用 <redacted> 占位，绝不打印 Cookie 值。"""
        return (
            f"WorkerRequest(job_id={self.job_id!r}, mode={self.mode!r}, "
            f"platform={self.platform!r}, keyword={self.keyword!r}, "
            f"limit={self.limit!r}, session_snapshot=<redacted>, "
            f"fast_path={self.fast_path!r}, bypass_cache={self.bypass_cache!r})"
        )

    def __str__(self) -> str:
        """str 与 repr 一致（%s 日志路径同样安全）。"""
        return self.__repr__()


class WorkerEvent(BaseModel):
    """Event emitted by worker on stdout (NDJSON with prefix)."""

    event: Literal["status", "result", "done", "error", "metrics"]
    job_id: str
    platform: PlatformSlug
    data: Any = None


# ── De-duplication helpers ─────────────────────────────────────────────

def make_dedup_key(platform: str, content_id: str) -> str:
    """Composite key for de-duplication across pages or platforms."""
    return f"{platform}:{content_id}"


# ── Interleaved merge ──────────────────────────────────────────────────

def interleave_results(
    platform_results: Dict[str, List[UnifiedSearchResult]],
    platform_order: Optional[List[str]] = None,
) -> List[UnifiedSearchResult]:
    """Round-robin interleave results from multiple platforms.

    Picks one result from each platform in order until all exhausted.
    Maintains each platform's internal rank order.
    """
    if platform_order is None:
        platform_order = PLATFORM_SLUGS

    queues: Dict[str, List[UnifiedSearchResult]] = {
        p: list(platform_results.get(p, [])) for p in platform_order
    }

    merged: List[UnifiedSearchResult] = []
    seen: set = set()
    changed = True
    while changed:
        changed = False
        for p in platform_order:
            while queues.get(p):
                item = queues[p].pop(0)
                key = make_dedup_key(item.platform, item.content_id)
                if key not in seen:
                    seen.add(key)
                    merged.append(item)
                    changed = True
                    break
    return merged


# ── Time parsing ───────────────────────────────────────────────────────

def _parse_timestamp(value: Any) -> Optional[str]:
    """Convert a platform timestamp (int seconds, int ms, or ISO string)
    to an ISO 8601 string, or return None."""
    if value is None:
        return None
    if isinstance(value, str):
        # Try parsing as ISO
        try:
            return datetime.fromisoformat(value.replace("Z", "+00:00")).isoformat()
        except (ValueError, TypeError):
            pass
        # Try parsing as int
        try:
            value = int(value)
        except (ValueError, TypeError):
            return None
    if isinstance(value, (int, float)):
        if value <= 0:
            return None
        # Heuristic: if < 10000000000 assume seconds; else ms
        if value < 10_000_000_000:
            ts = value
        else:
            ts = value / 1000.0
        try:
            return datetime.fromtimestamp(ts, tz=None).isoformat()
        except (OSError, ValueError, OverflowError):
            return None
    return None
