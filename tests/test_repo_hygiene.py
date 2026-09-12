# -*- coding: utf-8 -*-
# Copyright (c) 2025 relakkes@gmail.com
#
# This file is part of MediaCrawler project.
# Licensed under NON-COMMERCIAL LEARNING LICENSE 1.1

"""仓库卫生守护测试（代码瘦身后防止回潮）。

这些断言只读文件系统/git，不启动任何服务、不接触网络。它们守住四类
曾经真实发生过的问题：

1. 构建产物被提交进仓库（``release/`` 是 ``scripts/package_windows.py``
   的生成物，曾被提交 124 个文件，其中 30 个已落后于主源码）；
2. 上游文档站又被合并回来（``docs/`` 下只剩本产品自己的文档）；
3. ``requirements.txt`` 与 ``pyproject.toml`` 依赖漂移（曾漏掉 websockets、
   opencv-python 未固定版本）；
4. 打包清单引用了已删除的文件，或死代码被重新引入。
"""

import importlib.util
import re
import subprocess
import sys
from pathlib import Path

import pytest

_ROOT = Path(__file__).resolve().parent.parent

if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))


def _git(*args: str) -> str:
    """调用 git；环境里没有 git 时跳过（例如解压后的源码包）。"""
    try:
        result = subprocess.run(
            ["git", *args], cwd=_ROOT, capture_output=True, text=True,
            encoding="utf-8", errors="replace")
    except OSError:  # pragma: no cover - 只在不含 git 的环境触发
        pytest.skip("git 不可用")
    if result.returncode != 0:  # pragma: no cover
        pytest.skip("当前目录不是可用的 git 工作区")
    return result.stdout


# ── 1. 生成物不得进入版本库 ─────────────────────────────────────────────

def test_release_output_is_not_tracked():
    """release/ 是打包脚本的生成物，不得被 git 跟踪。"""
    tracked = _git("ls-files", "release").splitlines()
    assert tracked == [], f"release/ 下不应有受跟踪文件: {tracked[:5]}"


def test_generated_artifacts_are_gitignored():
    """生成目录必须写在 .gitignore 里，避免被 git add -A 扫进来。"""
    ignore = (_ROOT / ".gitignore").read_text(encoding="utf-8")
    for entry in ("/release/", "dist/", "build/", "webui/dist/"):
        assert entry in ignore, f".gitignore 缺少 {entry}"


# ── 2. 上游文档站不得回潮 ───────────────────────────────────────────────

def test_upstream_docs_site_is_gone():
    """docs/ 只保留本产品自己的文档；上游 VitePress 站点与其大体积资源已移除。"""
    docs = _ROOT / "docs"
    assert docs.is_dir(), "docs/ 应保留本产品自己的文档"
    forbidden = ["static", ".vitepress"]
    for name in forbidden:
        assert not (docs / name).exists(), f"docs/{name} 属于已移除的上游文档站"
    leftovers = [
        p.name for p in docs.rglob("*")
        if p.is_file() and p.suffix.lower() in (".ttf", ".woff", ".woff2", ".otf")
    ]
    assert leftovers == [], f"docs/ 不应再有字体等站点资源: {leftovers}"


def test_upstream_only_docs_are_not_tracked():
    """11 篇上游宣传/付费/代理文档与未被引用的 stopwords 不得回潮。"""
    tracked = _git("ls-files", "docs").splitlines()
    assert tracked, "docs/ 应至少保留本产品自己的文档"
    banned_fragments = (
        "index.md", "hit_stopwords", "\u4f5c\u8005\u4ecb\u7ecd", "\u5fae\u4fe1\u4ea4\u6d41\u7fa4",
        "\u5e38\u89c1\u95ee\u9898", "\u77e5\u8bc6\u4ed8\u8d39", "\u6350\u8d60\u540d\u5355",
        "\u4ee3\u7406\u4f7f\u7528", "\u5feb\u4ee3\u7406", "\u8c4c\u8c46HTTP",
        "\u624b\u673a\u53f7\u767b\u5f55", "CDP", "mediacrawlerpro",
    )
    for path in tracked:
        name = path.split("/", 1)[1]
        for fragment in banned_fragments:
            assert fragment not in name, f"上游文档回潮: {path}"


def test_root_docs_toolchain_is_removed():
    """根 package.json/lock 与 Pages 工作流只为上游文档站存在，已移除。"""
    for rel in ("package.json", "package-lock.json",
                ".github/workflows/deploy.yml"):
        assert not (_ROOT / rel).exists(), f"{rel} 应已移除"


# ── 3. 依赖声明不得漂移 ─────────────────────────────────────────────────

def _normalize(spec: str) -> tuple[str, str]:
    match = re.match(r"([A-Za-z0-9_.\-]+)\s*(.*)", spec.strip())
    name, version = match.group(1), match.group(2).strip()
    return name.lower().replace("_", "-"), version


def _pyproject_dependencies() -> dict:
    text = (_ROOT / "pyproject.toml").read_text(encoding="utf-8")
    block = re.search(r"dependencies\s*=\s*\[(.*?)\]", text, re.S).group(1)
    deps = {}
    for line in block.splitlines():
        match = re.match(r'\s*"([^"]+)"\s*,?', line)
        if match:
            name, version = _normalize(match.group(1))
            deps[name] = version
    return deps


def _requirements_dependencies() -> dict:
    deps = {}
    for line in (_ROOT / "requirements.txt").read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        name, version = _normalize(line)
        deps[name] = version
    return deps


def test_requirements_match_pyproject():
    """requirements.txt 必须与 pyproject.toml 的运行时依赖一致。

    requirements.txt 仍被 scripts/package_windows.py 打进发布包且没有版本检查，
    因此这里的奇偶校验是唯一防线（曾漏掉 websockets、opencv 未固定版本）。
    """
    pyproject = _pyproject_dependencies()
    requirements = _requirements_dependencies()
    assert set(pyproject) == set(requirements), (
        "依赖集合不一致: 仅 pyproject=%s, 仅 requirements=%s" % (
            sorted(set(pyproject) - set(requirements)),
            sorted(set(requirements) - set(pyproject))))
    mismatched = {
        name: (pyproject[name], requirements[name])
        for name in pyproject if pyproject[name] != requirements[name]
    }
    assert mismatched == {}, f"依赖版本声明不一致: {mismatched}"


# ── 4. 打包清单与死代码 ─────────────────────────────────────────────────

def _runtime_lists() -> tuple[tuple, tuple]:
    text = (_ROOT / "scripts" / "package_windows.py").read_text(encoding="utf-8")
    dirs = re.search(r"RUNTIME_DIRECTORIES\s*=\s*\((.*?)\)", text, re.S).group(1)
    files = re.search(r"RUNTIME_FILES\s*=\s*\((.*?)\)", text, re.S).group(1)
    parse = lambda block: tuple(re.findall(r'"([^"]+)"', block))
    return parse(dirs), parse(files)


def test_packaging_lists_exist_on_disk():
    """打包清单里的每一项都必须真实存在，否则组装发布包会直接抛错。"""
    directories, files = _runtime_lists()
    missing_dirs = [d for d in directories if not (_ROOT / d).is_dir()]
    missing_files = [f for f in files if not (_ROOT / f).is_file()]
    assert missing_dirs == [], f"打包清单里的目录不存在: {missing_dirs}"
    assert missing_files == [], f"打包清单里的文件不存在: {missing_files}"


def test_packaging_does_not_reference_removed_sms_helper():
    """recv_sms.py 已删除（产品登录走二维码 + 扩展同步），打包清单不得再提它。"""
    _, files = _runtime_lists()
    assert "recv_sms.py" not in files


@pytest.mark.parametrize("module", [
    "model.m_douyin",
    "model.m_bilibili",
    "model.m_xiaohongshu",
    "recv_sms",
])
def test_removed_modules_are_gone(module: str):
    """已删除的死模块不得被重新引入。"""
    assert importlib.util.find_spec(module) is None, f"{module} 应已删除"


@pytest.mark.parametrize("relative,symbols", [
    ("tools/easing.py", ["ease_in_quad", "ease_out_bounce", "ease_out_elastic"]),
    ("tools/time_util.py", ["get_current_timestamp", "get_current_date"]),
    ("tools/utils.py", ["str2bool"]),
    ("base/runtime_paths.py", ["worker_command"]),
    ("api/services/environment_health.py", ["reset_health_cache"]),
    ("api/services/accounts.py", ["RequiredLoginCookieMissingError"]),
    ("model/m_zhihu.py", ["ZhihuComment"]),
    ("media_platform/xhs/field.py", ["FeedType", "NoteType"]),
])
def test_removed_symbols_stay_removed(relative: str, symbols: list):
    """已删除的无引用符号不得回潮。

    用词边界匹配，避免 ``NoteType`` 命中仍在使用的 ``SearchNoteType``。
    """
    text = (_ROOT / relative).read_text(encoding="utf-8")
    for symbol in symbols:
        assert not re.search(r"\b%s\b" % re.escape(symbol), text), \
            f"{relative} 不应再定义 {symbol}"


def test_single_test_root():
    """测试只应有一个根目录（历史上 test/ 与 tests/ 并存）。"""
    assert (_ROOT / "tests").is_dir()
    assert not (_ROOT / "test").exists(), "遗留的 test/ 根目录应已合并进 tests/"
