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
_APP = (_ROOT / "App.tsx").read_text(encoding="utf-8")
_AUTOSYNC_HOOK = (_ROOT / "hooks" / "useAutoAccountSync.ts").read_text(encoding="utf-8")
_AUTOSYNC_COMPONENT = (_ROOT / "components" / "accounts" / "AccountAutoSync.tsx").read_text(encoding="utf-8")
_EXTENSION_SYNC = (_ROOT / "lib" / "extensionSync.ts").read_text(encoding="utf-8")
_ACCOUNT_GATE = (_ROOT / "lib" / "accountGate.ts").read_text(encoding="utf-8")


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
    """票据往返协议在 lib/extensionSync（账号页与自动同步共用一份实现）。"""
    assert "sync-ticket" in _EXTENSION_SYNC
    assert "sync-request" in _EXTENSION_SYNC
    assert "request_id" in _EXTENSION_SYNC
    assert "requestPlatformSync" in _ACCOUNTS


def test_accounts_extension_install_instructions_present():
    assert "chrome://extensions" in _ACCOUNTS
    assert "edge://extensions" in _ACCOUNTS
    assert "开发者模式" in _ACCOUNTS
    assert "browser_extension" in _ACCOUNTS


# ── Round 18: 未登录快速提示 + 打开程序即自动同步 ───────────────────────

def test_login_required_reason_is_surfaced():
    """login_required 也必须显示 error_summary（可操作原因），否则用户只看到
    "需要登录" 却不知道要去账号设置同步。"""
    assert 'info.error_summary || "需要登录"' in _STATUS_DISPLAY


def test_platform_status_exposes_full_status_text():
    """状态文案被截断时用 title 提供完整内容。"""
    assert "statusText" in _PLATFORM_STATUS
    assert "title={statusText}" in _PLATFORM_STATUS


def test_app_root_mounts_autosync():
    """自动同步必须挂在应用根部 —— 打开程序就同步，而不是进了账号页才同步。"""
    assert "AccountAutoSync" in _APP
    assert "<AccountAutoSync />" in _APP


def test_autosync_runs_on_open_and_on_resume():
    """触发时机：挂载（打开程序）以及页面回到前台（去浏览器登录完切回来）。"""
    assert "detectExtension" in _AUTOSYNC_HOOK
    assert "decideAutoSync" in _AUTOSYNC_HOOK
    assert "visibilitychange" in _AUTOSYNC_HOOK
    assert '"focus"' in _AUTOSYNC_HOOK


def test_extension_probe_retries_until_pong():
    """扩展探测必须重复 ping，不能只发一次。

    content script 以 document_idle 注入，可能晚于 React 挂载和第一次 ping；
    单次 ping 会石沉大海，把已安装的扩展误判成"未安装"，自动同步就永远不启动
    （用户实测：重启程序后没有任何同步动作）。
    """
    assert "EXTENSION_PROBE_INTERVAL_MS" in _EXTENSION_SYNC
    assert "setInterval" in _EXTENSION_SYNC
    assert "EXTENSION_PROBE_TOTAL_MS" in _EXTENSION_SYNC


def test_autosync_reprobes_extension_on_resume():
    """回到前台时若扩展尚未连接，必须重新探测（可能刚启用/重新加载扩展）。"""
    assert "detectExtension({ totalMs: EXTENSION_PROBE_TOTAL_MS })" in _AUTOSYNC_HOOK


def test_autosync_result_is_visible():
    """自动同步的结果必须留在页面上（不能只在运行中显示），否则用户会以为
    什么都没发生。"""
    assert "NOTE_VISIBLE_MS" in _AUTOSYNC_HOOK
    assert "!running && !note" in _AUTOSYNC_COMPONENT


def test_autosync_is_cooldown_bounded():
    """冷却与 guard 必须存在：不能因为账号轮询反复重启浏览器。"""
    assert "AUTO_SYNC_COOLDOWN_MS" in _AUTOSYNC_HOOK
    assert "createBulkSyncGuard" in _AUTOSYNC_HOOK
    # 首次尝试之后不再由账号轮询驱动
    assert "lastAttemptRef.current !== null" in _AUTOSYNC_HOOK


def test_autosync_stays_quiet_when_nothing_was_synced():
    """浏览器里没有可同步的会话时不打扰（否则每次打开程序都弹失败提示）。"""
    assert "shouldAnnounceAutoSync" in _AUTOSYNC_HOOK
    assert "shouldAnnounceAutoSync" in (
        _ROOT / "lib" / "accountBulkSync.ts").read_text(encoding="utf-8")


def test_accounts_page_no_longer_autosyncs():
    """账号页只保留手动一键同步；自动同步由根部负责，避免两处各跑一套队列。"""
    assert "decideAutoSync" not in _ACCOUNTS
    assert "runSyncQueue" in _ACCOUNTS


def test_search_waits_for_account_ops():
    """搜索提交前必须等账号操作结束，否则自动同步会把搜索顶成 409。"""
    assert "waitForAccountOpsIdle" in _HOOK
    assert "waitForAccountOpsIdle" in _ACCOUNT_GATE
    assert '"syncing"' in _ACCOUNT_GATE
    assert '"verifying"' in _ACCOUNT_GATE


def test_account_gate_fails_open():
    """探测不到账号状态时必须放行，绝不把用户的搜索卡住。"""
    assert "catch {" in _ACCOUNT_GATE
    assert "return true; // 读不到状态 → 放行" in _ACCOUNT_GATE


def test_accounts_bulk_progress_total_is_dynamic():
    """手动同步也可能只同步部分平台，进度分母不能用写死的 4。"""
    assert "/4`" not in _ACCOUNTS
    assert "${bulkCompleted}/${bulkTotal}" in _ACCOUNTS
