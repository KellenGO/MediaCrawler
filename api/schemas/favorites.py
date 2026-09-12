from __future__ import annotations

from datetime import datetime
from typing import Dict, List, Optional

from pydantic import BaseModel, Field, field_validator

from aggregate_search.models import PLATFORM_SLUGS, PlatformSlug, PlatformStatus, UnifiedSearchResult


class FavoritesJobRequest(BaseModel):
    platforms: List[PlatformSlug] = Field(default_factory=lambda: PLATFORM_SLUGS.copy(), min_length=1)
    limit_per_platform: int = Field(default=20, ge=1, le=40)

    @field_validator("platforms")
    @classmethod
    def unique_platforms(cls, value: List[PlatformSlug]) -> List[PlatformSlug]:
        if len(value) != len(set(value)):
            raise ValueError("平台不能重复")
        return value


class FavoritePlatformInfo(BaseModel):
    status: PlatformStatus = "pending"
    result_count: int = 0
    error_summary: Optional[str] = None


class FavoritesJobResponse(BaseModel):
    job_id: str
    overall: str
    created_at: datetime
    completed_at: Optional[datetime] = None
    platforms: Dict[str, FavoritePlatformInfo]
    results: List[UnifiedSearchResult]
