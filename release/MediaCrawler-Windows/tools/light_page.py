# -*- coding: utf-8 -*-
# Copyright (c) 2025 relakkes@gmail.com
#
# This file is part of MediaCrawler project.
# Repository: https://github.com/NanmiCoder/MediaCrawler/blob/main/tools/light_page.py
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

"""聚合搜索轻量页面加载（Round 16，仅 aggregate 模式启用）。

- goto 使用 ``domcontentloaded``（不等待图片/字体等资源）；
- 拦截 image / media / font，以及已确认无关的 analytics 域名；
- 绝不拦截 document / script / stylesheet / XHR / fetch（否则会破坏页面
  逻辑与数据请求）；但明确 analytics hostname 仍按安全规则拦截；
- analytics 判定基于 ``urlparse(url).hostname``（Round 16.1）：hostname
  等于允许域名或其子域才拦截 —— 绝不 endswith 完整 URL（路径/query 会
  干扰），也不命中恶意相似域名（如 google-analytics.com.evil.example）；
- route handler 随 browser context 关闭自动清理，无全局残留。
"""

from typing import Any
from urllib.parse import urlparse

# 已知与内容无关的 analytics 域名（保守白名单，绝不误伤平台自身 API）。
_ANALYTICS_DOMAINS = (
    "google-analytics.com",
    "googletagmanager.com",
    "hm.baidu.com",
    "umeng.com",
    "umengcloud.com",
    "cnzz.com",
    "cpro.baidu.com",
    "pos.baidu.com",
)

# 轻量导航参数：只等 DOM 就绪。
LIGHT_GOTO_KWARGS: dict = {"wait_until": "domcontentloaded"}


def _is_analytics(url: str) -> bool:
    """hostname 等于允许域名或以 .domain 结尾的子域才拦截。

    URL path/query 不参与匹配；大小写不敏感；恶意相似域名（如
    google-analytics.com.evil.example）不命中。
    """
    try:
        host = urlparse(url or "").hostname
    except ValueError:
        return False
    if not host:
        return False
    host = host.lower().rstrip(".")
    for domain in _ANALYTICS_DOMAINS:
        if host == domain or host.endswith("." + domain):
            return True
    return False


async def install_light_page_routes(context: Any) -> None:
    """在 context 上注册轻量拦截 route（随 context 关闭自动清理）。

    只拦截 image/media/font 与已确认无关的 analytics；document/script/
    stylesheet/XHR/fetch 绝不因 resource type 被拦截（analytics hostname
    例外，按安全规则拦截）。
    """
    try:
        await context.route("**/*", _light_route_handler)
    except Exception:
        # 某些 context 状态（已关闭/无路由能力）下注册失败不应影响主流程。
        pass


async def _light_route_handler(route: Any) -> None:
    try:
        request = route.request
        resource_type = getattr(request, "resource_type", None)
        if resource_type in ("image", "media", "font") or _is_analytics(request.url):
            await route.abort()
        else:
            await route.continue_()
    except Exception:
        # route 已被取消/页面已关闭：静默放行失败路径，不抛异常。
        try:
            await route.continue_()
        except Exception:
            pass


def light_goto_kwargs() -> dict:
    """聚合搜索的 goto 参数（domcontentloaded）。"""
    return dict(LIGHT_GOTO_KWARGS)
