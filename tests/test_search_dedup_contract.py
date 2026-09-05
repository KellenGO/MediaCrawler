"""The UI and API run the same public fixtures to prevent grouping drift."""

import json
from pathlib import Path

import pytest

from aggregate_search.models import UnifiedSearchResult, deduplicate_cross_platform_results


CASES = json.loads((Path(__file__).parent / "fixtures" / "search_dedup_cases.json").read_text(encoding="utf-8"))


@pytest.mark.parametrize("case", CASES, ids=lambda case: case["id"])
def test_shared_grouping_contract(case):
    results = [UnifiedSearchResult(url="https://example.test", **item) for item in case["results"]]
    grouped = deduplicate_cross_platform_results(results)
    actual = sorted(sorted(f"{source.platform}:{source.content_id}" for source in (item.grouped_sources or [item]))
                    for item in grouped)
    assert actual == sorted(sorted(group) for group in case["groups"])
    if "representatives" in case:
        assert [f"{item.platform}:{item.content_id}" for item in grouped] == case["representatives"]
