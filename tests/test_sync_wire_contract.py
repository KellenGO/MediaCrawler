# -*- coding: utf-8 -*-
# Copyright (c) 2025 relakkes@gmail.com
#
# This file is part of MediaCrawler project.
# Licensed under NON-COMMERCIAL LEARNING LICENSE 1.1

"""End-to-end cookie wire-contract tests.

The extension's production pure functions (browser_extension/sync_protocol.js)
are executed with Node to build the actual POST body from chrome-cookies-API
fixtures; the backend's PRODUCTION validate_chrome_v1_cookie_list /
map_chrome_cookie then consume it. No mapper logic is duplicated here — if
either side changes, these tests exercise the real code path.

The final assertion: the mapped output can be handed directly to Playwright
add_cookies — no sameSite:null, no expires:-1, valid positive expires kept.
"""

import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

_PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(_PROJECT_ROOT))

from api.services import accounts as acc  # noqa: E402
from api.services.accounts import (  # noqa: E402  (production functions)
    COOKIE_FORMAT_CHROME_V1,
    CookieFormatInvalidError,
    validate_chrome_v1_cookie_list,
)

_NODE = shutil.which("node")
requires_node = pytest.mark.skipif(_NODE is None, reason="node not installed")

_PLAYWRIGHT_KEYS = {"name", "value", "domain", "path",
                    "expires", "httpOnly", "secure", "sameSite"}

# ── Fixtures: REAL platform login cookie names, fully fake values ────────

_MAY_2025 = 1750000000.0

# 平台真实 pong/login 关键 Cookie 名称（仓库代码为准）：
#   bilibili: login.py SESSDATA or DedeUserID（bili_jct 为 CSRF）
#   zhihu:    client.py d_c0 必须存在；login.py 用 z_c0
#   xhs:      login.py web_session
#   douyin:   client.py pong 检查 LOGIN_STATUS == "1"
FIXTURES = {
    "bilibili": [
        {"name": "SESSDATA", "value": "fake-sessdata", "domain": ".bilibili.com",
         "path": "/", "expirationDate": _MAY_2025, "httpOnly": True,
         "secure": True, "sameSite": "lax", "session": False, "storeId": "0"},
        {"name": "bili_jct", "value": "fake-csrf", "domain": ".bilibili.com",
         "path": "/", "httpOnly": False, "secure": True, "sameSite": "lax",
         "session": True, "storeId": "0"},
        {"name": "DedeUserID", "value": "12345", "domain": ".bilibili.com",
         "path": "/", "expirationDate": _MAY_2025, "httpOnly": False,
         "secure": False, "sameSite": "no_restriction", "session": False,
         "storeId": "0"},
        {"name": "buvid3", "value": "fake-buvid", "domain": ".bilibili.com",
         "path": "/", "sameSite": "unspecified", "session": True, "storeId": "0"},
    ],
    "zhihu": [
        {"name": "z_c0", "value": "fake-zc0", "domain": ".zhihu.com",
         "path": "/", "expirationDate": _MAY_2025, "httpOnly": True,
         "secure": True, "sameSite": "no_restriction", "session": False,
         "storeId": "0"},
        {"name": "d_c0", "value": "fake-dc0", "domain": ".zhihu.com",
         "path": "/", "httpOnly": False, "secure": False, "sameSite": "lax",
         "session": True, "storeId": "0"},
    ],
    "xhs": [
        {"name": "web_session", "value": "fake-web-session",
         "domain": ".xiaohongshu.com", "path": "/", "httpOnly": True,
         "secure": True, "sameSite": "lax", "session": True, "storeId": "0"},
        {"name": "a1", "value": "fake-a1", "domain": ".xiaohongshu.com",
         "path": "/", "expirationDate": _MAY_2025, "httpOnly": True,
         "secure": True, "sameSite": "unspecified", "session": False,
         "storeId": "0"},
        # partitioned cookies must be dropped by the extension whitelist
        {"name": "partitioned_thing", "value": "x",
         "domain": ".xiaohongshu.com", "path": "/", "sameSite": "lax",
         "session": True, "storeId": "0",
         "partitionKey": {"topLevelSite": "https://www.xiaohongshu.com"}},
    ],
    "douyin": [
        {"name": "LOGIN_STATUS", "value": "1", "domain": ".douyin.com",
         "path": "/", "httpOnly": True, "secure": True, "sameSite": "lax",
         "session": True, "storeId": "0"},
        {"name": "sessionid", "value": "fake-sessionid", "domain": ".douyin.com",
         "path": "/", "expirationDate": _MAY_2025, "httpOnly": True,
         "secure": True, "sameSite": "no_restriction", "session": False,
         "storeId": "0"},
        {"name": "sessionid_ss", "value": "fake-ss", "domain": ".douyin.com",
         "path": "/", "httpOnly": True, "secure": True, "sameSite": "lax",
         "session": True, "storeId": "0"},
    ],
}

_BUILD_DRIVER = r"""
const fs = require('fs');
const sp = require('./browser_extension/sync_protocol.js');
const input = JSON.parse(fs.readFileSync(process.argv[1], 'utf8'));
const body = sp.buildSyncBody({
  platform: input.platform,
  cookies: input.cookies,
  requestId: input.request_id || 'wire-test',
  skippedPartitioned: input.skipped_partitioned || 0,
  storeCount: input.store_count || 1,
});
process.stdout.write(JSON.stringify(body));
"""

_PARSE_DRIVER = r"""
const fs = require('fs');
const sp = require('./browser_extension/sync_protocol.js');
const input = JSON.parse(fs.readFileSync(process.argv[1], 'utf8'));
process.stdout.write(JSON.stringify(sp.parseSyncResponse(input.data)));
"""


def _run_node(driver: str, payload: dict) -> dict:
    """Execute the PRODUCTION sync_protocol.js with Node, return parsed JSON."""
    payload_file = Path(os.environ.get("TEMP", ".")) / (
        "mc_wire_payload_%d.json" % abs(hash(json.dumps(payload, sort_keys=True))))
    payload_file.write_text(json.dumps(payload), encoding="utf-8")
    try:
        proc = subprocess.run(
            [_NODE, "-e", driver, str(payload_file)],
            cwd=str(_PROJECT_ROOT), capture_output=True, text=True,
            timeout=30, encoding="utf-8")
        assert proc.returncode == 0, proc.stderr
        return json.loads(proc.stdout)
    finally:
        try:
            payload_file.unlink()
        except OSError:
            pass


# ── Extension side: buildSyncBody (production JS) ────────────────────────

@requires_node
def test_extension_builds_chrome_v1_body_from_raw_cookies():
    """The production JS builds the chrome-v1 body: cookie_format, protocol
    v2, raw fields only — never Playwright-converted fields, never
    partitionKey."""
    body = _run_node(_BUILD_DRIVER, {
        "platform": "xhs", "cookies": FIXTURES["xhs"],
        "request_id": "req-abc", "store_count": 2,
    })
    assert body["cookie_format"] == "chrome-v1"
    assert body["extension_protocol_version"] == 2
    assert body["request_id"] == "req-abc"
    assert body["browser_cookie_store_count"] == 2
    # whitelist: raw chrome fields only, partitioned dropped
    for c in body["cookies"]:
        assert set(c).issubset({"name", "value", "domain", "path",
                                "expirationDate", "httpOnly", "secure",
                                "sameSite", "session", "storeId"})
        assert "partitionKey" not in c
    names = [c["name"] for c in body["cookies"]]
    assert "partitioned_thing" not in names
    assert "web_session" in names


# ── Full wire: production JS body -> production Python mapping ───────────

@requires_node
@pytest.mark.parametrize("platform", ["xhs", "douyin", "bilibili", "zhihu"])
def test_wire_contract_produces_playwright_ready_cookies(platform):
    """POST body built by the real extension code -> backend production
    validation/mapping -> output must be directly usable by Playwright
    add_cookies (the smoke test proves the launch side)."""
    body = _run_node(_BUILD_DRIVER, {
        "platform": platform, "cookies": FIXTURES[platform],
        "request_id": "wire-test", "store_count": 1,
    })
    assert body["cookie_format"] == COOKIE_FORMAT_CHROME_V1

    mapped, diag = validate_chrome_v1_cookie_list(platform, body["cookies"])
    # the extension already dropped partitioned cookies before the POST
    expected = [c for c in FIXTURES[platform] if "partitionKey" not in c]
    assert len(mapped) == len(expected)
    assert diag["received_cookie_count"] == len(body["cookies"])
    assert diag["accepted_cookie_count"] == len(expected)
    assert diag["required_cookie_present"] is True
    # Round 9: marker 诊断（名称 + 布尔值）如实反映白名单 Cookie 的存在性
    assert diag["login_marker_presence"] == {
        name: True for name in acc.LOGIN_MARKER_NAMES[platform]
    }, platform

    for m in mapped:
        assert set(m).issubset(_PLAYWRIGHT_KEYS)
        # Playwright rejects these
        assert "sameSite" not in m or m["sameSite"] is not None, (
            "sameSite must never be null")
        assert m.get("expires") != -1, "expires must never be -1"
        assert m.get("expires") != "inf", "expires must be finite"
        for v in m.values():
            assert v is not None

    by_name = {m["name"]: m for m in mapped}
    for c in expected:
        m = by_name[c["name"]]
        if isinstance(c.get("expirationDate"), (int, float)):
            # persistent cookie: original expiration preserved exactly
            assert m["expires"] == c["expirationDate"], c["name"]
        else:
            # session cookie: NO expires key at all
            assert "expires" not in m, c["name"]


@requires_node
@pytest.mark.parametrize("platform,same_site,expected", [
    ("bilibili", "lax", "Lax"),
    ("zhihu", "no_restriction", "None"),
    ("douyin", "strict", "Strict"),
])
def test_wire_contract_same_site_variants(platform, same_site, expected):
    """Chrome sameSite -> Playwright sameSite, via the real JS + Python
    pipeline; unspecified/absent sameSite omits the key entirely."""
    # 使用各平台真实登录关键 Cookie 名称（仓库 pong 逻辑为准），并带上平台
    # 登录谓词要求的伴侣 Cookie（zhihu 需要 d_c0；douyin 的 LOGIN_STATUS
    # 值必须严格为 "1"），否则校验会先于映射被拒。
    name = {"bilibili": "SESSDATA", "zhihu": "z_c0",
            "douyin": "LOGIN_STATUS"}[platform]

    def fixture_with(same_site):
        fixture = [{
            "name": name,
            "value": "1" if platform == "douyin" else "fake",
            "domain": ".%s" % acc_domain(platform),
            "path": "/", "sameSite": same_site, "session": True,
        }]
        if platform == "zhihu":
            fixture.append({
                "name": "d_c0", "value": "fake",
                "domain": ".zhihu.com", "path": "/", "session": True,
            })
        return fixture

    body = _run_node(_BUILD_DRIVER,
                     {"platform": platform, "cookies": fixture_with(same_site)})
    mapped, _ = validate_chrome_v1_cookie_list(platform, body["cookies"])
    assert mapped[0]["sameSite"] == expected

    body = _run_node(_BUILD_DRIVER,
                     {"platform": platform,
                      "cookies": fixture_with("unspecified")})
    mapped, _ = validate_chrome_v1_cookie_list(platform, body["cookies"])
    assert "sameSite" not in mapped[0]


def acc_domain(platform: str) -> str:
    from api.services.accounts import PLATFORM_COOKIE_DOMAINS
    return PLATFORM_COOKIE_DOMAINS[platform][0]


# ── Old / foreign formats must fail loudly, not silently ─────────────────

@pytest.mark.parametrize("bad_cookies", [
    # old extension format: Playwright "expires" field
    [{"name": "SESSDATA", "value": "v", "domain": ".bilibili.com",
      "expires": _MAY_2025}],
    # mixed: both expirationDate and expires
    [{"name": "SESSDATA", "value": "v", "domain": ".bilibili.com",
      "expirationDate": _MAY_2025, "expires": _MAY_2025}],
    # Playwright-style uppercase sameSite
    [{"name": "SESSDATA", "value": "v", "domain": ".bilibili.com",
      "sameSite": "Lax"}],
])
def test_old_format_returns_cookie_format_invalid(bad_cookies):
    """A stale extension must get cookie_format_invalid (clear fix
    instruction), never the confusing session_import_failed."""
    with pytest.raises(CookieFormatInvalidError) as exc:
        validate_chrome_v1_cookie_list("bilibili", bad_cookies)
    assert exc.value.safe_code == "cookie_format_invalid"
    assert exc.value.diagnostics["received_cookie_count"] == len(bad_cookies)


# ── Service worker response parsing (production JS) ──────────────────────

@requires_node
def test_parse_sync_response_structured_fields():
    parsed = _run_node(_PARSE_DRIVER, {"data": {
        "success": False, "verified": False,
        "safe_error_code": "required_login_cookie_missing",
        "safe_message": "当前浏览器没有读取到有效登录会话",
        "sync_stage": "cookie_validation",
        "received_cookie_count": 7,
        "accepted_cookie_count": 3,
        "skipped_cookie_count": 4,
        "required_cookie_present": False,
    }})
    assert parsed["safe_error_code"] == "required_login_cookie_missing"
    assert parsed["safe_message"] == "当前浏览器没有读取到有效登录会话"
    assert parsed["sync_stage"] == "cookie_validation"
    assert parsed["received_cookie_count"] == 7
    assert parsed["required_cookie_present"] is False
    assert parsed["success"] is False
    # Round 9: 无 marker 数据时保持 null；status 缺省为空串
    assert parsed["login_marker_presence"] is None
    assert parsed["status"] == ""


@requires_node
def test_parse_sync_response_login_marker_whitelist():
    """login_marker_presence 只透传白名单 marker 的布尔值 —— 白名单外的
    Cookie 名与任何非布尔值都被裁掉；status 透传（unverified 语义）。"""
    parsed = _run_node(_PARSE_DRIVER, {"data": {
        "success": True, "verified": False, "status": "unverified",
        "safe_error_code": "login_not_verified",
        "safe_message": "会话已导入，但尚未确认账号登录。你仍可以尝试搜索；"
                        "如搜索需要登录，再重新同步。",
        "login_marker_presence": {
            "LOGIN_STATUS": False, "sessionid": True, "sessionid_ss": False,
            "web_session": True, "d_c0": False, "z_c0": True,
            "SESSDATA": False, "DedeUserID": True,
            # 白名单外 / 非布尔值 —— 必须被裁掉
            "some_other_cookie": True,
            "x-zse-96": "secret-value",
            "web_session_value": "secret",
        },
    }})
    assert parsed["status"] == "unverified"
    assert parsed["safe_error_code"] == "login_not_verified"
    assert parsed["login_marker_presence"] == {
        "LOGIN_STATUS": False, "sessionid": True, "sessionid_ss": False,
        "web_session": True, "d_c0": False, "z_c0": True,
        "SESSDATA": False, "DedeUserID": True,
    }


@requires_node
def test_parse_sync_response_detail_fallback():
    """Legacy {detail: "..."} bodies still surface a safe message."""
    parsed = _run_node(_PARSE_DRIVER, {"data": {
        "detail": "会话导入失败",
    }})
    assert parsed["safe_message"] == "会话导入失败"
    assert parsed["safe_error_code"] == ""
    assert parsed["success"] is False
    # garbage bodies must not crash the parser
    for garbage in (None, "plain string", 42, []):
        parsed = _run_node(_PARSE_DRIVER, {"data": garbage})
        assert isinstance(parsed["safe_message"], str)


@requires_node
def test_parse_sync_response_http_error_without_body():
    """A non-JSON 5xx still parses to a failed result, not an exception."""
    parsed = _run_node(_PARSE_DRIVER, {"data": "Internal Server Error"})
    assert parsed["success"] is False
    assert parsed["safe_message"] == ""
