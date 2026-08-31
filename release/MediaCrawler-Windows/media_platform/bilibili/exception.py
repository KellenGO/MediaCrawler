# -*- coding: utf-8 -*-
# Copyright (c) 2025 relakkes@gmail.com
#
# This file is part of MediaCrawler project.
# Repository: https://github.com/NanmiCoder/MediaCrawler/blob/main/media_platform/bilibili/exception.py
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


# -*- coding: utf-8 -*-
# @Author  : relakkes@gmail.com
# @Time    : 2023/12/2 18:44
# @Desc    :

from typing import Any, Optional

from httpx import RequestError


class DataFetchError(RequestError):
    """something error when fetch

    Safe metadata for error classification (never contains URL query
    params / cookies / headers / response bodies):
    - ``stage``: where the request happened (search_list / video_detail /
      login_check / request);
    - ``http_status``: HTTP status code, or None;
    - ``platform_code``: Bilibili business code (e.g. -412 rate limit,
      -101 not logged in, -352 captcha), or None;
    - ``safe_message``: fixed / length-bounded safe text for user display.
    """

    def __init__(self, message: str = "", *, stage: Optional[str] = None,
                 http_status: Optional[int] = None,
                 platform_code: Any = None,
                 safe_message: Optional[str] = None,
                 request: Any = None):
        super().__init__(message, request=request)
        self.stage = stage
        self.http_status = http_status
        self.platform_code = platform_code
        self.safe_message = safe_message


class IPBlockError(RequestError):
    """fetch so fast that the server block us ip"""
