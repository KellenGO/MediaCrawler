import { test } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { deduplicateCrossPlatformResults, mergeSinglePlatformRetry } from "../src/lib/searchExperience.js";
import type { UnifiedSearchResult } from "../src/types/search.js";

interface DedupCase {
  id: string;
  results: Array<Partial<UnifiedSearchResult> & Pick<UnifiedSearchResult, "platform" | "content_id" | "title">>;
  groups: string[][];
  representatives?: string[];
}

// npm run test:search executes this file from webui/.test-dist/tests/.
const cases: DedupCase[] = JSON.parse(readFileSync(
  new URL("../../../tests/fixtures/search_dedup_cases.json", import.meta.url), "utf8"
));

function groups(results: UnifiedSearchResult[]): string[][] {
  return results.map((result) => (result.grouped_sources || [result])
    .map((source) => `${source.platform}:${source.content_id}`).sort()).sort();
}

for (const fixture of cases) {
  test(`shared grouping contract: ${fixture.id}`, () => {
    const results: UnifiedSearchResult[] = fixture.results.map((item) => ({
      content_type: "note", author: null, snippet: null, published_at: null,
      url: "https://example.test", cover_url: null, metrics: {}, rank: 0, ...item,
    }));
    const expected = fixture.groups.map((group) => [...group].sort()).sort();
    const grouped = deduplicateCrossPlatformResults(results);
    assert.deepEqual(groups(grouped), expected);
    if (fixture.representatives) {
      assert.deepEqual(grouped.map((item) => `${item.platform}:${item.content_id}`), fixture.representatives);
    }
    const platforms = [...new Set(results.map((item) => item.platform))];
    for (const platform of platforms) {
      const replay = JSON.parse(JSON.stringify(grouped)) as UnifiedSearchResult[];
      const retried = mergeSinglePlatformRetry(replay, platform,
        results.filter((item) => item.platform === platform), platforms);
      assert.deepEqual(groups(retried), expected, `retry ${platform}`);
    }
  });
}
