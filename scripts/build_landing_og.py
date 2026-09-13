"""生成推广落地页的社交分享卡片图 site/og.png（1200x630）。

og:image 是分享到微信 / 群 / 社交平台时卡片上的大图。它没有单独的源文件，
而是「把落地页首屏按 1200x630 截一张图」，因此改了落地页文案或配色后重新跑一次即可。

用法（仓库根目录）：

    .venv/Scripts/python.exe scripts/build_landing_og.py
    # 或
    uv run python scripts/build_landing_og.py

需要本机有 Chrome / Edge（走 Playwright 的 channel="msedge"），
与仓库里其他 smoke 脚本一致：不联网、不访问任何平台。
"""

from __future__ import annotations

import pathlib
import sys

from playwright.sync_api import sync_playwright

ROOT = pathlib.Path(__file__).resolve().parent.parent
PAGE = ROOT / "site" / "index.html"
OUT = ROOT / "site" / "og.png"

# 截图时压紧首屏（隐去导航与徽章、缩小字标），让结果页能完整露出
# 「搜索框 + 标题 + 平台进度 + 结果行」这一段，而不是被切掉半个窗口。
SHOT_CSS = """
.topbar{display:none !important}
.hero{padding:22px 0 0 !important}
.hero .pill{display:none !important}
.wordmark{font-size:42px !important}
.wordmark i{width:88px !important;height:6px !important;margin-top:6px !important}
.hero h1{font-size:28px !important;margin:18px auto 12px !important}
.hero .description{font-size:13.5px !important;margin-bottom:20px !important;max-width:60ch !important}
.checks{margin-bottom:18px !important}
.mock-wrap{margin-top:30px !important}
.mock-cap{display:none !important}
"""


def main() -> int:
    if not PAGE.exists():
        print(f"找不到落地页: {PAGE}", file=sys.stderr)
        return 1

    with sync_playwright() as p:
        browser = p.chromium.launch(channel="msedge")
        page = browser.new_page(viewport={"width": 1200, "height": 630}, device_scale_factor=1)
        page.goto(PAGE.as_uri())
        page.wait_for_timeout(1400)
        page.evaluate("document.documentElement.style.scrollBehavior='auto'")
        page.add_style_tag(content=SHOT_CSS)
        page.evaluate("window.scrollTo(0, 0)")
        page.wait_for_timeout(500)
        page.screenshot(path=str(OUT))
        browser.close()

    print(f"已写入 {OUT.relative_to(ROOT)}（1200x630，{OUT.stat().st_size} 字节）")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
