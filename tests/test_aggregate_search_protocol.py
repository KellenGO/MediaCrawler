# -*- coding: utf-8 -*-
# Copyright (c) 2025 relakkes@gmail.com
#
# This file is part of MediaCrawler project.
# Repository: https://github.com/NanmiCoder/MediaCrawler
# GitHub: https://github.com/NanmiCoder
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
# 使用本代码即表示您同意遵守上述原则和LICENSE中的所有条款。

"""
Unit tests for the worker communication protocol.

Tests cover:
- Event serialization / deserialization
- Prefix stripping and safety
- Invalid input handling
- Log lines passing through (not parsed as events)
- Secret-free verification
"""

import json
import sys
import os
import io

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest
from aggregate_search.protocol import (
    EVENT_PREFIX,
    EVENT_SEPARATOR,
    emit_event,
    parse_event_line,
    emit_status,
    emit_result,
    emit_done,
    emit_error,
    WorkerEvent,
    WorkerRequest,
)


class TestParseEventLine:
    def test_valid_event(self):
        evt = WorkerEvent(event="status", job_id="j1", platform="xhs", data={"status": "running"})
        payload = evt.model_dump_json(exclude_none=True)
        line = f"{EVENT_PREFIX}{EVENT_SEPARATOR}{payload}\n"
        parsed = parse_event_line(line)
        assert parsed is not None
        assert parsed.event == "status"
        assert parsed.job_id == "j1"
        assert parsed.platform == "xhs"

    def test_no_prefix_returns_none(self):
        line = "This is a normal log line\n"
        assert parse_event_line(line) is None

    def test_empty_line(self):
        assert parse_event_line("") is None
        assert parse_event_line("\n") is None

    def test_prefix_but_no_separator(self):
        line = f"{EVENT_PREFIX} some data\n"
        assert parse_event_line(line) is None

    def test_prefix_with_empty_body(self):
        line = f"{EVENT_PREFIX}{EVENT_SEPARATOR}\n"
        assert parse_event_line(line) is None

    def test_invalid_json(self):
        line = f"{EVENT_PREFIX}{EVENT_SEPARATOR}{{invalid json}}\n"
        assert parse_event_line(line) is None

    def test_platform_log_passes_through(self):
        """Normal platform logs must NOT be parsed as events."""
        log_lines = [
            "[XiaoHongShuCrawler] Starting search...",
            "INFO:httpx:Request to https://www.xiaohongshu.com/api/...",
            "DEBUG:asyncio:Using selector: SelectSelector",
            "",  # empty line
        ]
        for line in log_lines:
            assert parse_event_line(line) is None

    def test_prefix_in_middle_not_matched(self):
        """The prefix must be at the START of the line."""
        line = f"Some log text {EVENT_PREFIX}{EVENT_SEPARATOR}{{}}\n"
        assert parse_event_line(line) is None

    def test_result_event_parsing(self):
        result_data = {
            "platform": "xhs",
            "content_id": "abc123",
            "title": "测试",
            "url": "https://example.com",
            "rank": 0,
        }
        evt = WorkerEvent(event="result", job_id="j1", platform="xhs", data=result_data)
        payload = evt.model_dump_json(exclude_none=True)
        line = f"{EVENT_PREFIX}{EVENT_SEPARATOR}{payload}\n"
        parsed = parse_event_line(line)
        assert parsed is not None
        assert parsed.event == "result"
        assert parsed.data["content_id"] == "abc123"

    def test_error_event_parsing(self):
        evt = WorkerEvent(
            event="error",
            job_id="j1",
            platform="douyin",
            data={"type": "login_required", "message": "LoginRequiredError"},
        )
        payload = evt.model_dump_json(exclude_none=True)
        line = f"{EVENT_PREFIX}{EVENT_SEPARATOR}{payload}\n"
        parsed = parse_event_line(line)
        assert parsed is not None
        assert parsed.event == "error"
        assert parsed.data["type"] == "login_required"


class _FakeBinaryStdout:
    """Mimics a real stdout with a .buffer attribute for testing."""

    def __init__(self) -> None:
        self._buf = io.BytesIO()
        self.buffer = self  # self is the buffer

    def write(self, data: bytes) -> int:
        return self._buf.write(data)

    def flush(self) -> None:
        self._buf.flush()

    def getvalue(self) -> str:
        return self._buf.getvalue().decode("utf-8")


class TestEmitEvent:
    def test_emit_event_writes_to_stdout(self):
        old_stdout = sys.stdout
        try:
            fake = _FakeBinaryStdout()
            sys.stdout = fake

            evt = WorkerEvent(
                event="status",
                job_id="test_job",
                platform="bilibili",
                data={"status": "running"},
            )
            emit_event(evt)

            output = fake.getvalue()
            assert output.startswith(EVENT_PREFIX)
            assert EVENT_SEPARATOR in output
            assert "test_job" in output
            assert "running" in output
        finally:
            sys.stdout = old_stdout

    def test_emit_status_convenience(self):
        old_stdout = sys.stdout
        try:
            fake = _FakeBinaryStdout()
            sys.stdout = fake
            emit_status("job1", "xhs", "running", {"count": 5})
            output = fake.getvalue()
            assert "status" in output
            assert "running" in output
            assert "count" in output
        finally:
            sys.stdout = old_stdout

    def test_emit_result_convenience(self):
        old_stdout = sys.stdout
        try:
            fake = _FakeBinaryStdout()
            sys.stdout = fake
            emit_result("job1", "xhs", {"title": "Test"})
            output = fake.getvalue()
            assert "result" in output
            assert "Test" in output
        finally:
            sys.stdout = old_stdout

    def test_emit_done_convenience(self):
        old_stdout = sys.stdout
        try:
            fake = _FakeBinaryStdout()
            sys.stdout = fake
            emit_done("job1", "zhihu")
            output = fake.getvalue()
            assert "done" in output
        finally:
            sys.stdout = old_stdout

    def test_emit_error_convenience(self):
        old_stdout = sys.stdout
        try:
            fake = _FakeBinaryStdout()
            sys.stdout = fake
            emit_error("job1", "douyin", "rate_limited", "Too many requests")
            output = fake.getvalue()
            assert "error" in output
            assert "rate_limited" in output
            assert "Too many requests" in output
        finally:
            sys.stdout = old_stdout


class TestSecretSafety:
    """Secrets are recursively redacted from protocol events."""

    def _capture_emit(self, data: dict) -> str:
        old_stdout = sys.stdout
        try:
            fake = _FakeBinaryStdout()
            sys.stdout = fake
            emit_status("j1", "xhs", "running", data)
            return fake.getvalue()
        finally:
            sys.stdout = old_stdout

    def test_no_cookie_leak(self):
        output = self._capture_emit({"cookie": "secret123"})
        assert "secret123" not in output
        assert "[REDACTED]" in output

    def test_no_token_leak(self):
        output = self._capture_emit({"token": "bearer-abc"})
        assert "bearer-abc" not in output

    def test_no_authorization_leak(self):
        output = self._capture_emit({"authorization": "Bearer xyz"})
        assert "Bearer xyz" not in output

    def test_no_access_token_leak(self):
        output = self._capture_emit({"access_token": "at-secret"})
        assert "at-secret" not in output

    def test_hyphen_variant(self):
        output = self._capture_emit({"access-token": "hyphen-secret"})
        assert "hyphen-secret" not in output

    def test_underscore_variant(self):
        output = self._capture_emit({"access_token": "underscore-secret"})
        assert "underscore-secret" not in output

    def test_mixed_case(self):
        output = self._capture_emit({"Access_Token": "mixed-secret"})
        assert "mixed-secret" not in output

    def test_nested_secret(self):
        output = self._capture_emit({"data": {"cookie": "nested-secret"}})
        assert "nested-secret" not in output

    def test_nested_list(self):
        output = self._capture_emit({"items": [{"token": "list-secret"}]})
        assert "list-secret" not in output

    def test_deep_nesting(self):
        deep = {"a": {"b": {"c": {"d": {"e": {"f": {"g": {"h": {"i": {"j": {"k": {"cookie": "deep-secret"}}}}}}}}}}}}
        output = self._capture_emit(deep)
        assert "deep-secret" not in output

    def test_non_secret_preserved(self):
        output = self._capture_emit({"title": "普通标题", "author": "张三"})
        assert "普通标题" in output
        assert "张三" in output

    def test_refresh_token_redacted(self):
        output = self._capture_emit({"refresh_token": "rt-secret"})
        assert "rt-secret" not in output

    def test_xsec_token_redacted(self):
        output = self._capture_emit({"xsec_token": "xsec-secret-123"})
        assert "xsec-secret-123" not in output

    def test_api_token_hyphen_redacted(self):
        output = self._capture_emit({"api-token": "api-token-secret"})
        assert "api-token-secret" not in output

    def test_deep_nested_token(self):
        deep = {"data": {"results": [{"meta": {"access_token": "deep-nested-token"}}]}}
        output = self._capture_emit(deep)
        assert "deep-nested-token" not in output

    def test_no_secrets_serialized(self):
        data = {
            "results": [{"title": "OK", "Cookie": "leak1", "X-CSRF-Token": "leak2"}],
            "Authorization": "leak3",
            "xsec_token": "leak4",
        }
        output = self._capture_emit(data)
        for leak in ("leak1", "leak2", "leak3", "leak4"):
            assert leak not in output, f"secret '{leak}' leaked in: {output}"

    def test_error_message_no_stack_trace(self):
        """Error events should carry safe messages, not full exceptions."""
        evt = WorkerEvent(
            event="error",
            job_id="j1",
            platform="xhs",
            data={"type": "failed", "message": "Something went wrong"},
        )
        payload = evt.model_dump_json()
        # No traceback, no raw exception
        assert "Traceback" not in payload
        assert "File " not in payload


class TestWorkerRequest:
    def test_search_request(self):
        req = WorkerRequest(
            job_id="abc-123",
            mode="search",
            platform="xhs",
            keyword="露营装备",
            limit=10,
        )
        data = req.model_dump_json()
        assert "abc-123" in data
        assert "search" in data
        assert "露营装备" in data

    def test_login_request(self):
        req = WorkerRequest(
            job_id="login-1",
            mode="login",
            platform="douyin",
        )
        assert req.mode == "login"
        assert req.keyword == ""  # not needed for login
        assert req.limit == 10  # default
