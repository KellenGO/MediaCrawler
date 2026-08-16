# -*- coding: utf-8 -*-
# Copyright (c) 2025 relakkes@gmail.com
#
# This file is part of MediaCrawler project.
# Licensed under NON-COMMERCIAL LEARNING LICENSE 1.1

"""短内存聚合搜索结果缓存（Round 16 / 16.1）。

边界（严格）：
- key = 标准化关键词 + 平台 + limit + 账号代数；代数在账号同步/失效/清除/
  shutdown 时自增 → 缓存自动失效；
- TTL 默认 0（禁用）：UI 没有强制刷新入口，默认不缓存，避免用户看到陈旧
  结果；显式配置（MC_RESULTS_CACHE_TTL_SECONDS）时夹紧到 [60, 120] 秒；
- 最大容量 MAX_ENTRIES=200：get/set 时清理过期项；超容量按 LRU 淘汰
  （dict 插入序 = 最近使用序）；账号代数推进后旧代数条目在 set 时被清理，
  不永久留存；
- 只缓存平台终态 succeeded/empty（调用方负责只对这两种状态调用 set）；
- login_required / rate_limited / failed / timed_out / cancelled 绝不缓存；
- 不缓存半成品（只有平台完成后才写入）；不写 localStorage；
- 用户主动"重新搜索"（bypass_cache）跳过查/写；
- 全部在 API 进程内存，shutdown 由 search_job_manager.cleanup() 清空。
"""

from __future__ import annotations

import os
import time
from typing import Any, Dict, List, Optional, Tuple

from . import accounts as accounts_service

# TTL 秒数；0 = 禁用（默认）。环境变量显式开启时夹紧到 [60, 120]。
_CACHE_TTL_SECONDS: int = 0

# Round 16.1: 最大缓存条目数（平台粒度，总计）。
MAX_ENTRIES: int = 200

_cache: Dict[Tuple[Any, ...], Dict[str, Any]] = {}

_MIN_TTL = 60
_MAX_TTL = 120


def _parse_env_ttl() -> int:
    raw = os.environ.get("MC_RESULTS_CACHE_TTL_SECONDS", "")
    if not raw:
        return 0
    try:
        value = int(raw)
    except (TypeError, ValueError):
        return 0
    if value <= 0:
        return 0
    return max(_MIN_TTL, min(_MAX_TTL, value))


def _configure_ttl(seconds: int) -> None:
    global _CACHE_TTL_SECONDS
    _CACHE_TTL_SECONDS = max(0, int(seconds))


_configure_ttl(_parse_env_ttl())


def ttl_seconds() -> int:
    """当前 TTL（0 = 禁用）。测试用 monkeypatch 直接改。"""
    return _CACHE_TTL_SECONDS


def _key(keyword: str, platform: str, limit: int) -> Tuple[Any, ...]:
    return (
        keyword.strip().lower(),
        platform,
        int(limit),
        accounts_service.get_account_generation(platform),
    )


def _purge_expired(now: float) -> None:
    """get/set 时清理过期项（TTL 已过）。"""
    expired = [k for k, e in _cache.items()
               if now - e["ts"] > _CACHE_TTL_SECONDS]
    for k in expired:
        _cache.pop(k, None)


def _purge_stale_generation(platform: str) -> None:
    """账号代数推进后清理该平台旧代数条目（不可达，但不得永久留存）。"""
    current = accounts_service.get_account_generation(platform)
    stale = [k for k in _cache if k[1] == platform and k[3] != current]
    for k in stale:
        _cache.pop(k, None)


def _evict_if_full() -> None:
    """超容量按 LRU 淘汰（dict 插入序 = 最近使用序，队首最久未用）。"""
    while len(_cache) > MAX_ENTRIES:
        oldest = next(iter(_cache), None)
        if oldest is None:
            break
        _cache.pop(oldest, None)


def get(keyword: str, platform: str, limit: int) -> Optional[List[Dict[str, Any]]]:
    """命中返回结果 DTO 列表（副本）；未启用/过期/未命中返回 None。"""
    if _CACHE_TTL_SECONDS <= 0:
        return None
    now = time.monotonic()
    _purge_expired(now)
    key = _key(keyword, platform, limit)
    entry = _cache.get(key)
    if entry is None:
        return None
    # LRU：命中后移到队尾（重新插入）。
    _cache.pop(key, None)
    _cache[key] = entry
    return [dict(r) for r in entry["results"]]


def set(keyword: str, platform: str, limit: int,
        results: List[Any]) -> None:
    """写入缓存（调用方保证只对终态 succeeded/empty 调用）。"""
    if _CACHE_TTL_SECONDS <= 0:
        return
    now = time.monotonic()
    _purge_expired(now)
    _purge_stale_generation(platform)
    key = _key(keyword, platform, limit)
    payload = []
    for r in results or []:
        if hasattr(r, "model_dump"):
            payload.append(r.model_dump())
        elif isinstance(r, dict):
            payload.append(dict(r))
    # 已有同 key → 先移除再插入（保持 LRU 序）。
    _cache.pop(key, None)
    _cache[key] = {"results": payload, "ts": now}
    _evict_if_full()


def clear() -> None:
    """shutdown / 测试清理。"""
    _cache.clear()
