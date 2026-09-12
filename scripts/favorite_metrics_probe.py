"""Read one favourite per selected platform; print counters and safe status only.

Uses existing login profiles. Does not change remote collections or print tokens.
Run: .venv/Scripts/python.exe scripts/favorite_metrics_probe.py xhs bilibili zhihu
"""
import json
import os
from pathlib import Path
import subprocess
import sys


def main():
    root = Path(__file__).resolve().parents[1]
    platforms = sys.argv[1:] or ["xhs", "bilibili", "zhihu"]
    for platform in platforms:
        if platform not in ("xhs", "bilibili", "zhihu", "douyin"):
            raise SystemExit("Unknown platform")
        request = {"job_id": "favorite-metrics-probe", "mode": "favorites", "platform": platform, "limit": 1}
        try:
            proc = subprocess.run(
                [sys.executable, str(root / "aggregate_search" / "worker.py")], cwd=root,
                input=json.dumps(request) + "\n", capture_output=True, text=True, encoding="utf-8",
                errors="replace", timeout=195,
                env={**os.environ, "PYTHONUTF8": "1", "PYTHONIOENCODING": "utf-8"})
        except subprocess.TimeoutExpired:
            print(json.dumps({"platform": platform, "status": "probe_timeout"}), flush=True)
            continue
        rows = {}
        status = "no_events"
        for line in proc.stdout.splitlines():
            if not line.startswith("MC_AGG_EVENT\t"):
                continue
            try:
                event = json.loads(line.split("\t", 1)[1])
            except ValueError:
                continue
            data = event.get("data") or {}
            if event.get("event") == "result":
                rows[data.get("content_id")] = {
                    "metrics": data.get("metrics"), "metrics_status": data.get("metrics_status"),
                    "approximate": data.get("metrics_approximate", [])}
            elif event.get("event") == "status":
                status = data.get("status")
            elif event.get("event") == "error":
                status = data.get("type")
        print(json.dumps({"platform": platform, "status": status, "rows": list(rows.values())},
                         ensure_ascii=False), flush=True)


if __name__ == "__main__":
    main()
