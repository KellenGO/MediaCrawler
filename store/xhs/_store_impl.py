# -*- coding: utf-8 -*-
# Copyright (c) 2025 relakkes@gmail.com
#
# This file is part of MediaCrawler project.
# Repository: https://github.com/NanmiCoder/MediaCrawler/blob/main/store/xhs/_store_impl.py
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

"""Xiaohongshu storage implementation."""

import json
from typing import Dict

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from base.base_crawler import AbstractStore
from database.db_session import get_session
from database.models import XhsNote, XhsNoteComment
from store.base_store_impl import (
    CsvStoreImplement,
    ExcelStoreImplement,
    JsonStoreImplement,
    JsonlStoreImplement,
    MongoStoreImplement,
)
from tools.time_util import get_current_timestamp


class XhsCsvStoreImplement(CsvStoreImplement):
    platform = "xhs"


class XhsJsonStoreImplement(JsonStoreImplement):
    platform = "xhs"


class XhsJsonlStoreImplement(JsonlStoreImplement):
    platform = "xhs"


class XhsDbStoreImplement(AbstractStore):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)

    async def store_content(self, content_item: Dict):
        note_id = content_item.get("note_id")
        if not note_id:
            return
        async with get_session() as session:
            if await self.content_is_exist(session, note_id):
                await self.update_content(session, content_item)
            else:
                await self.add_content(session, content_item)

    async def add_content(self, session: AsyncSession, content_item: Dict):
        add_ts = int(get_current_timestamp())
        last_modify_ts = int(get_current_timestamp())
        note = XhsNote(
            creator_hash=content_item.get("creator_hash"),
            nickname=content_item.get("nickname"),
            add_ts=add_ts,
            last_modify_ts=last_modify_ts,
            note_id=content_item.get("note_id"),
            type=content_item.get("type"),
            title=content_item.get("title"),
            desc=content_item.get("desc"),
            video_url=content_item.get("video_url"),
            time=content_item.get("time"),
            last_update_time=content_item.get("last_update_time"),
            liked_count=str(content_item.get("liked_count")),
            collected_count=str(content_item.get("collected_count")),
            comment_count=str(content_item.get("comment_count")),
            share_count=str(content_item.get("share_count")),
            image_list=json.dumps(content_item.get("image_list")),
            tag_list=json.dumps(content_item.get("tag_list")),
            note_url=content_item.get("note_url"),
            source_keyword=content_item.get("source_keyword", ""),
            xsec_token=content_item.get("xsec_token", "")
        )
        session.add(note)

    async def update_content(self, session: AsyncSession, content_item: Dict):
        note_id = content_item.get("note_id")
        update_data = {
            "last_modify_ts": int(get_current_timestamp()),
            "liked_count": str(content_item.get("liked_count")),
            "collected_count": str(content_item.get("collected_count")),
            "comment_count": str(content_item.get("comment_count")),
            "share_count": str(content_item.get("share_count")),
            "last_update_time": content_item.get("last_update_time"),
        }
        stmt = update(XhsNote).where(XhsNote.note_id == note_id).values(**update_data)
        await session.execute(stmt)

    async def content_is_exist(self, session: AsyncSession, note_id: str) -> bool:
        stmt = select(XhsNote).where(XhsNote.note_id == note_id)
        result = await session.execute(stmt)
        return result.first() is not None

    async def store_comment(self, comment_item: Dict):
        if not comment_item:
            return
        async with get_session() as session:
            comment_id = comment_item.get("comment_id")
            if not comment_id:
                return
            if await self.comment_is_exist(session, comment_id):
                await self.update_comment(session, comment_item)
            else:
                await self.add_comment(session, comment_item)

    async def add_comment(self, session: AsyncSession, comment_item: Dict):
        comment = XhsNoteComment(
            creator_hash=comment_item.get("creator_hash"),
            nickname=comment_item.get("nickname"),
            add_ts=int(get_current_timestamp()),
            last_modify_ts=int(get_current_timestamp()),
            comment_id=comment_item.get("comment_id"),
            create_time=comment_item.get("create_time"),
            note_id=comment_item.get("note_id"),
            content=comment_item.get("content"),
            sub_comment_count=int(comment_item.get("sub_comment_count", 0) or 0),
            pictures=json.dumps(comment_item.get("pictures")),
            parent_comment_id=str(comment_item.get("parent_comment_id", "")),
            like_count=str(comment_item.get("like_count"))
        )
        session.add(comment)

    async def update_comment(self, session: AsyncSession, comment_item: Dict):
        comment_id = comment_item.get("comment_id")
        update_data = {
            "last_modify_ts": int(get_current_timestamp()),
            "like_count": str(comment_item.get("like_count")),
            "sub_comment_count": int(comment_item.get("sub_comment_count", 0) or 0),
        }
        stmt = update(XhsNoteComment).where(XhsNoteComment.comment_id == comment_id).values(**update_data)
        await session.execute(stmt)

    async def comment_is_exist(self, session: AsyncSession, comment_id: str) -> bool:
        stmt = select(XhsNoteComment).where(XhsNoteComment.comment_id == comment_id)
        result = await session.execute(stmt)
        return result.first() is not None

    async def store_creator(self, creator_item: Dict):
        # 教学版：创作者个人资料不再落库
        pass


class XhsSqliteStoreImplement(XhsDbStoreImplement):
    pass


class XhsMongoStoreImplement(MongoStoreImplement):
    collection_prefix = "xhs"
    content_id_field = "note_id"
    content_kind = "note"


class XhsExcelStoreImplement(ExcelStoreImplement):
    platform = "xhs"
