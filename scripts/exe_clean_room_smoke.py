"""Clean-room smoke tests for the PyInstaller Windows distribution."""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

# The smoke harness runs from the source checkout, while the executable under
# test is launched from the extracted package.
_REPO_ROOT = Path(__file__).resolve().parents[1]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

def _request(url: str) -> tuple[int, str]:
    try:
        with urlopen(Request(url), timeout=3) as response:
            return response.status, response.read().decode("utf-8", errors="replace")
    except HTTPError as exc:
        return exc.code, exc.read().decode("utf-8", errors="replace")
    except URLError:
        return 0, ""


def _clean_env(package: Path) -> dict[str, str]:
    env = os.environ.copy()
    env.pop("PYTHONPATH", None)
    system_root = os.environ.get("SystemRoot", r"C:\Windows")
    env["PATH"] = os.pathsep.join([
        str(package),
        str(package / "_internal"),
        str(Path(system_root) / "System32"),
        str(Path(system_root)),
    ])
    for name in ("PYTHONHOME", "VIRTUAL_ENV", "UV_PROJECT_ENVIRONMENT"):
        env.pop(name, None)
    return env


def _run(command: list[str], cwd: Path, env: dict[str, str], timeout: int = 60) -> str:
    result = subprocess.run(
        command, cwd=cwd, env=env, capture_output=True, text=True,
        errors="replace", timeout=timeout,
    )
    if result.returncode != 0:
        raise AssertionError(
            f"command failed ({result.returncode}): "
            f"{(result.stdout + result.stderr)[-3000:]}"
        )
    return result.stdout + result.stderr


def validate_distribution(package: Path) -> None:
    required = (package / "MediaCrawler.exe", package / "browser_extension")
    missing = [str(path.relative_to(package)) for path in required if not path.exists()]
    if missing:
        raise AssertionError(f"missing executable entries: {', '.join(missing)}")
    forbidden = {
        ".env", "browser_data", "logs", "node_modules", "tests", ".git",
        ".github", "webui/src", "__pycache__",
    }
    bad = []
    for path in package.rglob("*"):
        relative = path.relative_to(package).as_posix()
        if any(part in forbidden for part in relative.split("/")) or "webui/src/" in relative:
            bad.append(relative)
    if bad:
        raise AssertionError(f"forbidden executable entries: {', '.join(bad[:20])}")


def run_runtime_smoke(exe: Path, package: Path, env: dict[str, str]) -> None:
    output = _run([str(exe), "--frozen-runtime-smoke"], package, env, timeout=90)
    if "frozen imports: PASS" not in output or "signing runtime: PASS" not in output:
        raise AssertionError(f"runtime smoke output incomplete: {output[-2000:]}")


def run_worker_protocol_smoke(exe: Path, package: Path, env: dict[str, str]) -> None:
    process = subprocess.Popen(
        [str(exe), "--aggregate-worker"], cwd=package, env=env,
        stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
        text=True, encoding="utf-8", errors="replace",
    )
    try:
        # A clean EOF is the protocol's normal graceful-stop signal. This
        # proves the frozen worker entrypoint can start, read stdin, and exit
        # without reaching a live platform or requiring credentials.
        stdout, stderr = process.communicate("", timeout=30)
    except subprocess.TimeoutExpired:
        process.kill()
        process.communicate()
        raise AssertionError("frozen aggregate worker protocol timed out")
    if process.returncode != 0:
        raise AssertionError(f"frozen aggregate worker exited: {stderr[-1000:]}")
    if stdout.strip():
        raise AssertionError(f"frozen aggregate worker wrote unexpected output: {stdout}")


def run_web_smoke(exe: Path, package: Path, env: dict[str, str]) -> None:
    process = subprocess.Popen(
        [str(exe), "--no-browser"], cwd=package, env=env,
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
    )
    base_url = "http://127.0.0.1:8080"
    try:
        deadline = time.monotonic() + 45
        health = None
        while time.monotonic() < deadline:
            status, body = _request(f"{base_url}/api/health")
            if status == 200:
                try:
                    payload = json.loads(body)
                except json.JSONDecodeError:
                    payload = None
                if isinstance(payload, dict) and payload.get("status") == "ok":
                    health = payload
                    break
            if process.poll() is not None:
                raise AssertionError("frozen backend exited before health became ready")
            time.sleep(0.5)
        if health is None:
            raise AssertionError("frozen backend did not pass /api/health")

        for path in ("/", "/accounts"):
            status, body = _request(f"{base_url}{path}")
            if status != 200 or 'id="root"' not in body:
                raise AssertionError(f"SPA route failed: {path}")
        status, body = _request(f"{base_url}/api/health")
        if status != 200 or "<html" in body.lower():
            raise AssertionError("/api/health was consumed by SPA fallback")
        assets = sorted((package / "_internal" / "webui" / "dist" / "assets").iterdir())
        asset = next(path for path in assets if path.is_file())
        relative = asset.relative_to(package / "_internal" / "webui" / "dist").as_posix()
        status, _ = _request(f"{base_url}/{relative}")
        if status != 200:
            raise AssertionError(f"asset failed: {relative}")
        for path in ("/assets/missing.js", "/api/not-found", "/%2e%2e/api/main.py"):
            status, body = _request(f"{base_url}{path}")
            if status != 404 or 'id="root"' in body:
                raise AssertionError(f"unsafe path was not rejected: {path}")
    finally:
        if process.poll() is None:
            process.terminate()
            try:
                process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=10)


def main() -> int:
    if sys.platform != "win32":
        raise SystemExit("EXE clean-room smoke must run on Windows")
    parser = argparse.ArgumentParser()
    parser.add_argument("--package", type=Path, required=True)
    args = parser.parse_args()
    package = args.package.resolve()
    exe = package / "MediaCrawler.exe"
    validate_distribution(package)
    env = _clean_env(package)
    run_runtime_smoke(exe, package, env)
    run_worker_protocol_smoke(exe, package, env)
    run_web_smoke(exe, package, env)
    print("executable clean-room validation: PASS")
    print("node/python-free runtime: PASS")
    print("worker protocol: PASS")
    print("web serving: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
