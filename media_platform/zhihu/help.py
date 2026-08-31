# -*- coding: utf-8 -*-
# Copyright (c) 2025 relakkes@gmail.com
#
# This file is part of MediaCrawler project.
# Repository: https://github.com/NanmiCoder/MediaCrawler/blob/main/media_platform/zhihu/help.py
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
import json
from typing import Dict, List, Optional

import execjs
from parsel import Selector

from constant import zhihu as zhihu_constant
from model.m_zhihu import ZhihuContent, ZhihuCreator
from tools import utils
from tools.crawler_util import extract_text_from_html
from tools.user_hash import anonymize_user_id, mask_nickname
from base.runtime_paths import resource_path

ZHIHU_SGIN_JS = None


def sign(url: str, cookies: str) -> Dict:
    """
    zhihu sign algorithm
    Args:
        url: request url with query string
        cookies: request cookies with d_c0 key

    Returns:

    """
    global ZHIHU_SGIN_JS
    if not ZHIHU_SGIN_JS:
        ZHIHU_SGIN_JS = execjs.compile(
            resource_path("libs", "zhihu.js").read_text(encoding="utf-8-sig"))

    return ZHIHU_SGIN_JS.call("get_sign", url, cookies)


class ZhihuExtractor:
    def __init__(self):
        pass

    def extract_contents_from_search(self, json_data: Dict) -> List[ZhihuContent]:
        """
        extract zhihu contents
        Args:
            json_data: zhihu json data

        Returns:

        """
        if not json_data:
            return []

        search_result: List[Dict] = json_data.get("data", [])
        search_result = [s_item for s_item in search_result if s_item.get("type") in ['search_result', 'zvideo']]
        return self._extract_content_list([sr_item.get("object") for sr_item in search_result if sr_item.get("object")])


    def _extract_content_list(self, content_list: List[Dict]) -> List[ZhihuContent]:
        """
        extract zhihu content list
        Args:
            content_list:

        Returns:

        """
        if not content_list:
            return []

        res: List[ZhihuContent] = []
        for content in content_list:
            if content.get("type") == zhihu_constant.ANSWER_NAME:
                res.append(self._extract_answer_content(content))
            elif content.get("type") == zhihu_constant.ARTICLE_NAME:
                res.append(self._extract_article_content(content))
            elif content.get("type") == zhihu_constant.VIDEO_NAME:
                res.append(self._extract_zvideo_content(content))
            else:
                continue
        return res

    def _extract_answer_content(self, answer: Dict) -> ZhihuContent:
        """
        extract zhihu answer content
        Args:
            answer: zhihu answer

        Returns:
        """
        res = ZhihuContent()
        res.content_id = str(answer.get("id") or "")
        res.content_type = answer.get("type")
        res.content_text = extract_text_from_html(answer.get("content", ""))
        res.question_id = str(answer.get("question", {}).get("id") or "")
        res.content_url = f"{zhihu_constant.ZHIHU_URL}/question/{res.question_id}/answer/{res.content_id}"
        res.title = extract_text_from_html(answer.get("title", ""))
        res.desc = extract_text_from_html(answer.get("description", "") or answer.get("excerpt", ""))
        res.created_time = answer.get("created_time")
        res.updated_time = answer.get("updated_time")
        res.voteup_count = answer.get("voteup_count", 0)
        res.comment_count = answer.get("comment_count", 0)

        # extract author info
        author_info = self._extract_content_or_comment_author(answer.get("author"))
        res.creator_hash = author_info.creator_hash
        res.user_nickname = author_info.user_nickname
        return res

    def _extract_article_content(self, article: Dict) -> ZhihuContent:
        """
        extract zhihu article content
        Args:
            article: zhihu article

        Returns:

        """
        res = ZhihuContent()
        res.content_id = str(article.get("id") or "")
        res.content_type = article.get("type")
        res.content_text = extract_text_from_html(article.get("content"))
        res.content_url = f"{zhihu_constant.ZHIHU_ZHUANLAN_URL}/p/{res.content_id}"
        res.title = extract_text_from_html(article.get("title"))
        res.desc = extract_text_from_html(article.get("excerpt"))
        res.created_time = article.get("created_time", 0) or article.get("created", 0)
        res.updated_time = article.get("updated_time", 0) or article.get("updated", 0)
        res.voteup_count = article.get("voteup_count", 0)
        res.comment_count = article.get("comment_count", 0)

        # extract author info
        author_info = self._extract_content_or_comment_author(article.get("author"))
        res.creator_hash = author_info.creator_hash
        res.user_nickname = author_info.user_nickname
        return res

    def _extract_zvideo_content(self, zvideo: Dict) -> ZhihuContent:
        """
        extract zhihu zvideo content
        Args:
            zvideo:

        Returns:

        """
        res = ZhihuContent()
        res.content_id = str(zvideo.get("id") or "")
        res.content_type = zvideo.get("type")

        if "video" in zvideo and isinstance(zvideo.get("video"), dict): # This indicates data from the creator's homepage video list API
            res.content_url = f"{zhihu_constant.ZHIHU_URL}/zvideo/{res.content_id}"
            res.created_time = zvideo.get("published_at")
            res.updated_time = zvideo.get("updated_at")
        else:
            res.content_url = zvideo.get("video_url")
            res.created_time = zvideo.get("created_at")
        res.title = extract_text_from_html(zvideo.get("title"))
        res.desc = extract_text_from_html(zvideo.get("description"))
        res.voteup_count = zvideo.get("voteup_count")
        res.comment_count = zvideo.get("comment_count")

        # extract author info
        author_info = self._extract_content_or_comment_author(zvideo.get("author"))
        res.creator_hash = author_info.creator_hash
        res.user_nickname = author_info.user_nickname
        return res

    @staticmethod
    def _extract_content_or_comment_author(author: Dict) -> ZhihuCreator:
        """
        extract zhihu author
        Args:
            author:

        Returns:

        """
        res = ZhihuCreator()
        try:
            if not author:
                return res
            if not author.get("id"):
                author = author.get("member")
            res.creator_hash = anonymize_user_id(author.get("id"))
            res.user_nickname = mask_nickname(author.get("name"))

        except Exception as e :
            utils.logger.warning(
                f"[ZhihuExtractor._extract_content_or_comment_author] User Maybe Blocked. {e}"
            )
        return res

    def extract_answer_content_from_html(self, html_content: str) -> Optional[ZhihuContent]:
        """
        extract zhihu answer content from html
        Args:
            html_content:

        Returns:

        """
        js_init_data: str = Selector(text=html_content).xpath("//script[@id='js-initialData']/text()").get(default="")
        if not js_init_data:
            return None
        json_data: Dict = json.loads(js_init_data)
        answer_info: Dict = json_data.get("initialState", {}).get("entities", {}).get("answers", {})
        if not answer_info:
            return None

        return self._extract_answer_content(answer_info.get(list(answer_info.keys())[0]))

    def extract_article_content_from_html(self, html_content: str) -> Optional[ZhihuContent]:
        """
        extract zhihu article content from html
        Args:
            html_content:

        Returns:

        """
        js_init_data: str = Selector(text=html_content).xpath("//script[@id='js-initialData']/text()").get(default="")
        if not js_init_data:
            return None
        json_data: Dict = json.loads(js_init_data)
        article_info: Dict = json_data.get("initialState", {}).get("entities", {}).get("articles", {})
        if not article_info:
            return None

        return self._extract_article_content(article_info.get(list(article_info.keys())[0]))

    def extract_zvideo_content_from_html(self, html_content: str) -> Optional[ZhihuContent]:
        """
        extract zhihu zvideo content from html
        Args:
            html_content:

        Returns:

        """
        js_init_data: str = Selector(text=html_content).xpath("//script[@id='js-initialData']/text()").get(default="")
        if not js_init_data:
            return None
        json_data: Dict = json.loads(js_init_data)
        zvideo_info: Dict = json_data.get("initialState", {}).get("entities", {}).get("zvideos", {})
        users: Dict = json_data.get("initialState", {}).get("entities", {}).get("users", {})
        if not zvideo_info:
            return None

        # handler user info and video info
        video_detail_info: Dict = zvideo_info.get(list(zvideo_info.keys())[0])
        if not video_detail_info:
            return None
        if isinstance(video_detail_info.get("author"), str):
            author_name: str = video_detail_info.get("author")
            video_detail_info["author"] = users.get(author_name)

        return self._extract_zvideo_content(video_detail_info)


def judge_zhihu_url(note_detail_url: str) -> str:
    """
    judge zhihu url type
    Args:
        note_detail_url:
            eg1: https://www.zhihu.com/question/123456789/answer/123456789 # answer
            eg2: https://www.zhihu.com/p/123456789 # article
            eg3: https://www.zhihu.com/zvideo/123456789 # zvideo

    Returns:

    """
    if "/answer/" in note_detail_url:
        return zhihu_constant.ANSWER_NAME
    elif "/p/" in note_detail_url:
        return zhihu_constant.ARTICLE_NAME
    elif "/zvideo/" in note_detail_url:
        return zhihu_constant.VIDEO_NAME
    else:
        return ""
