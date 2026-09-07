"""Browser acceptance for search statistics and cooldowns; all APIs are mocked.

Build webui first, then run with the existing Python Playwright dependency.
Uses an isolated Edge context, never the user's browser profile or accounts.
"""

from __future__ import annotations

import json
import re
import sys
import threading
from datetime import datetime, timedelta, timezone
from functools import partial
from http.server import ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse

from playwright.sync_api import expect, sync_playwright
from result_library_smoke import QuietHandler

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from api.services.search_job_manager import _ActiveJob  # noqa: E402
from api.services.search_metrics import PlatformCooldowns, SearchMetrics  # noqa: E402


def main():
    if not (ROOT / "webui/dist/index.html").is_file():
        raise SystemExit("Build webui first: npm run build")
    metrics = SearchMetrics()
    sample = _ActiveJob("sample", "test", ["xhs", "bilibili"], 10)
    for platform, status in (("xhs", "rate_limited"), ("bilibili", "empty")):
        sample.worker_platforms.add(platform)
        sample.set_platform_status(platform, status)
        sample.timings[platform].first_result_ms = 1500
        sample.timings[platform].total_ms = 3000
        sample.timings[platform].fallback_active = False
    sample.finalize()
    metrics.record(sample)
    statistics = metrics.snapshot(PlatformCooldowns())
    empty = SearchMetrics().snapshot(PlatformCooldowns())
    now = datetime.now(timezone.utc)
    job = sample.to_response().model_dump(mode="json")
    job["platforms"]["xhs"]["cooldown_until"] = (now + timedelta(seconds=60)).isoformat()
    job["platforms"]["xhs"]["cooldown_skipped"] = True
    mode = "ok"
    counts = {"statistics": 0, "writes": 0}
    errors = []
    server = ThreadingHTTPServer(("127.0.0.1", 0), partial(QuietHandler, directory=str(ROOT / "webui/dist")))
    threading.Thread(target=server.serve_forever, daemon=True).start()
    origin = f"http://127.0.0.1:{server.server_port}"

    def route_request(route):
        path = urlparse(route.request.url).path
        if not route.request.url.startswith(origin + "/"):
            route.abort()
        elif path.startswith("/api/"):
            counts["writes"] += int(route.request.method != "GET")
            if path == "/api/search/statistics":
                counts["statistics"] += 1
                if mode == "error":
                    route.fulfill(status=503, json={"detail": "unavailable"})
                    return
                data = empty if mode == "empty" else statistics
            elif path == "/api/health":
                data = {"status": "ok", "environment_status": "ok"}
            elif path == "/api/search/accounts":
                data = {"accounts": []}
            elif path.startswith("/api/search/jobs"):
                data = job
            else:
                data = {}
            route.fulfill(json=data)
        else:
            route.continue_()

    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(channel="msedge")
            context = browser.new_context(viewport={"width": 1280, "height": 900})
            context.add_init_script("localStorage.setItem('mediacrawler_license_accepted', 'true')")
            context.route("**/*", route_request)
            page = context.new_page()
            page.on("pageerror", lambda error: errors.append(str(error)))
            page.clock.install(time=now)
            page.goto(origin)
            retry = page.get_by_role("button", name="重试 小红书", exact=True)
            expect(retry).to_be_disabled()
            expect(page.get_by_text(re.compile(r"冷却 \d+ 秒 · 未发起请求"))).to_be_visible()
            assert counts["statistics"] == 0
            page.get_by_role("button", name="查看搜索统计", exact=True).click()
            panel = page.get_by_role("region", name="最近搜索统计")
            expect(panel.get_by_text("参与 1 次 · 实际搜索 1 次", exact=True)).to_have_count(2)
            expect(panel.get_by_text("成功率 0%（0/1）", exact=True)).to_be_visible()
            expect(panel.get_by_text("成功率 100%（1/1）", exact=True)).to_be_visible()
            expect(panel.get_by_text("成功率 暂无样本（0/0）", exact=True)).to_have_count(2)
            mode = "error"
            panel.get_by_role("button", name="刷新统计", exact=True).click()
            expect(panel.get_by_role("alert")).to_contain_text("以下保留上次统计")
            mode = "empty"
            panel.get_by_role("button", name="刷新统计", exact=True).click()
            expect(panel.get_by_text("完成搜索后会在这里显示数据。", exact=False)).to_be_visible()
            mode = "ok"
            panel.get_by_role("button", name="刷新统计", exact=True).click()
            expect(panel.get_by_text("成功率 100%（1/1）", exact=True)).to_be_visible()
            for width in (320, 390, 1280):
                page.set_viewport_size({"width": width, "height": 900})
                assert page.evaluate("document.documentElement.scrollWidth <= innerWidth"), f"Overflow at {width}"
            page.get_by_role("button", name="收起搜索统计", exact=True).click()
            previous = counts["statistics"]
            page.clock.fast_forward(61000)
            expect(retry).to_be_enabled()
            assert counts["statistics"] == previous  # Closed panel stops polling.
            assert counts["writes"] == 0  # Expiry does not auto-retry.
            assert not errors, errors
            browser.close()
    finally:
        server.shutdown()
        server.server_close()
    print(json.dumps({"result": "passed", "checks": ["cooldown disable/expiry", "no automatic retry",
                     "statistics lazy load", "error preserves snapshot", "empty samples", "recovery",
                     "mobile layout", "closed panel stops polling", "no page errors"]}))


if __name__ == "__main__":
    main()
