import asyncio

import pytest

from api.services import accounts as acc


class _FakePage:
    def __init__(self, context):
        self.context = context
        self.goto_args = None

    async def goto(self, *args, **kwargs):
        self.goto_args = (args, kwargs)
        self.context.navigated = True

    async def wait_for_timeout(self, _milliseconds):
        await asyncio.sleep(0)

    async def close(self):
        pass


class _FakeContext:
    def __init__(self, initial_cookies, initialized_cookies=None):
        self.initial_cookies = list(initial_cookies)
        self.initialized_cookies = list(initialized_cookies or initial_cookies)
        self.navigated = False
        self.pages = []
        self.closed = False

    async def cookies(self, _urls=None):
        return list(self.initialized_cookies if self.navigated else self.initial_cookies)

    async def new_page(self):
        page = _FakePage(self)
        self.pages.append(page)
        return page

    async def close(self):
        self.closed = True


class _FakePlaywright:
    def __init__(self):
        self.stopped = False

    async def stop(self):
        self.stopped = True


def _prepare(monkeypatch, tmp_path):
    profile = tmp_path / "xhs_user_data_dir"
    profile.mkdir()
    monkeypatch.setattr(acc, "profile_dir_for", lambda _platform: profile)
    monkeypatch.setattr(acc, "_session_snapshots", {})
    monkeypatch.setattr(acc, "_account_generation", {})
    monkeypatch.setattr(acc, "_profile_locks", {})
    return profile


@pytest.mark.asyncio
async def test_existing_memory_snapshot_does_not_open_profile(monkeypatch, tmp_path):
    _prepare(monkeypatch, tmp_path)
    await acc.set_session_snapshot("xhs", {"a1": "memory"})

    async def fail_launch(_platform):
        raise AssertionError("profile must not open when snapshot exists")

    monkeypatch.setattr(acc, "_launch_profile_context", fail_launch)
    assert await acc.ensure_session_snapshot("xhs") == {"a1": "memory"}


@pytest.mark.asyncio
async def test_profile_snapshot_with_a1_is_restored_without_navigation(monkeypatch, tmp_path):
    _prepare(monkeypatch, tmp_path)
    context = _FakeContext([{"name": "a1", "value": "profile-a1"}])
    calls = 0

    async def launch(_platform):
        nonlocal calls
        calls += 1
        return _FakePlaywright(), context, "test"

    monkeypatch.setattr(acc, "_launch_profile_context", launch)
    assert await acc.ensure_session_snapshot("xhs") == {"a1": "profile-a1"}
    assert calls == 1
    assert context.pages == []
    assert context.closed


@pytest.mark.asyncio
async def test_profile_without_a1_gets_one_official_page_initialization(
    monkeypatch, tmp_path
):
    _prepare(monkeypatch, tmp_path)
    context = _FakeContext(
        [{"name": "web_session", "value": "session"}],
        [{"name": "web_session", "value": "session"},
         {"name": "a1", "value": "browser-created-a1"}],
    )

    async def launch(_platform):
        return _FakePlaywright(), context, "test"

    monkeypatch.setattr(acc, "_launch_profile_context", launch)
    assert await acc.ensure_session_snapshot("xhs") == {
        "web_session": "session", "a1": "browser-created-a1"
    }
    assert len(context.pages) == 1
    assert context.pages[0].goto_args[0][0] == acc.PLATFORM_HOME_URLS["xhs"]


@pytest.mark.asyncio
async def test_profile_without_a1_is_a_safe_miss(monkeypatch, tmp_path):
    _prepare(monkeypatch, tmp_path)
    context = _FakeContext([{"name": "web_session", "value": "session"}])

    async def launch(_platform):
        return _FakePlaywright(), context, "test"

    monkeypatch.setattr(acc, "_launch_profile_context", launch)
    assert await acc.ensure_session_snapshot("xhs") is None
    assert acc.get_session_snapshot("xhs") is None


@pytest.mark.asyncio
async def test_concurrent_restore_opens_profile_once(monkeypatch, tmp_path):
    _prepare(monkeypatch, tmp_path)
    context = _FakeContext([{"name": "a1", "value": "profile-a1"}])
    calls = 0

    async def launch(_platform):
        nonlocal calls
        calls += 1
        await asyncio.sleep(0)
        return _FakePlaywright(), context, "test"

    monkeypatch.setattr(acc, "_launch_profile_context", launch)
    results = await asyncio.gather(*(
        acc.ensure_session_snapshot("xhs") for _ in range(5)
    ))
    assert calls == 1
    assert all(item == {"a1": "profile-a1"} for item in results)

