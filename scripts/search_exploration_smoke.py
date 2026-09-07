"""Exercise exploration UI against isolated mocked APIs; no platform traffic."""
import json
import threading
from copy import deepcopy
from datetime import datetime, timezone
from functools import partial
from http.server import ThreadingHTTPServer
from urllib.parse import urlparse

from playwright.sync_api import expect, sync_playwright
from result_library_smoke import ROOT, QuietHandler, BOOKMARKS_KEY


def main():
    fetched = datetime.now(timezone.utc).isoformat()
    def note(content_id, title, platform="xhs"):
        return dict(platform=platform, content_id=content_id, title=title, content_type="note",
            url=(f"https://www.xiaohongshu.com/explore/{content_id}" if platform == "xhs" else f"https://www.bilibili.com/video/{content_id}"), author="测试作者",
            snippet="用于验证分页的素材摘要", published_at=None, cover_url=None, metrics={}, rank=0)
    old = note("old", "第一批收藏素材")
    new = note("new", "第二批新素材")
    version = note("video", old["title"], "bilibili")
    platforms = {p: dict(status="succeeded", result_count=1, error_summary=None,
                         fetched_at=fetched, cache_hit=False) for p in ("xhs", "bilibili")}
    first = dict(job_id="round-1", keyword="素材", overall="completed", created_at=fetched,
        completed_at=fetched, hydration_status="completed", total_ms=100, platforms=platforms, results=[old])
    first["exploration"] = dict(id="topic", round=1, max_per_platform=100, new_sources=1, new_contents=1,
        page_requests=2, duplicates=0, platforms={p: dict(collected=int(p == "xhs"), has_more=True) for p in platforms},
        previous_batches=[])
    def batch(job, number):
        return {**{key: deepcopy(job[key]) for key in ("job_id", "overall", "completed_at", "platforms", "results")}, "number": number}
    second = deepcopy(first)
    second.update(job_id="round-2", results=[new])
    prior = batch(first, 1)
    prior["results"] = [{**old, "grouped_sources": [old, version]}]
    second["exploration"].update(round=2, new_sources=2, new_contents=1, previous_batches=[prior],
        platforms={"xhs": dict(collected=2, has_more=True), "bilibili": dict(collected=1, has_more=False)})
    third = deepcopy(second)
    third.update(job_id="round-3", results=[])
    third["exploration"].update(round=3, new_sources=0, new_contents=0, previous_batches=[prior, batch(second, 2)],
        platforms={"xhs": dict(collected=2, has_more=False), "bilibili": dict(collected=1, has_more=False)})
    current = deepcopy(first)
    posts, errors = [], []
    server = ThreadingHTTPServer(("127.0.0.1", 0), partial(QuietHandler, directory=str(ROOT / "webui/dist")))
    threading.Thread(target=server.serve_forever, daemon=True).start()
    origin = f"http://127.0.0.1:{server.server_port}"

    def route_request(route):
        nonlocal current
        request = route.request
        path = urlparse(request.url).path
        if not request.url.startswith(origin + "/"):
            return route.abort()
        if not path.startswith("/api/"):
            return route.continue_()
        if path == "/api/search/jobs" and request.method == "POST":
            req = request.post_data_json
            posts.append(req)
            if req.get("continue_from") == "round-1":
                current = deepcopy(second)
            elif req.get("continue_from") == "round-2":
                current = deepcopy(third)
            else:
                current = deepcopy(first)
                current["job_id"] = "refreshed"
            return route.fulfill(json=current, status=201)
        if path.startswith("/api/search/jobs/"):
            data = current
        elif path == "/api/health":
            data = {"status": "ok", "environment_status": "ok", "version": "smoke", "version_match": True}
        elif path == "/api/search/accounts":
            data = {"accounts": []}
        else:
            data = {}
        route.fulfill(json=data)

    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(channel="msedge")
            context = browser.new_context(viewport={"width": 1280, "height": 900})
            context.add_init_script("localStorage.setItem('mediacrawler_license_accepted', 'true')")
            context.route("**/*", route_request)
            page = context.new_page()
            page.on("pageerror", lambda error: errors.append(str(error)))
            page.goto(origin)
            expect(page.get_by_role("button", name="换一批", exact=True)).to_be_enabled()
            expect(page.get_by_role("button", name="刷新结果", exact=True)).to_have_count(0)
            page.get_by_role("button", name="收藏 第一批收藏素材", exact=True).click()
            page.get_by_role("button", name="换一批", exact=True).click()
            expect(page.get_by_role("button", name="收藏 第二批新素材", exact=True)).to_be_visible()
            assert len(posts) == 1 and posts[0]["continue_from"] == "round-1"
            assert posts[0]["bypass_cache"] is True and posts[0]["limit_per_platform"] == 20
            assert "pagination" not in posts[0]
            page.locator("summary").filter(has_text="更多").click()
            page.get_by_label("查看轮次", exact=True).select_option("1")
            expect(page.get_by_role("button", name="选择收藏平台 第一批收藏素材", exact=True)).to_be_visible()
            expect(page.get_by_role("button", name="收藏 第二批新素材", exact=True)).to_have_count(0)
            assert page.evaluate(f"JSON.parse(localStorage.getItem('{BOOKMARKS_KEY}')).items.length") == 1
            page.reload()
            expect(page.get_by_role("button", name="收藏 第二批新素材", exact=True)).to_be_visible()
            page.locator("summary").filter(has_text="更多").click()
            page.get_by_label("查看轮次", exact=True).select_option("1")
            expect(page.get_by_role("button", name="选择收藏平台 第一批收藏素材", exact=True)).to_be_visible()
            page.get_by_label("查看轮次", exact=True).select_option("2")
            page.locator("summary").filter(has_text="更多").click()
            page.get_by_role("button", name="换一批", exact=True).click()
            expect(page.get_by_role("button", name="换一批", exact=True)).to_be_disabled()
            assert posts[-1]["continue_from"] == "round-2" and posts[-1]["platforms"] == ["xhs"]
            page.locator("summary").filter(has_text="更多").click()
            page.get_by_label("查看轮次", exact=True).select_option("2")
            expect(page.get_by_role("button", name="收藏 第二批新素材", exact=True)).to_be_visible()
            page.get_by_role("button", name="刷新结果", exact=True).click()
            expect(page.get_by_role("button", name="取消收藏 第一批收藏素材", exact=True)).to_be_visible()
            assert "continue_from" not in posts[-1] and posts[-1]["bypass_cache"] is True
            assert set(posts[-1]["platforms"]) == {"xhs", "bilibili"}
            for width in (390, 320):
                page.set_viewport_size({"width": width, "height": 844})
                assert page.evaluate("document.documentElement.scrollWidth <= window.innerWidth")
            page.set_viewport_size({"width": 1280, "height": 900})
            page.screenshot(path=str(ROOT / "build/search-exploration-desktop.png"), full_page=True)
            assert errors == [], errors
            context.close()
            browser.close()
        print(json.dumps({"passed": True, "search_posts": len(posts), "checks": [
            "next_batch", "distinct_results", "old_round_versions", "bookmarks_preserved", "reload_recovery",
            "exhaustion", "refresh_from_start", "collapsed_actions", "mobile_320_390"]}))
    finally:
        server.shutdown()
        server.server_close()


if __name__ == "__main__":
    main()
