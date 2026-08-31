"""Assemble and validate the node-free Windows release package."""

from __future__ import annotations

import argparse
import shutil
from pathlib import Path


RUNTIME_DIRECTORIES = (
    "api",
    "aggregate_search",
    "base",
    "cache",
    "config",
    "constant",
    "libs",
    "media_platform",
    "model",
    "proxy",
    "tools",
    "browser_extension",
)
RUNTIME_FILES = (
    "MediaCrawler.bat",
    "main.py",
    "recv_sms.py",
    "var.py",
    "pyproject.toml",
    "requirements.txt",
    "uv.lock",
    ".env.example",
    "LICENSE",
    "README.md",
)
FORBIDDEN_NAMES = {
    ".git",
    ".github",
    ".env",
    "browser_data",
    "logs",
    "node_modules",
    "__pycache__",
    ".pytest_cache",
    ".mypy_cache",
    ".ruff_cache",
}
FORBIDDEN_SUFFIXES = {".db", ".sqlite", ".sqlite3"}


def _copy_tree(source: Path, destination: Path) -> None:
    shutil.copytree(
        source,
        destination,
        ignore=shutil.ignore_patterns(
            "__pycache__",
            "*.pyc",
            ".pytest_cache",
            ".mypy_cache",
            ".ruff_cache",
        ),
    )


def assemble(
    root: Path,
    output_dir: Path,
    release_version: str | None = None,
) -> tuple[Path, Path]:
    package_dir = output_dir / "MediaCrawler-Windows"
    if package_dir.exists():
        shutil.rmtree(package_dir)
    package_dir.mkdir(parents=True)

    for relative in RUNTIME_DIRECTORIES:
        source = root / relative
        if not source.is_dir():
            raise FileNotFoundError(f"required runtime directory missing: {relative}")
        _copy_tree(source, package_dir / relative)

    for relative in RUNTIME_FILES:
        source = root / relative
        if not source.is_file():
            raise FileNotFoundError(f"required runtime file missing: {relative}")
        destination = package_dir / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, destination)

    start_script = root / "scripts" / "start.ps1"
    destination = package_dir / "scripts" / "start.ps1"
    destination.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(start_script, destination)

    dist = root / "webui" / "dist"
    if not (dist / "index.html").is_file():
        raise FileNotFoundError("webui/dist/index.html is required in the release package")
    _copy_tree(dist, package_dir / "webui" / "dist")

    if release_version:
        if any(char in release_version for char in "\r\n"):
            raise ValueError("release version must be a single line")
        (package_dir / "RELEASE_VERSION").write_text(
            release_version.strip() + "\n", encoding="utf-8"
        )

    validate(package_dir)
    archive = shutil.make_archive(
        str(output_dir / "MediaCrawler-Windows"),
        "zip",
        root_dir=output_dir,
        base_dir="MediaCrawler-Windows",
    )
    return package_dir, Path(archive)


def validate(package_dir: Path) -> None:
    required = (
        package_dir / "MediaCrawler.bat",
        package_dir / "scripts" / "start.ps1",
        package_dir / "api",
        package_dir / "aggregate_search",
        package_dir / "webui" / "dist" / "index.html",
    )
    missing = [str(path.relative_to(package_dir)) for path in required if not path.exists()]
    if missing:
        raise AssertionError(f"missing package entries: {', '.join(missing)}")

    forbidden = []
    for path in package_dir.rglob("*"):
        if path.is_symlink():
            forbidden.append(f"symlink:{path.relative_to(package_dir)}")
        if path.name in FORBIDDEN_NAMES:
            forbidden.append(str(path.relative_to(package_dir)))
        if path.is_file() and path.suffix.lower() in FORBIDDEN_SUFFIXES:
            forbidden.append(str(path.relative_to(package_dir)))
    if forbidden:
        raise AssertionError(f"forbidden package entries: {', '.join(forbidden)}")

    if (package_dir / "webui" / "src").exists():
        raise AssertionError("webui/src must not be packaged")
    launcher_text = (package_dir / "scripts" / "start.ps1").read_text(encoding="utf-8-sig")
    if "webui/src" in launcher_text or "node_modules" in launcher_text:
        raise AssertionError("launcher must not depend on frontend source or node_modules")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("--output", type=Path, default=Path("release"))
    parser.add_argument("--release-version", default=None)
    args = parser.parse_args()

    root = args.root.resolve()
    output_dir = args.output if args.output.is_absolute() else root / args.output
    output_dir.mkdir(parents=True, exist_ok=True)
    package_dir, archive = assemble(root, output_dir, args.release_version)
    print(f"validated staging: {package_dir}")
    print(f"created archive: {archive}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
