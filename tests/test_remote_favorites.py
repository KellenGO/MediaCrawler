from types import SimpleNamespace

import pytest
from pydantic import ValidationError

from aggregate_search.adapters import BilibiliAdapter, ZhihuAdapter
from aggregate_search.models import WorkerRequest
from api.schemas.favorites import FavoritesJobRequest
from api.services.favorites_job_manager import _Job
from media_platform.bilibili.core import BilibiliCrawler
from media_platform.douyin.core import DouYinCrawler
from media_platform.xhs.core import XiaoHongShuCrawler
from media_platform.zhihu.core import ZhihuCrawler


def test_favorites_request_contract_is_bounded_and_unique():
    assert FavoritesJobRequest().limit_per_platform == 20
    assert WorkerRequest(job_id="j", mode="favorites", platform="xhs").mode == "favorites"
    with pytest.raises(ValidationError):
        FavoritesJobRequest(platforms=["xhs", "xhs"])
    with pytest.raises(ValidationError):
        FavoritesJobRequest(limit_per_platform=41)


def test_folder_metadata_survives_bilibili_and_zhihu_adaptation():
    bili = BilibiliAdapter().adapt([{
        "bvid": "BV1test", "title": "视频", "cover": "https://i0.hdslb.com/a.jpg",
        "upper": {"name": "UP"}, "cnt_info": {"play": 12, "danmaku": 3},
        "_collection_name": "稍后学习",
    }])[0]
    assert bili.author == "UP"
    assert bili.metrics == {"view_count": 12, "danmaku_count": 3}
    assert bili.collection_names == ["稍后学习"]

    zhihu = ZhihuAdapter().adapt([{
        "id": 8, "type": "answer", "question": {"id": 7}, "title": "回答",
        "author": {"name": "答主"}, "_collection_name": "产品思考",
    }])[0]
    assert zhihu.url.endswith("/question/7/answer/8")
    assert zhihu.collection_names == ["产品思考"]


def test_favorites_job_interleaves_platforms_and_preserves_partial_results():
    job = _Job(FavoritesJobRequest(platforms=["xhs", "bilibili"], limit_per_platform=2))
    job.items["xhs"] = [BilibiliAdapter().adapt([{"bvid": "x", "title": "占位"}])[0].model_copy(update={"platform": "xhs"})]
    job.items["bilibili"] = BilibiliAdapter().adapt([
        {"bvid": "b1", "title": "一"}, {"bvid": "b2", "title": "二"}])
    job.platforms["xhs"].status = "succeeded"
    job.platforms["bilibili"].status = "failed"
    assert job.response().overall == "running"
    from datetime import datetime, timezone
    job.completed_at = datetime.now(timezone.utc)
    response = job.response()
    assert response.overall == "partial"
    assert [item.content_id for item in response.results] == ["x", "b1", "b2"]


@pytest.mark.asyncio
async def test_xhs_and_douyin_favorites_are_bounded():
    xhs_batches = []
    xhs = SimpleNamespace(
        xhs_client=SimpleNamespace(get_collected_notes=lambda *_: None),
        _result_limit=lambda: 2,
        _result_sink_call=xhs_batches.append,
    )

    async def xhs_page(*_):
        return {"items": [{"id": "1"}, {"id": "2"}, {"id": "3"}], "has_more": True, "cursor": "next"}
    xhs.xhs_client.get_collected_notes = xhs_page
    await XiaoHongShuCrawler.fetch_favorites(xhs)
    assert [item["id"] for item in xhs_batches[0]] == ["1", "2"]

    dy_batches = []
    dy = SimpleNamespace(
        dy_client=SimpleNamespace(), _result_limit=lambda: 1,
        _result_sink_call=dy_batches.append,
    )

    async def dy_page(*_):
        return {"aweme_list": [{"aweme_id": "a"}, {"aweme_id": "b"}], "has_more": 1, "cursor": 10}
    dy.dy_client.get_collected_awemes = dy_page
    await DouYinCrawler.fetch_favorites(dy)
    assert [item["aweme_id"] for item in dy_batches[0]] == ["a"]


@pytest.mark.asyncio
async def test_folder_fetchers_flatten_and_report_duplicate_membership():
    bili_batches = []

    class BiliClient:
        async def get(self, *_args, **_kwargs): return {"mid": 1}
        async def get_created_favorite_folders(self, _mid):
            return {"list": [{"id": 10, "title": "A"}, {"id": 11, "title": "B"}]}
        async def get_favorite_folder_contents(self, media_id, *_):
            return {"medias": [{"bvid": "same", "title": "one"},
                                {"bvid": str(media_id), "title": "two"}], "has_more": False}

    bili = SimpleNamespace(bili_client=BiliClient(), _result_limit=lambda: 3,
                           _result_sink_call=bili_batches.append)
    await BilibiliCrawler.fetch_favorites(bili)
    flattened = [item for batch in bili_batches for item in batch]
    assert [item["bvid"] for item in flattened] == ["same", "10", "same", "11"]
    assert [item["_collection_name"] for item in flattened] == ["A", "A", "B", "B"]

    zh_batches = []

    class ZhClient:
        async def get_current_user_info(self): return {"url_token": "me"}
        async def get_user_collections(self, _token):
            return {"data": [{"id": "c", "title": "精选"}]}
        async def get_collection_items(self, *_):
            return {"data": [{"content": {"type": "article", "id": 9, "title": "文章"}}],
                    "paging": {"is_end": True}}

    zh = SimpleNamespace(zhihu_client=ZhClient(), _result_limit=lambda: 5,
                         _result_sink_call=zh_batches.append)
    await ZhihuCrawler.fetch_favorites(zh)
    assert zh_batches[0][0]["_collection_name"] == "精选"
