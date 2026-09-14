# -*- coding: utf-8 -*-
# Copyright (c) 2025 relakkes@gmail.com
# This file is part of MediaCrawler project.
# Licensed under NON-COMMERCIAL LEARNING LICENSE 1.1

"""二维码弹窗策略测试。

背景（用户实测反馈）：应用自带扫码登录会打开一个**可见**浏览器窗口，平台登录页
自己就画着二维码；此时 ``tools.crawler_util.show_qrcode`` 再用系统图片查看器弹
一个二维码，纯属重复且会盖住浏览器窗口。

因此弹窗只在无头模式保留（无头时没有别的办法把二维码递给用户）。
"""

import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import config
import tools.crawler_util as crawler_util

# 一段合法 data URL 形态的 base64（内容本身无所谓：可见模式下不该被解码）。
_QR_DATA_URL = "data:image/png;base64,iVBORw0KGgo="


class _DialogReached(Exception):
    """哨兵：说明函数真的走到了"打开/显示图片"那一步。"""


def _fail_if_opened(_data):
    raise _DialogReached("Image.open was called")


def test_show_qrcode_is_noop_when_browser_is_visible(monkeypatch):
    """HEADLESS=False（默认，含应用自带扫码登录）→ 不弹窗、不解码。"""
    monkeypatch.setattr(config, "HEADLESS", False)
    monkeypatch.setattr(crawler_util.Image, "open", _fail_if_opened)

    # 不抛 _DialogReached 就说明在弹窗之前就返回了。
    crawler_util.show_qrcode(_QR_DATA_URL)


def test_show_qrcode_still_pops_up_when_headless(monkeypatch):
    """HEADLESS=True → 保留弹窗（这里用哨兵证明确实走到了那一步）。"""
    monkeypatch.setattr(config, "HEADLESS", True)
    monkeypatch.setattr(crawler_util.Image, "open", _fail_if_opened)

    with pytest.raises(_DialogReached):
        crawler_util.show_qrcode(_QR_DATA_URL)


def test_show_qrcode_reads_headless_flag_at_call_time(monkeypatch):
    """必须是调用时读取 config.HEADLESS，而不是 import 时快照。

    worker 会在运行中改写 config.HEADLESS（登录模式强制 False），
    快照会让开关失效。
    """
    monkeypatch.setattr(crawler_util.Image, "open", _fail_if_opened)

    monkeypatch.setattr(config, "HEADLESS", False)
    crawler_util.show_qrcode(_QR_DATA_URL)  # 不弹

    monkeypatch.setattr(config, "HEADLESS", True)
    with pytest.raises(_DialogReached):
        crawler_util.show_qrcode(_QR_DATA_URL)  # 同一个进程内立刻切到弹窗

    monkeypatch.setattr(config, "HEADLESS", False)
    crawler_util.show_qrcode(_QR_DATA_URL)  # 再切回来仍然不弹
