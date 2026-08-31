"""Validate and archive the PyInstaller Windows distribution."""

from __future__ import annotations

import argparse
import hashlib
import shutil
from pathlib import Path


FORBIDDEN_PARTS = {
    ".git", ".github", ".env", "browser_data", "logs", "node_modules",
    "webui/src", "tests", "__pycache__",
}


def validate(distribution: Path) -> None:
    required = (
        distribution / "MediaCrawler.exe",
        distribution / "browser_extension",
    )
    missing = [str(path.relative_to(distribution)) for path in required
               if not path.exists()]
    if missing:
        raise AssertionError(f"missing executable entries: {', '.join(missing)}")

    bad = []
    for path in distribution.rglob("*"):
        relative = path.relative_to(distribution).as_posix()
        if any(part in relative.split("/") for part in FORBIDDEN_PARTS):
            bad.append(relative)
    if (distribution / "webui" / "src").exists():
        bad.append("webui/src")
    if bad:
        raise AssertionError(f"forbidden executable entries: {', '.join(bad[:20])}")


def archive(distribution: Path, output_dir: Path) -> tuple[Path, Path]:
    validate(distribution)
    archive_path = Path(shutil.make_archive(
        str(output_dir / "MediaCrawler-Windows-x64"),
        "zip",
        root_dir=distribution.parent,
        base_dir=distribution.name,
    ))
    digest = hashlib.sha256(archive_path.read_bytes()).hexdigest()
    checksum_path = archive_path.with_suffix(archive_path.suffix + ".sha256")
    checksum_path.write_text(
        f"{digest}  {archive_path.name}\n", encoding="ascii")
    return archive_path, checksum_path


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--distribution", type=Path,
                        default=Path("dist") / "MediaCrawler")
    parser.add_argument("--output", type=Path, default=Path("dist"))
    args = parser.parse_args()
    distribution = args.distribution.resolve()
    output_dir = args.output.resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    archive_path, checksum_path = archive(distribution, output_dir)
    print(f"validated executable distribution: {distribution}")
    print(f"created archive: {archive_path}")
    print(f"created checksum: {checksum_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
