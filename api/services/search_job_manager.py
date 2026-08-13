# -*- coding: utf-8 -*-
# Copyright (c) 2025 relakkes@gmail.com
#
# This file is part of MediaCrawler project.
# Licensed under NON-COMMERCIAL LEARNING LICENSE 1.1

"""In-memory search job manager with proper subprocess lifecycle."""

from __future__ import annotations

import asyncio
import logging
import os
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional

from aggregate_search.models import (
    PLATFORM_SLUGS, UnifiedSearchResult, interleave_results, make_dedup_key,
    is_valid_platform,
)
from aggregate_search.protocol import parse_event_line, WorkerRequest
from ..schemas.search import (
    SearchJobResponse, SearchJobRequestSchema, PlatformStatusInfo,
)

WORKER_TIMEOUT_SECONDS = 100
GRACE_PERIOD_SECONDS = 5.0
# Bound on waiting for an already in-flight cancel to finish (idempotent
# repeat cancel). The cancel cleanup itself is bounded by GRACE_PERIOD.
CANCEL_WAIT_TIMEOUT = 30.0
_MAX_STDERR_TAIL = 40
_PROJECT_ROOT = Path(__file__).parent.parent.parent
_WORKER_SCRIPT = str(_PROJECT_ROOT / "aggregate_search" / "worker.py")

logger = logging.getLogger(__name__)

# ── Stderr safety ───────────────────────────────────────────────────────

# Only filter the most obvious leak patterns. Do NOT duplicate protocol.py.
_STDERR_FILTER_WORDS = ("cookie=", "authorization:", "xsec_token=",
                        "access_token=", "refresh_token=", "password=")


def _safe_error_summary(msg: str) -> str:
    return str(msg)[:200]


# ── Job Manager ─────────────────────────────────────────────────────────

class SearchJobManager:
    def __init__(self) -> None:
        self._lock = asyncio.Lock()
        self._active_job: Optional[_ActiveJob] = None
        self._recent_job: Optional[_ActiveJob] = None

    def is_search_active(self) -> bool:
        job = self._active_job
        return job is not None and not job.is_terminal()

    async def create_job(self, req: SearchJobRequestSchema) -> SearchJobResponse:
        async with self._lock:
            if self._active_job is not None and not self._active_job.is_terminal():
                raise JobConflictError("A search job is already running.")

            platforms = req.platforms
            if not platforms:
                raise InvalidPlatformsError("At least one platform is required.")
            seen = set()
            for p in platforms:
                if p in seen:
                    raise InvalidPlatformsError(f"Duplicate platform: {p}")
                if not is_valid_platform(p):
                    raise InvalidPlatformsError(f"Invalid platform: {p}")
                seen.add(p)

            job_id = uuid.uuid4().hex[:12]
            job = _ActiveJob(
                job_id=job_id, keyword=req.keyword.strip(),
                platforms=platforms, limit_per_platform=req.limit_per_platform,
            )
            self._active_job = job
            self._recent_job = job

        job.task = asyncio.create_task(self._run_job(job))
        return job.to_response()

    async def get_job(self, job_id: str) -> Optional[SearchJobResponse]:
        if self._active_job and self._active_job.job_id == job_id:
            return self._active_job.to_response()
        if self._recent_job and self._recent_job.job_id == job_id:
            return self._recent_job.to_response()
        return None

    async def get_current(self) -> Optional[SearchJobResponse]:
        if self._active_job:
            return self._active_job.to_response()
        if self._recent_job:
            return self._recent_job.to_response()
        return None

    async def _run_job(self, job: "_ActiveJob") -> None:
        tasks = [asyncio.create_task(self._run_worker(job, p), name=f"w-{p}")
                 for p in job.platforms]
        await asyncio.gather(*tasks, return_exceptions=True)
        job.finalize()

    async def _run_worker(self, job: "_ActiveJob", platform: str) -> None:
        job.set_platform_status(platform, "running", 0)
        done_received = False
        proc = None
        stdout_task = None
        stderr_task = None

        try:
            env = {**os.environ, "PYTHONUTF8": "1",
                   "PYTHONIOENCODING": "utf-8", "PYTHONUNBUFFERED": "1"}
            proc = await asyncio.create_subprocess_exec(
                sys.executable, _WORKER_SCRIPT,
                stdin=asyncio.subprocess.PIPE, stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE, cwd=str(_PROJECT_ROOT), env=env,
            )
            job.procs.append(proc)

            request = WorkerRequest(
                job_id=job.job_id, mode="search", platform=platform,
                keyword=job.keyword, limit=job.limit_per_platform,
            )
            request_json = request.model_dump_json() + "\n"
            try:
                if proc.stdin:
                    proc.stdin.write(request_json.encode("utf-8"))
                    await proc.stdin.drain()
                    proc.stdin.close()
            except Exception:
                # stdin write failed — process may still be alive, must clean up
                job.set_platform_status(platform, "failed", error_summary="stdin write failed")
                return

            stdout_task = asyncio.create_task(
                self._read_worker_output(job, platform, job.job_id, proc))
            stderr_task = asyncio.create_task(
                self._read_worker_stderr(proc))

            done, pending = await asyncio.wait(
                [stdout_task, stderr_task], timeout=WORKER_TIMEOUT_SECONDS)

            timed_out = bool(pending)
            if pending:
                for t in pending:
                    t.cancel()
                await self._terminate_process(proc, platform, job)
            elif stdout_task in done:
                try:
                    done_received = stdout_task.result()
                except Exception:
                    pass

            # Drain remaining stdout
            try:
                while True:
                    raw = await asyncio.wait_for(proc.stdout.readline(), timeout=0.5)
                    if not raw:
                        break
            except (asyncio.TimeoutError, Exception):
                pass

            # Wait for process exit
            try:
                await asyncio.wait_for(proc.wait(), timeout=GRACE_PERIOD_SECONDS + 2)
            except asyncio.TimeoutError:
                try:
                    proc.kill()
                    await proc.wait()
                except Exception:
                    pass
            except Exception:
                # Round 13: 取消清理可能正并发 wait 同一进程 —— 该异常
                # 绝不能逃逸进 job.task（否则 cancel_job 的 await 会收到
                # 非 CancelledError 异常）。
                pass

            exit_code = proc.returncode if proc.returncode is not None else -1

            current = job.platforms_state.get(platform)
            # timed_out is final — don't override
            if current and current.status == "timed_out":
                return
            # A real error was already received from the worker — don't
            # override it with a "no done event" heuristic.
            if current and current.status in ("failed", "login_required",
                                              "rate_limited", "cancelled"):
                return

            if done_received and exit_code != 0:
                job.set_platform_status(platform, "failed",
                                       error_summary=f"Worker exited with code {exit_code}")
            elif not done_received:
                job.set_platform_status(platform, "failed",
                                       error_summary=f"exit {exit_code}, no done event")
            elif current and current.status == "running":
                job.set_platform_status(
                    platform,
                    "succeeded" if job.platform_results.get(platform) else "empty")

        except Exception as e:
            job.set_platform_status(platform, "failed", error_summary=_safe_error_summary(str(e)))
        finally:
            # Cancel reader tasks if still running
            for t in (stdout_task, stderr_task):
                if t and not t.done():
                    t.cancel()
            if stdout_task or stderr_task:
                await asyncio.gather(
                    *(t for t in (stdout_task, stderr_task) if t),
                    return_exceptions=True)
            # Ensure process is dead
            if proc is not None and proc.returncode is None:
                try:
                    proc.terminate()
                except Exception:
                    pass
                try:
                    await asyncio.wait_for(proc.wait(), timeout=GRACE_PERIOD_SECONDS)
                except asyncio.TimeoutError:
                    try:
                        proc.kill()
                        await proc.wait()
                    except Exception:
                        pass
                except Exception:
                    # Round 13: 与取消清理并发 wait 同一进程 —— 不得逃逸。
                    # 注意：任务被取消时此处 await 会抛 CancelledError
                    # （BaseException），仍正常向上传播保持取消语义。
                    pass

    async def _read_worker_output(
        self, job: "_ActiveJob", platform: str, expected_job_id: str,
        proc: asyncio.subprocess.Process,
    ) -> bool:
        if not proc.stdout:
            return False
        done_received = False
        while True:
            raw = await proc.stdout.readline()
            if not raw:
                break
            try:
                line_str = raw.decode("utf-8", errors="replace").strip()
            except Exception:
                continue
            if not line_str:
                continue
            event = parse_event_line(line_str)
            if event is None:
                continue
            if event.job_id != expected_job_id or event.platform != platform:
                continue

            if event.event == "status":
                sd = event.data or {}
                job.set_platform_status(platform, sd.get("status", "running"))
            elif event.event == "result":
                rd = event.data
                if isinstance(rd, dict) and rd.get("platform") == platform:
                    try:
                        job.add_result(platform, UnifiedSearchResult(**rd))
                    except Exception:
                        pass
            elif event.event == "error":
                ed = event.data or {}
                job.set_platform_status(platform, ed.get("type", "failed"),
                                       error_summary=_safe_error_summary(ed.get("message", "")))
            elif event.event == "done":
                done_received = True
                break
        return done_received

    async def _read_worker_stderr(self, proc: asyncio.subprocess.Process) -> None:
        if not proc.stderr:
            return
        tail: List[str] = []
        while True:
            raw = await proc.stderr.readline()
            if not raw:
                break
            try:
                line = raw.decode("utf-8", errors="replace").strip()
            except Exception:
                continue
            if not line:
                continue
            lowered = line.lower()
            if any(w in lowered for w in _STDERR_FILTER_WORDS):
                continue
            tail.append(line)
            if len(tail) > _MAX_STDERR_TAIL:
                tail.pop(0)

    async def _terminate_process(
        self, proc: asyncio.subprocess.Process, platform: str, job: "_ActiveJob",
    ) -> None:
        try:
            if proc.returncode is None:
                proc.terminate()
        except Exception:
            pass
        try:
            await asyncio.wait_for(proc.wait(), timeout=GRACE_PERIOD_SECONDS)
        except asyncio.TimeoutError:
            try:
                proc.kill()
                await proc.wait()
            except Exception:
                pass
        except Exception:
            pass  # Round 13: 并发清理异常不得逃逸
        # Only set timed_out if not already terminal
        cur = job.platforms_state.get(platform)
        if cur and cur.status not in ("succeeded", "empty", "login_required",
                                       "rate_limited", "failed", "cancelled"):
            job.set_platform_status(platform, "timed_out")

    async def cancel_job(self, job_id: str) -> bool:
        """Cancel the active job.

        Contract (Round 13):
        - Returns True when the job is being / has been cancelled by this
          or a concurrent cancel (idempotent — a repeat cancel waits for the
          in-flight cleanup instead of returning 404/500 or starting a
          second cleanup).
        - Returns False only for an unknown job or a job already in a NORMAL
          terminal state (completed/partial/failed — nothing to cancel).
        - Never raises for cleanup problems: every step is bounded and
          isolated, and an outer finally guarantees the job reaches a
          queryable ``cancelled`` terminal state (``_cancelling=False``,
          ``_cancelled=True``, pending/running platforms -> cancelled,
          succeeded/empty platforms and results preserved, ``finalize()``,
          handled procs removed from ``job.procs``).
        """
        job = self._active_job
        if job is None or job.job_id != job_id:
            return False
        if job.is_terminal():
            # 已取消的 job 重复取消 → 幂等成功；正常终态 → 无可取消。
            return job._cancelled
        # 已有取消在途：等待同一取消操作完成（不启动第二套清理）。
        if job._cancelling:
            await self._await_cancel_done(job)
            return True
        async with job.cancel_lock:
            if job.is_terminal():
                return job._cancelled
            if job._cancelling:
                await self._await_cancel_done(job)
                return True

            job._cancelling = True
            try:
                for p in job.platforms:
                    if job.platforms_state[p].status in ("pending", "running"):
                        job.set_platform_status(p, "cancelled", error_summary="已取消")
                await self._cleanup_job_processes(job)
                await self._stop_job_task(job)
            finally:
                # 最外层 finally：无论哪一步失败，任务都必须进入
                # 可查询的 cancelled 终态，绝不永久卡在 cancelling。
                job._cancelling = False
                job._cancelled = True
                for p in job.platforms:
                    if job.platforms_state[p].status in ("pending", "running"):
                        job.set_platform_status(p, "cancelled", error_summary="已取消")
                job.finalize()
                job.cancel_done.set()
        return True

    async def _await_cancel_done(self, job: "_ActiveJob") -> None:
        """等待在途取消结束（有界；清理本身有界，超时仅防御）。"""
        try:
            await asyncio.wait_for(job.cancel_done.wait(), timeout=CANCEL_WAIT_TIMEOUT)
        except asyncio.TimeoutError:
            logger.warning("cancel: waited for in-flight cancel of %s "
                           "but it did not finish within %ss", job.job_id,
                           CANCEL_WAIT_TIMEOUT)

    async def _cleanup_job_processes(self, job: "_ActiveJob") -> None:
        """Kill + bounded-wait every live subprocess.

        - 每个进程 kill/terminate + wait 带超时；
        - 单个进程的失败被隔离（记录异常类型），不影响其他进程清理；
        - 已处理的进程从 job.procs 移除。
        本方法绝不抛异常。
        """
        procs = list(job.procs)
        for proc in procs:
            try:
                if proc.returncode is None:
                    proc.kill()
            except Exception as e:
                logger.warning("cancel: kill proc %s failed: %s",
                               getattr(proc, "pid", "?"), type(e).__name__)
        for proc in procs:
            try:
                await asyncio.wait_for(proc.wait(), timeout=GRACE_PERIOD_SECONDS)
            except asyncio.TimeoutError:
                try:
                    proc.kill()
                    await asyncio.wait_for(proc.wait(),
                                           timeout=GRACE_PERIOD_SECONDS)
                except Exception as e:
                    logger.warning("cancel: proc %s did not exit after kill: %s",
                                   getattr(proc, "pid", "?"), type(e).__name__)
            except Exception as e:
                logger.warning("cancel: wait proc %s failed: %s",
                               getattr(proc, "pid", "?"), type(e).__name__)
        for proc in procs:
            try:
                job.procs.remove(proc)
            except ValueError:
                pass

    async def _stop_job_task(self, job: "_ActiveJob") -> None:
        """取消并等待 job.task；任何异常（CancelledError / RuntimeError /
        ExceptionGroup / 超时）都不得冒泡到调用方。"""
        task = job.task
        if task is None or task.done():
            return
        task.cancel()
        try:
            await asyncio.wait_for(task, timeout=GRACE_PERIOD_SECONDS + 2)
        except (asyncio.TimeoutError, asyncio.CancelledError, Exception) as e:
            logger.warning("cancel: job task %s cleanup: %s",
                           job.job_id, type(e).__name__)

    async def cleanup(self) -> None:
        """Shutdown cleanup：与 cancel_job 使用同一组有界、防逃逸的
        清理原语（并发调用不会死锁、不留下进程）。"""
        job = self._active_job
        if job is None:
            return
        # Mark all running platforms as cancelled
        for p in job.platforms:
            if job.platforms_state[p].status in ("pending", "running"):
                job.set_platform_status(p, "cancelled", error_summary="服务已停止")
        await self._cleanup_job_processes(job)
        await self._stop_job_task(job)
        job._cancelled = True
        job.finalize()
        job.cancel_done.set()


# ── Active Job ──────────────────────────────────────────────────────────

class _ActiveJob:
    def __init__(self, job_id: str, keyword: str, platforms: List[str],
                 limit_per_platform: int) -> None:
        self.job_id = job_id
        self.keyword = keyword
        self.platforms = platforms
        self.limit_per_platform = limit_per_platform
        self.created_at = datetime.now(timezone.utc).isoformat()
        self.completed_at: Optional[str] = None
        self.platforms_state: Dict[str, PlatformStatusInfo] = {
            p: PlatformStatusInfo(status="pending") for p in platforms}
        self.platform_results: Dict[str, List[UnifiedSearchResult]] = {
            p: [] for p in platforms}
        self._seen_keys: set = set()
        self.procs: List[asyncio.subprocess.Process] = []
        self.task: Optional[asyncio.Task] = None
        self._cancelling: bool = False
        self._cancelled: bool = False
        # ── Per-job cancel coordination (Round 13) ─────────────────────
        # cancel_lock: 同一 job 只允许一套并发清理。
        # cancel_done: 清理完成信号（重复取消等待它即可，幂等）。
        self.cancel_lock = asyncio.Lock()
        self.cancel_done = asyncio.Event()

    def set_platform_status(self, platform: str, status: str, result_count: int = 0,
                            error_summary: Optional[str] = None) -> None:
        info = self.platforms_state.get(platform)
        if info is None:
            return
        # timed_out is terminal and must not be downgraded
        if info.status == "timed_out" and status not in ("timed_out",):
            return
        terminal = {"succeeded", "empty", "login_required",
                    "rate_limited", "timed_out", "failed", "cancelled"}
        if info.status in terminal and status not in terminal:
            return
        info.status = status
        if result_count:
            info.result_count = max(info.result_count, result_count)
        if error_summary:
            info.error_summary = error_summary

    def add_result(self, platform: str, result: UnifiedSearchResult) -> None:
        key = make_dedup_key(platform, result.content_id)
        if key in self._seen_keys:
            return
        self._seen_keys.add(key)
        lst = self.platform_results.setdefault(platform, [])
        if len(lst) < self.limit_per_platform:
            lst.append(result)
            info = self.platforms_state.get(platform)
            if info:
                info.result_count = len(lst)

    def is_terminal(self) -> bool:
        return self._compute_overall() in (
            "completed", "partial", "failed", "cancelled")

    def finalize(self) -> None:
        self.completed_at = datetime.now(timezone.utc).isoformat()
        for p, results in self.platform_results.items():
            info = self.platforms_state.get(p)
            if info and info.status in ("running", "pending"):
                info.status = "succeeded" if results else "empty"
                info.result_count = len(results)

    def _compute_overall(self) -> str:
        if self._cancelled:
            return "cancelled"
        if self._cancelling:
            return "cancelling"
        statuses = [info.status for info in self.platforms_state.values()]
        terminal = {"succeeded", "empty", "login_required",
                    "rate_limited", "timed_out", "failed", "cancelled"}
        if not all(s in terminal for s in statuses):
            return "running"
        successes = sum(1 for s in statuses if s in {"succeeded", "empty"})
        failures = len(statuses) - successes
        if failures == 0:
            return "completed"
        if successes > 0:
            return "partial"
        return "failed"

    def to_response(self) -> SearchJobResponse:
        all_results = interleave_results(
            self.platform_results, platform_order=self.platforms)
        pdict: Dict[str, PlatformStatusInfo] = {}
        for p in self.platforms:
            info = self.platforms_state.get(p)
            if info:
                pdict[p] = PlatformStatusInfo(
                    status=info.status, result_count=info.result_count,
                    error_summary=info.error_summary)
        return SearchJobResponse(
            job_id=self.job_id, overall=self._compute_overall(),
            keyword=self.keyword, created_at=self.created_at,
            completed_at=self.completed_at, platforms=pdict, results=all_results)


class JobConflictError(Exception):
    pass


class InvalidPlatformsError(Exception):
    pass


search_job_manager = SearchJobManager()
