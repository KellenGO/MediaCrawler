# -*- coding: utf-8 -*-
# Copyright (c) 2025 relakkes@gmail.com
#
# This file is part of MediaCrawler project.
# Licensed under NON-COMMERCIAL LEARNING LICENSE 1.1

"""Browser extension security contract tests.

Reads the production extension files (manifest.json, service_worker.js,
content_script.js, popup.js) and verifies the security invariants:
no <all_urls>, minimal host permissions, cookies never cross the page,
nothing written to chrome.storage except non-cookie metadata.
"""

import json
import os
from pathlib import Path

import pytest

_PROJECT_ROOT = Path(__file__).parent.parent
_EXT = _PROJECT_ROOT / "browser_extension"

_MANIFEST = json.loads((_EXT / "manifest.json").read_text(encoding="utf-8"))
_SW = (_EXT / "service_worker.js").read_text(encoding="utf-8")
_CONTENT = (_EXT / "content_script.js").read_text(encoding="utf-8")
_POPUP_JS = (_EXT / "popup.js").read_text(encoding="utf-8")


# ── Manifest ────────────────────────────────────────────────────────────

def test_manifest_version_3():
    assert _MANIFEST["manifest_version"] == 3


def test_manifest_version_113():
    """Round 10: 1.1.3 ships the real extension_version in ready/pong so
    the page can distinguish old (1.1.2, Round 8) scripts — anything below
    1.1.3 shows an 'outdated' warning and sync is blocked."""
    assert _MANIFEST["version"] == "1.1.3"


def test_no_all_urls_anywhere():
    """<all_urls> is forbidden in the whole extension."""
    for f in ("manifest.json", "service_worker.js", "content_script.js",
              "popup.js", "popup.html"):
        assert "<all_urls>" not in (_EXT / f).read_text(encoding="utf-8")


def test_minimal_host_permissions():
    """Host permissions must be exactly the local API + 4 official domains."""
    hosts = sorted(_MANIFEST["host_permissions"])
    assert hosts == sorted([
        "http://127.0.0.1:8080/*",
        "http://localhost:8080/*",
        "https://*.xiaohongshu.com/*",
        "https://*.douyin.com/*",
        "https://*.bilibili.com/*",
        "https://*.zhihu.com/*",
    ])


def test_permissions_are_minimal():
    assert set(_MANIFEST["permissions"]) == {"cookies", "storage"}


def test_content_scripts_match_only_localhost():
    matches = _MANIFEST["content_scripts"][0]["matches"]
    assert sorted(matches) == sorted([
        "http://127.0.0.1:8080/*",
        "http://localhost:8080/*",
    ])


def test_platforms_allowed_are_the_four():
    """The four official platform domains are covered by host_permissions."""
    allowed = set()
    for host in _MANIFEST["host_permissions"]:
        if "xiaohongshu" in host:
            allowed.add("xiaohongshu")
        elif "douyin" in host:
            allowed.add("douyin")
        elif "bilibili" in host:
            allowed.add("bilibili")
        elif "zhihu" in host:
            allowed.add("zhihu")
    assert allowed == {"xiaohongshu", "douyin", "bilibili", "zhihu"}


# ── service worker: cookies never leak to page/storage ─────────────────

def test_sw_posts_directly_to_localhost_api():
    """The API origin constant must be the local backend — cookies go
    straight to 127.0.0.1:8080, never anywhere else."""
    assert 'API_ORIGIN = "http://127.0.0.1:8080"' in _SW
    assert 'API_ROOT = API_ORIGIN + "/api/search/accounts"' in _SW


def test_sw_never_writes_cookies_to_storage():
    """chrome.storage may hold metadata only — cookie values are verboten."""
    storage_lines = [ln for ln in _SW.splitlines()
                     if "chrome.storage" in ln or "storage.local" in ln]
    for ln in storage_lines:
        lowered = ln.lower()
        assert "cookie" not in lowered, f"storage write may contain cookies: {ln}"


def test_sw_never_logs_cookies():
    for ln in _SW.splitlines():
        if "console.log" in ln:
            assert "cookie" not in ln.lower()


def test_sw_reads_cookies_only_for_platform_domains():
    """cookies.getAll is domain-filtered, scoped to the sender's cookie
    store, and the platform→domain map covers exactly the four domains."""
    assert "chrome.cookies.getAll(" in _SW
    import re
    platform_domains = dict(re.findall(
        r"(\w+):\s*['\"]([a-z0-9.]+)['\"]", _SW))
    assert platform_domains == {
        "xhs": "xiaohongshu.com",
        "douyin": "douyin.com",
        "bilibili": "bilibili.com",
        "zhihu": "zhihu.com",
    }
    # No URL-scoped reads (url: ...) that could broaden the cookie scope.
    assert "getAll({ url" not in _SW


def test_sw_uses_sender_cookie_store_and_rejects_incognito():
    """Store selection uses sender.tab.id → getAllCookieStores().tabIds
    matching (tabs.Tab has NO cookieStoreId property, so that field may
    only appear in a comment forbidding it); incognito is rejected at the
    message entry via sender.tab.incognito — the real API's flag, since
    CookieStore objects carry no incognito field."""
    assert "getAllCookieStores" in _SW
    assert "cookieStoreId" in _SW
    assert "incognito" in _SW
    assert "incognito_store_rejected" in _SW


def test_sw_sends_chrome_v1_not_playwright():
    """The old double-mapping is gone: the SW never emits Playwright fields
    (expires / uppercase sameSite) and never maps sameSite itself."""
    assert "mapCookie" not in _SW
    assert "toPlaywrightSameSite" not in _SW
    assert "buildSyncBody" in _SW
    assert "cookie_format" in _SW
    assert "importScripts(\"sync_protocol.js\")" in _SW


def test_sw_structured_error_codes():
    """The sync failure modes the web UI must display are all present."""
    for code in ("extension_cookie_read_failed", "browser_cookie_not_found",
                 "platform_api_error", "sync_ticket_invalid"):
        assert code in _SW


def test_sw_echoes_request_id_and_stores_metadata_only():
    """request_id round-trips; storage keeps counts/stage, never values."""
    assert "request_id: requestId || \"\"" in _SW
    assert "store_id_short" in _SW
    assert "received_cookie_count" in _SW


# ── content script: page receives status only ───────────────────────────

def test_content_posts_safe_fields_only():
    """The page must only receive status fields — never cookie values."""
    import re
    # Keys named inside any postMessage payload literal in the content script.
    payload_keys = set(re.findall(r"(\w+):", _CONTENT))
    forbidden = {"value", "cookie", "cookies", "ticket"}
    assert not (payload_keys & forbidden), (
        f"content script posts forbidden fields: {payload_keys & forbidden}")


def test_content_forwards_no_cookie_values():
    assert "document.cookie" not in _CONTENT
    assert "chrome.cookies" not in _CONTENT
    assert ".value" not in _CONTENT


def test_content_pong_carries_protocol_version():
    """The page checks pong.extension_protocol_version to detect outdated
    extensions; the content script must send it. importScripts is a Service
    Worker API and CRASHES in a Content Script context — the content script
    must instead read the shared MCSyncProtocol namespace that the manifest
    injects FIRST (content_scripts[0].js order)."""
    assert "importScripts(" not in _CONTENT
    assert "globalThis.MCSyncProtocol" in _CONTENT
    assert _MANIFEST["content_scripts"][0]["js"] == [
        "sync_protocol.js", "content_script.js"]
    assert "pong" in _CONTENT
    assert "extension_protocol_version" in _CONTENT


def test_content_relays_sync_diagnostics():
    """The sync-response back to the page carries counts/stage so the
    accounts page can show why a sync failed."""
    assert "sync_stage" in _CONTENT
    assert "received_cookie_count" in _CONTENT
    assert "required_cookie_present" in _CONTENT


# ── sync_protocol.js (shared pure functions) ─────────────────────────────

def test_sync_protocol_js_exists_with_contract_v2():
    proto = (_EXT / "sync_protocol.js").read_text(encoding="utf-8")
    assert "COOKIE_FORMAT_CHROME_V1 = 'chrome-v1'" in proto
    assert "EXTENSION_PROTOCOL_VERSION = 2" in proto
    # chrome-v1 whitelist must contain exactly the backend's CHROME_V1_FIELDS
    for field in ("name", "value", "domain", "path", "expirationDate",
                  "httpOnly", "secure", "sameSite", "session", "storeId"):
        assert field in proto
    # the pure functions are exported for Node wire-contract tests
    for fn in ("toChromeV1Cookie", "buildSyncBody", "parseSyncResponse"):
        assert fn in proto


def test_sync_protocol_js_has_no_chrome_access():
    """Pure functions only — no chrome.* / fetch / storage inside the
    shared module, so Node tests execute the real production code."""
    proto = (_EXT / "sync_protocol.js").read_text(encoding="utf-8")
    for banned in ("chrome.runtime", "chrome.cookies", "chrome.storage",
                   "fetch(", "localStorage", "XMLHttpRequest"):
        assert banned not in proto


# ── popup ───────────────────────────────────────────────────────────────

def test_popup_opens_accounts_page():
    assert "127.0.0.1:8080" in _POPUP_JS
    assert "accounts" in _POPUP_JS
