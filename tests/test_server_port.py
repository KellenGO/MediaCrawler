# -*- coding: utf-8 -*-
# Copyright (c) 2025 relakkes@gmail.com
# This file is part of MediaCrawler project.
# Licensed under NON-COMMERCIAL LEARNING LICENSE 1.1

"""端口解析测试（``base.server_port``）。

同一个仓库可能有多个 check-out 同时跑，靠 ``SIYE_PORT`` 覆盖端口避免撞车；
产品默认必须仍然是 8080（README、浏览器扩展 manifest 都按它写）。
"""

import os
import sys


from base.server_port import DEFAULT_PORT, ENV_VAR, base_url, resolve_port


def test_env_var_name_and_default_are_stable():
    """变量名与默认端口是对外契约（脚本、扩展、文档都按它写）。"""
    assert ENV_VAR == "SIYE_PORT"
    assert DEFAULT_PORT == 8080


def test_defaults_to_product_port_when_unset(monkeypatch):
    monkeypatch.delenv(ENV_VAR, raising=False)
    assert resolve_port() == 8080
    monkeypatch.setenv(ENV_VAR, "8092")
    assert resolve_port() == 8092
    monkeypatch.delenv(ENV_VAR)
    assert resolve_port() == 8080


def test_reads_env_override(monkeypatch):
    monkeypatch.setenv(ENV_VAR, "8090")
    assert resolve_port() == 8090


def test_tolerates_surrounding_whitespace(monkeypatch):
    monkeypatch.setenv(ENV_VAR, "  8091  ")
    assert resolve_port() == 8091


def test_invalid_values_fall_back_instead_of_crashing(monkeypatch):
    """启动阶段不该因为一个打错的环境变量直接崩掉。"""
    for raw in ["", "   ", "abc", "0", "-1", "70000", "8080.5", "1e3", "0x1f90"]:
        monkeypatch.setenv(ENV_VAR, raw)
        assert resolve_port() == 8080, raw


def test_explicit_default_argument_is_honoured(monkeypatch):
    monkeypatch.delenv(ENV_VAR, raising=False)
    assert resolve_port(default=9000) == 9000
    monkeypatch.setenv(ENV_VAR, "9001")
    assert resolve_port(default=9000) == 9001


def test_boundary_ports_are_accepted(monkeypatch):
    for raw in ["1", "65535"]:
        monkeypatch.setenv(ENV_VAR, raw)
        assert resolve_port() == int(raw)


def test_base_url_uses_env_port_without_trailing_slash(monkeypatch):
    monkeypatch.setenv(ENV_VAR, "8090")
    assert base_url() == "http://127.0.0.1:8090"
    assert base_url(port=8081) == "http://127.0.0.1:8081"


def test_port_is_read_at_call_time_not_import_time(monkeypatch):
    """必须是调用时读环境变量：启动脚本会在运行前 set，import 时还没设。"""
    monkeypatch.delenv(ENV_VAR, raising=False)
    assert resolve_port() == 8080
    monkeypatch.setenv(ENV_VAR, "8092")
    assert resolve_port() == 8092
    monkeypatch.delenv(ENV_VAR)
    assert resolve_port() == 8080


def test_tray_and_backend_share_custom_port():
    import os
    import subprocess
    import sys
    result = subprocess.run(
        [sys.executable, "-c", "import tray_main,desktop_main; assert tray_main.PORT == desktop_main.PORT == 8092; assert tray_main.BASE_URL == desktop_main.BASE_URL"],
        env={**os.environ, "SIYE_PORT": "8092"}, capture_output=True, text=True,
        timeout=20,
    )
    assert result.returncode == 0, result.stderr
