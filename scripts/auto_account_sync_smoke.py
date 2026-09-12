# -*- coding: utf-8 -*-
# Copyright (c) 2025 relakkes@gmail.com
#
# This file is part of MediaCrawler project.
# Licensed under NON-COMMERCIAL LEARNING LICENSE 1.1

"""打开程序时自动同步登录状态 —— 真实浏览器冒烟（Round 18）。

验证两条互补的路径，全部使用系统 Edge、隔离 context、不接触真实平台账号：

场景 A（未安装扩展）：
    打开页面必须**不**发起任何同步 —— 扩展未连接时 decideAutoSync 应当直接
    放弃，而且页面不能因为新挂载的自动同步链路而报错。

场景 B（扩展在线 + 有未验证平台）：
    伪造一个只应答 pong 的 content script（协议 v2 / 版本 1.1.3），并把
    GET /api/search/accounts 的响应改写成"bilibili 尚未确认登录"，然后断言
    页面在打开后自动去申请一次性同步票据 —— 那是自动同步真正启动的第一个
    网络动作。

场景 C（扩展注入较晚）：
    同场景 B，但伪造的 content script 延迟 1500ms 才注册监听，模拟
    ``run_at: document_idle`` 晚于 React 挂载。探测必须重试才能发现扩展；
    单次 ping 会漏掉，导致"已装扩展却不同步"。

故意不应答 sync-request：本脚本不导入 Cookie、不启动验证浏览器、不访问真实
平台账号。后端返回的票据是内存态、60 秒过期。

前置：后端已在运行，且已构建前端（webui/dist）。
用法：
    uv run python scripts/auto_account_sync_smoke.py
    uv run python scripts/auto_account_sync_smoke.py --channel chromium
"""

import argparse
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from playwright.sync_api import sync_playwright

DEFAULT_BASE = "http://127.0.0.1:8080"

# 伪造 content script：只应答 ping，让网页认为扩展已安装且版本可用。
FAKE_EXTENSION = """
window.addEventListener('message', (event) => {
  const m = event.data;
  if (m && m.source === 'mc-accounts' && m.type === 'ping') {
    window.postMessage({
      source: 'mc-accounts', type: 'pong',
      extension_protocol_version: 2, extension_version: '1.1.3',
    }, '*');
  }
});
"""

LICENSE_ACCEPTED = "localStorage.setItem('mediacrawler_license_accepted', 'true')"


def _new_page(browser, fake_extension: bool, extension_delay_ms: int = 0):
    context = browser.new_context()
    context.add_init_script(LICENSE_ACCEPTED)
    if fake_extension:
        if extension_delay_ms > 0:
            # 模拟 content script 以 document_idle 注入、晚于 React 挂载：
            # 单次 ping 会石沉大海，探测必须重试才能发现扩展。
            context.add_init_script(
                "setTimeout(() => {%s}, %d);" % (FAKE_EXTENSION, extension_delay_ms))
        else:
            context.add_init_script(FAKE_EXTENSION)
    page = context.new_page()
    errors: list[str] = []
    page.on("pageerror", lambda e: errors.append(str(e)))
    return context, page, errors


def _wait_for_ticket(page, timeout_ms: int) -> bool:
    """等到（或等不到）自动同步申请的票据请求。"""
    try:
        with page.expect_request(
            lambda r: r.method == "POST" and r.url.endswith("/sync-ticket"),
            timeout=timeout_ms,
        ):
            return True
    except Exception:
        return False


def scenario_no_extension(browser, base: str) -> bool:
    print("\n=== 场景 A：未安装扩展 → 不得发起同步 ===")
    context, page, errors = _new_page(browser, fake_extension=False)
    sync_requests: list[str] = []
    page.on("request", lambda r: sync_requests.append(r.url)
            if r.method == "POST" and r.url.endswith("/sync") else None)
    fired = False
    try:
        # 期望窗口覆盖"页面加载 + 扩展探测 + 首次账号加载 + 自动同步判定"。
        with page.expect_request(
            lambda r: r.method == "POST" and r.url.endswith("/sync-ticket"),
            timeout=10000,
        ):
            page.goto(base, wait_until="domcontentloaded", timeout=30000)
        fired = True  # with 正常退出 = 真的收到了票据请求
    except Exception:
        fired = False
    # 判定发生在账号状态首次就绪之后，再留一点时间确认没有迟到动作。
    page.wait_for_timeout(3000)
    body = page.inner_text("body")
    rendered = "搜索" in body
    context.close()

    print("  搜索界面已渲染    :", rendered)
    print("  页面未捕获错误    :", errors or "无")
    print("  误发起的同步票据  :", "有（错误）" if fired else "无（正确）")
    print("  误发起的 /sync    :", sync_requests or "无（正确）")
    ok = rendered and not errors and not fired and not sync_requests
    print("  场景 A:", "PASS" if ok else "FAIL")
    return ok


def scenario_extension_online(browser, base: str, delay_ms: int = 0) -> bool:
    label = "场景 B：扩展在线 + 有未验证平台 → 打开即自动同步" if delay_ms == 0 else \
        "场景 C：扩展注入较晚（document_idle 晚于应用挂载）→ 仍须自动同步"
    print("\n=== %s ===" % label)
    context, page, errors = _new_page(browser, fake_extension=True,
                                      extension_delay_ms=delay_ms)

    def patch_accounts(route):
        resp = route.fetch()
        try:
            data = resp.json()
        except Exception:
            route.fulfill(response=resp)
            return
        for account in data.get("accounts", []):
            if account.get("platform") == "bilibili":
                account["status"] = "unverified"
                account["verified"] = False
                account["safe_error_code"] = None
        route.fulfill(status=200, content_type="application/json",
                      body=json.dumps(data))

    page.route("**/api/search/accounts", patch_accounts)

    started = time.time()
    fired = False
    try:
        with page.expect_request(
            lambda r: r.method == "POST" and r.url.endswith("/sync-ticket"),
            timeout=30000,
        ):
            page.goto(base, wait_until="domcontentloaded", timeout=30000)
        fired = True  # with 正常退出 = 真的收到了票据请求
    except Exception:
        fired = False
    elapsed = time.time() - started

    banner = "正在自动同步登录状态" in page.inner_text("body")
    context.close()

    print("  自动同步已触发    :", fired)
    print("  自动同步横幅可见  :", banner)
    print("  打开页面→发起同步 :", "%.1f 秒" % elapsed if fired else "未触发")
    print("  页面未捕获错误    :", errors or "无")
    ok = fired and not errors
    print("  %s: %s" % ("场景 B" if delay_ms == 0 else "场景 C", "PASS" if ok else "FAIL"))
    return ok


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-url", default=DEFAULT_BASE)
    parser.add_argument("--channel", default="msedge",
                        help="Playwright 浏览器通道（默认系统 Edge）")
    args = parser.parse_args()

    with sync_playwright() as p:
        browser = p.chromium.launch(channel=args.channel, headless=True)
        try:
            a = scenario_no_extension(browser, args.base_url)
            b = scenario_extension_online(browser, args.base_url, delay_ms=0)
            c = scenario_extension_online(browser, args.base_url, delay_ms=1500)
        finally:
            browser.close()

    print("\n总计:", "全部 PASS" if (a and b and c) else "存在 FAIL")
    return 0 if (a and b and c) else 1


if __name__ == "__main__":
    raise SystemExit(main())
