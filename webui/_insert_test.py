"""一次性脚本：向 libraryApi.test.ts 插入 parseGroupKey 测试（跑完即删）。"""

def main():
    import io

    path = "tests/libraryApi.test.ts"
    src = io.open(path, encoding="utf-8").read()

    src = src.replace(
        'import { MAX_BACKUP_BYTES, publicResult } from "../src/lib/bookmarks.js";',
        'import { MAX_BACKUP_BYTES } from "../src/lib/bookmarks.js";',
    )

    addition = """// ── groupKey 还原（批量加入/移出收藏夹的关键路径） ─────────────────────

    test("parseGroupKey：把结果列表的分组勾选还原成收藏库的单条 key", () => {
      jsonEqual(parseGroupKey('["xhs|n1"]'), ["xhs|n1"]);
      jsonEqual(parseGroupKey('["xhs|n1","bilibili|b1"]'), ["xhs|n1", "bilibili|b1"]);
      jsonEqual(parseGroupKey('["bilibili|BV1|extra"]'), ["bilibili|BV1|extra"]);
    });

    test("parseGroupKey：垃圾输入返回空数组（调用方据此提示而不是发坏请求）", () => {
      jsonEqual(parseGroupKey("不是 JSON"), []);
      jsonEqual(parseGroupKey(JSON.stringify({ not: "array" })), []);
      jsonEqual(parseGroupKey(JSON.stringify([1, null, "xhs|ok"])), ["xhs|ok"]);
      jsonEqual(parseGroupKey('["no-separator"]'), []);
    });

    """

    lines = src.splitlines(keepends=True)
    idx = next((i for i, line in enumerate(lines) if line.startswith("// ── key 解析")), None)
    if idx is None:
        raise SystemExit("marker not found")
    if "parseGroupKey：" in src:
        print("already inserted; skip")
    else:
        lines.insert(idx, addition)
        io.open(path, "w", encoding="utf-8").write("".join(lines))
        print("inserted at line", idx + 1)


if __name__ == "__main__":
    main()
