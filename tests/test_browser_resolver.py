# -*- coding: utf-8 -*-
# Copyright (c) 2025 relakkes@gmail.com
#
# This file is part of MediaCrawler project.
# Licensed under NON-COMMERCIAL LEARNING LICENSE 1.1

"""Browser resolution tests — all call production functions.

Covers the regression where Bilibili/Zhihu unconditionally used
``channel="chrome"`` (Chromium distribution not found error) and the
shared resolver priority: CUSTOM_BROWSER_PATH > Chrome > Edge > bundled.
"""

import os
import sys
from pathlib import Path

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import config
from tools.browser_launcher import (
    BrowserUnavailableError,
    _find_chrome_exe,
    _find_edge_exe,
    resolve_playwright_browser,
)
from aggregate_search.worker import _classify_error, _safe_error_message

_PROJECT_ROOT = Path(__file__).parent.parent
_CORE_FILES = {
    "bilibili": _PROJECT_ROOT / "media_platform" / "bilibili" / "core.py",
    "zhihu": _PROJECT_ROOT / "media_platform" / "zhihu" / "core.py",
}


# ── Resolver priority (production function) ─────────────────────────────

def test_resolver_custom_path_wins(monkeypatch, tmp_path):
    """CUSTOM_BROWSER_PATH (existing file) beats everything else."""
    fake = tmp_path / "fake_browser.exe"
    fake.write_bytes(b"MZ")
    monkeypatch.setattr("tools.browser_launcher._find_chrome_exe",
                        lambda: "C:\\chrome.exe")
    monkeypatch.setattr("tools.browser_launcher._find_edge_exe",
                        lambda: "C:\\msedge.exe")
    monkeypatch.setattr(config, "CUSTOM_BROWSER_PATH", str(fake))
    exe, channel, backend = resolve_playwright_browser()
    assert exe == str(fake)
    assert channel is None
    assert backend == "custom"


def test_resolver_chrome_wins_over_edge(monkeypatch):
    """Chrome beats Edge; channel must never be set when exe is set."""
    monkeypatch.setattr("tools.browser_launcher._find_chrome_exe",
                        lambda: "C:\\chrome.exe")
    monkeypatch.setattr("tools.browser_launcher._find_edge_exe",
                        lambda: "C:\\msedge.exe")
    monkeypatch.setattr(config, "CUSTOM_BROWSER_PATH", "")
    exe, channel, backend = resolve_playwright_browser()
    assert exe == "C:\\chrome.exe"
    assert channel is None
    assert backend == "chrome"


def test_resolver_edge_fallback(monkeypatch):
    """No Chrome → Edge; still no channel."""
    monkeypatch.setattr("tools.browser_launcher._find_chrome_exe",
                        lambda: None)
    monkeypatch.setattr("tools.browser_launcher._find_edge_exe",
                        lambda: "C:\\msedge.exe")
    monkeypatch.setattr(config, "CUSTOM_BROWSER_PATH", "")
    exe, channel, backend = resolve_playwright_browser()
    assert exe == "C:\\msedge.exe"
    assert channel is None
    assert backend == "edge"


def test_resolver_bundled_fallback(monkeypatch):
    """No Chrome/Edge → bundled Chromium (no path, no channel)."""
    monkeypatch.setattr("tools.browser_launcher._find_chrome_exe",
                        lambda: None)
    monkeypatch.setattr("tools.browser_launcher._find_edge_exe",
                        lambda: None)
    monkeypatch.setattr(config, "CUSTOM_BROWSER_PATH", "")
    exe, channel, backend = resolve_playwright_browser()
    assert exe is None
    assert channel is None
    assert backend == "playwright-chromium"


def test_resolver_ignores_missing_custom_path(monkeypatch):
    """A CUSTOM_BROWSER_PATH that is not a file must be ignored."""
    monkeypatch.setattr("tools.browser_launcher._find_chrome_exe",
                        lambda: "C:\\chrome.exe")
    monkeypatch.setattr("tools.browser_launcher._find_edge_exe",
                        lambda: None)
    monkeypatch.setattr(config, "CUSTOM_BROWSER_PATH",
                        "C:\\does-not-exist.exe")
    exe, channel, backend = resolve_playwright_browser()
    assert exe == "C:\\chrome.exe"
    assert backend == "chrome"


def test_find_chrome_edge_are_production_helpers():
    """Sanity: the helper functions are importable and return str|None."""
    for fn in (_find_chrome_exe, _find_edge_exe):
        result = fn()
        assert result is None or isinstance(result, str)


def test_browser_unavailable_error_code():
    """The worker must surface browser_unavailable, not a raw Exception."""
    err = BrowserUnavailableError()
    assert err.safe_code == "browser_unavailable"
    assert _classify_error(err) == "browser_unavailable"
    assert _safe_error_message(err) == "没有找到可用的浏览器"


# ── Production source: no unconditional channel="chrome" ────────────────

@pytest.mark.parametrize("name", ["bilibili", "zhihu"])
def test_core_never_hardcodes_channel_chrome(name):
    """The core must never unconditionally use channel="chrome"."""
    src = _CORE_FILES[name].read_text(encoding="utf-8")
    # Strip comments — the fix's own comment mentions the old bug.
    code_lines = [ln for ln in src.splitlines()
                  if not ln.strip().startswith("#")]
    code = "\n".join(code_lines)
    assert 'channel="chrome"' not in code, (
        f"{name}/core.py still hardcodes channel=\"chrome\"")
    assert "resolve_playwright_browser" in code


def test_launch_browser_uses_executable_path_not_channel(monkeypatch):
    """Bilibili launch_browser passes executable_path (never channel)
    when the resolver found a real browser."""
    from media_platform.bilibili.core import BilibiliCrawler

    recorded = {}

    class _FakeChromium:
        executable_path = "C:\\chrome.exe"

        async def launch_persistent_context(self, **kwargs):
            recorded.update(kwargs)
            return object()

    monkeypatch.setattr(
        "media_platform.bilibili.core.resolve_playwright_browser",
        lambda: ("C:\\chrome.exe", None, "chrome"))
    monkeypatch.setattr(config, "SAVE_LOGIN_STATE", True)
    monkeypatch.setattr(config, "PLATFORM", "bili")

    import asyncio
    asyncio.run(BilibiliCrawler().launch_browser(
        _FakeChromium(), None, "Mozilla/5.0 test", headless=True))

    assert recorded.get("executable_path") == "C:\\chrome.exe"
    assert "channel" not in recorded
    assert recorded.get("headless") is True


def test_launch_browser_bundled_missing_raises_unavailable(monkeypatch):
    """Bundled Chromium fallback that is not installed → browser_unavailable,
    never a launch of a non-existent channel."""
    from media_platform.bilibili.core import BilibiliCrawler

    class _FakeChromium:
        executable_path = "C:\\no-such-chromium.exe"

    monkeypatch.setattr(
        "media_platform.bilibili.core.resolve_playwright_browser",
        lambda: (None, None, "playwright-chromium"))
    monkeypatch.setattr(config, "SAVE_LOGIN_STATE", True)
    monkeypatch.setattr(config, "PLATFORM", "bili")

    import asyncio
    with pytest.raises(BrowserUnavailableError) as ei:
        asyncio.run(BilibiliCrawler().launch_browser(
            _FakeChromium(), None, "UA", headless=True))
    assert ei.value.safe_code == "browser_unavailable"


def test_launch_browser_bundled_present_uses_bundled(monkeypatch):
    """Bundled Chromium that does exist → launched via executable_path."""
    from media_platform.bilibili.core import BilibiliCrawler

    recorded = {}

    class _FakeChromium:
        executable_path = __file__  # exists on disk

        async def launch_persistent_context(self, **kwargs):
            recorded.update(kwargs)
            return object()

    monkeypatch.setattr(
        "media_platform.bilibili.core.resolve_playwright_browser",
        lambda: (None, None, "playwright-chromium"))
    monkeypatch.setattr(config, "SAVE_LOGIN_STATE", True)
    monkeypatch.setattr(config, "PLATFORM", "bili")

    import asyncio
    asyncio.run(BilibiliCrawler().launch_browser(
        _FakeChromium(), None, "UA", headless=True))

    assert recorded.get("executable_path") == __file__
    assert "channel" not in recorded


def test_zhihu_launch_browser_never_channel(monkeypatch):
    """Zhihu launch_browser also uses the shared resolver."""
    from media_platform.zhihu.core import ZhihuCrawler

    recorded = {}

    class _FakeChromium:
        executable_path = "C:\\msedge.exe"

        async def launch_persistent_context(self, **kwargs):
            recorded.update(kwargs)
            return object()

    monkeypatch.setattr(
        "media_platform.zhihu.core.resolve_playwright_browser",
        lambda: ("C:\\msedge.exe", None, "edge"))
    monkeypatch.setattr(config, "SAVE_LOGIN_STATE", True)
    monkeypatch.setattr(config, "PLATFORM", "zhihu")

    import asyncio
    asyncio.run(ZhihuCrawler().launch_browser(
        _FakeChromium(), None, "UA", headless=True))

    assert recorded.get("executable_path") == "C:\\msedge.exe"
    assert "channel" not in recorded
