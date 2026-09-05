"""Exercise the built result library UI with mocked APIs and an isolated browser.

Run after `cd webui && npm run build`: python scripts/result_library_smoke.py
Uses the project's existing Playwright dependency and system Edge by default.
"""

from __future__ import annotations

import argparse
import csv
import io
import json
import re
import threading
from datetime import datetime, timedelta, timezone
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from tempfile import TemporaryDirectory
from urllib.parse import urlparse

from playwright.sync_api import expect, sync_playwright


ROOT = Path(__file__).resolve().parents[1]
BOOKMARKS_KEY = "aggregate_search_bookmarks_v1"


class QuietHandler(SimpleHTTPRequestHandler):
    def log_message(self, format, *args):
        pass


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--channel", default="msedge", help="Browser channel, or chromium")
    args = parser.parse_args()
    dist = ROOT / "webui" / "dist"
    if not (dist / "index.html").is_file():
        raise SystemExit("Build webui first: npm run build")
    now = datetime.now(timezone.utc)
    fetched = now.isoformat()

    def source(platform, content_id, title, kind, url, age):
        return dict(platform=platform, content_id=content_id, title=title,
                    content_type=kind, url=url, author="测试作者", snippet="研究素材摘要",
                    published_at=(now - timedelta(days=age)).isoformat(), cover_url=None,
                    metrics={"like_count": 12}, rank=1, grouped_sources=None)

    note = source("xhs", "old-note", "研究素材图文", "note", "https://www.xiaohongshu.com/explore/old-note", 20)
    video = source("bilibili", "new-video", "研究素材视频", "video", "https://www.bilibili.com/video/new-video", 1)
    article = source("zhihu", "article", "独立文章", "article", "https://zhuanlan.zhihu.com/p/article", 2)
    group = {**note, "grouped_sources": [note, video]}
    job = dict(job_id="library-smoke", overall="completed", keyword="研究素材",
               created_at=fetched, completed_at=fetched, total_ms=100,
               hydration_status="completed", results=[group, article],
               platforms={p: dict(status="succeeded", result_count=1, error_summary=None,
                                  fetched_at=fetched, cache_hit=False)
                          for p in ("xhs", "bilibili", "zhihu")})
    serving_job = True
    api_writes = []
    errors = []
    server = ThreadingHTTPServer(("127.0.0.1", 0), partial(QuietHandler, directory=str(dist)))
    threading.Thread(target=server.serve_forever, daemon=True).start()
    origin = f"http://127.0.0.1:{server.server_port}"

    def route_request(route):
        url = urlparse(route.request.url)
        if not route.request.url.startswith(origin + "/"):
            route.abort()
        elif url.path.startswith("/api/"):
            if route.request.method != "GET":
                api_writes.append((route.request.method, url.path))
            if url.path == "/api/health":
                data = {"status": "ok", "environment_status": "ok"}
            elif url.path == "/api/search/accounts":
                data = {"accounts": []}
            elif url.path.startswith("/api/search/jobs/"):
                data = job if serving_job else None
            else:
                data = {}
            route.fulfill(json=data)
        else:
            route.continue_()

    try:
        (ROOT / "build").mkdir(exist_ok=True)
        with TemporaryDirectory(prefix="result-library-", dir=ROOT / "build") as temp, sync_playwright() as p:
            browser = p.chromium.launch(**({} if args.channel == "chromium" else {"channel": args.channel}))
            context = browser.new_context(viewport={"width": 1280, "height": 900},
                                          permissions=["clipboard-read", "clipboard-write"])
            context.add_init_script("localStorage.setItem('mediacrawler_license_accepted', 'true')")
            context.route("**/*", route_request)
            page = context.new_page()
            page.on("pageerror", lambda error: errors.append(str(error)))
            page.goto(origin)
            expect(page.get_by_role("button", name="收藏全部来源 研究素材图文", exact=True)).to_be_visible()
            page.get_by_label("发布时间筛选").select_option("7")
            page.get_by_label("内容类型筛选").select_option("note")
            expect(page.get_by_role("button", name="导出 CSV", exact=True)).to_be_disabled()
            page.get_by_label("内容类型筛选").select_option("video")
            expect(page.get_by_role("checkbox", name="选择 研究素材视频", exact=True)).to_be_visible()
            page.get_by_label("结果内关键词").fill("视频")
            expect(page.locator("mark")).to_have_text(["视频"])
            page.get_by_role("button", name="清除筛选", exact=True).click()
            page.get_by_role("button", name="收藏全部来源 研究素材图文", exact=True).click()
            page.get_by_role("button", name="本地收藏（2）", exact=True).click()
            library = page.get_by_role("region", name="本地收藏", exact=True)
            expect(library.get_by_role("checkbox")).to_have_count(3)
            library.get_by_label("备注 研究素材视频", exact=True).fill("稍后整理，保留原文")
            library.locator("button:enabled").filter(has_text=re.compile("^保存备注$")).click()
            expect(library.get_by_text("尚未保存", exact=False)).to_have_count(0)

            page.reload()
            page.get_by_role("button", name="本地收藏（2）", exact=True).click()
            expect(library.get_by_label("备注 研究素材视频", exact=True)).to_have_value("稍后整理，保留原文")
            library.get_by_role("checkbox", name="选择 研究素材视频", exact=True).check()
            for label, filename in (("导出 CSV", "selected.csv"), ("导出 Markdown", "selected.md")):
                with page.expect_download() as download:
                    library.get_by_role("button", name=label, exact=True).click()
                path = Path(temp) / filename
                download.value.save_as(path)
                text = path.read_text(encoding="utf-8-sig")
                assert "稍后整理，保留原文" in text and video["url"] in text
                assert note["url"] not in text and fetched in text
                if filename.endswith(".csv"):
                    rows = list(csv.DictReader(io.StringIO(text)))
                    assert len(rows) == 1 and rows[0]["标题"] == video["title"]
                    assert rows[0]["收藏时间"]
            library.get_by_role("button", name="复制链接", exact=True).click()
            expect(page.get_by_text("原文链接已复制", exact=True)).to_be_visible()
            assert page.evaluate("navigator.clipboard.readText()") == video["url"]

            # No recovered job is needed to access previously saved content.
            serving_job = False
            page.evaluate("sessionStorage.clear()")
            page.reload()
            page.get_by_role("button", name="本地收藏（2）", exact=True).click()
            expect(library.get_by_label("备注 研究素材视频", exact=True)).to_have_value("稍后整理，保留原文")
            for width in (390, 320, 1280):
                page.set_viewport_size({"width": width, "height": 900})
                assert page.evaluate("document.documentElement.scrollWidth <= innerWidth"), f"Overflow at {width}px"

            # Real storage events from another tab must update this page.
            other = context.new_page()
            other.goto(origin)
            other.get_by_role("button", name="本地收藏（2）", exact=True).click()
            other.get_by_role("button", name="取消收藏 研究素材图文", exact=True).click()
            expect(library.get_by_role("button", name="取消收藏 研究素材图文", exact=True)).to_have_count(0)
            assert page.evaluate(f"JSON.parse(localStorage.getItem('{BOOKMARKS_KEY}')).items.length") == 1
            other.close()

            serving_job = True
            page.reload()
            expect(page.get_by_role("button", name="收藏 独立文章", exact=True)).to_be_visible()
            page.evaluate("""key => {
                const original = Storage.prototype.setItem;
                Storage.prototype.setItem = function(k, v) {
                    if (k === key) throw new DOMException('Denied', 'QuotaExceededError');
                    return original.call(this, k, v);
                };
            }""", BOOKMARKS_KEY)
            page.get_by_role("button", name="收藏 独立文章", exact=True).click()
            expect(page.get_by_text("收藏未保存：浏览器存储不可用或空间不足。请先导出已有收藏。", exact=True)).to_be_visible()
            expect(page.get_by_role("button", name="收藏 独立文章", exact=True)).to_have_attribute("aria-pressed", "false")
            assert page.evaluate(f"JSON.parse(localStorage.getItem('{BOOKMARKS_KEY}')).items.length") == 1
            assert not errors, errors
            assert not api_writes, api_writes
            browser.close()
    finally:
        server.shutdown()
        server.server_close()
    print(json.dumps({"result": "passed", "checks": ["group filters", "highlight", "bookmark reload",
                     "notes", "selected CSV/Markdown export", "clipboard", "idle library", "mobile layout",
                     "cross-tab updates", "storage failure", "no API writes", "no page errors"]}))


if __name__ == "__main__":
    main()
