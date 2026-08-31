"""Run runtime and web smoke tests against an extracted release package."""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import time
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


FORBIDDEN_NAMES = {
    ".env",
    ".git",
    ".github",
    "browser_data",
    "logs",
    "node_modules",
    "__pycache__",
    "tests",
}
FORBIDDEN_SUFFIXES = {".db", ".sqlite", ".sqlite3"}


def _request(url: str) -> tuple[int, str]:
    try:
        with urlopen(Request(url, headers={"Accept": "text/html,application/json,*/*"}), timeout=3) as response:
            return response.status, response.read().decode("utf-8", errors="replace")
    except HTTPError as exc:
        return exc.code, exc.read().decode("utf-8", errors="replace")
    except URLError:
        return 0, ""


def validate_package(package: Path) -> None:
    required = (
        package / "MediaCrawler.bat",
        package / "scripts" / "start.ps1",
        package / "api" / "main.py",
        package / "pyproject.toml",
        package / "RELEASE_VERSION",
        package / "webui" / "dist" / "index.html",
    )
    missing = [str(path.relative_to(package)) for path in required if not path.exists()]
    if missing:
        raise AssertionError(f"missing package entries: {', '.join(missing)}")

    forbidden = []
    for path in package.rglob("*"):
        if any(part in FORBIDDEN_NAMES for part in path.parts):
            forbidden.append(str(path.relative_to(package)))
        if path.is_file() and path.suffix.lower() in FORBIDDEN_SUFFIXES:
            forbidden.append(str(path.relative_to(package)))
    if forbidden:
        raise AssertionError(f"forbidden package entries: {', '.join(forbidden[:10])}")

    if (package / "webui" / "src").exists():
        raise AssertionError("webui/src must not be packaged")
    if (package / ".venv").exists():
        raise AssertionError("runtime venv must stay outside the package")

    suspicious_absolute_path = re.compile(r"(?:[A-Za-z]:\\Users\\|/home/|/workspace/)")
    for path in package.rglob("*"):
        if not path.is_file():
            continue
        try:
            text = path.read_text(encoding="utf-8-sig")
        except (UnicodeDecodeError, OSError):
            continue
        if suspicious_absolute_path.search(text):
            raise AssertionError(f"absolute user/workspace path found in {path.relative_to(package)}")


def run_import_smoke(package: Path, python_executable: Path) -> None:
    import_script = (
        "import api.main; "
        "import aggregate_search.worker; "
        "import api.services.accounts; "
        "import api.services.result_hydration; "
        "from aggregate_search.adapters import XhsAdapter, DouyinAdapter, BilibiliAdapter, ZhihuAdapter; "
        "from media_platform.xhs import client as xhs_client; "
        "from media_platform.douyin import client as douyin_client; "
        "from media_platform.bilibili import client as bilibili_client; "
        "from media_platform.zhihu import client as zhihu_client; "
        "print('production imports: PASS')"
    )
    env = os.environ.copy()
    env.pop("PYTHONPATH", None)
    result = subprocess.run(
        [str(python_executable), "-c", import_script],
        cwd=package,
        env=env,
        capture_output=True,
        text=True,
        errors="replace",
        timeout=45,
    )
    if result.returncode != 0:
        output = (result.stdout + result.stderr)[-3000:]
        raise AssertionError(f"production import smoke failed: {output}")


def run_launcher_smoke(package: Path) -> None:
    env = os.environ.copy()
    env.pop("PYTHONPATH", None)
    env["MEDIACRAWLER_LAUNCHER_TEST"] = "1"
    result = subprocess.run(
        ["cmd.exe", "/c", "MediaCrawler.bat"],
        cwd=package,
        env=env,
        capture_output=True,
        text=True,
        errors="replace",
        timeout=90,
    )
    if result.returncode != 0:
        output = (result.stdout + result.stderr)[-2000:]
        raise AssertionError(f"packaged launcher failed ({result.returncode}): {output}")


def run_web_smoke(package: Path, python_executable: Path) -> None:
    env = os.environ.copy()
    env.pop("PYTHONPATH", None)
    process = subprocess.Popen(
        [
            str(python_executable),
            "-m",
            "uvicorn",
            "api.main:app",
            "--host",
            "127.0.0.1",
            "--port",
            "8080",
        ],
        cwd=package,
        env=env,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    base_url = "http://127.0.0.1:8080"
    try:
        deadline = time.monotonic() + 45
        health = None
        while time.monotonic() < deadline:
            status, body = _request(f"{base_url}/api/health")
            if status == 200:
                try:
                    health = json.loads(body)
                except json.JSONDecodeError:
                    health = None
                if isinstance(health, dict) and health.get("status") == "ok":
                    break
            if process.poll() is not None:
                raise AssertionError("packaged backend exited before health became ready")
            time.sleep(0.5)
        if not isinstance(health, dict) or health.get("status") != "ok":
            raise AssertionError("packaged backend did not pass /api/health")

        for path in ("/", "/accounts"):
            status, body = _request(f"{base_url}{path}")
            if status != 200 or 'id="root"' not in body:
                raise AssertionError(f"{path} did not serve the SPA entry point")

        status, body = _request(f"{base_url}/api/health")
        if status != 200 or not body.lstrip().startswith("{") or "<html" in body.lower():
            raise AssertionError("/api/health was consumed by the SPA fallback")

        assets = sorted((package / "webui" / "dist" / "assets").iterdir())
        asset = next(path for path in assets if path.is_file())
        relative_asset = asset.relative_to(package / "webui" / "dist").as_posix()
        status, _ = _request(f"{base_url}/{relative_asset}")
        if status != 200:
            raise AssertionError(f"built asset was not served: {relative_asset}")

        for path in ("/assets/missing-release-smoke.js", "/api/not-a-real-endpoint", "/%2e%2e/api/main.py"):
            status, body = _request(f"{base_url}{path}")
            if status != 404 or 'id="root"' in body:
                raise AssertionError(f"unsafe or missing path was not rejected: {path}")
    finally:
        if process.poll() is None:
            process.terminate()
            try:
                process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=10)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--package", type=Path, required=True)
    parser.add_argument("--python", type=Path, required=True)
    args = parser.parse_args()

    package = args.package.resolve()
    python_executable = args.python.resolve()
    if not package.is_dir() or not python_executable.is_file():
        raise FileNotFoundError("clean-room package or runtime Python is missing")
    if Path.cwd().resolve() == package:
        raise AssertionError("smoke runner must be outside the extracted package")

    validate_package(package)
    run_import_smoke(package, python_executable)
    run_launcher_smoke(package)
    run_web_smoke(package, python_executable)
    print("clean-room package validation: PASS")
    print("launcher smoke: PASS")
    print("node-free backend/web smoke: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
