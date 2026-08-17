# -*- coding: utf-8 -*-
# Copyright (c) 2025 relakkes@gmail.com
#
# This file is part of MediaCrawler project.
# Licensed under NON-COMMERCIAL LEARNING LICENSE 1.1

"""WebUI contract tests.

The webui has no JS test framework (no vitest — adding one would be a new
dependency), so these tests verify the PRODUCTION source files themselves:
exact UI strings, the login_required → accounts-page navigation, and the
existence/wiring of the exported pure functions that encode the
current-job recovery race rules. They read the real files — nothing is
copied or re-implemented here.
"""

import re
from pathlib import Path

import pytest

_ROOT = Path(__file__).parent.parent / "webui" / "src"

_PLATFORM_STATUS = (_ROOT / "components" / "search" / "PlatformStatus.tsx").read_text(encoding="utf-8")
_STATUS_DISPLAY = (_ROOT / "lib" / "statusDisplay.ts").read_text(encoding="utf-8")
_TYPES = (_ROOT / "types" / "search.ts").read_text(encoding="utf-8")
_SEARCH_PAGE = (_ROOT / "components" / "search" / "SearchPage.tsx").read_text(encoding="utf-8")
_HOOK = (_ROOT / "hooks" / "useAggregateSearch.ts").read_text(encoding="utf-8")
_EXPERIENCE_HOOK = (_ROOT / "hooks" / "useSearchExperience.ts").read_text(encoding="utf-8")
_ACCOUNTS = (_ROOT / "components" / "accounts" / "AccountsPage.tsx").read_text(encoding="utf-8")
_RESULT_CARD = (_ROOT / "components" / "search" / "ResultCard.tsx").read_text(encoding="utf-8")


# ── cancelling / cancelled UI text ──────────────────────────────────────

def test_overall_badge_texts():
    """cancelling → 正在取消; cancelled → 搜索已取消; failed → ✗ 搜索失败."""
    assert "正在取消" in _PLATFORM_STATUS
    assert "搜索已取消" in _PLATFORM_STATUS
    assert "✗ 搜索失败" in _PLATFORM_STATUS


def test_platform_status_has_cancelled_case():
    """cancelled 分支与 STATUS_LABELS 回退随 statusLine 迁至 statusDisplay.ts。"""
    assert '"cancelled"' in _STATUS_DISPLAY
    assert 'STATUS_LABELS[status]' in _STATUS_DISPLAY
    assert "statusLine" in _PLATFORM_STATUS  # 组件仍接线生产 statusLine


def test_status_label_cancelled():
    assert 'cancelled: "已取消"' in _TYPES


def test_result_card_renders_optional_snippet():
    assert "result.snippet" in _RESULT_CARD
    assert "line-clamp-3" in _RESULT_CARD


def test_search_request_cache_bypass_is_wired():
    assert "bypass_cache?: boolean" in _TYPES
    assert "bypass_cache: bypassCache" in _HOOK
    assert "bypassCache = false" in _HOOK
    assert "handleRefresh" in _EXPERIENCE_HOOK
    assert "current.keyword" in _EXPERIENCE_HOOK


def test_platform_status_union_includes_cancelled():
    assert '"cancelled"' in _TYPES


# ── login_required → 账号设置 (no aux login from search page) ───────────

def test_search_page_navigates_to_accounts():
    assert "前往账号设置" in _SEARCH_PAGE
    assert "onNavigateAccounts" in _SEARCH_PAGE


def test_search_page_no_longer_starts_login():
    """The search page must not start the aux login itself."""
    assert "handleLogin" not in _SEARCH_PAGE
    assert "useLogin" not in _SEARCH_PAGE


# ── current-job recovery race (pure functions exist & are wired) ────────

def test_race_pure_functions_exported():
    assert "export function shouldApplyRecoveredJob" in _HOOK
    assert "export function shouldClearJobOn404" in _HOOK


def test_race_get_current_job_accepts_abort_signal():
    """getCurrentJob must take an AbortSignal and forward it to axios."""
    assert "signal" in _HOOK
    assert "getCurrentJob" in _HOOK


def test_race_generation_guards_are_wired():
    """startSearch/reset must bump the generation so late responses are
    discarded."""
    assert "generationRef" in _HOOK


def test_race_404_clears_only_matching_job():
    assert "shouldClearJobOn404" in _HOOK


# ── accounts page: security-conscious interactions ──────────────────────

def test_accounts_delete_has_double_confirm():
    assert _ACCOUNTS.count("window.confirm") >= 2


def test_accounts_opens_official_pages_in_current_browser():
    """Login pages open via window.open in the current browser — no
    Playwright import, no backend call for opening login pages."""
    assert "window.open" in _ACCOUNTS
    import_lines = [ln for ln in _ACCOUNTS.splitlines()
                    if ln.strip().startswith("import")]
    for word in ("playwright", "launch_persistent_context"):
        assert word not in "\n".join(import_lines)


def test_accounts_sync_uses_ticket_flow():
    assert "sync-ticket" in _ACCOUNTS
    assert "sync-request" in _ACCOUNTS
    assert "request_id" in _ACCOUNTS


def test_accounts_extension_install_instructions_present():
    assert "chrome://extensions" in _ACCOUNTS
    assert "edge://extensions" in _ACCOUNTS
    assert "开发者模式" in _ACCOUNTS
    assert "browser_extension" in _ACCOUNTS
