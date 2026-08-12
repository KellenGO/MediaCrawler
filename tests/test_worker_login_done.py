# -*- coding: utf-8 -*-
# Copyright (c) 2025 relakkes@gmail.com
#
# This file is part of MediaCrawler project.
# Licensed under NON-COMMERCIAL LEARNING LICENSE 1.1

"""Worker login flow tests — the production ``aggregate_search.worker``
functions, with only the platform-boundary seams (crawler factory, protocol
emitters, sys.exit) swapped.

Verifies:
- exactly one ``done`` event on success / verification failure / timeout /
  generic exception / ``_WorkerExit``;
- ``succeeded`` is only emitted after re-reading cookies and a pong-verified
  session (``_verify_login_success``, production function);
- a login ``_WorkerExit`` must exit with code 1 (never 0).
"""

import asyncio
import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import aggregate_search.worker as worker
from aggregate_search.models import WorkerRequest
from aggregate_search.worker import _WorkerExit, _run_login, main

# ── Recorders ───────────────────────────────────────────────────────────

class _Events:
    def __init__(self):
        self.status = []
        self.errors = []
        self.done = []  # list so the recorder can append to it

    @property
    def counts(self):
        return {"status": len(self.status), "errors": len(self.errors),
                "done": len(self.done)}


class _FakeCtx:
    """browser_context with real cookie semantics used by _verify_login_success."""

    def __init__(self, cookies=None):
        self._cookies = cookies or []

    async def cookies(self, urls):
        return list(self._cookies)

    async def close(self):
        pass


class _FakeClient:
    def __init__(self, pong_result):
        self.cookie_dict = {}
        self.pong_called = 0
        self._pong_result = pong_result

    async def update_cookies(self, browser_context=None, urls=None):
        pass

    async def pong(self):
        self.pong_called += 1
        return self._pong_result


class _FakeCrawler:
    """Minimal crawler: what _run_login needs (search attr, browser_context,
    platform client attrs) plus a pluggable start()."""

    def __init__(self, start_impl, ctx=None, client=None):
        self.search = None
        self.browser_context = ctx
        # _CLIENT_ATTRS looks up per core platform — expose all four.
        for name in ("xhs_client", "dy_client", "bili_client", "zhihu_client"):
            setattr(self, name, client)
        self.runtime_options = None
        self.start = start_impl


def _make_factory(start_impl, ctx=None, client=None):
    class _Factory:
        @staticmethod
        def create_crawler(platform=None):
            return _FakeCrawler(start_impl, ctx, client)
    return _Factory


def _install(monkeypatch, evt: _Events, factory):
    monkeypatch.setattr(worker, "emit_status",
                        lambda *a, **k: evt.status.append((a, k)))
    monkeypatch.setattr(worker, "emit_error",
                        lambda *a, **k: evt.errors.append((a, k)))
    monkeypatch.setattr(worker, "emit_done",
                        lambda *a, **k: evt.done.append(1))
    monkeypatch.setattr("main.CrawlerFactory", factory)


# ── Exactly one done event ──────────────────────────────────────────────

def test_login_success_emits_one_done_and_verified(monkeypatch):
    """Real login path: pong-verified session → succeeded + exactly 1 done."""
    evt = _Events()
    ctx = _FakeCtx([{"name": "d_c0", "value": "abc"}])
    client = _FakeClient(pong_result=True)

    async def start():
        pass

    _install(monkeypatch, evt, _make_factory(start, ctx, client))
    asyncio.run(_run_login("j1", "zhihu"))

    assert evt.done == [1]
    assert evt.counts["errors"] == 0
    statuses = [s[0][2] for s in evt.status]
    assert "succeeded" in statuses
    assert client.pong_called == 1, "session must be pong-verified"


def test_login_verification_failure_one_done(monkeypatch):
    """pong fails → login_verification_failed + exactly 1 done, no success."""
    evt = _Events()
    ctx = _FakeCtx([{"name": "d_c0", "value": "abc"}])
    client = _FakeClient(pong_result=False)

    async def start():
        pass

    _install(monkeypatch, evt, _make_factory(start, ctx, client))
    asyncio.run(_run_login("j2", "zhihu"))

    assert evt.done == [1]
    error_types = [e[0][2] for e in evt.errors]
    assert error_types == ["login_verification_failed"]
    assert "succeeded" not in [s[0][2] for s in evt.status]


def test_login_timeout_one_done(monkeypatch):
    """Timeout → timed_out + exactly 1 done."""
    evt = _Events()

    async def start():
        raise asyncio.TimeoutError()

    _install(monkeypatch, evt, _make_factory(start))
    asyncio.run(_run_login("j3", "xhs"))

    assert evt.done == [1]
    assert [e[0][2] for e in evt.errors] == ["timed_out"]


def test_login_worker_exit_one_done_and_reraised(monkeypatch):
    """A platform sys.exit() during login → error + 1 done, then re-raise."""
    evt = _Events()

    async def start():
        raise _WorkerExit("sys.exit(1) intercepted")

    _install(monkeypatch, evt, _make_factory(start))
    with pytest.raises(_WorkerExit):
        asyncio.run(_run_login("j4", "bilibili"))

    assert evt.done == [1]
    assert [e[0][2] for e in evt.errors] == ["login_verification_failed"]


def test_login_generic_exception_one_done(monkeypatch):
    """Generic error → classified error + exactly 1 done."""
    evt = _Events()

    async def start():
        raise RuntimeError("boom")

    _install(monkeypatch, evt, _make_factory(start))
    asyncio.run(_run_login("j5", "douyin"))

    assert evt.done == [1]
    assert [e[0][2] for e in evt.errors] == ["failed"]
    # Errors must carry the short safe message, not a traceback.
    message = evt.errors[0][0][3]
    assert "Traceback" not in message


def test_login_without_cookies_never_succeeds(monkeypatch):
    """No cookies after login → cannot be verified → not succeeded."""
    evt = _Events()
    ctx = _FakeCtx([])  # empty cookie jar
    client = _FakeClient(pong_result=True)

    async def start():
        pass

    _install(monkeypatch, evt, _make_factory(start, ctx, client))
    asyncio.run(_run_login("j6", "xhs"))

    assert evt.done == [1]
    assert client.pong_called == 0
    assert "succeeded" not in [s[0][2] for s in evt.status]


def test_worker_exit_must_not_become_exit0_in_login_mode(monkeypatch):
    """main(): a login-failure _WorkerExit must exit 1, never 0."""
    request = WorkerRequest(
        job_id="j7", mode="login", platform="xhs", keyword="", limit=1)
    exits = []

    async def fake_run_worker(*a, **k):
        raise _WorkerExit("sys.exit(1) intercepted")

    monkeypatch.setattr(worker, "read_request", lambda: request)
    monkeypatch.setattr(worker, "run_worker", fake_run_worker)
    monkeypatch.setattr(worker.sys, "exit", lambda code=0: exits.append(code))

    main()
    assert exits == [1], "login failure must not exit 0"


def test_worker_exit_search_mode_exits_zero(monkeypatch):
    """main(): a search-mode _WorkerExit still exits 0 (search done)."""
    request = WorkerRequest(
        job_id="j8", mode="search", platform="xhs", keyword="k", limit=1)
    exits = []

    async def fake_run_worker(*a, **k):
        raise _WorkerExit("sys.exit(0) intercepted")

    monkeypatch.setattr(worker, "read_request", lambda: request)
    monkeypatch.setattr(worker, "run_worker", fake_run_worker)
    monkeypatch.setattr(worker.sys, "exit", lambda code=0: exits.append(code))

    main()
    assert exits == [0]
