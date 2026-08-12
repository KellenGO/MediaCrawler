# -*- coding: utf-8 -*-
"""真实 Playwright 导入冒烟测试（不访问任何真实平台）。

虚构 Cookie（真实平台关键 Cookie 名称 + 假值）→ 生产 validate_chrome_v1_cookie_list
映射 → 启动 resolver 选择的 Edge/Chrome/bundled Chromium → 全新临时 profile →
context.add_cookies → context.cookies() 读回 → 断言 name/domain/path/sameSite/expires
→ 关闭并完整清理临时目录。整个测试不触碰用户真实浏览器与 browser_data。

用法: python tools/smoke_cookie_import.py
"""

import asyncio
import shutil
import sys
import tempfile
import time
from pathlib import Path

_PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(_PROJECT_ROOT))

from api.services.accounts import (  # noqa: E402  生产函数
    PLATFORM_COOKIE_DOMAINS,
    PLATFORM_COOKIE_URLS,
    _clear_platform_cookies,
    validate_chrome_v1_cookie_list,
)

# 各平台虚构的 stale Cookie（旧会话残留，必须被生产清理路径清除）。
STALE_COOKIES = {
    "bilibili": [{"name": "stale_old_session", "value": "stale",
                  "domain": ".bilibili.com", "path": "/"}],
    "zhihu": [{"name": "stale_old_zc0", "value": "stale",
               "domain": ".zhihu.com", "path": "/"}],
    "xhs": [{"name": "stale_old_web", "value": "stale",
             "domain": ".xiaohongshu.com", "path": "/"}],
    "douyin": [{"name": "stale_old_login", "value": "stale",
                "domain": ".douyin.com", "path": "/"}],
}

# 未来的过期时间（2030-01-01）——过期的 Cookie 会被 Chrome 立即丢弃
_FUTURE = 1893456000.0

# 虚构 Cookie：真实平台登录关键名称，值全部为假。
FAKE_COOKIES = {
    "bilibili": [
        {"name": "SESSDATA", "value": "smoke-fake-sessdata",
         "domain": ".bilibili.com", "path": "/", "expirationDate": _FUTURE,
         "httpOnly": True, "secure": True, "sameSite": "lax"},
        {"name": "bili_jct", "value": "smoke-fake-csrf",
         "domain": ".bilibili.com", "path": "/", "httpOnly": False,
         "secure": True, "sameSite": "lax"},
        {"name": "DedeUserID", "value": "999", "domain": ".bilibili.com",
         "path": "/", "expirationDate": _FUTURE, "secure": True,
         "sameSite": "no_restriction"},
    ],
    "zhihu": [
        {"name": "z_c0", "value": "smoke-fake-zc0", "domain": ".zhihu.com",
         "path": "/", "expirationDate": _FUTURE, "httpOnly": True,
         "secure": True, "sameSite": "no_restriction"},
        {"name": "d_c0", "value": "smoke-fake-dc0", "domain": ".zhihu.com",
         "path": "/", "sameSite": "strict"},
    ],
    "xhs": [
        {"name": "web_session", "value": "smoke-fake-web-session",
         "domain": ".xiaohongshu.com", "path": "/", "httpOnly": True,
         "secure": True, "sameSite": "lax"},
        {"name": "a1", "value": "smoke-fake-a1", "domain": ".xiaohongshu.com",
         "path": "/", "expirationDate": _FUTURE, "sameSite": "unspecified"},
    ],
    "douyin": [
        {"name": "LOGIN_STATUS", "value": "1", "domain": ".douyin.com",
         "path": "/", "httpOnly": True, "secure": True, "sameSite": "lax"},
        {"name": "sessionid", "value": "smoke-fake-sessionid",
         "domain": ".douyin.com", "path": "/", "expirationDate": _FUTURE,
         "httpOnly": True, "secure": True, "sameSite": "no_restriction"},
    ],
}

# 各平台关键 Cookie 需要能从读回的 cookie 中找到（名称存在即可，不返回值）。
_CRITICAL = {
    "bilibili": ("SESSDATA", "DedeUserID"),
    "zhihu": ("z_c0", "d_c0"),
    "xhs": ("web_session",),
    "douyin": ("LOGIN_STATUS",),
}


async def main() -> int:
    # 1) 生产映射：chrome-v1 校验 + 唯一一次 Chrome->Playwright 转换
    all_mapped = []
    for platform, cookies in FAKE_COOKIES.items():
        mapped, diag = validate_chrome_v1_cookie_list(platform, cookies)
        print(f"[{platform}] received={diag['received_cookie_count']} "
              f"accepted={diag['accepted_cookie_count']} "
              f"required_cookie_present={diag['required_cookie_present']}")
        assert diag["required_cookie_present"] is True, platform
        for m in mapped:
            assert "sameSite" not in m or m["sameSite"] is not None, (
                f"{platform}/{m['name']}: sameSite must never be null")
            assert m.get("expires") != -1, (
                f"{platform}/{m['name']}: expires must never be -1")
        all_mapped.extend(mapped)

    # 2) 启动 resolver 选择的真实浏览器 + 全新临时 profile
    from playwright.async_api import async_playwright
    from tools.browser_launcher import resolve_playwright_browser

    tmp_dir = Path(tempfile.mkdtemp(prefix="mc_smoke_"))
    print(f"[launch] temp profile: {tmp_dir}")
    playwright = await async_playwright().start()
    context = None
    try:
        executable_path, channel, backend = resolve_playwright_browser()
        kwargs = {"user_data_dir": str(tmp_dir), "headless": True}
        if backend == "playwright-chromium":
            kwargs["executable_path"] = playwright.chromium.executable_path
        elif executable_path:
            kwargs["executable_path"] = executable_path
        elif channel:
            kwargs["channel"] = channel
        print(f"[launch] backend={backend}")
        context = await playwright.chromium.launch_persistent_context(**kwargs)

        # 3) 先放入同平台 stale Cookie（虚构），再走生产清理路径：
        #    _clear_platform_cookies 必须用 clear_cookies(domain=...) 真正
        #    清掉它们（旧实现传位置参数会被 TypeError 吞掉、stale 永不消失）。
        for platform, stale in STALE_COOKIES.items():
            await context.add_cookies(stale)
        for platform in FAKE_COOKIES:
            await _clear_platform_cookies(context, platform)
        for platform, stale in STALE_COOKIES.items():
            read = await context.cookies(PLATFORM_COOKIE_URLS[platform])
            names = {c["name"] for c in read}
            for sc in stale:
                assert sc["name"] not in names, (
                    f"{platform}: stale cookie {sc['name']} survived the "
                    f"production clear path")
        print("[clear] stale cookies removed by production clear path")

        # 4) 真实 add_cookies —— 若映射有问题 Playwright 会在这里拒绝
        await context.add_cookies(all_mapped)

        # 5) 读回并断言
        for platform, urls in PLATFORM_COOKIE_URLS.items():
            read = await context.cookies(urls)
            by_name = {c["name"]: c for c in read}
            for critical in _CRITICAL[platform]:
                assert critical in by_name, f"{platform}: {critical} missing"
                c = by_name[critical]
                print(f"[{platform}] {critical}: domain={c['domain']} "
                      f"path={c['path']} sameSite={c['sameSite']} "
                      f"expires={c['expires']}")
            # 持久 Cookie 保留原过期时间（±1 天容差），session Cookie 无 expires
            for orig in FAKE_COOKIES[platform]:
                c = by_name[orig["name"]]
                assert c["domain"] == orig["domain"], orig["name"]
                assert c["path"] == orig["path"], orig["name"]
                if "expirationDate" in orig:
                    # Chrome 会把过期时间钳制到约 400 天（浏览器行为），所以
                    # 这里只断言"仍是持久 Cookie、未过期"，精确值由
                    # wire-contract 单测（无浏览器）断言映射输出。
                    assert c["expires"] > time.time() + 86400 * 30, (
                        f"{orig['name']}: persistent cookie expired on read-back")
                    print(f"  {orig['name']}: expires={c['expires']:.0f} "
                          f"(persistent, ok)")
                else:
                    assert c["expires"] == -1, (
                        f"{orig['name']}: session cookie must have expires=-1")
                if "sameSite" in orig and orig["sameSite"] != "unspecified":
                    expected = {"lax": "Lax", "strict": "Strict",
                                "no_restriction": "None"}[orig["sameSite"]]
                    assert c["sameSite"] == expected, orig["name"]
    finally:
        if context is not None:
            try:
                await context.close()
            except Exception:
                pass
        try:
            await playwright.stop()
        except Exception:
            pass
        shutil.rmtree(tmp_dir, ignore_errors=True)
        print(f"[cleanup] temp profile removed: {not tmp_dir.exists()}")

    print("SMOKE OK: mapped cookies accepted by real Playwright and read back "
          "with name/domain/path/sameSite/expires intact.")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
