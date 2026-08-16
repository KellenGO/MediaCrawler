# -*- coding: utf-8 -*-
# Copyright (c) 2025 relakkes@gmail.com
#
# This file is part of MediaCrawler project.
# Licensed under NON-COMMERCIAL LEARNING LICENSE 1.1
#
# 声明：本代码仅供学习和研究目的使用。使用者应遵守以下原则：
# 1. 不得用于任何商业用途。
# 2. 使用时应遵守目标平台的使用条款和robots.txt规则。
# 3. 不得进行大规模爬取或对平台造成运营干扰。
# 4. 应合理控制请求频率，避免给目标平台带来不必要的负担。
# 5. 不得用于任何非法或不当的用途。
#
# 详细许可条款请参阅项目根目录下的LICENSE文件。

"""
Round 16 内存会话快照生命周期测试。

快照只存在于 API 进程内存（cookie name→value），绝不落盘/日志/响应：
- set/get/clear/复制语义；
- 登录失效（mark_login_required_from_search）→ 清除；
- 重新同步入口 → 清除旧快照；验证通过 → 捕获新快照；验证未通过 → 清除；
- 清除账号（delete_platform_session）→ 清除；
- shutdown（cancel_verify_tasks）→ 全部清除；
- 快照绝不进入 get_accounts() 响应；
- Round 16.1：WorkerRequest 的 repr/str/%s/%r、类型校验错误均不回显快照。
"""

import asyncio
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest
from api.services import accounts as acc

_XHS_COOKIES = [
    {"name": "web_session", "value": "fake-xhs-session",
     "domain": ".xiaohongshu.com", "path": "/",
     "expirationDate": 1750000000.0, "httpOnly": True, "secure": True,
     "sameSite": "no_restriction"},
    {"name": "a1", "value": "fake-a1", "domain": ".xiaohongshu.com",
     "sameSite": "lax"},
]


class _FakeCtx:
    def __init__(self, existing=None):
        self.existing = existing or []
        self.cleared_domains = []
        self.added = []

    async def cookies(self, urls=None):
        return list(self.existing)

    async def add_cookies(self, mapped):
        self.added.extend(mapped)

    async def clear_cookies(self, *, name=None, domain=None, path=None):
        self.cleared_domains.append(domain)

    async def new_page(self, *a, **k):
        class _P:
            async def goto(self, *a, **k):
                pass
        return _P()

    async def close(self):
        pass


class _FakePW:
    async def stop(self):
        pass


def _patch_launch(monkeypatch, ctx):
    async def fake_launch(platform):
        return _FakePW(), ctx, "edge"
    monkeypatch.setattr("api.services.accounts._launch_profile_context",
                        fake_launch)


def _reset_state(platform: str = "xhs") -> None:
    acc._set_state(platform, status="disconnected", verified=False,
                   display_name=None, last_verified_at=None,
                   safe_error_code=None, safe_message=None,
                   browser_backend=None)


class TestSnapshotLifecycle:
    def test_set_get_roundtrip(self):
        async def scenario():
            await acc.set_session_snapshot(
                "xhs", {"web_session": "v1", "a1": "v2"})
            snap = acc.get_session_snapshot("xhs")
            assert snap == {"web_session": "v1", "a1": "v2"}
            await acc.clear_session_snapshot("xhs")
            assert acc.get_session_snapshot("xhs") is None
        asyncio.run(scenario())

    def test_get_returns_copy(self):
        async def scenario():
            await acc.set_session_snapshot("xhs", {"web_session": "orig"})
            snap = acc.get_session_snapshot("xhs")
            assert snap is not None
            snap["web_session"] = "mutated"
            assert acc.get_session_snapshot("xhs")["web_session"] == "orig"
            await acc.clear_session_snapshot("xhs")
        asyncio.run(scenario())

    def test_empty_dict_clears(self):
        async def scenario():
            await acc.set_session_snapshot("xhs", {"web_session": "v"})
            await acc.set_session_snapshot("xhs", {})
            assert acc.get_session_snapshot("xhs") is None
        asyncio.run(scenario())

    def test_unknown_platform_ignored(self):
        async def scenario():
            await acc.set_session_snapshot("nope", {"a": "b"})
            assert acc.get_session_snapshot("nope") is None
        asyncio.run(scenario())

    def test_login_required_clears_snapshot(self):
        async def scenario():
            await acc.set_session_snapshot("xhs", {"web_session": "v"})
            acc.mark_login_required_from_search("xhs")
            try:
                assert acc.get_session_snapshot("xhs") is None
            finally:
                _reset_state("xhs")
        asyncio.run(scenario())

    def test_sync_entry_clears_old_snapshot_on_failed_verify(self, monkeypatch):
        """重新同步入口清除旧快照；验证未通过 → 快照保持清除。"""
        ctx = _FakeCtx(existing=list(_XHS_COOKIES))
        _patch_launch(monkeypatch, ctx)
        monkeypatch.setattr(
            "api.services.accounts._pong_with_profile",
            lambda p, c, metrics=None: asyncio.sleep(0, result=False))

        async def scenario():
            await acc.set_session_snapshot("xhs", {"web_session": "OLD"})
            assert acc.get_session_snapshot("xhs") == {"web_session": "OLD"}
            result = await acc.sync_platform_cookies(
                "xhs", _XHS_COOKIES,
                cookie_format=acc.COOKIE_FORMAT_CHROME_V1,
                extension_protocol_version=2)
            assert result["status"] == "unverified"
            assert acc.get_session_snapshot("xhs") is None
            _reset_state("xhs")
        asyncio.run(scenario())

    def test_sync_success_captures_fresh_snapshot(self, monkeypatch):
        """验证通过 → 用同一 context 的 Cookie 捕获新快照（替换旧值）。"""
        fresh = [
            {"name": "web_session", "value": "FRESH-SESSION",
             "domain": ".xiaohongshu.com"},
            {"name": "a1", "value": "FRESH-A1", "domain": ".xiaohongshu.com"},
        ]
        ctx = _FakeCtx(existing=fresh)
        _patch_launch(monkeypatch, ctx)
        monkeypatch.setattr(
            "api.services.accounts._pong_with_profile",
            lambda p, c, metrics=None: asyncio.sleep(0, result=True))

        async def scenario():
            await acc.set_session_snapshot("xhs", {"web_session": "OLD"})
            result = await acc.sync_platform_cookies(
                "xhs", _XHS_COOKIES,
                cookie_format=acc.COOKIE_FORMAT_CHROME_V1,
                extension_protocol_version=2)
            assert result["verified"] is True
            snap = acc.get_session_snapshot("xhs")
            assert snap == {"web_session": "FRESH-SESSION", "a1": "FRESH-A1"}
            await acc.clear_session_snapshot("xhs")
            _reset_state("xhs")
        asyncio.run(scenario())

    def test_delete_platform_session_clears_snapshot(self, monkeypatch, tmp_path):
        """清除账号 → 快照清除（profile 路径指向不存在的临时目录）。"""
        monkeypatch.setattr(acc, "_resolve_profile_path",
                            lambda platform: tmp_path / "no_such_profile")

        async def scenario():
            await acc.set_session_snapshot("xhs", {"web_session": "v"})
            result = await acc.delete_platform_session("xhs")
            assert result["success"] is True
            assert acc.get_session_snapshot("xhs") is None
            _reset_state("xhs")
        asyncio.run(scenario())

    def test_shutdown_clears_all_snapshots(self):
        async def scenario():
            await acc.set_session_snapshot("xhs", {"web_session": "x"})
            await acc.set_session_snapshot("zhihu", {"d_c0": "z"})
            await acc.cancel_verify_tasks()  # 生产 shutdown 路径
            assert acc.get_session_snapshot("xhs") is None
            assert acc.get_session_snapshot("zhihu") is None
        asyncio.run(scenario())

    def test_snapshot_never_in_accounts_response(self):
        """get_accounts() 输出绝不包含快照（即使快照已设置）。"""
        async def scenario():
            await acc.set_session_snapshot("xhs", {"web_session": "TOP-SECRET"})
            try:
                accounts_list = acc.get_accounts()
                assert "TOP-SECRET" not in str(accounts_list)
                for info in accounts_list:
                    assert "cookie" not in str(info).lower()
            finally:
                await acc.clear_session_snapshot("xhs")
        asyncio.run(scenario())

    def test_repr_and_validation_error_have_no_snapshot(self):
        """WorkerRequest 携带快照时：repr/str/格式化日志不得含 Cookie 值；
        类型校验错误（ValueError/ValidationError）也不得回显输入值。"""
        from aggregate_search.models import WorkerRequest
        req = WorkerRequest(
            job_id="j1", mode="search", platform="xhs",
            keyword="test", limit=5,
            session_snapshot={"web_session": "REPR-SECRET", "d_c0": "DC0-SECRET"},
        )
        # repr/str/%s/%r 全部安全（Field(repr=False) 完全省略该字段）。
        assert "REPR-SECRET" not in repr(req)
        assert "DC0-SECRET" not in repr(req)
        assert "REPR-SECRET" not in str(req)
        assert "REPR-SECRET" not in f"{req}"
        assert "REPR-SECRET" not in f"{req!r}"
        # 校验失败（类型错误）不得回显输入值。
        with pytest.raises(ValueError) as ei:
            WorkerRequest(
                job_id="j1", mode="search", platform="xhs",
                session_snapshot="ERR-SECRET")  # 非 dict
        assert "ERR-SECRET" not in str(ei.value)
        with pytest.raises(ValueError) as ei:
            WorkerRequest(
                job_id="j1", mode="search", platform="xhs",
                session_snapshot={"web_session": 123})  # 值非 str
        assert "123" not in str(ei.value)
        # 其他字段的 ValidationError 也不得打印快照。
        with pytest.raises(Exception) as ei:
            WorkerRequest(
                job_id="j1", mode="search", platform="nope",
                session_snapshot={"web_session": "ERR-SECRET"})
        assert "ERR-SECRET" not in str(ei.value)
        # 正向对照：model_dump_json 是唯一受支持的传输序列化（经 stdin），
        # 必须包含快照。
        dumped = req.model_dump_json()
        assert "REPR-SECRET" in dumped

    def test_model_validate_error_hides_snapshot_input(self):
        """Round 16.2: model_validate 收到非法 session_snapshot 时，
        hide_input_in_errors 使 ValidationError 不含任何快照键和值；
        正常协议构造仍可用。"""
        from aggregate_search.models import WorkerRequest
        from pydantic import ValidationError
        # 非法值（字符串内嵌 cookie 键值）。
        with pytest.raises(ValidationError) as ei:
            WorkerRequest.model_validate({
                "job_id": "j1", "mode": "search", "platform": "xhs",
                "keyword": "k", "limit": 5,
                "session_snapshot": "web_session=MODEL-SECRET"})
        err_text = str(ei.value)
        assert "MODEL-SECRET" not in err_text
        assert "web_session" not in err_text
        # 非法 dict（值非 str）。
        with pytest.raises(ValidationError) as ei:
            WorkerRequest.model_validate({
                "job_id": "j1", "mode": "search", "platform": "xhs",
                "session_snapshot": {"d_c0": 12345}})
        assert "12345" not in str(ei.value)
        assert "d_c0" not in str(ei.value)
        # repr/str 日志路径不得打印快照值（安全 __repr__/__str__）。
        req = WorkerRequest(
            job_id="j1", mode="search", platform="xhs", keyword="k", limit=5,
            session_snapshot={"web_session": "LOG-SECRET"})
        assert "LOG-SECRET" not in repr(req)
        assert "LOG-SECRET" not in str(req)
        assert "LOG-SECRET" not in f"{req}"
        assert "<redacted>" in repr(req)
        assert "<redacted>" in str(req)
        # 正常协议构造仍可用（model_validate 合法输入）。
        ok = WorkerRequest.model_validate({
            "job_id": "j2", "mode": "search", "platform": "xhs",
            "keyword": "k", "limit": 5,
            "session_snapshot": {"web_session": "OK-SECRET"}})
        assert ok.session_snapshot == {"web_session": "OK-SECRET"}
        assert "OK-SECRET" in ok.model_dump_json()  # stdin 传输序列化
