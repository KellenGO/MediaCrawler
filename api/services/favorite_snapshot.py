"""Public result metadata encoded in the existing JSON column (legacy-compatible)."""

import json

METRIC_NAMES = ("like_count", "view_count", "collect_count", "comment_count", "share_count", "coin_count", "danmaku_count")


def encode_metrics(result: dict) -> str:
    counts = result.get("metrics")
    counts = counts if isinstance(counts, dict) else {}
    metadata = {
        "collection_names": result.get("collection_names", []),
        "metrics_status": result.get("metrics_status"),
        "metrics_updated_at": result.get("metrics_updated_at"),
        "metrics_approximate": result.get("metrics_approximate", []),
    }
    return json.dumps({"counts": counts, "metadata": metadata}, ensure_ascii=False)


def decode_metrics(raw: str) -> dict:
    try:
        payload = json.loads(raw or "{}")
    except (ValueError, TypeError):
        payload = {}
    if not isinstance(payload, dict):
        payload = {}
    # Old releases stored only a flat dictionary of counts.
    metadata = payload.get("metadata", {}) if isinstance(payload.get("counts"), dict) else {}
    counts = payload.get("counts", payload)
    metadata = metadata if isinstance(metadata, dict) else {}
    status = metadata.get("metrics_status")
    names = metadata.get("collection_names")
    approximate = metadata.get("metrics_approximate")
    return {
        "metrics": counts,
        "metrics_status": status if status in ("pending", "complete", "partial", "unavailable", "failed") else None,
        "metrics_updated_at": metadata.get("metrics_updated_at") if isinstance(metadata.get("metrics_updated_at"), (float, int)) else None,
        "metrics_approximate": [name for name in approximate if name in METRIC_NAMES] if isinstance(approximate, list) else [],
        "collection_names": [name for name in names if isinstance(name, str)][:20] if isinstance(names, list) else [],
    }
