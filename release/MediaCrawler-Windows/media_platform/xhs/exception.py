# -*- coding: utf-8 -*-
# Copyright (c) 2025 relakkes@gmail.com
#
# This file is part of MediaCrawler project.
# Repository: https://github.com/NanmiCoder/MediaCrawler/blob/main/media_platform/xhs/exception.py
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


from httpx import RequestError


class DataFetchError(RequestError):
    """something error when fetch"""


class IPBlockError(RequestError):
    """fetch so fast that the server block us ip"""


class NoteNotFoundError(RequestError):
    """Note does not exist or is abnormal"""


class XhsRateLimitError(RequestError):
    """小红书风控/验证码限制（HTTP 461/471）—— Round 17.2。

    平台对请求发起验证码/访问限制挑战。这是平台明确的"受限"信号，不是
    网络临时错误：461/471 只允许发起 1 次请求，绝不自动重试（重试会重复
    触发风控）。

    safe_code 固定为 "rate_limited"；safe_message 为固定中文文案。
    str/repr 绝不包含：response body、URL、query、Cookie、header、
    Verifyuuid、Verifytype、xsec_token —— 构造时只接收状态码。
    """

    def __init__(self, http_status: int):
        self.safe_code = "rate_limited"
        self.safe_message = "小红书触发验证码或访问限制，请稍后再试"
        self.http_status = int(http_status)
        super().__init__(self.safe_message)

    def __str__(self) -> str:
        return self.safe_message

    def __repr__(self) -> str:
        return (f"XhsRateLimitError(http_status={self.http_status}, "
                f"safe_code={self.safe_code!r}, "
                f"safe_message={self.safe_message!r})")
