# -*- coding: utf-8 -*-
# Copyright (c) 2025 relakkes@gmail.com
#
# This file is part of MediaCrawler project.
# Licensed under NON-COMMERCIAL LEARNING LICENSE 1.1

"""搜索前登录预检测试（Round 18）。

背景：未登录时发起搜索，浏览器路径要先启动浏览器 + 导航，十几秒后才在
``pong()`` 处失败并回报"需要登录"。修复是在 spawn worker 之前做一次完全
本地的毫秒级判定。

关键点（也是本文件主要防回归的地方）：Playwright 一旦启动就会创建 profile
目录，所以"有没有 profile 目录"几乎恒为真，不能作为判据；真正的判据是
profile 的 cookie 库里有没有**未过期**的登录标记 cookie。

所有测试都指向临时目录，绝不触碰真实 ``browser_data``。
"""

import os
import sqlite3
import sys
import time
from pathlib import Path

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from api.services import accounts as acc
from api.services.accounts import (
    LOGIN_MARKER_NAMES,
    _live_login_marker_in_profile,
    search_login_block,
)

_CHROMIUM_EPOCH_OFFSET_SECONDS = 11644473600
_YEAR_US = 365 * 24 * 3600 * 1_000_000


@pytest.fixture(autouse=True)
def _clean_account_state():
    """本文件会用各种过期/未登录状态写账号服务，用例之间必须互不影响。"""
    for platform in acc.PLATFORM_PROFILE_DIRS:
        acc._platform_state.pop(platform, None)
        acc._session_snapshots.pop(platform, None)
    yield
    for platform in acc.PLATFORM_PROFILE_DIRS:
        acc._platform_state.pop(platform, None)
        acc._session_snapshots.pop(platform, None)


def _now_chromium() -> int:
    return int((time.time() + _CHROMIUM_EPOCH_OFFSET_SECONDS) * 1_000_000)


def _isolate(monkeypatch, tmp_path) -> Path:
    """把 profile 根目录指向临时目录，并清掉内存状态/会话快照。"""
    monkeypatch.setattr(acc, "BROWSER_DATA_DIR", tmp_path)
    monkeypatch.setattr(
        acc, "profile_dir_for",
        lambda p: tmp_path / acc.PLATFORM_PROFILE_DIRS[p])
    for platform in acc.PLATFORM_PROFILE_DIRS:
        acc._platform_state.pop(platform, None)
        acc._session_snapshots.pop(platform, None)
    return tmp_path


def _write_cookies_db(platform: str, rows, *, rel: str = "Default/Network/Cookies",
                      root: Path | None = None) -> Path:
    """在临时 profile 里建一个真实的 Chromium 风格 Cookies 库。

    rows: (name, host_key, expires_utc) 三元组序列。
    """
    base = root if root is not None else acc.BROWSER_DATA_DIR
    db_path = base / acc.PLATFORM_PROFILE_DIRS[platform] / rel
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db_path)
    try:
        conn.execute(
            "CREATE TABLE cookies (name TEXT, host_key TEXT, expires_utc INTEGER)")
        conn.executemany("INSERT INTO cookies VALUES (?, ?, ?)", rows)
        conn.commit()
    finally:
        conn.close()
    return db_path


# ── _live_login_marker_in_profile：核心判据 ─────────────────────────────

def test_live_marker_present_is_detected(monkeypatch, tmp_path):
    """未过期的 web_session → profile 里有活登录标记。"""
    _isolate(monkeypatch, tmp_path)
    _write_cookies_db("xhs", [("web_session", ".xiaohongshu.com", _now_chromium() + _YEAR_US)])
    assert _live_login_marker_in_profile("xhs") is True


def test_expired_marker_is_not_live(monkeypatch, tmp_path):
    """过期时间已过的 web_session 不算登录 —— 这正是"登录已失效"。"""
    _isolate(monkeypatch, tmp_path)
    _write_cookies_db("xhs", [("web_session", ".xiaohongshu.com", _now_chromium() - _YEAR_US)])
    assert _live_login_marker_in_profile("xhs") is False


def test_session_cookie_expires_utc_zero_counts_as_live(monkeypatch, tmp_path):
    """expires_utc=0 是会话 cookie，只要浏览器还持有就仍有效 → 视为活。"""
    _isolate(monkeypatch, tmp_path)
    _write_cookies_db("bilibili", [("SESSDATA", ".bilibili.com", 0)])
    assert _live_login_marker_in_profile("bilibili") is True


def test_marker_for_other_domain_is_ignored(monkeypatch, tmp_path):
    """同名 cookie 但 host 不属于该平台 → 不能当成本平台登录。"""
    _isolate(monkeypatch, tmp_path)
    _write_cookies_db("zhihu", [("z_c0", ".example.com", _now_chromium() + _YEAR_US)])
    assert _live_login_marker_in_profile("zhihu") is False


def test_non_marker_cookie_is_not_login(monkeypatch, tmp_path):
    """有 cookie 但没有登录标记（如仅有 a1/webId）→ 未登录。"""
    _isolate(monkeypatch, tmp_path)
    _write_cookies_db("xhs", [
        ("a1", ".xiaohongshu.com", _now_chromium() + _YEAR_US),
        ("webId", ".xiaohongshu.com", _now_chromium() + _YEAR_US),
    ])
    assert _live_login_marker_in_profile("xhs") is False


def test_missing_cookie_db_is_not_login(monkeypatch, tmp_path):
    """profile 目录存在但没有任何 cookie 库 → 未登录。"""
    _isolate(monkeypatch, tmp_path)
    acc.profile_dir_for("xhs").mkdir(parents=True)
    assert _live_login_marker_in_profile("xhs") is False


def test_legacy_cookie_db_location_is_supported(monkeypatch, tmp_path):
    """旧版 Chromium 把 Cookies 放在 Default/ 下，也要能识别。"""
    _isolate(monkeypatch, tmp_path)
    _write_cookies_db("zhihu", [("z_c0", ".zhihu.com", _now_chromium() + _YEAR_US)],
                      rel="Default/Cookies")
    assert _live_login_marker_in_profile("zhihu") is True


def test_corrupt_db_fails_open(monkeypatch, tmp_path):
    """库文件存在但损坏 → 失败开放（放行），绝不因读不了就把搜索拦掉。"""
    _isolate(monkeypatch, tmp_path)
    db_path = acc.profile_dir_for("xhs") / "Default" / "Network" / "Cookies"
    db_path.parent.mkdir(parents=True, exist_ok=True)
    db_path.write_bytes(b"this is not a sqlite database")
    assert _live_login_marker_in_profile("xhs") is True


def test_db_without_cookies_table_fails_open(monkeypatch, tmp_path):
    """表结构变化（没有 cookies 表）→ 同样失败开放。"""
    _isolate(monkeypatch, tmp_path)
    db_path = acc.profile_dir_for("xhs") / "Default" / "Network" / "Cookies"
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db_path)
    conn.execute("CREATE TABLE unrelated (x INTEGER)")
    conn.commit()
    conn.close()
    assert _live_login_marker_in_profile("xhs") is True


# ── search_login_block：三种必然失败的拦截 ──────────────────────────────

def test_block_when_profile_has_no_live_marker(monkeypatch, tmp_path):
    """核心场景：profile 目录存在（Playwright 建的）但没有活登录标记。

    修复前这里返回 None（放行）→ 用户白等十几秒；修复后必须立即拦截。
    """
    _isolate(monkeypatch, tmp_path)
    acc.profile_dir_for("xhs").mkdir(parents=True)
    block = search_login_block("xhs")
    assert block is not None
    assert "小红书" in block
    assert "账号设置" in block


def test_allow_when_profile_has_live_marker(monkeypatch, tmp_path):
    """profile 里有活登录标记 → 放行（浏览器路径可能成功）。"""
    _isolate(monkeypatch, tmp_path)
    _write_cookies_db("xhs", [("web_session", ".xiaohongshu.com", _now_chromium() + _YEAR_US)])
    assert search_login_block("xhs") is None


def test_allow_when_session_snapshot_exists(monkeypatch, tmp_path):
    """有内存会话快照 → 放行，且完全不读 profile 文件。"""
    _isolate(monkeypatch, tmp_path)
    acc._session_snapshots["bilibili"] = {"SESSDATA": "snapshot-value"}
    try:
        assert search_login_block("bilibili") is None
    finally:
        acc._session_snapshots.pop("bilibili", None)


def test_block_when_status_expired(monkeypatch, tmp_path):
    """账号状态已判定失效 → 即使 profile 里有活 cookie 也拦（状态是事实来源）。"""
    _isolate(monkeypatch, tmp_path)
    _write_cookies_db("bilibili", [("SESSDATA", ".bilibili.com", _now_chromium() + _YEAR_US)])
    acc._set_state("bilibili", status="expired", verified=False)
    assert search_login_block("bilibili") is not None


def test_block_when_status_disconnected(monkeypatch, tmp_path):
    _isolate(monkeypatch, tmp_path)
    acc._set_state("zhihu", status="disconnected", verified=False)
    assert search_login_block("zhihu") is not None


def test_block_when_no_profile_at_all(monkeypatch, tmp_path):
    """从未同步过（无快照、无 profile）→ 拦截。"""
    _isolate(monkeypatch, tmp_path)
    assert search_login_block("zhihu") is not None


def test_douyin_is_never_blocked(monkeypatch, tmp_path):
    """抖音可以匿名公开搜索，绝不参与预检（否则会拦掉本来能用的搜索）。"""
    _isolate(monkeypatch, tmp_path)
    assert search_login_block("douyin") is None


@pytest.mark.parametrize("platform", ["xhs", "bilibili", "zhihu"])
def test_douyin_excluded_from_needs_session(platform):
    assert platform in acc.SEARCH_NEEDS_SESSION
    assert "douyin" not in acc.SEARCH_NEEDS_SESSION


def test_block_message_contains_no_secrets(monkeypatch, tmp_path):
    """拦截文案必须只含平台名 + 固定指引，不含任何路径/Cookie。"""
    _isolate(monkeypatch, tmp_path)
    acc.profile_dir_for("xhs").mkdir(parents=True)
    block = search_login_block("xhs") or ""
    assert str(tmp_path) not in block
    assert "Cookie" not in block
    assert "web_session" not in block


def test_marker_names_match_pong_requirements():
    """预检使用的标记正是各平台 pong() 判定登录所依赖的会话 cookie。"""
    assert acc._SEARCH_LOGIN_MARKERS["xhs"] == ("web_session",)
    assert acc._SEARCH_LOGIN_MARKERS["bilibili"] == ("SESSDATA",)
    assert acc._SEARCH_LOGIN_MARKERS["zhihu"] == ("z_c0",)


def test_zhihu_d_c0_alone_is_not_login(monkeypatch, tmp_path):
    """知乎只有 d_c0（访问官网即生成）不算登录 —— pong 仍会返回 False。

    诊断白名单 LOGIN_MARKER_NAMES 含 d_c0，若拿它当预检判据就会漏判，
    退回"启动浏览器白等十几秒"的老行为。
    """
    _isolate(monkeypatch, tmp_path)
    _write_cookies_db("zhihu", [("d_c0", ".zhihu.com", _now_chromium() + _YEAR_US)])
    assert acc._live_login_marker_in_profile("zhihu") is False
    assert search_login_block("zhihu") is not None


def test_bilibili_dedeuserid_alone_is_not_login(monkeypatch, tmp_path):
    """B站只有 DedeUserID（辅助 cookie）不算登录，SESSDATA 才是会话。"""
    _isolate(monkeypatch, tmp_path)
    _write_cookies_db(
        "bilibili", [("DedeUserID", ".bilibili.com", _now_chromium() + _YEAR_US)])
    assert acc._live_login_marker_in_profile("bilibili") is False
    assert search_login_block("bilibili") is not None


def test_diagnostic_whitelist_is_not_reused_for_precheck():
    """预检用的标记集必须比诊断白名单更严格（防止有人又合并两者）。"""
    for platform, markers in acc._SEARCH_LOGIN_MARKERS.items():
        assert set(markers).issubset(set(LOGIN_MARKER_NAMES[platform]))
        assert "d_c0" not in markers
        assert "DedeUserID" not in markers


# ── 接入 SearchJobManager：预检命中时绝不 spawn worker ──────────────────

@pytest.mark.asyncio
async def test_manager_reports_login_required_without_spawning_worker(monkeypatch, tmp_path):
    """未登录时搜索：平台立即变 login_required，且不启动任何 worker。

    这是本次修复的核心断言 —— "不再花十几秒启动浏览器才报未登录"等价于
    "预检命中时 _run_worker 一次都不会被调用"。
    """
    import uuid

    import api.services.search_job_manager as sjm
    from api.schemas.search import SearchJobRequestSchema
    from api.services.search_job_manager import SearchJobManager

    _isolate(monkeypatch, tmp_path)
    # conftest 默认把预检设为放行（让伪造 worker 的既有用例与 CI 一致），
    # 这里装回真实实现，测的才是生产路径。
    monkeypatch.setattr(sjm, "search_login_block", acc.search_login_block)
    # Playwright 启动过的痕迹：profile 目录在，但里面没有活登录标记。
    acc.profile_dir_for("xhs").mkdir(parents=True)

    manager = SearchJobManager()
    spawned: list = []

    async def _must_not_run(job, platform):  # pragma: no cover - 命中即失败
        spawned.append(platform)
        raise AssertionError("login pre-check must prevent worker spawn")

    monkeypatch.setattr(manager, "_run_worker", _must_not_run)

    req = SearchJobRequestSchema(
        keyword=f"precheck-{uuid.uuid4().hex[:8]}",
        platforms=["xhs"], limit_per_platform=2)
    created = await manager.create_job(req)
    job = manager._active_job
    assert job is not None
    await job.task

    info = created.platforms["xhs"]
    assert spawned == []
    response = await manager.get_job(created.job_id)
    assert response is not None
    assert response.platforms["xhs"].status == "login_required"
    assert response.platforms["xhs"].error_summary
    assert "小红书" in response.platforms["xhs"].error_summary
    assert response.overall == "failed"
    # 预检不是限流：不得产生冷却，用户修好登录后应立即能重试。
    assert manager.cooldowns.remaining("xhs") == 0
    assert info is not None


@pytest.mark.asyncio
async def test_manager_still_spawns_worker_when_login_ok(monkeypatch, tmp_path):
    """有活登录标记时预检必须放行，worker 照常启动（防止过度拦截）。"""
    import uuid

    import api.services.search_job_manager as sjm
    from api.schemas.search import SearchJobRequestSchema
    from api.services.search_job_manager import SearchJobManager

    _isolate(monkeypatch, tmp_path)
    monkeypatch.setattr(sjm, "search_login_block", acc.search_login_block)
    _write_cookies_db(
        "xhs", [("web_session", ".xiaohongshu.com", _now_chromium() + _YEAR_US)])

    manager = SearchJobManager()
    spawned: list = []

    async def _fake_worker(job, platform):
        spawned.append(platform)
        job.set_platform_status(platform, "empty")

    monkeypatch.setattr(manager, "_run_worker", _fake_worker)

    req = SearchJobRequestSchema(
        keyword=f"precheck-ok-{uuid.uuid4().hex[:8]}",
        platforms=["xhs"], limit_per_platform=2)
    created = await manager.create_job(req)
    await manager._active_job.task

    assert spawned == ["xhs"]
    response = await manager.get_job(created.job_id)
    assert response is not None
    assert response.platforms["xhs"].status == "empty"

