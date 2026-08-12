# -*- coding: utf-8 -*-
# Copyright (c) 2025 relakkes@gmail.com
#
# This file is part of MediaCrawler project.
# Repository: https://github.com/NanmiCoder/MediaCrawler
# GitHub: https://github.com/NanmiCoder
# Licensed under NON-COMMERCIAL LEARNING LICENSE 1.1

from .base import BasePlatformAdapter
from .xhs import XhsAdapter
from .douyin import DouyinAdapter
from .bilibili import BilibiliAdapter
from .zhihu import ZhihuAdapter

__all__ = [
    "BasePlatformAdapter",
    "XhsAdapter",
    "DouyinAdapter",
    "BilibiliAdapter",
    "ZhihuAdapter",
]
