import asyncio

import api.services.accounts as accounts


class _Page:
    def __init__(self, context):
        self.context = context

    async def goto(self, *_args, **_kwargs):
        self.context.goto_calls += 1
        if self.context.goto_error is not None:
            raise self.context.goto_error
        self.context.cookies_now = list(self.context.after_navigation)

    async def wait_for_timeout(self, _milliseconds):
        return None

    async def close(self):
        self.context.page_close_calls += 1


class _Context:
    def __init__(self, before, after_navigation=None, goto_error=None):
        self.cookies_now = list(before)
        self.after_navigation = list(after_navigation or before)
        self.goto_error = goto_error
        self.cookie_reads = 0
        self.goto_calls = 0
        self.page_close_calls = 0
        self.new_page_calls = 0

    async def cookies(self, _urls=None):
        self.cookie_reads += 1
        return list(self.cookies_now)

    async def new_page(self):
        self.new_page_calls += 1
        return _Page(self)


def _cookie(name, value):
    return {"name": name, "value": value}


def _install_client(monkeypatch, captured, pong_result=True):
    class _Client:
        def __init__(self, *, headers, cookie_dict, **_kwargs):
            captured["cookie_dict"] = dict(cookie_dict)
            captured["cookie_header"] = headers["Cookie"]

        async def pong(self, raise_on_error=False):
            captured["raise_on_error"] = raise_on_error
            return pong_result

    monkeypatch.setattr(
        "media_platform.xhs.client.XiaoHongShuClient", _Client,
    )


def test_xhs_pong_with_a1_does_not_navigate(monkeypatch):
    captured = {}
    _install_client(monkeypatch, captured)
    context = _Context([
        _cookie("web_session", "session"),
        _cookie("a1", "existing-a1"),
    ])

    verdict = asyncio.run(accounts._pong_with_profile("xhs", context))

    assert verdict == "verified"
    assert context.new_page_calls == 0
    assert captured["cookie_dict"]["a1"] == "existing-a1"
    assert "existing-a1" in captured["cookie_header"]


def test_xhs_pong_rereads_cookies_and_rebuilds_client_after_navigation(monkeypatch):
    captured = {}
    _install_client(monkeypatch, captured)
    context = _Context(
        [_cookie("web_session", "session")],
        after_navigation=[
            _cookie("web_session", "session"),
            _cookie("a1", "refreshed-a1"),
        ],
    )

    verdict = asyncio.run(accounts._pong_with_profile("xhs", context))

    assert verdict == "verified"
    assert context.new_page_calls == 1
    assert context.cookie_reads == 2
    assert captured["cookie_dict"] == {
        "web_session": "session",
        "a1": "refreshed-a1",
    }
    assert "refreshed-a1" in captured["cookie_header"]


def test_xhs_pong_without_a1_after_navigation_is_unavailable(monkeypatch):
    captured = {}
    _install_client(monkeypatch, captured)
    context = _Context(
        [_cookie("web_session", "session")],
        after_navigation=[_cookie("web_session", "session")],
    )

    verdict = asyncio.run(accounts._pong_with_profile("xhs", context))

    assert verdict == "unavailable"
    assert context.new_page_calls == 1
    assert captured == {}


def test_xhs_pong_navigation_failure_is_unavailable(monkeypatch):
    captured = {}
    _install_client(monkeypatch, captured)
    context = _Context(
        [_cookie("web_session", "session")],
        goto_error=RuntimeError("navigation failed"),
    )

    verdict = asyncio.run(accounts._pong_with_profile("xhs", context))

    assert verdict == "unavailable"
    assert context.new_page_calls == 1
    assert captured == {}


def test_xhs_pong_false_keeps_not_logged_in_semantics(monkeypatch):
    captured = {}
    _install_client(monkeypatch, captured, pong_result=False)
    context = _Context([_cookie("a1", "existing-a1")])

    verdict = asyncio.run(accounts._pong_with_profile("xhs", context))

    assert verdict == "not_logged_in"
    assert captured["raise_on_error"] is True


def test_xhs_snapshot_restore_reuses_the_same_cookie_initialization(monkeypatch, tmp_path):
    context = _Context(
        [_cookie("web_session", "session")],
        after_navigation=[
            _cookie("web_session", "session"),
            _cookie("a1", "refreshed-a1"),
        ],
    )

    class _Playwright:
        async def stop(self):
            return None

    profile = tmp_path / "xhs-profile"
    profile.mkdir()
    monkeypatch.setattr(accounts, "profile_dir_for", lambda _platform: profile)

    async def _launch(_platform):
        return _Playwright(), context, None

    monkeypatch.setattr(accounts, "_launch_profile_context", _launch)
    accounts._session_snapshots.pop("xhs", None)

    snapshot = asyncio.run(accounts.ensure_session_snapshot("xhs"))

    assert snapshot == {
        "web_session": "session",
        "a1": "refreshed-a1",
    }
    assert context.new_page_calls == 1
    accounts._session_snapshots.pop("xhs", None)
