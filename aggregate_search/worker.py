# -*- coding: utf-8 -*-
# Copyright (c) 2025 relakkes@gmail.com
#
# This file is part of MediaCrawler project.
# Licensed under NON-COMMERCIAL LEARNING LICENSE 1.1

"""
Standalone worker process for aggregate search.

Reads a ``WorkerRequest`` JSON line from stdin (UTF-8), runs the platform
crawler or login flow, and emits ``MC_AGG_EVENT``-prefixed NDJSON lines
on stdout (UTF-8 binary).

Security: No cookies, tokens, or headers in stdout events.
"""

from __future__ import annotations

import asyncio
import os
import sys
import time
from pathlib import Path
from typing import Any, Dict, List

# Round 16.1: 进程启动时刻必须在任何重型 import 之前记录（只依赖 stdlib）。
_PROCESS_START = time.perf_counter()

# Ensure project root is on sys.path
_PROJECT_ROOT = Path(__file__).parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

import config
from base.crawler_runtime import CrawlerRuntimeOptions
from base.exceptions import LoginRequiredError, RateLimitError
from tools import utils
from aggregate_search.protocol import (
    read_request, emit_status, emit_result, emit_done, emit_error,
    emit_metrics,
)
from aggregate_search.models import agg_to_core_platform
from aggregate_search.adapters import (
    XhsAdapter, DouyinAdapter, BilibiliAdapter, ZhihuAdapter,
)

# Round 16.1: 模块加载完成即固定 worker 就绪耗时（进程启动→就绪），
# 是进程生命周期内的常量 —— 绝不随 resident 空闲时间增长。
_PROCESS_READY_MS = int((time.perf_counter() - _PROCESS_START) * 1000)

# 知乎 worker 使用的 UA（浏览器路径与 fast path 共用，避免重复字面量）。
_ZHIHU_USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/128.0.0.0 Safari/537.36"
)


def _snapshot_has_dc0(snapshot: Optional[Dict[str, str]]) -> bool:
    """快照中是否存在有效 d_c0（知乎签名必需；不打印 Cookie 值）。"""
    if not snapshot:
        return False
    value = snapshot.get("d_c0")
    return isinstance(value, str) and bool(value)

WORKER_TIMEOUT_SECONDS = 90

_ADAPTERS = {
    "xhs": XhsAdapter(),
    "douyin": DouyinAdapter(),
    "bilibili": BilibiliAdapter(),
    "zhihu": ZhihuAdapter(),
}


# ── Error classification ────────────────────────────────────────────────

# 抖音搜索接口已知的风控/验证码 status_code（与
# media_platform.douyin.core.DOUYIN_RATE_LIMIT_STATUS_CODES 一致；这里兜底
# 覆盖从 client/网络层直接冒上来的同类异常）。
_DOUYIN_RATE_LIMIT_CODES = frozenset({21111, 21004, -20})


def _classify_error(exc: Exception) -> str:
    # Platform-defined safe codes (e.g. browser_unavailable, login_qr_not_found)
    safe_code = getattr(exc, "safe_code", None)
    if isinstance(safe_code, str) and safe_code:
        return safe_code
    if isinstance(exc, LoginRequiredError):
        return "login_required"
    if isinstance(exc, RateLimitError):
        return "rate_limited"
    if isinstance(exc, asyncio.TimeoutError):
        return "timed_out"
    # Bilibili rich error metadata (stage/http_status/platform_code) is more
    # reliable than class-name heuristics — check it first.
    platform_code = getattr(exc, "platform_code", None)
    if isinstance(platform_code, (int, float)) and not isinstance(platform_code, bool):
        if platform_code in (-412, -352) or platform_code in _DOUYIN_RATE_LIMIT_CODES:
            return "rate_limited"
        if platform_code == -101:  # 未登录
            return "login_required"
    http_status = getattr(exc, "http_status", None)
    if isinstance(http_status, (int, float)) and not isinstance(http_status, bool):
        if http_status == 403:  # 403 多为风控/验证码拦截
            return "rate_limited"
        if http_status >= 500:
            return "failed"
    name = type(exc).__name__.lower()
    for p in ("login", "auth", "cookie", "session", "unauthorized"):
        if p in name:
            return "login_required"
    for p in ("rate", "throttl", "limit", "captcha", "block", "forbidden"):
        if p in name:
            return "rate_limited"
    for p in ("timeout",):
        if p in name:
            return "timed_out"
    # Message-level heuristics (classification only — display text still
    # comes from safe_message, never from the raw message).
    msg = str(exc).lower()
    if "d_c0" in msg:  # 知乎签名需要 d_c0，缺失即搜索需要登录会话
        return "login_required"
    for p in ("captcha", "verify", "风控", "验证码", "blocked", "受限"):
        if p in msg:
            return "rate_limited"
    return "failed"


def _safe_error_message(exc: Exception) -> str:
    """Short safe message for an exception — never a traceback."""
    msg = getattr(exc, "safe_message", None)
    if isinstance(msg, str) and msg:
        return msg
    return type(exc).__name__


# ── Standard search (xhs, douyin, bilibili) ─────────────────────────────

async def _run_standard_search(
    job_id: str, platform: str, keyword: str, limit: int,
    session_snapshot: Optional[Dict[str, str]] = None,
) -> None:
    core_platform = agg_to_core_platform(platform)
    adapter = _ADAPTERS[platform]
    total_emitted = 0
    seen_ids: set = set()
    next_rank = 0

    def handle_results(native_batch: List[Any]) -> None:
        nonlocal total_emitted, next_rank
        if not native_batch:
            return
        dict_batch: List[Dict] = []
        for item in native_batch:
            if hasattr(item, "model_dump"):
                dict_batch.append(item.model_dump())
            elif isinstance(item, dict):
                dict_batch.append(item)
            else:
                dict_batch.append({"data": item})

        results = adapter.adapt(dict_batch, keyword)
        for r in results:
            # Apply worker-side dedup and limit
            dedup_key = f"{platform}:{r.content_id}"
            if dedup_key in seen_ids:
                continue
            if total_emitted >= limit:
                break
            seen_ids.add(dedup_key)
            total_emitted += 1
            if platform == "xhs":
                # Round 16.1: xhs 流式 sink 的详情按完成顺序到达，rank 已由
                # crawler 盖章为原始搜索列表序号 —— 不按到达顺序覆盖。
                pass
            else:
                # 其余平台批次即源顺序（分页/整页 sink），rank 保持到达顺序。
                r.rank = next_rank
                next_rank += 1
            r_data = r.model_dump()
            r_data.pop("event", None)
            r_data.pop("job_id", None)
            emit_result(job_id, platform, r_data)

    # Set config for core platform
    config.PLATFORM = core_platform
    config.KEYWORDS = keyword
    config.CRAWLER_TYPE = "search"
    config.CRAWLER_MAX_NOTES_COUNT = limit + 5
    config.ENABLE_GET_COMMENTS = False
    config.ENABLE_GET_MEIDAS = False
    config.ENABLE_CDP_MODE = False
    config.CDP_CONNECT_EXISTING = False
    config.HEADLESS = True
    config.SAVE_LOGIN_STATE = True
    config.LOGIN_TYPE = "qrcode"
    config.ENABLE_IP_PROXY = False
    # 小红书有限并发（其余平台保持 1，禁止无限并发）；四平台仍是独立 worker
    # 进程并行，各 crawler 修改全局 config 互不影响。
    config.MAX_CONCURRENCY_NUM = 2 if core_platform == "xhs" else 1
    # Force normal search mode for Bilibili
    if core_platform == "bili":
        config.BILI_SEARCH_MODE = "normal"

    crawler = None
    try:
        from main import CrawlerFactory

        # Round 16.1: worker 就绪耗时 = 进程启动→模块加载完成（固定常量，
        # 不随 resident 空闲时间增长）。
        emit_metrics(job_id, platform, {
            "worker_ready_ms": _PROCESS_READY_MS,
        })

        def _phase_metric(phase: str, elapsed_ms: int) -> None:
            # 只上报数字；manager 端白名单字段合并进 timings。
            emit_metrics(job_id, platform, {f"{phase}_ms": elapsed_ms})

        # Round 16: 无浏览器快速路径（xhs 需快照；bilibili 轻量列表可无登录
        # 直搜；douyin 无 fast path）。首条结果 emit 前失败 → 安全回退浏览器
        # 路径；已 emit 结果后失败 → 不重跑（避免重复）。
        if core_platform in ("xhs", "bili") and \
                (session_snapshot or core_platform == "bili"):
            try:
                await _run_fast_standard_search(
                    job_id, platform, core_platform, keyword, limit,
                    handle_results, session_snapshot or {}, _phase_metric,
                )
                if total_emitted == 0:
                    emit_status(job_id, platform, "empty",
                                {"message": "No results found."})
                else:
                    emit_status(job_id, platform, "succeeded")
                emit_done(job_id, platform)
                return
            except Exception as exc:
                if total_emitted > 0:
                    # 已有结果：不完整重跑（防重复），按错误上报。
                    error_type = _classify_error(exc)
                    safe_msg = _safe_error_message(exc)
                    emit_error(job_id, platform, error_type, safe_msg)
                    emit_done(job_id, platform)
                    return
                # 尚无结果 → 记录回退原因并走浏览器路径。
                emit_metrics(job_id, platform, {
                    "fast_path_used": False,
                    "fallback_reason": "fast_path_failed"})

        crawler = CrawlerFactory.create_crawler(platform=core_platform)
        crawler.runtime_options = CrawlerRuntimeOptions(
            result_sink=handle_results,
            persist_results=False,
            login_policy="fail_fast",
            enable_comments=False,
            enable_media=False,
            result_limit=limit,
            strict_errors=True,
            headless=True,
            # bilibili: 搜索列表已含 MVP 字段，跳过逐条详情 API（P0 轻量模式）
            fetch_details=(core_platform != "bili"),
            # douyin: pong 未确认登录时仍尝试公开搜索（登录门禁不适用公开 API）
            allow_public_search=(core_platform == "dy"),
            # xhs: 详情按原始顺序逐条 sink + 复用单个 httpx client（Phase 3）
            stream_results=(core_platform == "xhs"),
            reuse_http_client=True,
            light_page=True,
            metrics_cb=_phase_metric,
        )

        emit_status(job_id, platform, "running")
        await asyncio.wait_for(crawler.start(), timeout=WORKER_TIMEOUT_SECONDS)

        if total_emitted == 0:
            emit_status(job_id, platform, "empty", {"message": "No results found."})
        else:
            emit_status(job_id, platform, "succeeded")

    except asyncio.TimeoutError:
        emit_error(job_id, platform, "timed_out", f"Search timed out after {WORKER_TIMEOUT_SECONDS}s")
    except Exception as exc:
        error_type = _classify_error(exc)
        safe_msg = _safe_error_message(exc)
        emit_error(job_id, platform, error_type, safe_msg)
    finally:
        try:
            await _cleanup_crawler(crawler)
        except Exception:
            pass

    emit_done(job_id, platform)


# ── Fast path (no-browser, Round 16) ────────────────────────────────────

async def _run_fast_standard_search(
    job_id: str, platform: str, core_platform: str, keyword: str, limit: int,
    handle_results, session_snapshot: Dict[str, str], phase_metric,
) -> None:
    """无浏览器快速路径：从内存会话快照构造 client，直接跑搜索（不启动
    浏览器）。只在 aggregate 模式调用；任何异常向上传播，由调用方决定
    回退（首条结果前）或按错误上报（已有结果不重跑）。

    返回时结果已通过 ``handle_results`` emit（或合法 empty）。
    """
    from main import CrawlerFactory

    emit_metrics(job_id, platform, {"fast_path_used": True})
    crawler = CrawlerFactory.create_crawler(platform=core_platform)
    crawler.runtime_options = CrawlerRuntimeOptions(
        result_sink=handle_results,
        persist_results=False,
        login_policy="fail_fast",
        enable_comments=False,
        enable_media=False,
        result_limit=limit,
        strict_errors=True,
        headless=True,
        fetch_details=(core_platform != "bili"),
        stream_results=(core_platform == "xhs"),
        reuse_http_client=True,
        metrics_cb=phase_metric,
    )
    try:
        if core_platform == "xhs":
            crawler.xhs_client = await crawler.create_xhs_client_from_snapshot(
                session_snapshot)
            await crawler.search()
        elif core_platform == "bili":
            crawler.bili_client = await crawler.create_bilibili_client_from_snapshot(
                session_snapshot)
            await crawler.search_by_keywords()
        else:  # pragma: no cover — douyin 不走 fast path
            raise RuntimeError("fast path not supported")
    finally:
        try:
            await _cleanup_crawler(crawler)
        except Exception:
            pass


# ── Zhihu search ────────────────────────────────────────────────────────

async def _run_zhihu_search(
    job_id: str, platform: str, keyword: str, limit: int,
    session_snapshot: Optional[Dict[str, str]] = None,
) -> None:
    """
    Zhihu search reusing the core's persistent-context + search-page flow.
    Uses raw API response to get PUBLIC nicknames (bypassing the extractor).
    Round 16: 快照中存在有效 d_c0 时走无浏览器快速路径（零页面导航）。
    """
    from playwright.async_api import async_playwright
    from media_platform.zhihu.client import ZhiHuClient
    from tools.browser_launcher import (
        BrowserUnavailableError, resolve_playwright_browser,
    )

    core_platform = agg_to_core_platform(platform)
    adapter = _ADAPTERS["zhihu"]
    browser_context = None
    total_emitted = 0
    seen_ids: set = set()
    next_rank = 0

    config.PLATFORM = core_platform
    config.HEADLESS = True
    config.SAVE_LOGIN_STATE = True
    config.LOGIN_TYPE = "qrcode"
    config.ENABLE_CDP_MODE = False
    config.CDP_CONNECT_EXISTING = False
    config.ENABLE_IP_PROXY = False

    def _zh_emit(search_res) -> None:
        """从知乎搜索响应适配并 emit 结果（fast path 与浏览器路径共用）。"""
        nonlocal total_emitted, next_rank
        if not isinstance(search_res, dict):
            return
        data_items = search_res.get("data", [])
        raw_objects = [
            item.get("object")
            for item in data_items
            if item.get("type") in ("search_result", "zvideo")
               and item.get("object")
        ]
        if not raw_objects:
            return
        results = adapter.adapt(raw_objects, keyword)
        for r in results:
            dedup_key = f"{platform}:{r.content_id}"
            if dedup_key in seen_ids:
                continue
            if total_emitted >= limit:
                break
            seen_ids.add(dedup_key)
            r.rank = next_rank
            next_rank += 1
            total_emitted += 1
            r_data = r.model_dump()
            r_data.pop("event", None)
            r_data.pop("job_id", None)
            emit_result(job_id, platform, r_data)

    try:
        emit_status(job_id, platform, "running")
        emit_metrics(job_id, platform, {
            "worker_ready_ms": _PROCESS_READY_MS,
        })
        _zh_phase = time.perf_counter()

        # ── Round 16 fast path：快照含有效 d_c0 → 无浏览器直搜 ──────────
        # 零页面导航、不做 pong 门禁（搜索响应本身能分类错误）；失败且
        # 尚无结果 → 安全回退下方浏览器路径；已有结果 → 不重跑。
        if session_snapshot and _snapshot_has_dc0(session_snapshot):
            emit_metrics(job_id, platform, {"fast_path_used": True})
            _fp_cookie_str = "; ".join(
                f"{k}={v}" for k, v in session_snapshot.items())
            fp_client = ZhiHuClient(
                proxy=None,
                headers={
                    "accept": "*/*",
                    "accept-language": "zh-CN,zh;q=0.9",
                    "cookie": _fp_cookie_str,  # lowercase, matching _pre_headers
                    "priority": "u=1, i",
                    "referer": "https://www.zhihu.com/search?q=python&time_interval=a_year&type=content",
                    "user-agent": _ZHIHU_USER_AGENT,
                    "x-api-version": "3.0.91",
                    "x-app-za": "OS=Web",
                    "x-requested-with": "fetch",
                    "x-zse-93": "101_3_3.0",
                },
                playwright_page=None,
                cookie_dict=dict(session_snapshot),
                reuse_http_client=True,
            )
            try:
                search_res = await fp_client.get("/api/v4/search_v3", {
                    "gk_version": "gz-gaokao",
                    "t": "general",
                    "q": keyword,
                    "correction": 1,
                    "offset": 0,
                    "limit": min(limit + 5, 20),
                    "filter_fields": "",
                    "lc_idx": 0,
                    "show_all_topics": 0,
                    "search_source": "Filter",
                })
                emit_metrics(job_id, platform, {
                    "search_api_ms": int(
                        (time.perf_counter() - _zh_phase) * 1000)})
                _zh_emit(search_res)
                if total_emitted == 0:
                    emit_status(job_id, platform, "empty",
                                {"message": "No results found."})
                else:
                    emit_status(job_id, platform, "succeeded")
                emit_done(job_id, platform)
                return
            except Exception as exc:
                if total_emitted > 0:
                    # 已有结果：不完整重跑（防重复），按错误上报。
                    error_type = _classify_error(exc)
                    safe_msg = _safe_error_message(exc)
                    emit_error(job_id, platform, error_type, safe_msg)
                    emit_done(job_id, platform)
                    return
                emit_metrics(job_id, platform, {
                    "fast_path_used": False,
                    "fallback_reason": "fast_path_failed"})
                # 无结果 → 回退浏览器路径（继续执行下方代码）。

        async with async_playwright() as playwright:
            user_data_dir = os.path.join(
                os.getcwd(), "browser_data",
                config.USER_DATA_DIR % core_platform
            )
            user_agent = _ZHIHU_USER_AGENT
            # Resolve browser: CUSTOM_BROWSER_PATH > Chrome > Edge > bundled Chromium
            executable_path, channel, backend = resolve_playwright_browser()
            if backend == "playwright-chromium":
                bundled_path = playwright.chromium.executable_path
                if not bundled_path or not os.path.isfile(bundled_path):
                    raise BrowserUnavailableError(
                        "没有找到可用的浏览器，请安装 Chrome 或 Edge 后重试")
                executable_path = bundled_path
            launch_kwargs: Dict = {
                "user_data_dir": user_data_dir,
                "accept_downloads": True,
                "headless": True,
                "viewport": {"width": 1920, "height": 1080},
                "user_agent": user_agent,
            }
            if executable_path:
                launch_kwargs["executable_path"] = executable_path
            elif channel:
                launch_kwargs["channel"] = channel
            browser_context = await playwright.chromium.launch_persistent_context(
                **launch_kwargs,
            )
            await browser_context.add_init_script(path="libs/stealth.min.js")
            # Round 16 轻量页面：拦截 image/media/font/analytics，导航用
            # domcontentloaded；route 随 context 关闭自动清理。
            from tools.light_page import install_light_page_routes, light_goto_kwargs
            await install_light_page_routes(browser_context)
            emit_metrics(job_id, platform, {
                "browser_launch_ms": int((time.perf_counter() - _zh_phase) * 1000)})

            page = await browser_context.new_page()
            await page.goto("https://www.zhihu.com", **light_goto_kwargs())

            # 先访问搜索页 —— 知乎的 d_c0 等会话 Cookie 往往只在真实访问
            # 搜索页后由浏览器生成/刷新；pong 与搜索 API 都必须用它签名。
            await page.goto(
                "https://www.zhihu.com/search?q=python&search_source=Guess"
                "&utm_content=search_hot&type=content",
                **light_goto_kwargs(),
            )
            # Phase 3.4: 有界条件等待 d_c0（最迟 3s），不再固定 sleep(3)。
            await _wait_for_zhihu_dc0(browser_context)
            emit_metrics(job_id, platform, {
                "navigation_ms": int((time.perf_counter() - _zh_phase) * 1000)})

            # Build client with cookies REFRESHED after the search-page
            # navigation (must contain d_c0 when the page generated it).
            cookie_str, cookie_dict = await _get_browser_cookies(
                browser_context, ["https://www.zhihu.com"]
            )

            zhihu_client = ZhiHuClient(
                proxy=None,
                headers={
                    "accept": "*/*",
                    "accept-language": "zh-CN,zh;q=0.9",
                    "cookie": cookie_str,  # lowercase, matching ZhiHuClient._pre_headers
                    "priority": "u=1, i",
                    "referer": "https://www.zhihu.com/search?q=python&time_interval=a_year&type=content",
                    "user-agent": user_agent,
                    "x-api-version": "3.0.91",
                    "x-app-za": "OS=Web",
                    "x-requested-with": "fetch",
                    "x-zse-93": "101_3_3.0",
                },
                playwright_page=page,
                cookie_dict=cookie_dict,
                reuse_http_client=True,
            )

            # pong 只是诊断，不是门禁：公开搜索 API 不确认登录也可能返回
            # 合法结果 —— pong 失败仍继续尝试搜索。
            logged_in = await zhihu_client.pong()
            utils.logger.info(
                f"[worker._run_zhihu_search] zhihu pong logged_in={logged_in}, "
                f"d_c0_present={'d_c0' in cookie_dict}")
            emit_metrics(job_id, platform, {
                "preflight_ms": int((time.perf_counter() - _zh_phase) * 1000)})

            # Direct search API call (bypass extractor for public nicknames)
            page_size = min(limit + 5, 20)
            try:
                search_res = await zhihu_client.get("/api/v4/search_v3", {
                    "gk_version": "gz-gaokao",
                    "t": "general",
                    "q": keyword,
                    "correction": 1,
                    "offset": 0,
                    "limit": page_size,
                    "filter_fields": "",
                    "lc_idx": 0,
                    "show_all_topics": 0,
                    "search_source": "Filter",
                })
            except Exception as exc:
                # 搜索 API 明确无法签名（d_c0 缺失）= 需要登录会话；403/风控
                # 由 _classify_error 归为 rate_limited，不在这里吞掉。
                if "d_c0" in str(exc):
                    emit_error(job_id, platform, "login_required",
                               "知乎搜索需要登录会话，请前往账号设置重新同步")
                    emit_done(job_id, platform)
                    return
                raise

            if not isinstance(search_res, dict):
                emit_status(job_id, platform, "empty",
                           {"message": "No results found."})
                emit_done(job_id, platform)
                return
            emit_metrics(job_id, platform, {
                "search_api_ms": int((time.perf_counter() - _zh_phase) * 1000)})

            _zh_emit(search_res)

            if total_emitted == 0:
                emit_status(job_id, platform, "empty")
            else:
                emit_status(job_id, platform, "succeeded")

    except asyncio.TimeoutError:
        emit_error(job_id, platform, "timed_out", "Search timed out")
    except Exception as exc:
        error_type = _classify_error(exc)
        safe_msg = _safe_error_message(exc)
        emit_error(job_id, platform, error_type, safe_msg)
    finally:
        if browser_context:
            try:
                await browser_context.close()
            except Exception:
                pass

    emit_done(job_id, platform)


# ── Login-only ──────────────────────────────────────────────────────────

_CLIENT_ATTRS = {
    "xhs": "xhs_client",
    "dy": "dy_client",
    "bili": "bili_client",
    "zhihu": "zhihu_client",
}


async def _verify_login_success(crawler: Any, core_platform: str) -> bool:
    """Re-read cookies from the crawler's context and verify the session
    with the platform's own pong()/check_login_state().

    Returns True only when the session is actually verified after login.
    """
    ctx = getattr(crawler, "browser_context", None)
    client = getattr(crawler, _CLIENT_ATTRS.get(core_platform, "_no_client"), None)
    if ctx is None or client is None:
        return False
    url_by_platform = {
        "xhs": ["https://www.xiaohongshu.com"],
        "dy": ["https://www.douyin.com"],
        "bili": ["https://www.bilibili.com"],
        "zhihu": ["https://www.zhihu.com"],
    }
    urls = url_by_platform.get(core_platform)
    if not urls:
        return False
    try:
        cookies = await ctx.cookies(urls)
        if not cookies:
            return False
        client.cookie_dict = {c["name"]: c["value"] for c in cookies}
        update_cookies = getattr(client, "update_cookies", None)
        if callable(update_cookies):
            try:
                await update_cookies(browser_context=ctx, urls=urls)
            except Exception:
                pass
        pong = getattr(client, "pong", None)
        if not callable(pong):
            return False
        import inspect
        try:
            sig = inspect.signature(pong)
            result = pong(ctx) if "browser_context" in sig.parameters else pong()
        except Exception:
            result = pong()
        if asyncio.iscoroutine(result):
            return bool(await result)
        return bool(result)
    except Exception:
        return False


async def _run_login(job_id: str, platform: str) -> None:
    """Login-only: launch visible browser, do QR login, save profile, exit.

    Guarantees exactly one ``done`` event (success, failure, timeout, or
    ``_WorkerExit``) and only emits ``succeeded`` after the session has been
    re-read and verified via the platform's own pong/check_login_state.
    """
    core_platform = agg_to_core_platform(platform)

    config.PLATFORM = core_platform
    config.HEADLESS = False
    config.CDP_HEADLESS = False
    config.ENABLE_CDP_MODE = False
    config.CDP_CONNECT_EXISTING = False
    config.LOGIN_TYPE = "qrcode"
    config.SAVE_LOGIN_STATE = True
    config.CRAWLER_TYPE = "search"
    config.KEYWORDS = "__LOGIN_ONLY_NO_SEARCH__"
    config.CRAWLER_MAX_NOTES_COUNT = 0  # Don't fetch any results
    config.ENABLE_GET_COMMENTS = False
    config.ENABLE_GET_MEIDAS = False
    config.ENABLE_IP_PROXY = False
    config.ENABLE_GET_WORDCLOUD = False

    crawler = None
    done_emitted = False

    def _emit_done_once() -> None:
        nonlocal done_emitted
        if not done_emitted:
            emit_done(job_id, platform)
            done_emitted = True

    try:
        from main import CrawlerFactory
        crawler = CrawlerFactory.create_crawler(platform=core_platform)

        crawler.runtime_options = CrawlerRuntimeOptions(
            persist_results=False,
            login_policy="interactive",
            enable_comments=False,
            enable_media=False,
            result_limit=0,
            headless=False,
        )

        emit_status(job_id, platform, "running",
                    {"message": "浏览器窗口已打开，请扫码登录。"})

        # Override search so it does NOT run for login-only
        original_search = getattr(crawler, "search", None)

        async def _noop_search():
            """Login-only: skip all search/storing."""
            pass

        crawler.search = _noop_search

        try:
            await asyncio.wait_for(crawler.start(), timeout=600)
        finally:
            if original_search is not None:
                crawler.search = original_search

        # Re-read cookies and verify the session BEFORE declaring success.
        verified = await _verify_login_success(crawler, core_platform)
        if verified:
            emit_status(job_id, platform, "succeeded",
                        {"message": "登录成功，会话已验证并保存。"})
        else:
            emit_error(job_id, platform, "login_verification_failed",
                       "登录验证失败，请重试")
        _emit_done_once()

    except _WorkerExit:
        # A platform login module called sys.exit() — login failed.
        emit_error(job_id, platform, "login_verification_failed",
                   "登录失败：未在限定时间内完成扫码登录")
        _emit_done_once()
        raise
    except asyncio.TimeoutError:
        emit_error(job_id, platform, "timed_out",
                   "登录超时（10 分钟）")
        _emit_done_once()
    except Exception as exc:
        error_type = _classify_error(exc)
        safe_msg = _safe_error_message(exc)
        emit_error(job_id, platform, error_type, f"登录失败：{safe_msg}")
        _emit_done_once()
    finally:
        try:
            await _cleanup_crawler(crawler)
        except Exception:
            pass
        _emit_done_once()


# ── Cleanup helpers ─────────────────────────────────────────────────────

async def _has_zhihu_dc0(browser_context: Any) -> bool:
    """读取 zhihu.com 域下 Cookie，返回是否存在非空 d_c0（不打印 Cookie 值）。"""
    try:
        cookies = await browser_context.cookies(["https://www.zhihu.com"])
    except Exception:
        return False
    for c in cookies or []:
        if c.get("name") == "d_c0" and c.get("value"):
            return True
    return False


async def _wait_for_zhihu_dc0(
    browser_context: Any,
    timeout_seconds: float = 3.0,
    interval_seconds: float = 0.2,
    monotonic=time.monotonic,
    sleep=asyncio.sleep,
) -> bool:
    """有界条件等待（Phase 3.4）：每约 interval_seconds 轮询 zhihu.com
    域下 d_c0 Cookie，一旦非空立即继续；超时按现有逻辑继续，不打印 Cookie 值。

    monotonic/sleep 可注入，便于确定性测试（不依赖墙钟）。
    """
    deadline = monotonic() + timeout_seconds
    while True:
        if await _has_zhihu_dc0(browser_context):
            return True
        if monotonic() >= deadline:
            return False
        await sleep(interval_seconds)


async def _cleanup_crawler(crawler: Any) -> None:
    if crawler is None:
        return
    # Round 16: 关闭所有平台的复用 API client（幂等 aclose/close），再关浏览器。
    for attr in ("xhs_client", "dy_client", "bili_client", "zhihu_client"):
        api_client = getattr(crawler, attr, None)
        if api_client is not None:
            closer = getattr(api_client, "aclose", None) or getattr(api_client, "close", None)
            if closer is not None:
                try:
                    await closer()
                except Exception:
                    pass
    cdp = getattr(crawler, "cdp_manager", None)
    if cdp is not None:
        try:
            await cdp.cleanup(force=True)
        except Exception:
            pass
        return
    ctx = getattr(crawler, "browser_context", None)
    if ctx is not None:
        try:
            await ctx.close()
        except Exception:
            pass


async def _get_browser_cookies(browser_context, urls: List[str]):
    """Extract cookies from a Playwright browser context, filtered by URL."""
    cookies = await browser_context.cookies(urls)
    cookie_str = "; ".join([f"{c['name']}={c['value']}" for c in cookies])
    cookie_dict = {c["name"]: c["value"] for c in cookies}
    return cookie_str, cookie_dict


# ── Dispatcher ──────────────────────────────────────────────────────────

async def run_worker(
    job_id: str, mode: str, platform: str, keyword: str, limit: int,
    session_snapshot: Optional[Dict[str, str]] = None,
    fast_path: bool = False,
) -> None:
    if mode == "login":
        await _run_login(job_id, platform)
        return

    if mode != "search":
        emit_error(job_id, platform, "failed", f"Unknown mode: {mode}")
        return

    if platform == "zhihu":
        await _run_zhihu_search(
            job_id, platform, keyword, limit,
            session_snapshot=session_snapshot if fast_path else None)
    else:
        await _run_standard_search(
            job_id, platform, keyword, limit,
            session_snapshot=session_snapshot if fast_path else None)


class _WorkerExit(Exception):
    """Raised instead of calling sys.exit() in login modules."""
    pass


def main() -> None:
    """Worker entry: one-shot (default) or resident loop (--resident).

    Resident mode (Round 16 supervisor): reads NDJSON requests from stdin in a
    loop — one request per line — until stdin closes (graceful stop) or the
    request cap is reached (max-requests restart). Cookies/URLs never enter
    argv; only the ``--resident`` flag does.
    """
    resident = "--resident" in sys.argv
    max_requests = 1
    if resident:
        try:
            max_requests = max(1, int(os.environ.get("MC_WORKER_MAX_REQUESTS", "20")))
        except (TypeError, ValueError):
            max_requests = 20

    # Monkey-patch sys.exit so platform login modules don't kill us silently.
    # They call sys.exit() on login failure — we convert that to an exception
    # the worker can catch and report.
    _original_exit = sys.exit

    def _safe_exit(code=0):
        raise _WorkerExit(f"sys.exit({code}) intercepted by worker")

    sys.exit = _safe_exit  # type: ignore

    exit_code = 0
    processed = 0
    try:
        while True:
            try:
                request = read_request()
            except EOFError:
                break  # stdin closed → 优雅退出
            except Exception as exc:
                # Round 16.1: 只输出异常类型 —— str(exc) 可能包含请求行内容
                # （如 JSONDecodeError 回显输入，可能含 Cookie/快照）。
                sys.stderr.buffer.write(
                    ("Worker failed to read request: "
                     f"{type(exc).__name__}\n").encode("utf-8"))
                sys.stderr.buffer.flush()
                exit_code = 1
                break
            processed += 1
            request_exit = 0
            try:
                asyncio.run(
                    run_worker(
                        job_id=request.job_id,
                        mode=request.mode,
                        platform=request.platform,
                        keyword=request.keyword,
                        limit=request.limit,
                        session_snapshot=request.session_snapshot,
                        fast_path=request.fast_path,
                    )
                )
            except _WorkerExit:
                # Platform login module called sys.exit() — the worker's
                # exception handlers already emitted error events. A
                # login-failure exit must NOT become a normal exit 0.
                request_exit = 0 if request.mode != "login" else 1
            except KeyboardInterrupt:
                request_exit = 130
            except Exception as exc:
                # Round 16.1: 未捕获异常 → 记录安全错误码后立即结束进程。
                # 绝不打印 traceback（帧/异常消息可能含请求、Cookie 或快照），
                # 也绝不继续 resident 循环读取下一请求 —— 否则 manager 收
                # 不到 done/EOF，只能等完整 WORKER_TIMEOUT_SECONDS。
                sys.stderr.buffer.write(
                    ("Worker aborted by uncaught exception "
                     f"({type(exc).__name__}); exiting\n").encode("utf-8"))
                sys.stderr.buffer.flush()
                request_exit = 1
            if request_exit != 0:
                exit_code = request_exit
            # 未捕获异常/键盘中断后立即退出，不再处理下一请求。
            if not resident or processed >= max_requests or request_exit != 0:
                break
    finally:
        sys.exit = _original_exit  # type: ignore

    sys.exit = _original_exit  # type: ignore
    sys.exit(exit_code)


if __name__ == "__main__":
    main()
