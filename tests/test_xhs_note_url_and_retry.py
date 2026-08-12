# -*- coding: utf-8 -*-
# Copyright (c) 2025 relakkes@gmail.com
#
# This file is part of MediaCrawler project.
# Licensed under NON-COMMERCIAL LEARNING LICENSE 1.1

"""XHS note URL construction and RetryError HTML fallback — production
functions ``aggregate_search.adapters.xhs.build_note_url`` /
``XhsAdapter.adapt`` and ``media_platform.xhs.core.XiaoHongShuCrawler.
get_note_detail_async_task``.
"""

import asyncio
import os
import sys
from urllib.parse import parse_qs, urlsplit

import pytest
from tenacity import RetryError

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import config
from base.crawler_runtime import CrawlerRuntimeOptions
from aggregate_search.adapters import XhsAdapter
from aggregate_search.adapters.xhs import (
    XHS_ALLOWED_HOSTS, XHS_EXPLORE_URL, build_note_url,
)
from media_platform.xhs.core import XiaoHongShuCrawler
from media_platform.xhs.exception import DataFetchError

# ── build_note_url (production function) ────────────────────────────────

def test_note_url_with_token_and_source_encoded():
    """xsec params go through urllib.parse.urlencode — never hand-joined."""
    url = build_note_url("abc123", xsec_token="tok en&x=1",
                         xsec_source="pc_search")
    parts = urlsplit(url)
    assert parts.netloc == "www.xiaohongshu.com"
    qs = parse_qs(parts.query)
    assert qs["xsec_token"] == ["tok en&x=1"]       # properly encoded
    assert qs["xsec_source"] == ["pc_search"]


def test_note_url_default_source_is_pc_search():
    url = build_note_url("abc123", xsec_token="tok")
    qs = parse_qs(urlsplit(url).query)
    assert qs["xsec_source"] == ["pc_search"]


def test_note_url_existing_url_wins_when_allowed():
    existing = "https://www.xiaohongshu.com/explore/other_id"
    url = build_note_url("abc123", note_url=existing, xsec_token="tok")
    assert url == existing


def test_note_url_external_domain_rejected():
    """A note_url from an external domain must be ignored."""
    url = build_note_url("abc123",
                         note_url="https://evil.example.com/explore/abc123",
                         xsec_token="tok")
    assert urlsplit(url).netloc == "www.xiaohongshu.com"


def test_note_url_no_token_plain_explore():
    url = build_note_url("abc123")
    assert url == XHS_EXPLORE_URL.format(note_id="abc123")


def test_note_url_empty_token_falls_back_to_plain():
    url = build_note_url("abc123", xsec_token="")
    assert "xsec" not in urlsplit(url).query


def test_allowed_hosts_set_matches_requirements():
    assert XHS_ALLOWED_HOSTS == {
        "www.xiaohongshu.com", "xiaohongshu.com", "www.rednote.com"}


def test_adapter_result_url_domain_always_official():
    """Every adapted ResultCard URL must sit on an allowed xhs host."""
    adapter = XhsAdapter()
    results = adapter.adapt([{
        "note_id": "n1",
        "title": "T",
        "xsec_token": "tok&x=1",
        "note_url": "https://evil.example.com/explore/n1",
    }], keyword="k")
    assert len(results) == 1
    host = urlsplit(results[0].url).netloc
    assert host in XHS_ALLOWED_HOSTS


# ── get_note_detail_async_task RetryError fallback (production) ─────────

class _FakeClient:
    """Pluggable xhs client for the production crawler method."""

    def __init__(self, api_impl, html_impl):
        self._api = api_impl
        self._html = html_impl

    async def get_note_by_id(self, note_id, xsec_source, xsec_token):
        return await self._api(note_id, xsec_source, xsec_token)

    async def get_note_by_id_from_html(self, note_id, xsec_source,
                                       xsec_token, enable_cookie=True):
        return await self._html(note_id, xsec_source, xsec_token)


def _make_crawler(monkeypatch, api_impl, html_impl, strict):
    monkeypatch.setattr(config, "CRAWLER_MAX_SLEEP_SEC", 0)
    crawler = XiaoHongShuCrawler()
    crawler.xhs_client = _FakeClient(api_impl, html_impl)
    crawler.runtime_options = CrawlerRuntimeOptions(strict_errors=strict)
    return crawler


def _retry_error():
    return RetryError(last_attempt=None)


async def _run(crawler, note_id="n1"):
    return await crawler.get_note_detail_async_task(
        note_id, "pc_search", "tok", asyncio.Semaphore(1))


def test_retry_error_then_html_success(monkeypatch):
    """RetryError from API + successful HTML fallback → note returned
    (with xsec fields merged) — the RetryError must NOT kill the note."""
    async def api(*a):
        raise _retry_error()

    async def html(*a):
        return {"note_id": "n1", "title": "From HTML"}

    crawler = _make_crawler(monkeypatch, api, html, strict=True)
    result = asyncio.run(_run(crawler))
    assert result is not None
    assert result["title"] == "From HTML"
    assert result["xsec_token"] == "tok"
    assert result["xsec_source"] == "pc_search"


def test_retry_error_html_empty_strict_raises(monkeypatch):
    """RetryError + empty HTML + strict_errors=True → DataFetchError."""
    async def api(*a):
        raise _retry_error()

    async def html(*a):
        return None

    crawler = _make_crawler(monkeypatch, api, html, strict=True)
    with pytest.raises(DataFetchError):
        asyncio.run(_run(crawler))


def test_retry_error_html_empty_lenient_returns_none(monkeypatch):
    """RetryError + empty HTML + strict_errors=False → None (skip)."""
    async def api(*a):
        raise _retry_error()

    async def html(*a):
        return None

    crawler = _make_crawler(monkeypatch, api, html, strict=False)
    assert asyncio.run(_run(crawler)) is None


def test_api_empty_still_tries_html(monkeypatch):
    """Empty API result (no exception) must still hit the HTML fallback."""
    calls = []

    async def api(*a):
        return None

    async def html(*a):
        calls.append(a)
        return {"note_id": "n1", "title": "T"}

    crawler = _make_crawler(monkeypatch, api, html, strict=True)
    result = asyncio.run(_run(crawler))
    assert result is not None
    assert calls, "HTML fallback was never attempted"
