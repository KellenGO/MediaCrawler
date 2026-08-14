# -*- coding: utf-8 -*-
# Copyright (c) 2025 relakkes@gmail.com
#
# This file is part of MediaCrawler project.
# Repository: https://github.com/NanmiCoder/MediaCrawler/blob/main/store/bilibili/_store_impl.py
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

"""Bilibili storage implementation (parameterized by store.base_store_impl)."""

from database.models import BilibiliUpDynamic, BilibiliVideo, BilibiliVideoComment
from store.base_store_impl import (
    CsvStoreImplement,
    DbStoreImplement,
    ExcelStoreImplement,
    JsonStoreImplement,
    JsonlStoreImplement,
    MongoStoreImplement,
)


def _preprocess_video(item):
    item["liked_count"] = int(item.get("liked_count", 0) or 0)
    item["create_time"] = int(item.get("create_time", 0) or 0)


def _preprocess_bili_comment(item):
    item["create_time"] = int(item.get("create_time", 0) or 0)
    item["like_count"] = str(item.get("like_count", "0"))
    item["sub_comment_count"] = str(item.get("sub_comment_count", "0"))
    item["parent_comment_id"] = str(item.get("parent_comment_id", "0"))


class BiliCsvStoreImplement(CsvStoreImplement):
    platform = "bili"
    content_item_type = "videos"
    persist_creator = True


class BiliDbStoreImplement(DbStoreImplement):
    content_model = BilibiliVideo
    comment_model = BilibiliVideoComment
    dynamic_model = BilibiliUpDynamic
    content_id_field = "video_id"
    comment_id_field = "comment_id"
    dynamic_id_field = "dynamic_id"
    modify_ts_on_create = True
    modify_ts_on_update = True
    content_preprocess = staticmethod(_preprocess_video)
    comment_preprocess = staticmethod(_preprocess_bili_comment)


class BiliJsonStoreImplement(JsonStoreImplement):
    platform = "bili"
    persist_creator = True


class BiliJsonlStoreImplement(JsonlStoreImplement):
    platform = "bili"
    persist_creator = True


class BiliSqliteStoreImplement(BiliDbStoreImplement):
    pass


class BiliMongoStoreImplement(MongoStoreImplement):
    collection_prefix = "bilibili"
    content_id_field = "video_id"
    content_kind = "video"


class BiliExcelStoreImplement(ExcelStoreImplement):
    platform = "bilibili"
