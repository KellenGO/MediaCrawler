"""托盘启动器（tray_main.py）的纯逻辑测试。

只覆盖不需要真实托盘/窗口的部分：角色判定、后端启动命令构造、日志命名、
健康检查形状识别、单实例锁、图标生成、菜单文案。
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

import pytest

from tray_main import (
    MAIN_EXE_NAME,
    ROLE_LAUNCHER,
    ROLE_SERVER,
    ROLE_SMOKE,
    ROLE_WORKER,
    SingleInstanceLock,
    detect_role,
    is_our_backend,
    log_file,
    main_exe_command,
    make_icon_image,
    tray_menu_items,
    stop_backend,
)


# ── 角色判定 ────────────────────────────────────────────────────────────


def test_detect_role_covers_all_entry_points() -> None:
    assert detect_role(["--aggregate-worker"]) == ROLE_WORKER
    assert detect_role(["--frozen-runtime-smoke"]) == ROLE_SMOKE
    assert detect_role(["--no-browser"]) == ROLE_SERVER
    assert detect_role(["--server"]) == ROLE_SERVER
    assert detect_role([]) == ROLE_LAUNCHER


def test_detect_role_worker_wins_over_other_flags() -> None:
    """worker 也会被带上 --no-browser 之类的参数时不至于跑成后端。"""
    assert detect_role(["--no-browser", "--aggregate-worker"]) == ROLE_WORKER


# ── 后端启动命令 ────────────────────────────────────────────────────────


def test_frozen_launcher_targets_sibling_console_exe(tmp_path: Path) -> None:
    """打包后必须拉起同目录的 SiYe.exe（console 版），而不是启动器自己。"""
    launcher = tmp_path / "四野.exe"
    launcher.write_bytes(b"stub")
    console_exe = tmp_path / MAIN_EXE_NAME
    console_exe.write_bytes(b"stub")

    command = main_exe_command("--no-browser", frozen=True, executable=str(launcher), root=tmp_path)

    assert command == [str(console_exe), "--no-browser"]


def test_frozen_launcher_falls_back_to_itself_when_sibling_missing(tmp_path: Path) -> None:
    launcher = tmp_path / "四野.exe"
    launcher.write_bytes(b"stub")

    command = main_exe_command("--no-browser", frozen=True, executable=str(launcher), root=tmp_path)

    assert command == [str(launcher), "--no-browser"]


def test_source_mode_uses_python_and_tray_main(tmp_path: Path) -> None:
    command = main_exe_command("--no-browser", frozen=False, executable="python.exe", root=tmp_path)

    assert command[0] == "python.exe"
    assert Path(command[1]).name == "tray_main.py"
    assert command[1].startswith(str(tmp_path))
    assert command[2] == "--no-browser"


# ── 日志 ────────────────────────────────────────────────────────────────


def test_log_file_is_daily_and_inside_directory(tmp_path: Path) -> None:
    path = log_file(tmp_path, datetime(2026, 9, 13, 20, 30))

    assert path.name == "backend-20260913.log"
    assert path.parent == tmp_path


# ── 后端识别 ────────────────────────────────────────────────────────────


def test_is_our_backend_requires_the_project_health_shape() -> None:
    assert is_our_backend({"backend_available": True, "api_version": "0.2.0", "platforms": {}}) is True
    assert is_our_backend({"backend_available": True, "api_version": "0.2.0"}) is False
    assert is_our_backend({"status": "ok"}) is False
    assert is_our_backend(None) is False
    assert is_our_backend("不是对象") is False


# ── 菜单与图标 ──────────────────────────────────────────────────────────


def test_tray_menu_labels_are_stable() -> None:
    assert tray_menu_items() == ["打开四野", "打开日志目录", "退出四野"]


def test_icon_image_is_rgba_square() -> None:
    image = make_icon_image(48)

    assert image.size == (48, 48)
    assert image.mode == "RGBA"
    # 中间应有不透明的品牌色像素（渐变条），四角是透明的
    assert image.getpixel((24, 24))[3] == 255
    assert image.getpixel((0, 0))[3] == 0


# ── 单实例锁 ────────────────────────────────────────────────────────────


@pytest.mark.skipif(__import__("os").name != "nt", reason="文件锁实现只在 Windows 生效")
def test_single_instance_lock_blocks_second_launcher(tmp_path: Path) -> None:
    lock_path = tmp_path / "launcher.lock"
    first = SingleInstanceLock(lock_path)
    second = SingleInstanceLock(lock_path)

    assert first.acquire() is True
    assert second.acquire() is False  # 第二次双击不应再起一个托盘

    first.release()
    assert second.acquire() is True
    second.release()
    assert lock_path.exists()


def test_single_instance_lock_creates_parent_directory(tmp_path: Path) -> None:
    lock = SingleInstanceLock(tmp_path / "data" / "launcher.lock")

    assert lock.acquire() is True
    lock.release()

    assert (tmp_path / "data").is_dir()


def test_stop_backend_closes_control_pipe_before_forcing_exit():
    import subprocess
    import sys
    process = subprocess.Popen(
        [sys.executable, "-c", "import sys; sys.stdin.buffer.read(); sys.exit(0)"],
        stdin=subprocess.PIPE, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        creationflags=subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0,
    )
    try:
        stop_backend(process, timeout=5)
        assert process.returncode == 0  # graceful EOF path, not TerminateProcess
    finally:
        if process.poll() is None:
            process.kill()
            process.wait()


def test_launcher_cleans_up_on_normal_tray_return(monkeypatch, tmp_path):
    import tray_main
    calls = []
    backend = object()
    monkeypatch.setattr(tray_main, "application_root", lambda: tmp_path)
    monkeypatch.setattr(tray_main, "backend_alive", lambda: False)
    monkeypatch.setattr(tray_main, "start_backend", lambda _: backend)
    monkeypatch.setattr(tray_main, "wait_for_backend", lambda _: True)
    monkeypatch.setattr(tray_main.webbrowser, "open", lambda _: None)
    monkeypatch.setattr(tray_main.TrayLauncher, "run", lambda _: None)
    monkeypatch.setattr(tray_main, "stop_backend", calls.append)
    assert tray_main.run_launcher() == 0
    assert calls == [backend]
    lock = SingleInstanceLock(tmp_path / "data" / tray_main.LOCK_NAME)
    assert lock.acquire()
    lock.release()
