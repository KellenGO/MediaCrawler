"""Verify metrics on the current search batch without repeating the search.

Restores cookies from existing headless profiles, never prints them, and uses
the normal post-search hydrator. Does not mutate the running server's job.
"""
import asyncio
import json
import logging
from pathlib import Path
import sys
import urllib.request

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


async def main():
    from playwright.async_api import async_playwright
    from tools.browser_launcher import resolve_playwright_browser
    from api.services.accounts import profile_dir_for, PLATFORM_COOKIE_URLS, set_session_snapshot
    from api.services.result_hydration import ResultHydrator
    from aggregate_search.models import UnifiedSearchResult

    logging.disable(logging.CRITICAL)
    data = json.load(urllib.request.urlopen("http://127.0.0.1:8080/api/search/jobs/current", timeout=10))
    rows = {}
    for result in data["results"]:
        for source in result.get("grouped_sources") or [result]:
            if source["platform"] in ("bilibili", "zhihu"):
                rows[(source["platform"], source["content_id"])] = UnifiedSearchResult(**source)
    async with async_playwright() as playwright:
        executable, channel, _ = resolve_playwright_browser()
        for platform in ("bilibili", "zhihu"):
            kwargs = {"headless": True}
            if executable:
                kwargs["executable_path"] = executable
            elif channel:
                kwargs["channel"] = channel
            context = await playwright.chromium.launch_persistent_context(str(profile_dir_for(platform)), **kwargs)
            try:
                cookies = await context.cookies(PLATFORM_COOKIE_URLS[platform])
                await set_session_snapshot(platform, {c["name"]: c["value"] for c in cookies})
            finally:
                await context.close()
    hydrator = ResultHydrator()
    try:
        await hydrator.hydrate_metrics(list(rows.values()), asyncio.Event(), lambda _: None)
    finally:
        await hydrator.close()
    for platform in ("bilibili", "zhihu"):
        results = [r for r in rows.values() if r.platform == platform]
        print(json.dumps({"platform": platform, "count": len(results), "coverage": {
            k: sum(k in r.metrics for r in results) for k in
            ("view_count", "like_count", "comment_count", "collect_count", "coin_count")},
            "states": {s: sum(r.metrics_status == s for r in results) for s in ("complete", "partial", "failed")},
            "missing_views_types": [r.content_type for r in results if "view_count" not in r.metrics],
            "error": hydrator.metric_errors.get(platform)}, ensure_ascii=False), flush=True)


if __name__ == "__main__":
    asyncio.run(main())
