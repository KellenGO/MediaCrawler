# -*- coding: utf-8 -*-
# Copyright (c) 2025 relakkes@gmail.com
#
# This file is part of MediaCrawler project.
# Repository: https://github.com/NanmiCoder/MediaCrawler/blob/main/tests/test_store_base_contract.py
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

"""瘦身契约测试：直接验证生产 store 类（store.base_store_impl 与各平台
``_store_impl``/factory），不连接真实 Redis/Mongo/MySQL，不复制基类判断逻辑。

契约表里只有"瘦身前就已存在的行为期望"（平台名、item_type、ORM 模型、
ID 字段、creator 是否落盘等），不包含任何实现推导。
"""

from unittest.mock import patch

import pytest

import config
from database.models import (
    BilibiliUpDynamic,
    BilibiliVideo,
    BilibiliVideoComment,
    DouyinAweme,
    DouyinAwemeComment,
    KuaishouVideo,
    KuaishouVideoComment,
    TiebaComment,
    TiebaNote,
    WeiboNote,
    WeiboNoteComment,
    ZhihuComment,
    ZhihuContent,
)
from store import base_store_impl
from store.excel_store_base import ExcelStoreBase

import store.bilibili as bili
import store.douyin as dy
import store.kuaishou as ks
import store.tieba as tieba
import store.weibo as wb
import store.xhs as xhs
import store.zhihu as zhihu

# ---------------------------------------------------------------------------
# 契约表：瘦身前行为（item_type 与平台名等），不是实现推导。
# ---------------------------------------------------------------------------

SAVE_OPTIONS = ["csv", "json", "jsonl", "db", "postgres", "sqlite", "mongodb", "excel"]


def _file_store_contract():
    return {
        "xhs": (xhs.XhsCsvStoreImplement, "xhs", False, "contents"),
        "douyin": (dy.DouyinCsvStoreImplement, "douyin", True, "contents"),
        "kuaishou": (ks.KuaishouCsvStoreImplement, "kuaishou", False, "contents"),
        "bilibili": (bili.BiliCsvStoreImplement, "bili", True, "videos"),
        "weibo": (wb.WeiboCsvStoreImplement, "weibo", False, "contents"),
        "tieba": (tieba.TieBaCsvStoreImplement, "tieba", True, "contents"),
        "zhihu": (zhihu.ZhihuCsvStoreImplement, "zhihu", False, "contents"),
    }


def _db_store_contract():
    # xhs 的 Db 存储是独立实现（XhsDbStoreImplement(AbstractStore)），单独断言
    return {
        "douyin": (dy.DouyinDbStoreImplement, DouyinAweme, DouyinAwemeComment, "aweme_id", "comment_id"),
        "kuaishou": (ks.KuaishouDbStoreImplement, KuaishouVideo, KuaishouVideoComment, "video_id", "comment_id"),
        "bilibili": (bili.BiliDbStoreImplement, BilibiliVideo, BilibiliVideoComment, "video_id", "comment_id"),
        "weibo": (wb.WeiboDbStoreImplement, WeiboNote, WeiboNoteComment, "note_id", "comment_id"),
        "tieba": (tieba.TieBaDbStoreImplement, TiebaNote, TiebaComment, "note_id", "comment_id"),
        "zhihu": (zhihu.ZhihuDbStoreImplement, ZhihuContent, ZhihuComment, "content_id", "comment_id"),
    }


def _mongo_store_contract():
    return {
        "xhs": (xhs.XhsMongoStoreImplement, "xhs", "note_id", "note"),
        "douyin": (dy.DouyinMongoStoreImplement, "douyin", "aweme_id", "aweme"),
        "kuaishou": (ks.KuaishouMongoStoreImplement, "kuaishou", "video_id", "video"),
        "bilibili": (bili.BiliMongoStoreImplement, "bilibili", "video_id", "video"),
        "weibo": (wb.WeiboMongoStoreImplement, "weibo", "note_id", "note"),
        "tieba": (tieba.TieBaMongoStoreImplement, "tieba", "note_id", "note"),
        "zhihu": (zhihu.ZhihuMongoStoreImplement, "zhihu", "note_id", "note"),
    }


def _excel_store_contract():
    return {
        "xhs": (xhs.XhsExcelStoreImplement, "xhs"),
        "douyin": (dy.DouyinExcelStoreImplement, "douyin"),
        "kuaishou": (ks.KuaishouExcelStoreImplement, "kuaishou"),
        "bilibili": (bili.BiliExcelStoreImplement, "bilibili"),
        "weibo": (wb.WeiboExcelStoreImplement, "weibo"),
        "tieba": (tieba.TieBaExcelStoreImplement, "tieba"),
        "zhihu": (zhihu.ZhihuExcelStoreImplement, "zhihu"),
    }


_FACTORIES = {
    "xhs": xhs.XhsStoreFactory,
    "douyin": dy.DouyinStoreFactory,
    "kuaishou": ks.KuaishouStoreFactory,
    "bilibili": bili.BiliStoreFactory,
    "weibo": wb.WeibostoreFactory,
    "tieba": tieba.TieBaStoreFactory,
    "zhihu": zhihu.ZhihuStoreFactory,
}

_MODULES = {
    "xhs": xhs,
    "douyin": dy,
    "kuaishou": ks,
    "bilibili": bili,
    "weibo": wb,
    "tieba": tieba,
    "zhihu": zhihu,
}

_PREFIX = {
    "xhs": "Xhs",
    "douyin": "Douyin",
    "kuaishou": "Kuaishou",
    "bilibili": "Bili",
    "weibo": "Weibo",
    "tieba": "TieBa",
    "zhihu": "Zhihu",
}

_EXPECTED_IMPL = {
    ("csv",): 0,
    ("json",): 1,
    ("jsonl",): 2,
    ("db", "postgres"): 3,
    ("sqlite",): 4,
    ("mongodb",): 5,
    ("excel",): 6,
}


def _platform_classes(platform):
    m = _MODULES[platform]
    p = _PREFIX[platform]
    return tuple(
        getattr(m, f"{p}{suffix}StoreImplement")
        for suffix in ("Csv", "Json", "Jsonl", "Db", "Sqlite", "Mongo", "Excel")
    )


# ---------------------------------------------------------------------------
# factory 返回正确实现（覆盖 csv/json/jsonl/db/postgres/sqlite/mongodb/excel）
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("platform", sorted(_FACTORIES))
@pytest.mark.parametrize("save_option", SAVE_OPTIONS)
def test_factory_returns_expected_implementation(platform, save_option):
    factory = _FACTORIES[platform]
    classes = _platform_classes(platform)
    for options, index in _EXPECTED_IMPL.items():
        if save_option in options:
            expected = classes[index]
            break
    else:  # pragma: no cover
        raise AssertionError(f"unmapped save option {save_option}")

    with patch.object(config, "SAVE_DATA_OPTION", save_option):
        store = factory.create_store()

    if save_option == "excel":
        assert isinstance(store, ExcelStoreBase)
    else:
        assert isinstance(store, expected)


# ---------------------------------------------------------------------------
# 文件存储参数：platform / content_item_type / comment_item_type /
# creator_item_type / persist_creator 与瘦身前一致
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("platform", sorted(_file_store_contract()))
def test_file_store_parameters(platform):
    cls, expected_platform, expected_persist, expected_content_type = _file_store_contract()[platform]
    assert cls.platform == expected_platform
    assert cls.content_item_type == expected_content_type
    assert cls.comment_item_type == "comments"
    assert cls.creator_item_type == "creators"
    assert cls.persist_creator is expected_persist


# ---------------------------------------------------------------------------
# FileStore 用正确的 AsyncFileWriter 方法与 item_type 写入
# ---------------------------------------------------------------------------

class _RecordingWriter:
    def __init__(self, platform, crawler_type):
        self.platform = platform
        self.crawler_type = crawler_type
        self.calls = []

    async def write_to_csv(self, item, item_type):
        self.calls.append(("csv", item_type, item))

    async def write_to_jsonl(self, item, item_type):
        self.calls.append(("jsonl", item_type, item))

    async def write_single_item_to_json(self, item, item_type):
        self.calls.append(("json", item_type, item))


@pytest.mark.parametrize(
    ("store_cls", "expected_method", "expected_content_type"),
    [
        (xhs.XhsCsvStoreImplement, "csv", "contents"),
        (dy.DouyinCsvStoreImplement, "csv", "contents"),
        (bili.BiliCsvStoreImplement, "csv", "videos"),
        (xhs.XhsJsonStoreImplement, "json", "contents"),
        (ks.KuaishouJsonlStoreImplement, "jsonl", "contents"),
    ],
)
def test_file_store_writes_via_expected_method(store_cls, expected_method, expected_content_type):
    with patch.object(base_store_impl, "AsyncFileWriter", _RecordingWriter):
        store = store_cls()
    writer = store.writer

    async def run():
        await store.store_content({"id": "1"})
        await store.store_comment({"comment_id": "c1"})
        await store.store_creator({"user": "u"})

    _run(run)
    # FileStoreImplement 把子类的 platform 透传给 AsyncFileWriter
    assert writer.platform == store_cls.platform
    assert writer.calls[0] == (expected_method, expected_content_type, {"id": "1"})
    assert writer.calls[1] == (expected_method, "comments", {"comment_id": "c1"})
    if store_cls.persist_creator:
        assert writer.calls[2] == (expected_method, "creators", {"user": "u"})
    else:
        assert len(writer.calls) == 2  # creator 不落盘（教学版）


def test_file_store_creator_not_persisted_when_disabled():
    """persist_creator=False 时 store_creator 不写任何文件。"""
    with patch.object(base_store_impl, "AsyncFileWriter", _RecordingWriter):
        store = wb.WeiboCsvStoreImplement()

    _run(lambda: store.store_creator({"user": "u"}))
    assert store.writer.calls == []


# ---------------------------------------------------------------------------
# Db 存储参数：ORM 模型与 ID 字段与瘦身前一致（不触发任何 DB 连接）
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("platform", sorted(_db_store_contract()))
def test_db_store_models_and_id_fields(platform):
    cls, content_model, comment_model, content_id, comment_id = _db_store_contract()[platform]
    assert cls.content_model is content_model
    assert cls.comment_model is comment_model
    assert cls.content_id_field == content_id
    assert cls.comment_id_field == comment_id


def test_db_store_platform_specific_flags():
    """瘦身前各平台 Db 存储的差异 flag 逐项保留。"""
    assert dy.DouyinDbStoreImplement.content_create_guard == "title"
    assert ks.KuaishouDbStoreImplement.safe_update is True
    assert wb.WeiboDbStoreImplement.safe_update is True
    assert wb.WeiboDbStoreImplement.modify_ts_on_create is True
    assert wb.WeiboDbStoreImplement.modify_ts_on_update is True
    assert bili.BiliDbStoreImplement.dynamic_model is BilibiliUpDynamic
    assert bili.BiliDbStoreImplement.dynamic_id_field == "dynamic_id"
    assert tieba.TieBaDbStoreImplement.add_ts_on_create is False
    assert zhihu.ZhihuDbStoreImplement.safe_update is True
    assert zhihu.ZhihuDbStoreImplement.conditional_add_ts is True


def test_xhs_db_store_keeps_own_implementation():
    """小红书 Db 存储是独立实现：factory 返回的仍是 XhsDbStoreImplement。"""
    from base.base_crawler import AbstractStore
    assert issubclass(xhs.XhsDbStoreImplement, AbstractStore)
    assert not issubclass(xhs.XhsDbStoreImplement, base_store_impl.DbStoreImplement)
    with patch.object(config, "SAVE_DATA_OPTION", "db"):
        store = xhs.XhsStoreFactory.create_store()
    assert isinstance(store, xhs.XhsDbStoreImplement)


# ---------------------------------------------------------------------------
# Mongo 存储：collection_prefix 正确透传（构造不建立任何连接）
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("platform", sorted(_mongo_store_contract()))
def test_mongo_store_prefix_and_id_fields(platform):
    cls, prefix, content_id, kind = _mongo_store_contract()[platform]
    assert cls.collection_prefix == prefix
    assert cls.content_id_field == content_id
    assert cls.comment_id_field == "comment_id"
    assert cls.content_kind == kind
    # 实例化只保存前缀，不发起任何连接
    store = cls()
    assert store.mongo_store.collection_prefix == prefix


# ---------------------------------------------------------------------------
# Excel 存储：platform 正确透传到 ExcelStoreBase 单例
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("platform", sorted(_excel_store_contract()))
def test_excel_store_passes_platform(platform, tmp_path):
    cls, excel_platform = _excel_store_contract()[platform]
    with patch.object(config, "SAVE_DATA_PATH", str(tmp_path)):
        store = cls()
    assert isinstance(store, ExcelStoreBase)
    assert store.platform == excel_platform


def _run(coro_fn):
    """在临时事件循环中执行 async 协程工厂。"""
    import asyncio
    return asyncio.new_event_loop().run_until_complete(coro_fn())
