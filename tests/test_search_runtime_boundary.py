"""Static guards for the aggregate search runtime boundary."""

import ast
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
CORE_FILES = (
    ROOT / "media_platform" / "xhs" / "core.py",
    ROOT / "media_platform" / "douyin" / "core.py",
    ROOT / "media_platform" / "bilibili" / "core.py",
    ROOT / "media_platform" / "zhihu" / "core.py",
)


def _module_imports(path: Path):
    tree = ast.parse(path.read_text(encoding="utf-8"))
    imports = []
    for node in tree.body:
        if isinstance(node, ast.Import):
            imports.extend(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            imports.append(node.module or "")
    return imports


def test_platform_core_does_not_load_legacy_store_or_proxy_pool_at_import_time():
    for path in CORE_FILES:
        imports = _module_imports(path)
        assert not any(name == "store" or name.startswith("store.") for name in imports), path
        assert "proxy.proxy_ip_pool" not in imports, path


def test_platform_core_no_longer_references_the_proxy_pool():
    """IP 代理池是 fork 遗留，2026-09-14 整体删除。

    ``ENABLE_IP_PROXY`` 恒为 False 且 worker 四条主路径还各自再强制赋值一次，
    所以这些分支从未执行过。这里守住的是「不要再被加回来」。
    """
    for path in CORE_FILES:
        source = path.read_text(encoding="utf-8")
        assert "proxy.proxy_ip_pool" not in source, path
        assert "ip_proxy_pool" not in source, path
        assert "ENABLE_IP_PROXY" not in source, path


def test_platform_search_entrypoints_are_preserved():
    for path in CORE_FILES:
        tree = ast.parse(path.read_text(encoding="utf-8"))
        crawler = next(node for node in tree.body if isinstance(node, ast.ClassDef))
        methods = {
            node.name for node in crawler.body
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
        }
        assert {"start", "search", "close"}.issubset(methods), path


def test_hydration_detail_clients_are_preserved():
    expected = {
        ROOT / "media_platform" / "xhs" / "client.py": {"get_note_by_id"},
        ROOT / "media_platform" / "bilibili" / "client.py": {"get_video_info"},
        ROOT / "media_platform" / "zhihu" / "client.py": {
            "get_answer_info", "get_article_info", "get_video_info",
        },
    }
    for path, required in expected.items():
        tree = ast.parse(path.read_text(encoding="utf-8"))
        client = next(node for node in tree.body if isinstance(node, ast.ClassDef))
        methods = {
            node.name for node in client.body
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
        }
        assert required <= methods, path
