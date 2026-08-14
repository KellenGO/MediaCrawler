# -*- coding: utf-8 -*-
# Copyright (c) 2025 relakkes@gmail.com
#
# This file is part of MediaCrawler project.
# Repository: https://github.com/NanmiCoder/MediaCrawler/blob/main/store/base_store_impl.py
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

"""平台通用的存储实现。

各平台 ``store/<platform>/_store_impl.py`` 只需以类属性（平台名、ORM 模型、
ID 字段、时间戳策略等）参数化继承这里的通用实现，行为与原先逐平台复制
的代码完全一致。
"""

from typing import Dict

from sqlalchemy import select

from base.base_crawler import AbstractStore
from database.db_session import get_session
from database.mongodb_store_base import MongoDBStoreBase
from tools import utils
from tools.async_file_writer import AsyncFileWriter
from var import crawler_type_var


def filter_model_fields(model_cls, item: Dict) -> Dict:
    """只保留目标 ORM 模型已有的列，避免把已删除/多余字段传给 ORM 构造。"""
    allowed = {col.name for col in model_cls.__table__.columns}
    return {k: v for k, v in item.items() if k in allowed}


class FileStoreImplement(AbstractStore):
    """CSV/JSON/JSONL 存储的通用基类，子类只需设置 ``platform`` 等类属性。"""

    platform: str = ""
    content_item_type: str = "contents"
    comment_item_type: str = "comments"
    creator_item_type: str = "creators"
    persist_creator: bool = False  # 教学版：创作者个人资料默认不再落库

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.writer = AsyncFileWriter(platform=self.platform, crawler_type=crawler_type_var.get())

    async def store_content(self, content_item: Dict):
        await self._write(content_item, self.content_item_type)

    async def store_comment(self, comment_item: Dict):
        await self._write(comment_item, self.comment_item_type)

    async def store_creator(self, creator: Dict):
        if self.persist_creator:
            await self._write(creator, self.creator_item_type)

    async def store_contact(self, contact_item: Dict):
        await self._write(contact_item, "contacts")

    async def store_dynamic(self, dynamic_item: Dict):
        await self._write(dynamic_item, "dynamics")

    async def _write(self, item: Dict, item_type: str):
        raise NotImplementedError


class CsvStoreImplement(FileStoreImplement):
    async def _write(self, item: Dict, item_type: str):
        await self.writer.write_to_csv(item=item, item_type=item_type)


class JsonStoreImplement(FileStoreImplement):
    async def _write(self, item: Dict, item_type: str):
        await self.writer.write_single_item_to_json(item=item, item_type=item_type)


class JsonlStoreImplement(FileStoreImplement):
    async def _write(self, item: Dict, item_type: str):
        await self.writer.write_to_jsonl(item=item, item_type=item_type)


class DbStoreImplement(AbstractStore):
    """内容/评论（及可选动态）ORM upsert 存储的通用基类。

    通过类属性参数化各平台原有语义：时间戳策略、字段过滤、hasattr 保护等。
    """

    content_model = None
    comment_model = None
    dynamic_model = None
    content_id_field = "content_id"
    comment_id_field = "comment_id"
    dynamic_id_field = "dynamic_id"
    content_create_guard = None  # 创建内容时必须为真的字段
    safe_update = False          # 更新时仅 setattr ORM 对象已有的键
    add_ts_on_create = True
    modify_ts_on_create = False
    modify_ts_on_update = False
    conditional_add_ts = False   # 仅当 item 未提供 add_ts 时才写入
    content_filter = None        # (model, item) -> item
    comment_filter = None
    content_preprocess = None    # upsert 前原地修改 item
    comment_preprocess = None

    async def store_content(self, content_item: Dict):
        if self.content_filter:
            content_item = self.content_filter(self.content_model, content_item)
        await self._upsert(self.content_model, self.content_id_field, content_item,
                           self.content_create_guard, self.content_preprocess)

    async def store_comment(self, comment_item: Dict):
        if self.comment_filter:
            comment_item = self.comment_filter(self.comment_model, comment_item)
        await self._upsert(self.comment_model, self.comment_id_field, comment_item,
                           None, self.comment_preprocess)

    async def store_creator(self, creator: Dict):
        pass

    async def store_contact(self, contact_item: Dict):
        pass

    async def store_dynamic(self, dynamic_item: Dict):
        if self.dynamic_model is not None:
            await self._upsert(self.dynamic_model, self.dynamic_id_field, dynamic_item, None, None)

    async def _upsert(self, model, id_field, item, create_guard, preprocess):
        if preprocess:
            preprocess(item)
        async with get_session() as session:
            result = await session.execute(select(model).where(getattr(model, id_field) == item.get(id_field)))
            detail = result.scalar_one_or_none()
            if detail:
                if self.modify_ts_on_update:
                    item["last_modify_ts"] = utils.get_current_timestamp()
                for key, value in item.items():
                    if not self.safe_update or hasattr(detail, key):
                        setattr(detail, key, value)
            elif not create_guard or item.get(create_guard):
                if self.add_ts_on_create:
                    if self.conditional_add_ts:
                        item.setdefault("add_ts", utils.get_current_timestamp())
                    else:
                        item["add_ts"] = utils.get_current_timestamp()
                if self.modify_ts_on_create:
                    item["last_modify_ts"] = utils.get_current_timestamp()
                session.add(model(**item))
            await session.commit()


class MongoStoreImplement(AbstractStore):
    """MongoDB upsert 存储的通用基类，子类设置前缀与 ID 字段。"""

    collection_prefix = ""
    content_id_field = "content_id"
    comment_id_field = "comment_id"
    content_kind = "item"

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.mongo_store = MongoDBStoreBase(collection_prefix=self.collection_prefix)

    async def store_content(self, content_item: Dict):
        item_id = content_item.get(self.content_id_field)
        if not item_id:
            return
        await self.mongo_store.save_or_update(
            collection_suffix="contents",
            query={self.content_id_field: item_id},
            data=content_item,
        )
        utils.logger.info(f"[{type(self).__name__}.store_content] Saved {self.content_kind} {item_id} to MongoDB")

    async def store_comment(self, comment_item: Dict):
        comment_id = comment_item.get(self.comment_id_field)
        if not comment_id:
            return
        await self.mongo_store.save_or_update(
            collection_suffix="comments",
            query={self.comment_id_field: comment_id},
            data=comment_item,
        )
        utils.logger.info(f"[{type(self).__name__}.store_comment] Saved comment {comment_id} to MongoDB")

    async def store_creator(self, creator_item: Dict):
        pass


class ExcelStoreImplement:
    """Excel 存储：``__new__`` 返回共享的 ExcelStoreBase 单例。"""

    platform = ""

    def __new__(cls, *args, **kwargs):
        from store.excel_store_base import ExcelStoreBase
        return ExcelStoreBase.get_instance(platform=cls.platform, crawler_type=crawler_type_var.get())
