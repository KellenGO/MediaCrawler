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

from typing import Dict, List, Literal, Optional

from pydantic import BaseModel, Field, field_validator

from aggregate_search.models import (
    PLATFORM_SLUGS,
    OverallStatus,
    PlatformSlug,
    PlatformStatus,
    UnifiedSearchResult,
)

MAX_LIMIT_PER_PLATFORM = 20


class SearchJobRequestSchema(BaseModel):
    keyword: str = Field(..., min_length=1, max_length=200)
    platforms: List[PlatformSlug] = Field(
        default_factory=lambda: PLATFORM_SLUGS.copy(),
        min_length=1,
    )
    limit_per_platform: int = Field(default=10, ge=1, le=MAX_LIMIT_PER_PLATFORM)

    @field_validator("platforms")
    @classmethod
    def platforms_not_empty(cls, v: List[str]) -> List[str]:
        if not v:
            raise ValueError("At least one platform is required.")
        return v


class PlatformStatusInfo(BaseModel):
    status: PlatformStatus = "pending"
    result_count: int = 0
    error_summary: Optional[str] = None


class SearchJobResponse(BaseModel):
    job_id: str
    overall: OverallStatus
    keyword: str
    created_at: str
    completed_at: Optional[str] = None
    platforms: Dict[str, PlatformStatusInfo] = Field(default_factory=dict)
    results: List[UnifiedSearchResult] = Field(default_factory=list)
