# -*- coding: utf-8 -*-
# Copyright (c) 2025 relakkes@gmail.com
#
# This file is part of MediaCrawler project.
# Licensed under NON-COMMERCIAL LEARNING LICENSE 1.1

"""项目知识库（wiki）结构守卫。

这些断言只读文件系统，不启动服务、不接触网络。它们守住的不是"文档写得好不好"，
而是**结构不会悄悄烂掉**：

1. 入口文件与功能地图存在（`AGENTS.md`、`docs/index.md`）；
2. 功能地图里的相对链接全部有效（改文件名后忘了改索引 = 新 agent 点空）；
3. 每份 feature 文档都有必备小节（缺了小节说明是半成品）；
4. 每个 feature 文件都在地图上有一行，反之亦然（避免"文档写了但没人找得到"）；
5. `AGENTS.md` 的「完成定义（DoD）」没有被删掉。

**它不检查内容是否写对**——内容的准确性只能靠 agent 自觉，所以 DoD 里要求
改完功能同步更新对应那一份。
"""

import re
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent

_AGENTS = _ROOT / "AGENTS.md"
_INDEX = _ROOT / "docs" / "index.md"
_FEATURES_DIR = _ROOT / "docs" / "features"
_DECISIONS_DIR = _ROOT / "docs" / "decisions"

# 每份 feature 文档必须具备的小节（顺序不强制）。
_REQUIRED_SECTIONS = (
    "## 一句话",
    "## 代码入口",
    "## 关键决定",
    "## 已知坑 / 边界",
    "## 测试怎么跑",
)

_LINK_RE = re.compile(r"\[[^\]]*\]\(([^)#]+)\)")

# 「代码入口」里用反引号包起来的路径（形如 `api/services/accounts.py`）。
# 只认带扩展名且不含空格/通配符的那些，避免把普通术语当成路径。
_CODE_PATH_RE = re.compile(r"`([A-Za-z0-9_./-]+\.(?:py|ts|tsx|js|json|ps1|bat|spec|toml|md))`")
# 允许写不存在的路径：明确标注为「历史 / 已删 / 计划」时用这个后缀
_CODE_PATH_OK_SUFFIX = "（历史记录，已不存在）"


def _code_entry_paths(text: str):
    """抽出 feature 文档里提到的代码路径（相对仓库根）。"""
    for match in _CODE_PATH_RE.finditer(text):
        candidate = match.group(1).strip()
        if candidate.startswith(("/", "../")):
            continue
        # 排除明显是「函数/表/字段」的写法与通配符
        if "*" in candidate or candidate.endswith("/"):
            continue
        # 只校验「相对仓库根」的路径（带目录分隔符）。文档里也会出现
        # 与同格其它文件并列的裸文件名（如 `useAccounts.ts`），
        # 它们相对的是同格已写出的目录，无法单独解析，跳过。
        if "/" not in candidate:
            continue
        yield candidate



def _feature_files():
    """真实的 feature 文档（以下划线开头的模板/草稿不计）。"""
    assert _FEATURES_DIR.is_dir(), "缺少 docs/features/ 目录"
    return sorted(
        path for path in _FEATURES_DIR.glob("*.md")
        if not path.name.startswith("_")
    )


def test_entry_point_and_index_exist():
    """AGENTS.md 与 docs/index.md 是 agent 的入口，不能缺。"""
    assert _AGENTS.is_file(), "缺少 AGENTS.md（agent 入口）"
    assert _INDEX.is_file(), "缺少 docs/index.md（功能地图）"


def test_agents_md_keeps_definition_of_done():
    """DoD 是"干完活同步维护 wiki"的落点，不许被删。"""
    text = _AGENTS.read_text(encoding="utf-8")
    assert "完成定义" in text, "AGENTS.md 缺少「完成定义（DoD）」小节"
    assert "docs/features/" in text, "AGENTS.md 的 DoD 必须提到要更新 docs/features/"


def test_index_relative_links_resolve():
    """功能地图里的相对链接必须都能打开。"""
    text = _INDEX.read_text(encoding="utf-8")
    broken = []
    for match in _LINK_RE.finditer(text):
        link = match.group(1).strip()
        if link.startswith(("http://", "https://", "mailto:")):
            continue
        target = (_INDEX.parent / link).resolve()
        if not target.exists():
            broken.append(link)
    assert broken == [], f"docs/index.md 里有打不开的链接: {broken}"


def test_every_feature_is_listed_in_the_index():
    """每份 feature 文档都要在地图上有一行，否则等于没人能找到它。"""
    index_text = _INDEX.read_text(encoding="utf-8")
    missing = [
        path.name for path in _feature_files()
        if path.name not in index_text
    ]
    assert missing == [], (
        "docs/index.md 缺少这些功能的条目（请各加一行）: %s" % missing)


def test_index_does_not_list_phantom_features():
    """地图上指向 docs/features/ 的链接，目标必须真的存在。"""
    index_text = _INDEX.read_text(encoding="utf-8")
    phantom = []
    for match in _LINK_RE.finditer(index_text):
        link = match.group(1).strip()
        if "features/" not in link or link.startswith(("http://", "https://")):
            continue
        if not (_INDEX.parent / link).exists():
            phantom.append(link)
    assert phantom == [], f"docs/index.md 指向不存在的功能文档: {phantom}"


def test_feature_documents_have_required_sections():
    """必备小节缺一即是半成品。"""
    problems = []
    for path in _feature_files():
        text = path.read_text(encoding="utf-8")
        lacking = [section for section in _REQUIRED_SECTIONS if section not in text]
        if lacking:
            problems.append(f"{path.name} 缺: {lacking}")
    assert problems == [], "feature 文档缺少必备小节: " + "; ".join(problems)


def test_decisions_are_recorded_with_status():
    """决策记录要有「状态」，否则读的人不知道它到底定了没有。"""
    if not _DECISIONS_DIR.is_dir():
        return
    problems = []
    for path in sorted(_DECISIONS_DIR.glob("*.md")):
        text = path.read_text(encoding="utf-8")
        if "状态" not in text:
            problems.append(path.name)
    assert problems == [], f"决策记录缺少「状态」行: {problems}"


def test_template_is_not_treated_as_a_feature():
    """模板文件必须以下划线开头，否则会被当成真 doc 混进清单。"""
    if not _FEATURES_DIR.is_dir():
        return
    stray = [p.name for p in _FEATURES_DIR.glob("*.md")
             if "TEMPLATE" in p.name.upper() and not p.name.startswith("_")]
    assert stray == [], f"模板文件应以下划线开头: {stray}"


def test_feature_code_entry_paths_exist():
    """「代码入口」里写的文件必须真的存在。

    这是唯一能自动抓住「文档腐坏」的一条：文件被改名 / 移动 / 删除后，
    文档里的路径不会自己报错，新 agent 照着找就会找空。
    （行号不在校验范围内 —— 也正因为会漂移，文档里不要写行号。）
    """
    missing = []
    for path in _feature_files():
        for candidate in _code_entry_paths(path.read_text(encoding="utf-8")):
            if not (_ROOT / candidate).exists():
                missing.append(f"{path.name} → {candidate}")
    assert missing == [], (
        "feature 文档的「代码入口」指向不存在的文件（改文件名后请同步文档；"
        "确属历史记录请在该路径后标注「" + _CODE_PATH_OK_SUFFIX + "」）: "
        + "; ".join(missing))

