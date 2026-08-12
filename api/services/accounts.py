# -*- coding: utf-8 -*-
# Copyright (c) 2025 relakkes@gmail.com
#
# This file is part of MediaCrawler project.
# Licensed under NON-COMMERCIAL LEARNING LICENSE 1.1

"""Account session service for the aggregate search backend.

Responsibilities:
- one-time sync tickets (>=128-bit, 60s TTL, single-use, memory-only);
- cookie domain whitelist validation per platform;
- Chrome-cookie -> Playwright-cookie mapping;
- importing cookies into an independent headless profile under browser_data/;
- verifying a profile via the platform's own pong/check_login_state;
- deleting a profile (browser_data only, path-verified);
- in-memory per-platform account state.

Security: no cookies/tokens/profile absolute paths ever leave this service
in responses; no raw cookie JSON is persisted — only the browser profile
itself persists the session. No usernames/passwords are stored.
"""

from __future__ import annotations

import asyncio
import math
import os
import secrets
import shutil
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

_PROJECT_ROOT = Path(__file__).parent.parent.parent
BROWSER_DATA_DIR = _PROJECT_ROOT / "browser_data"

# Platform -> official cookie domains (subdomain match allowed).
PLATFORM_COOKIE_DOMAINS: Dict[str, tuple] = {
    "xhs": ("xiaohongshu.com",),
    "douyin": ("douyin.com",),
    "bilibili": ("bilibili.com",),
    "zhihu": ("zhihu.com",),
}

# Platform -> profile dir name (must match config.USER_DATA_DIR % platform).
PLATFORM_PROFILE_DIRS: Dict[str, str] = {
    "xhs": "xhs_user_data_dir",
    "douyin": "dy_user_data_dir",
    "bilibili": "bili_user_data_dir",
    "zhihu": "zhihu_user_data_dir",
}

PLATFORM_HOME_URLS: Dict[str, str] = {
    "xhs": "https://www.xiaohongshu.com",
    "douyin": "https://www.douyin.com",
    "bilibili": "https://www.bilibili.com",
    "zhihu": "https://www.zhihu.com",
}

# Platform -> URL for cookie reading / pong verification.
PLATFORM_COOKIE_URLS: Dict[str, list] = {
    "xhs": ["https://www.xiaohongshu.com"],
    "douyin": ["https://www.douyin.com"],
    "bilibili": ["https://www.bilibili.com"],
    "zhihu": ["https://www.zhihu.com"],
}

TICKET_TTL_SECONDS = 60
_SYNC_TICKET_LENGTH_BITS = 256

# Cookie wire contract: the extension sends raw Chrome-cookies-API fields
# exactly once; the backend performs the single Chrome -> Playwright mapping.
COOKIE_FORMAT_CHROME_V1 = "chrome-v1"
CHROME_V1_FIELDS = frozenset({
    "name", "value", "domain", "path", "expirationDate",
    "httpOnly", "secure", "sameSite", "session", "storeId",
})
# Playwright-style sameSite values are NOT part of the chrome-v1 contract.
PLAYWRIGHT_SAME_SITE_VALUES = frozenset({"Lax", "Strict", "None"})

# Bounded verification after a sync: if pong takes longer, the profile keeps
# verifying in the background and the sync reports status=verifying.
SYNC_VERIFY_TIMEOUT_SECONDS = 30

# Wire protocol version: must match browser_extension/sync_protocol.js's
# EXTENSION_PROTOCOL_VERSION. Older/newer extensions are rejected with a
# structured extension_protocol_outdated error.
EXTENSION_PROTOCOL_VERSION = 2

# Platform login cookies (name presence only — never values). Names follow
# the repo's real pong / login checks:
#   bilibili  login.py:76  "SESSDATA or DedeUserID"  (bili_jct = CSRF for POSTs)
#   zhihu     client.py:76 d_c0 required; login.py:68 uses z_c0
#   xhs       login.py:78  web_session changes on login
#   douyin    client.py:159 pong checks cookie LOGIN_STATUS == "1"
REQUIRED_COOKIE_NAMES: Dict[str, tuple] = {
    "bilibili": ("SESSDATA", "bili_jct", "DedeUserID"),
    "zhihu": ("z_c0", "d_c0"),
    "xhs": ("web_session", "a1"),
    "douyin": ("LOGIN_STATUS", "sessionid", "sessionid_ss"),
}
# The critical subset whose presence means "this browser has a login".
CRITICAL_COOKIE_NAMES: Dict[str, tuple] = {
    "bilibili": ("SESSDATA", "DedeUserID"),
    "zhihu": ("z_c0", "d_c0"),
    "xhs": ("web_session",),
    "douyin": ("LOGIN_STATUS",),
}

# Login-marker whitelist for the login_marker_presence diagnostic: marker
# NAME + presence boolean ONLY — values never leave this module. This is a
# heuristic (import-time signal), NOT the verification result: import is
# allowed with any valid platform cookie, and only the platform's own pong
# decides connected/verified (zhihu d_c0 may only be generated after the
# browser visits the official site).
LOGIN_MARKER_NAMES: Dict[str, tuple] = {
    "douyin": ("LOGIN_STATUS", "sessionid", "sessionid_ss"),
    "zhihu": ("z_c0", "d_c0"),
    "bilibili": ("SESSDATA", "DedeUserID"),
    "xhs": ("web_session",),
}


def _diagnostics(received: int = 0, stage: str = "cookie_validation") -> Dict[str, Any]:
    """Structured sync diagnostics — counts and marker booleans only,
    never cookie values."""
    return {
        "received_cookie_count": received,
        "accepted_cookie_count": 0,
        "skipped_cookie_count": 0,
        "rejected_cookie_count": 0,
        "required_cookie_present": False,
        "login_marker_presence": {},
        "browser_cookie_store_count": 0,
        "sync_stage": stage,
    }


class TicketError(Exception):
    """Invalid / expired / reused / mismatched sync ticket."""

    def __init__(self, message: str = "同步票据无效"):
        self.safe_code = "sync_ticket_invalid"
        super().__init__(message)


class CookieDomainRejectedError(Exception):
    def __init__(self, message: str = "Cookie 域名不在该平台允许的官方域名内",
                 diagnostics: Optional[Dict[str, Any]] = None):
        self.safe_code = "cookie_domain_rejected"
        self.diagnostics = diagnostics or {}
        super().__init__(message)


class SessionImportError(Exception):
    def __init__(self, message: str = "会话导入失败",
                 diagnostics: Optional[Dict[str, Any]] = None):
        self.safe_code = "session_import_failed"
        self.diagnostics = diagnostics or {}
        super().__init__(message)


class CookieFormatInvalidError(Exception):
    """The payload is not the chrome-v1 wire contract (mixed/unknown fields)."""

    def __init__(self, message: str = "Cookie 格式不兼容，请重新加载浏览器扩展后再试",
                 diagnostics: Optional[Dict[str, Any]] = None):
        self.safe_code = "cookie_format_invalid"
        self.diagnostics = diagnostics or {}
        super().__init__(message)


class RequiredLoginCookieMissingError(Exception):
    """Cookies were read, but none of the platform's login cookies exist."""

    def __init__(self, message: str = "当前浏览器没有读取到有效登录会话，"
                                      "请确认扩展安装在实际登录账号所使用的 Edge profile 中",
                 diagnostics: Optional[Dict[str, Any]] = None):
        self.safe_code = "required_login_cookie_missing"
        self.diagnostics = diagnostics or {}
        super().__init__(message)


class ExtensionProtocolOutdatedError(Exception):
    """The extension speaks a different wire protocol version."""

    def __init__(self, message: str = "扩展版本与后端协议不兼容，"
                                      "请在扩展管理页点击\"重新加载\"后刷新本页",
                 diagnostics: Optional[Dict[str, Any]] = None):
        self.safe_code = "extension_protocol_outdated"
        self.diagnostics = diagnostics or {}
        super().__init__(message)


class PlatformError(Exception):
    def __init__(self, message: str = "不支持的平台"):
        self.safe_code = "sync_ticket_invalid"
        super().__init__(message)


# ── One-time tickets ────────────────────────────────────────────────────

class _Ticket:
    __slots__ = ("platform", "expires_at", "used")

    def __init__(self, platform: str) -> None:
        self.platform = platform
        self.expires_at = time.monotonic() + TICKET_TTL_SECONDS
        self.used = False


_tickets: Dict[str, _Ticket] = {}
_tickets_lock = asyncio.Lock()


def create_sync_ticket(platform: str) -> str:
    """Create a one-time sync ticket (memory-only)."""
    if platform not in PLATFORM_PROFILE_DIRS:
        raise PlatformError(f"不支持的平台: {platform}")
    ticket = secrets.token_urlsafe(_SYNC_TICKET_LENGTH_BITS // 8)
    _tickets[ticket] = _Ticket(platform)
    return ticket


def _purge_expired_tickets() -> None:
    now = time.monotonic()
    for key in [k for k, t in _tickets.items() if t.expires_at <= now]:
        _tickets.pop(key, None)


async def consume_sync_ticket(ticket: str, platform: str) -> None:
    """Validate and consume a one-time ticket.

    Raises TicketError unless the ticket exists, is unexpired, unused, and
    bound to the same platform.
    """
    async with _tickets_lock:
        _purge_expired_tickets()
        t = _tickets.pop(ticket, None)
        if t is None:
            raise TicketError("同步票据无效或已过期")
        if t.used:
            raise TicketError("同步票据已被使用")
        if t.platform != platform:
            raise TicketError("同步票据与平台不匹配")
        t.used = True  # single-use


# ── Cookie validation & mapping ─────────────────────────────────────────

def cookie_domain_allowed(platform: str, domain: str) -> bool:
    """A cookie domain must belong to the platform's official domains."""
    allowed = PLATFORM_COOKIE_DOMAINS.get(platform, ())
    if not allowed:
        return False
    d = (domain or "").lower().lstrip(".")
    if not d:
        return False
    return any(d == a or d.endswith("." + a) for a in allowed)


def map_chrome_cookie(cookie: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """Map ONE chrome-v1 cookie to the Playwright cookie shape.

    The backend performs this mapping exactly once — the extension must NOT
    pre-convert. Rules:
    - ``expirationDate`` -> ``expires`` only when it is a finite positive
      number; session cookies get NO ``expires`` key (never ``-1``).
    - ``sameSite``: no_restriction->None, lax->Lax, strict->Strict; any other
      value (unspecified/null/unknown) omits the key entirely — NEVER
      ``sameSite: null`` (Playwright rejects it).
    - partitioned cookies (``partitionKey``) are skipped — caller counts.
    - malformed single cookies return None — caller counts them as skipped
      instead of failing the whole batch.
    """
    name = cookie.get("name")
    value = cookie.get("value")
    domain = cookie.get("domain")
    if not name or value is None or not domain:
        return None
    if cookie.get("partitionKey"):
        return None  # partitioned cookie — unsupported, skip
    out: Dict[str, Any] = {
        "name": name,
        "value": value,
        "domain": domain,
        "path": cookie.get("path") or "/",
        "httpOnly": bool(cookie.get("httpOnly")),
        "secure": bool(cookie.get("secure")),
    }
    expiration = cookie.get("expirationDate")
    if isinstance(expiration, (int, float)) and not isinstance(expiration, bool):
        f = float(expiration)
        if math.isfinite(f) and f > 0:
            out["expires"] = f
    # NaN / Infinity / non-positive / non-numeric -> no expires key at all.
    same_site = cookie.get("sameSite")
    if same_site == "no_restriction":
        out["sameSite"] = "None"
    elif same_site == "lax":
        out["sameSite"] = "Lax"
    elif same_site == "strict":
        out["sameSite"] = "Strict"
    # unspecified / null / unknown -> omit sameSite entirely (never null).
    return out


def validate_chrome_v1_cookie_list(
    platform: str, cookies: List[Dict[str, Any]],
) -> "tuple[List[Dict[str, Any]], Dict[str, Any]]":
    """Enforce the chrome-v1 wire contract and map to Playwright shape.

    Returns ``(mapped, diagnostics)``. Raises:
    - CookieFormatInvalidError — unknown fields, both expirationDate and
      expires, or Playwright-style sameSite values (old-format payloads);
    - CookieDomainRejectedError — third-party cookie (backend whitelist).

    Login markers are a HEURISTIC diagnostic only: as long as at least one
    legal platform cookie maps, import is allowed. The platform's own pong
    after profile import is the only source of connected/verified.
    """
    diag = _diagnostics(received=len(cookies or []))
    mapped: List[Dict[str, Any]] = []
    # name -> (first non-empty value). Only used by the platform login
    # predicates below; values NEVER enter diagnostics or responses.
    received_values: Dict[str, str] = {}
    for c in cookies or []:
        if not isinstance(c, dict):
            diag["skipped_cookie_count"] += 1
            continue
        unknown = set(c) - CHROME_V1_FIELDS - {"partitionKey"}
        if unknown:
            raise CookieFormatInvalidError(
                f"Cookie 包含不兼容字段: {sorted(unknown)[0]}", diagnostics=diag)
        if c.get("expirationDate") is not None and "expires" in c:
            raise CookieFormatInvalidError(
                "Cookie 同时包含新旧两种过期字段", diagnostics=diag)
        if c.get("sameSite") in PLAYWRIGHT_SAME_SITE_VALUES:
            raise CookieFormatInvalidError(
                "Cookie sameSite 使用了非 Chrome 原始格式", diagnostics=diag)
        name = c.get("name")
        if name:
            value = c.get("value")
            if isinstance(value, str) and value:
                received_values.setdefault(name, value)
        if c.get("partitionKey"):
            diag["skipped_cookie_count"] += 1
            continue
        domain = (c.get("domain") or "").lower()
        if not cookie_domain_allowed(platform, domain):
            diag["rejected_cookie_count"] += 1
            raise CookieDomainRejectedError(diagnostics=diag)
        m = map_chrome_cookie(c)
        if m is None:
            diag["skipped_cookie_count"] += 1
            continue
        mapped.append(m)
        diag["accepted_cookie_count"] += 1

    markers = _login_marker_presence(platform, received_values)
    diag["login_marker_presence"] = markers
    # Compat heuristic field: at least one whitelisted login marker was
    # received. It is a diagnostic only — it never blocks import and never
    # implies a logged-in session.
    diag["required_cookie_present"] = any(markers.values())
    return mapped, diag


def _login_marker_presence(platform: str,
                           received_values: Dict[str, str]) -> Dict[str, bool]:
    """Presence booleans for the platform's whitelisted login markers —
    NAME + true/false only, values never leave this module. A marker is
    present when its name was received with a non-empty value. This is a
    diagnostic, NOT a login verdict: e.g. zhihu often only has z_c0 before
    the browser visits the official site (d_c0 is generated by the page).
    """
    return {
        name: bool(received_values.get(name))
        for name in LOGIN_MARKER_NAMES.get(platform, ())
    }


# ── Profile paths ───────────────────────────────────────────────────────

def profile_dir_for(platform: str) -> Path:
    """Profile path is always generated from the backend whitelist."""
    name = PLATFORM_PROFILE_DIRS.get(platform)
    if not name:
        raise PlatformError(f"不支持的平台: {platform}")
    return BROWSER_DATA_DIR / name


def _resolve_profile_path(platform: str) -> Path:
    """Resolve and verify the profile path stays inside browser_data."""
    resolved = profile_dir_for(platform).resolve()
    base = BROWSER_DATA_DIR.resolve()
    if str(resolved) != str(base) and not str(resolved).startswith(str(base) + os.sep):
        raise SessionImportError("非法路径：profile 不在 browser_data 目录内")
    return resolved


# ── In-memory platform state ────────────────────────────────────────────

_platform_state: Dict[str, Dict[str, Any]] = {}
_state_lock = asyncio.Lock()


def _fresh_state() -> Dict[str, Any]:
    return {
        "status": "disconnected",
        "verified": False,
        "display_name": None,
        "last_verified_at": None,
        "safe_error_code": None,
        "safe_message": None,
        "browser_backend": None,
    }


def _state_of(platform: str) -> Dict[str, Any]:
    if platform not in PLATFORM_PROFILE_DIRS:
        raise PlatformError(f"不支持的平台: {platform}")
    st = _platform_state.get(platform)
    if st is None:
        st = _fresh_state()
        # A leftover profile only means "exists locally, not yet verified" —
        # never "connected": connected implies verified=True.
        if profile_dir_for(platform).is_dir():
            st["status"] = "unverified"
        _platform_state[platform] = st
    # Invariant: connected requires verified. Enforced on every read.
    if st.get("status") == "connected" and not st.get("verified"):
        st["status"] = "unverified"
    return st


def _set_state(platform: str, **kw: Any) -> Dict[str, Any]:
    st = _state_of(platform)
    for k, v in kw.items():
        st[k] = v
    return st


# ── Browser resolution (server side) ────────────────────────────────────

async def _launch_profile_context(platform: str):
    """Open the platform's headless persistent profile context.

    Uses the shared resolver (CUSTOM_BROWSER_PATH > Chrome > Edge > bundled
    Chromium); exactly one of executable_path/channel is used. Returns
    (playwright, context, backend_name) — caller must close the context and
    stop the playwright instance.
    """
    from playwright.async_api import async_playwright
    from tools.browser_launcher import (
        BrowserUnavailableError, resolve_playwright_browser,
    )

    profile_dir = _resolve_profile_path(platform)
    profile_dir.mkdir(parents=True, exist_ok=True)

    playwright = await async_playwright().start()
    try:
        chromium = playwright.chromium
        executable_path, channel, backend = resolve_playwright_browser()
        if backend == "playwright-chromium":
            bundled_path = chromium.executable_path
            if not bundled_path or not os.path.isfile(bundled_path):
                raise BrowserUnavailableError(
                    "没有找到可用的浏览器，请安装 Chrome 或 Edge 后重试")
            executable_path = bundled_path
        kwargs: Dict[str, Any] = {
            "user_data_dir": str(profile_dir),
            "accept_downloads": True,
            "headless": True,
            "viewport": {"width": 1920, "height": 1080},
        }
        if executable_path:
            kwargs["executable_path"] = executable_path
        elif channel:
            kwargs["channel"] = channel
        context = await chromium.launch_persistent_context(**kwargs)
        return playwright, context, backend
    except Exception:
        await playwright.stop()
        raise


# ── Per-platform profile lock ───────────────────────────────────────────

_profile_locks: Dict[str, asyncio.Lock] = {}


def _profile_lock(platform: str) -> asyncio.Lock:
    lock = _profile_locks.get(platform)
    if lock is None:
        lock = asyncio.Lock()
        _profile_locks[platform] = lock
    return lock


# ── Public operations ───────────────────────────────────────────────────

def get_accounts() -> List[Dict[str, Any]]:
    """Per-platform account status — never includes secrets or paths."""
    out: List[Dict[str, Any]] = []
    for platform in ("xhs", "douyin", "bilibili", "zhihu"):
        st = _state_of(platform)
        out.append({
            "platform": platform,
            "profile_exists": profile_dir_for(platform).is_dir(),
            "status": st["status"],
            "verified": bool(st["verified"]),
            "display_name": st["display_name"],
            "last_verified_at": st["last_verified_at"],
            "safe_error_code": st["safe_error_code"],
            "safe_message": st["safe_message"],
            "browser_backend": st["browser_backend"],
        })
    return out


async def sync_platform_cookies(
    platform: str,
    cookies: List[Dict[str, Any]],
    *,
    cookie_format: str,
    extension_protocol_version: int = 0,
    browser_cookie_store_count: int = 0,
) -> Dict[str, Any]:
    """Import chrome-v1 cookies, then verify the session within a bound.

    The extension sends raw Chrome cookies exactly once; the backend performs
    the single Chrome -> Playwright mapping here. Import success is NOT login
    verification — the profile is re-opened and checked with the platform's
    own pong (bounded by SYNC_VERIFY_TIMEOUT_SECONDS). On timeout the verify
    keeps running in the background and this returns status=verifying.
    """
    if platform not in PLATFORM_PROFILE_DIRS:
        raise PlatformError(f"不支持的平台: {platform}")
    if cookie_format != COOKIE_FORMAT_CHROME_V1:
        raise CookieFormatInvalidError(
            "Cookie 格式不兼容，请重新加载浏览器扩展后再试")
    # Structured protocol check: an old/new extension must get its own error
    # code, not a generic session_import_failed.
    if extension_protocol_version != EXTENSION_PROTOCOL_VERSION:
        raise ExtensionProtocolOutdatedError()

    mapped, diag = validate_chrome_v1_cookie_list(platform, cookies)
    diag["browser_cookie_store_count"] = max(0, int(browser_cookie_store_count or 0))
    if not mapped:
        raise SessionImportError("没有可导入的合法 Cookie", diagnostics=diag)

    # 同步入口在改变状态（syncing）之前捕获此前状态 —— 之后 _import 和
    # verify 都读不到 "connected"（已被覆盖）。显式传给本次验证，绝不依赖
    # 已被覆盖的全局状态，并发时也不会串用其他平台/上一任务的状态。
    previous_status = _state_of(platform).get("status")
    await _import_profile_cookies(platform, mapped, diag)

    result = await _bounded_verify(platform, diag, previous_status=previous_status)
    counts = {k: diag[k] for k in (
        "received_cookie_count", "accepted_cookie_count",
        "skipped_cookie_count", "rejected_cookie_count",
        "required_cookie_present", "login_marker_presence",
        "browser_cookie_store_count", "sync_stage")}
    if result is None:  # bound expired — verification continues in background
        return {
            "success": True, "platform": platform, "verified": False,
            "status": "verifying", "safe_error_code": None,
            "safe_message": "会话已导入，仍在后台验证", **counts,
        }
    status = result.get("status", "unverified")
    safe_error_code = result.get("safe_error_code")
    safe_message = result.get("safe_message")
    if result.get("verified"):
        return {
            "success": True, "platform": platform, "verified": True,
            "status": status, "safe_error_code": safe_error_code,
            "safe_message": safe_message or "会话导入成功且验证通过",
            **counts, "sync_stage": "completed",
        }
    if status == "failed":
        # Real technical failure during verification (browser launch etc.):
        # still a hard failure, not "unverified".
        return {
            "success": False, "platform": platform, "verified": False,
            "status": "failed", "safe_error_code": safe_error_code or "login_verification_failed",
            "safe_message": safe_message or "会话验证失败，请重新同步", **counts,
        }
    if status == "unavailable":
        # 验证过程不可用（网络/超时/403 风控/导航失败）：不得声称未登录或
        # 会话失效，只报告"当前无法验证登录状态"。
        return {
            "success": True, "platform": platform, "verified": False,
            "status": "unavailable",
            "safe_error_code": safe_error_code or "login_verification_unavailable",
            "safe_message": safe_message or "当前无法验证登录状态，仍可尝试搜索或稍后重新验证",
            **counts,
        }
    # 明确未登录（expired / unverified）——会话已导入，公开搜索仍可尝试；
    # 只有真实验证决定 connected vs unverified vs expired。
    return {
        "success": True, "platform": platform, "verified": False,
        "status": status,
        "safe_error_code": safe_error_code or "login_not_verified",
        "safe_message": safe_message or (
            "会话已导入，但尚未确认账号登录。"
            "你仍可以尝试搜索；如搜索需要登录，再重新同步。"),
        **counts,
    }


async def _import_profile_cookies(
    platform: str, mapped: List[Dict[str, Any]], diag: Dict[str, Any],
) -> None:
    """Clear the platform's OWN stale cookies in the profile, then import.

    Never deletes the whole profile dir, never touches other platforms'
    cookies, and never touches the user's live browser.
    """
    diag["sync_stage"] = "profile_import"
    async with _profile_lock(platform):
        _set_state(platform, status="syncing",
                   safe_error_code=None, safe_message=None)
        playwright = None
        context = None
        try:
            playwright, context, backend = await _launch_profile_context(platform)
            await _clear_platform_cookies(context, platform)
            await context.add_cookies(mapped)
            # Visit the home page once so the browser persists the cookies
            # into the profile before we close.
            try:
                page = await context.new_page()
                await page.goto(
                    PLATFORM_HOME_URLS[platform],
                    wait_until="domcontentloaded", timeout=15000)
            except Exception:
                pass
        except Exception as exc:
            _set_state(platform, status="failed",
                       safe_error_code="session_import_failed",
                       safe_message="会话导入失败，请重新同步")
            raise SessionImportError("会话导入失败", diagnostics=diag) from exc
        finally:
            if context is not None:
                try:
                    await context.close()
                except Exception:
                    pass
            if playwright is not None:
                try:
                    await playwright.stop()
                except Exception:
                    pass
        _set_state(platform, browser_backend=backend)


async def _clear_platform_cookies(context, platform: str) -> None:
    """Remove ONLY this platform's cookies from the profile before import.

    Playwright's BrowserContext.clear_cookies is KEYWORD-ONLY
    (clear_cookies(*, name=None, domain=None, path=None)); passing a
    positional list raises TypeError. That error used to be swallowed here,
    so stale cookies were never actually cleared. Now nothing is swallowed:
    any read/clear failure propagates to _import_profile_cookies and becomes
    session_import_failed — a visible, honest failure.
    """
    urls = PLATFORM_COOKIE_URLS.get(platform, [])
    if not urls:
        return
    existing = await context.cookies(urls)
    domains = {
        d for d in (c.get("domain") for c in existing)
        if d and cookie_domain_allowed(platform, d)  # only whitelisted domains
    }
    for d in domains:
        await context.clear_cookies(domain=d)


# ONE bounded verify task per platform at a time, held by a strong reference
# here: asyncio.wait_for's timeout only cancels the shield, NOT the task, so
# without this dict the task could be garbage-collected mid-flight or —
# worse — a new verify could be spawned while the old one is still running.
# The task removes itself on completion; cancel_verify_tasks() is called on
# app shutdown.
_verify_tasks: Dict[str, asyncio.Task] = {}


async def _bounded_verify(
    platform: str, diag: Dict[str, Any],
    previous_status: Optional[str] = None,
) -> Optional[Dict[str, Any]]:
    """Verify the just-imported profile within SYNC_VERIFY_TIMEOUT_SECONDS.

    Returns the full verify_platform result dict; None when the bound
    expired (the verify task keeps running and the caller reports
    status=verifying). ``previous_status`` is captured by the sync entry
    point BEFORE status="syncing" overwrites it — without it, re-syncing a
    connected account would always see was_connected=False. Exactly one
    verify task exists per platform: a timeout keeps the original task
    running and a later call reuses it instead of spawning a duplicate.
    """
    diag["sync_stage"] = "verification"
    task = _verify_tasks.get(platform)
    if task is None or task.done():
        task = asyncio.create_task(
            verify_platform(platform, previous_status=previous_status))
        _verify_tasks[platform] = task
        task.add_done_callback(_make_verify_done_cb(platform))
    try:
        result = await asyncio.wait_for(
            asyncio.shield(task), timeout=SYNC_VERIFY_TIMEOUT_SECONDS)
        return result
    except asyncio.TimeoutError:
        return None
    except Exception:
        # verify_platform 内部异常路径已把状态写成 failed；这里如实返回，
        # 让 sync 报告 login_verification_failed，而不是当作"未登录"。
        return {
            "success": False, "platform": platform,
            "verified": False, "status": "failed",
            "safe_error_code": "login_verification_failed",
            "safe_message": "会话验证失败，请重新同步",
        }


def _make_verify_done_cb(platform: str):
    def _on_done(task: asyncio.Task) -> None:
        if _verify_tasks.get(platform) is task:
            _verify_tasks.pop(platform, None)
    return _on_done


def is_verify_active(platform: str) -> bool:
    """该平台是否存在仍在运行的后台验证任务。

    Round 11 竞态防护：有界验证超时（30s）后任务在后台继续跑，期间再次
    sync / verify / delete 同一平台会与后台任务并发操作同一 profile ——
    路由必须返回 409 verification_in_progress，不允许两个任务顺序覆盖
    同一个平台 profile。任务完成（done callback 弹出）后恢复可操作。
    """
    task = _verify_tasks.get(platform)
    return task is not None and not task.done()


async def cancel_verify_tasks() -> None:
    """Cancel any in-flight bounded verify tasks (app shutdown)."""
    pending = [t for t in _verify_tasks.values() if not t.done()]
    for t in pending:
        t.cancel()
    if pending:
        await asyncio.gather(*pending, return_exceptions=True)


async def verify_platform(platform: str, previous_status: Optional[str] = None) -> Dict[str, Any]:
    """Open the profile headless and verify the session via the platform's
    own pong / check_login_state. Profile dir existing is NOT proof of login.

    ``previous_status``: the caller (sync_platform_cookies) captures the
    pre-sync state BEFORE it writes status="syncing" — reading the global
    state here would always see "syncing"/"verifying" and was_connected
    would be dead. When None (direct /verify endpoint), falls back to
    reading the current global state.
    """
    if platform not in PLATFORM_PROFILE_DIRS:
        raise PlatformError(f"不支持的平台: {platform}")

    async with _profile_lock(platform):
        # 在把状态改成 verifying 之前记录"此前是否已确认登录"——否则
        # was_connected 恒为 False，expired 分支永远走不到。显式传入的
        # previous_status 优先（同步入口在写入 syncing 之前捕获）。
        if previous_status is not None:
            was_connected = previous_status == "connected"
        else:
            was_connected = _state_of(platform).get("status") == "connected"
        _set_state(platform, status="verifying",
                   safe_error_code=None, safe_message=None)
        playwright = None
        context = None
        verdict = "unavailable"
        backend = None
        try:
            playwright, context, backend = await _launch_profile_context(platform)
            # Platform client for pong — production function, not test logic.
            verdict = await _pong_with_profile(platform, context)
        except Exception as exc:
            # 真实验证阶段的技术失败（浏览器启动等）→ failed，不是 unverified。
            _set_state(platform, status="failed", verified=False,
                       safe_error_code="login_verification_failed",
                       safe_message="会话验证失败，请重新同步")
            raise SessionImportError("会话验证失败") from exc
        finally:
            if context is not None:
                try:
                    await context.close()
                except Exception:
                    pass
            if playwright is not None:
                try:
                    await playwright.stop()
                except Exception:
                    pass

        # 兼容旧式布尔（True/False monkeypatch 与内部调用点）
        if verdict is True or verdict == "verified":
            _set_state(platform, status="connected", verified=True,
                       display_name=None,
                       last_verified_at=datetime.now(timezone.utc).isoformat(),
                       safe_error_code=None, safe_message=None,
                       browser_backend=backend)
            return {
                "success": True,
                "platform": platform,
                "verified": True,
                "status": "connected",
                "safe_error_code": None,
                "safe_message": "会话验证通过",
            }

        # 三态：验证过程不可用（网络/超时/403 风控/导航失败/客户端技术
        # 错误）→ 无法得出登录结论 —— 不得声称"未登录"或"会话失效"。
        # Round 11 不变量（推翻 Round 10 的"unavailable 保持 connected"）：
        # verified=true 只表示"本次真实验证成功"，unavailable 绝不是成功；
        # 无论此前是否 connected，一律 status=unavailable、verified=False、
        # 不标记 expired、不清除已导入 profile、保留 last_verified_at。
        if verdict == "unavailable":
            msg = "当前无法验证登录状态，仍可尝试搜索或稍后重新验证"
            _set_state(platform, status="unavailable", verified=False,
                       safe_error_code="login_verification_unavailable",
                       safe_message=msg, browser_backend=backend)
            return {
                "success": True, "platform": platform,
                "verified": False, "status": "unavailable",
                "safe_error_code": "login_verification_unavailable",
                "safe_message": msg,
            }

        # 明确未登录（pong=False）：之前曾确认过登录，现在真实验证明确
        # 失效 → expired；从未确认过 → unverified（会话已导入，只是还没
        # 确认登录，公开搜索仍可尝试）。
        if was_connected:
            _set_state(platform, status="expired", verified=False,
                       safe_error_code="login_required",
                       safe_message="会话已失效，请到账号设置重新同步",
                       browser_backend=backend)
            return {
                "success": True,
                "platform": platform,
                "verified": False,
                "status": "expired",
                "safe_error_code": "login_required",
                "safe_message": "会话已失效，请到账号设置重新同步",
            }
        _set_state(platform, status="unverified", verified=False,
                   safe_error_code="login_not_verified",
                   safe_message="会话已导入，但尚未确认账号登录。"
                               "你仍可以尝试搜索；如搜索需要登录，再重新同步。",
                   browser_backend=backend)
        return {
            "success": True,
            "platform": platform,
            "verified": False,
            "status": "unverified",
            "safe_error_code": "login_not_verified",
            "safe_message": "会话已导入，但尚未确认账号登录。"
                            "你仍可以尝试搜索；如搜索需要登录，再重新同步。",
        }


async def _pong_with_profile(platform: str, context) -> str:
    """Verify the profile session with the platform's own client.

    Three-state verdict (Round 10): "verified" = 真实确认登录；
    "not_logged_in" = 平台检查明确返回未登录；"unavailable" = 网络错误、
    超时、403 风控、导航失败或客户端技术错误 —— 无法得出登录结论，
    绝不能当作"明确未登录"。返回 False/True 的旧式布尔调用点由
    verify_platform 兼容处理。
    """
    urls = PLATFORM_COOKIE_URLS.get(platform)
    if not urls:
        return "unavailable"
    try:
        cookies = await context.cookies(urls)
    except Exception:
        # cookie 读取本身失败（浏览器/context 技术问题）→ 无法验证
        return "unavailable"
    if not cookies:
        return "not_logged_in"
    cookie_dict = {c["name"]: c["value"] for c in cookies}
    cookie_str = "; ".join(f"{c['name']}={c['value']}" for c in cookies)

    if platform == "xhs":
        try:
            from media_platform.xhs.client import XiaoHongShuClient
            client = XiaoHongShuClient(
                proxy=None, headers={
                    "User-Agent": _UA, "Cookie": cookie_str,
                }, playwright_page=None, cookie_dict=cookie_dict)
            # raise_on_error=True：平台 pong 不再吞异常 —— 网络错误/超时/
            # 403 风控/接口异常会传播到这里被 except 归为 unavailable；
            # 只有 200 + 明确无登录（success=false）才返回 False →
            # not_logged_in。默认 False 的 console/login 行为保持不变。
            return "verified" if bool(await client.pong(raise_on_error=True)) else "not_logged_in"
        except Exception:
            return "unavailable"
    if platform == "douyin":
        # DouYinClient.pong 依赖 playwright_page 读 localStorage（快路径），
        # 绝不能传 None —— 从该 profile context 创建真实页面并打开官网，
        # 让页面带上刚导入的 Cookie；导航失败 = 无法访问官方站点确认登录
        # → unavailable（不是"明确未登录"）。
        try:
            from media_platform.douyin.client import DouYinClient
            page = await context.new_page()
        except Exception:
            return "unavailable"
        try:
            try:
                await page.goto(
                    PLATFORM_HOME_URLS[platform],
                    wait_until="domcontentloaded", timeout=15000)
            except Exception:
                return "unavailable"
            client = DouYinClient(
                proxy=None, headers={
                    "User-Agent": _UA, "Cookie": cookie_str,
                }, playwright_page=page, cookie_dict=cookie_dict)
            try:
                # douyin pong 本身不吞异常（localStorage 快路径除外）：
                # cookies 读取失败会直接传播 → unavailable。
                return "verified" if bool(await client.pong(context)) else "not_logged_in"
            except Exception:
                return "unavailable"
        finally:
            try:
                await page.close()
            except Exception:
                pass
    if platform == "bilibili":
        try:
            from media_platform.bilibili.client import BilibiliClient
            client = BilibiliClient(
                proxy=None, headers={
                    "User-Agent": _UA, "Cookie": cookie_str,
                }, playwright_page=None, cookie_dict=cookie_dict)
            # raise_on_error=True：403/-412 风控/5xx/网络异常传播 →
            # unavailable；DataFetchError(-101) 平台明确未登录码 → False →
            # not_logged_in；isLogin=false → not_logged_in。
            return "verified" if bool(await client.pong(raise_on_error=True)) else "not_logged_in"
        except Exception:
            return "unavailable"
    if platform == "zhihu":
        # 知乎时序（联调结论）：d_c0 往往只在真实访问知乎页面后由浏览器
        # 生成 —— 初始只有 z_c0 时不能直接 pong（_pre_headers 会抛
        # "d_c0 not found in cookies"）。顺序必须是：
        #   1) 创建真实 page；2) 访问官网；3) 访问搜索页；
        #   4) 从 context 重新读取 Cookie；5) 用刷新后的 cookie 构建
        #   client；6) 现在再检查 d_c0 并调用 pong；
        #   7) page 在 finally 中关闭。
        # 官网导航失败 → unavailable（无法访问官方站点确认登录）；
        # 搜索页导航失败 → 继续（官网已访问，d_c0 可能已生成）；
        # 导航后仍无 d_c0 → pong 返回 False → not_logged_in，
        # 绝不抛出内部异常。
        try:
            from media_platform.zhihu.client import ZhiHuClient
            page = await context.new_page()
        except Exception:
            return "unavailable"
        try:
            try:
                await page.goto(
                    PLATFORM_HOME_URLS[platform],
                    wait_until="domcontentloaded", timeout=15000)
            except Exception:
                return "unavailable"
            try:
                await page.goto(
                    "https://www.zhihu.com/search?q=python&search_source=Guess"
                    "&utm_content=search_hot&type=content",
                    wait_until="domcontentloaded", timeout=15000)
            except Exception:
                pass
            try:
                refreshed = await context.cookies(urls)
                refreshed_dict = {c["name"]: c["value"] for c in refreshed}
                refreshed_str = "; ".join(
                    f"{c['name']}={c['value']}" for c in refreshed)
                client = ZhiHuClient(
                    proxy=None, headers={
                        "User-Agent": _UA, "cookie": refreshed_str,
                    }, playwright_page=page, cookie_dict=refreshed_dict)
                # raise_on_error=True：ForbiddenError（403 风控/验证码）、
                # DataFetchError、超时等传播 → unavailable；200 响应但无
                # uid/name（明确无用户）→ not_logged_in。
                return "verified" if bool(await client.pong(raise_on_error=True)) else "not_logged_in"
            except Exception:
                return "unavailable"
        finally:
            try:
                await page.close()
            except Exception:
                pass
    return "unavailable"


_UA = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/128.0.0.0 Safari/537.36"
)


async def delete_platform_session(platform: str) -> Dict[str, Any]:
    """Delete the platform's profile directory (browser_data only)."""
    if platform not in PLATFORM_PROFILE_DIRS:
        raise PlatformError(f"不支持的平台: {platform}")

    async with _profile_lock(platform):
        target = _resolve_profile_path(platform)
        if target.is_dir():
            shutil.rmtree(target)
        _set_state(platform, status="disconnected", verified=False,
                   display_name=None, last_verified_at=None,
                   safe_error_code=None, safe_message=None)
        return {
            "success": True,
            "platform": platform,
            "safe_error_code": None,
            "safe_message": "登录状态已清除",
        }
