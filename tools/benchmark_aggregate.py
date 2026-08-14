# -*- coding: utf-8 -*-
# Copyright (c) 2025 relakkes@gmail.com
#
# This file is part of MediaCrawler project.
# Repository: https://github.com/NanmiCoder/MediaCrawler/blob/main/tools/benchmark_aggregate.py
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

"""聚合搜索耗时基准脚本（Phase 1）。

调用现有 POST /api/search/jobs 与 GET /api/search/jobs/{job_id}，
只打印状态、数量与 timing 数字；不打印结果正文、Cookie 或账号信息；
不自动登录、不操作浏览器 profile。

用法::

    python tools/benchmark_aggregate.py --keyword 露营 --platforms xhs,douyin --limit 5 --runs 3
    python tools/benchmark_aggregate.py --url http://127.0.0.1:8080 --keyword 测试 --runs 1
"""

import argparse
import sys
import time
from typing import Dict, List, Optional

import httpx

DEFAULT_BASE_URL = "http://127.0.0.1:8080"
POLL_INTERVAL_SECONDS = 0.5
MAX_WAIT_SECONDS = 180.0

PLATFORM_ORDER = ["xhs", "douyin", "bilibili", "zhihu"]


def _timing_line(timings: Optional[Dict]) -> str:
    if not timings:
        return "-"
    parts = []
    if timings.get("spawn_ms") is not None:
        parts.append(f"spawn={timings['spawn_ms']}ms")
    if timings.get("first_result_ms") is not None:
        parts.append(f"first={timings['first_result_ms']}ms")
    if timings.get("total_ms") is not None:
        parts.append(f"total={timings['total_ms']}ms")
    return " ".join(parts) if parts else "-"


def _post_job(client: httpx.Client, keyword: str, platforms: List[str],
              limit: int) -> Dict:
    payload: Dict = {"keyword": keyword, "limit_per_platform": limit}
    if platforms:
        payload["platforms"] = platforms
    resp = client.post("/api/search/jobs", json=payload)
    resp.raise_for_status()
    return resp.json()


def _wait_terminal(client: httpx.Client, job_id: str) -> Dict:
    deadline = time.monotonic() + MAX_WAIT_SECONDS
    while time.monotonic() < deadline:
        resp = client.get(f"/api/search/jobs/{job_id}")
        resp.raise_for_status()
        data = resp.json()
        if data.get("overall") not in ("running", "cancelling"):
            return data
        time.sleep(POLL_INTERVAL_SECONDS)
    data = client.get(f"/api/search/jobs/{job_id}").json()
    print(f"[warn] job {job_id} 未在 {MAX_WAIT_SECONDS:.0f}s 内到达终态，输出当前快照")
    return data


def _run_once(client: httpx.Client, keyword: str, platforms: List[str],
              limit: int, run_index: int) -> Dict:
    job = _post_job(client, keyword, platforms, limit)
    job_id = job["job_id"]
    print(f"run#{run_index + 1} job={job_id} keyword={keyword!r} "
          f"platforms={','.join(job.get('platforms', platforms) or platforms)} "
          f"limit={limit}")
    terminal = _wait_terminal(client, job_id)
    print(f"  overall={terminal.get('overall')} "
          f"total_ms={terminal.get('total_ms')} "
          f"results={len(terminal.get('results') or [])}")
    for p in PLATFORM_ORDER:
        info = (terminal.get("platforms") or {}).get(p)
        if info is None:
            continue
        print(f"  {p:8s} status={info.get('status'):14s} "
              f"count={info.get('result_count'):3d} "
              f"timing=[{_timing_line(info.get('timings'))}]")
    return terminal


def _summarize(runs: List[Dict]) -> None:
    print("\n== 汇总 ==")
    firsts = []
    totals = []
    job_totals = []
    for run in runs:
        for p in PLATFORM_ORDER:
            info = (run.get("platforms") or {}).get(p) or {}
            t = info.get("timings") or {}
            if t.get("first_result_ms") is not None:
                firsts.append(t["first_result_ms"])
            if t.get("total_ms") is not None:
                totals.append(t["total_ms"])
        if run.get("total_ms") is not None:
            job_totals.append(run["total_ms"])
    if job_totals:
        print(f"job 总耗时: min={min(job_totals)}ms "
              f"avg={sum(job_totals) // len(job_totals)}ms max={max(job_totals)}ms "
              f"runs={len(job_totals)}")
    if firsts:
        print(f"平台首条结果: min={min(firsts)}ms "
              f"avg={sum(firsts) // len(firsts)}ms max={max(firsts)}ms n={len(firsts)}")
    if totals:
        print(f"平台完成: min={min(totals)}ms "
              f"avg={sum(totals) // len(totals)}ms max={max(totals)}ms n={len(totals)}")


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(
        description="聚合搜索耗时基准（仅打印状态/数量/timing，不含结果正文与账号信息）")
    parser.add_argument("--url", default=DEFAULT_BASE_URL, help="API 基地址")
    parser.add_argument("--keyword", default="测试", help="搜索关键词")
    parser.add_argument("--platforms", default="",
                        help="逗号分隔的平台列表，如 xhs,douyin（默认全部）")
    parser.add_argument("--limit", type=int, default=5,
                        help="每平台结果上限（1-20）")
    parser.add_argument("--runs", type=int, default=1, help="重复次数")
    args = parser.parse_args(argv)

    platforms = [p.strip() for p in args.platforms.split(",") if p.strip()]
    if args.limit < 1 or args.limit > 20:
        parser.error("--limit 必须在 1-20 之间")
    if args.runs < 1:
        parser.error("--runs 至少为 1")

    try:
        with httpx.Client(base_url=args.url, timeout=15.0) as client:
            # 健康检查：GET /api/search/jobs/current 可访问即认为 API 已启动
            try:
                client.get("/api/search/jobs/current")
            except httpx.HTTPError:
                pass  # 404/409 都说明服务在跑；只有连接失败才算未启动
            runs = [_run_once(client, args.keyword, platforms, args.limit, i)
                    for i in range(args.runs)]
    except httpx.ConnectError as exc:
        print(f"[error] API 未启动：无法连接 {args.url}（{exc}）。"
              "请先启动：uvicorn api.main:app --port 8080", file=sys.stderr)
        return 1
    except httpx.HTTPStatusError as exc:
        print(f"[error] API 返回 {exc.response.status_code}：{exc}", file=sys.stderr)
        return 1

    if args.runs > 1:
        _summarize(runs)
    return 0


if __name__ == "__main__":
    sys.exit(main())
