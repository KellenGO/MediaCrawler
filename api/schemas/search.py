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
Pydantic schemas for the aggregate search API.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field, field_validator

from aggregate_search.models import (
    PLATFORM_SLUGS,
    OverallStatus,
    PlatformSlug,
    PlatformStatus,
    UnifiedSearchResult,
)

MAX_LIMIT_PER_PLATFORM = 20
MIN_LIMIT_PER_PLATFORM = 1


class SearchJobRequestSchema(BaseModel):
    keyword: str = Field(..., min_length=1, max_length=200)
    platforms: List[PlatformSlug] = Field(
        default_factory=lambda: PLATFORM_SLUGS.copy(),
        min_length=1,
    )
    limit_per_platform: int = Field(default=10, ge=1, le=MAX_LIMIT_PER_PLATFORM)
    # Round 15: 按平台独立数量。声明为 Any 并在 validator 中做严格整数校验，
    # 避免 pydantic lax 模式把 "5"/true 强转成 int 而绕过上限校验。
    # 优先于 limit_per_platform；缺失平台回退 limit_per_platform（默认 10）。
    platform_limits: Optional[Dict[str, Any]] = Field(default=None)
    # Round 16: 用户主动"重新搜索"时绕过内存结果缓存（默认 False）。
    bypass_cache: bool = Field(default=False)

    @field_validator("platforms")
    @classmethod
    def platforms_not_empty(cls, v: List[str]) -> List[str]:
        if not v:
            raise ValueError("At least one platform is required.")
        return v

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
                raise ValueError(f"{key} 的数量必须是 1–{MAX_LIMIT_PER_PLATFORM} 的整数")
            if val < MIN_LIMIT_PER_PLATFORM or val > MAX_LIMIT_PER_PLATFORM:
                raise ValueError(f"{key} 的数量必须在 1–{MAX_LIMIT_PER_PLATFORM} 之间")
        return v


class PlatformTimingInfo(BaseModel):
    """平台搜索耗时指标（毫秒，perf_counter 单调时钟；无数据为 None）。

    定义（Round 16.1 统一语义，全部为累计耗时，互不混用）：
    - spawn_ms            parent 创建/取得 worker 的耗时（复用既有进程≈0）；
    - worker_ready_ms     进程启动→模块加载完成的固定常量（不随空闲增长）；
    - reused_worker       本次搜索是否复用了既有常驻 worker 进程；
    - browser_launch_ms   从请求开始到浏览器 context 启动完成（累计）；
    - navigation_ms       从请求开始到初始页面导航完成（累计）；
    - preflight_ms        从请求开始到登录预检完成（累计）；
    - search_api_ms       从请求开始到首次搜索 API 响应（累计）；
    - first_result_ms     从 job 开始到首条合法结果；
    - total_ms            平台进入终态的总耗时；
    - fast_path_used      是否命中无浏览器快速路径；
    - fallback_reason     回退原因安全枚举（无响应体）。

    只包含耗时数字与安全枚举，绝不包含 Cookie/URL/响应体等敏感信息。
    """

    spawn_ms: Optional[int] = None            # worker 子进程创建/取得耗时
    worker_ready_ms: Optional[int] = None     # 进程启动→就绪（固定常量）
    reused_worker: Optional[bool] = None      # 本次是否复用常驻 worker
    browser_launch_ms: Optional[int] = None   # 浏览器 context 启动（累计）
    navigation_ms: Optional[int] = None       # 初始页面导航（累计）
    preflight_ms: Optional[int] = None        # 登录预检（累计）
    search_api_ms: Optional[int] = None       # 首次搜索 API 响应（累计）
    first_result_ms: Optional[int] = None     # 从 job 开始到首条合法结果
    total_ms: Optional[int] = None            # 平台进入终态的总耗时
    fast_path_used: Optional[bool] = None     # 是否命中无浏览器快速路径
    fallback_reason: Optional[str] = None     # 回退原因安全枚举（无响应体）


class PlatformStatusInfo(BaseModel):
    status: PlatformStatus = "pending"
    result_count: int = 0
    error_summary: Optional[str] = None
    timings: Optional[PlatformTimingInfo] = None


class SearchJobResponse(BaseModel):
    job_id: str
    overall: OverallStatus
    keyword: str
    created_at: str
    completed_at: Optional[str] = None
    total_ms: Optional[int] = None  # job 级总耗时（毫秒）
    platforms: Dict[str, PlatformStatusInfo] = Field(default_factory=dict)
    results: List[UnifiedSearchResult] = Field(default_factory=list)
