# -*- coding: utf-8 -*-
# Copyright (c) 2025 relakkes@gmail.com
#
# This file is part of MediaCrawler project.
# Licensed under NON-COMMERCIAL LEARNING LICENSE 1.1

"""XHS note URL construction and safe adapter URL handling."""

import os
import sys
from urllib.parse import parse_qs, urlsplit

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import config
from aggregate_search.adapters import XhsAdapter
from aggregate_search.adapters.xhs import (
    XHS_ALLOWED_HOSTS, XHS_EXPLORE_URL, build_note_url,
)

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


def test_existing_official_note_url_keeps_search_context_for_hydration():
    adapter = XhsAdapter()
    results = adapter.adapt([{
        "id": "n1",
        "note_url": "https://www.xiaohongshu.com/explore/n1",
        "xsec_token": "tok",
        "xsec_source": "pc_search",
        "note_card": {"display_title": "标题"},
    }])
    assert "xsec_token=tok" in results[0].url
    assert "xsec_source=pc_search" in results[0].url
