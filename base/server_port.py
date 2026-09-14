# -*- coding: utf-8 -*-
# Copyright (c) 2025 relakkes@gmail.com
# This file is part of MediaCrawler project.
# Licensed under NON-COMMERCIAL LEARNING LICENSE 1.1

"""后端监听端口的单一来源。

产品默认仍然是 ``127.0.0.1:8080``（文档、浏览器扩展的 host 权限都按它写）。
但同一个仓库可能有多个 check-out（git worktree）同时跑，第二个实例会撞端口，
所以允许用环境变量 ``SIYE_PORT`` 覆盖。

所有"自己监听/自己访问"的入口都必须走这里，避免端口在多处各写一份、改一个漏一个：
- ``api/main.py``（``python -m api.main``）
- ``desktop_main.py``（桌面/打包入口）

启动脚本（``MediaCrawler.bat`` / ``启动-源码.bat`` / ``scripts/start.ps1``）读同一个变量名；
扩展与文档保持产品默认，见各自的说明。
"""

from __future__ import annotations

import os

#: 覆盖端口用的环境变量名。
ENV_VAR = "SIYE_PORT"

#: 产品默认端口（与 README、浏览器扩展 manifest 保持一致）。
DEFAULT_PORT = 8080


def resolve_port(default: int = DEFAULT_PORT) -> int:
    """解析本次进程应该监听的端口。

    优先级：``SIYE_PORT``（合法时）→ ``default``。
    非数字、空值、越界（<1 或 >65535）一律**静默回退**到默认端口 ——
    启动阶段不该因为一个打错的环境变量直接崩掉。
    """
    raw = os.environ.get(ENV_VAR, "")
    if not isinstance(raw, str):
        return default
    raw = raw.strip()
    if not raw:
        return default
    try:
        port = int(raw)
    except (TypeError, ValueError):
        return default
    if not 1 <= port <= 65535:
        return default
    return port


def base_url(port: int | None = None, host: str = "127.0.0.1") -> str:
    """拼出本机页面地址（给"启动后打开浏览器"这类用途）。"""
    return f"http://{host}:{port if port is not None else resolve_port()}"
