"""
分析清洗后分段的长度分布，为分块策略提供依据
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import json
from config import PROCESSED_DIR


def main():
    segments_file = PROCESSED_DIR / "npc_segments.json"
    with open(segments_file, "r", encoding="utf-8") as f:
        segs = json.load(f)

    lengths = [len(s["content"]) for s in segs]
    print(f"总段数: {len(segs)}")
    print(f"最短: {min(lengths)} 字")
    print(f"最长: {max(lengths)} 字")
    print(f"平均长度: {sum(lengths) / len(lengths):.1f} 字")
    print(f"中位数长度: {sorted(lengths)[len(lengths) // 2]} 字")

    print("\n长度分布:")
    for threshold in [50, 100, 200, 300, 400, 500, 600, 800, 1000, 1500, 2000]:
        count = sum(1 for L in lengths if L > threshold)
        print(f"  >{threshold:4d}字: {count:4d} 条")

    print("\n最长的 10 条:")
    for s in sorted(segs, key=lambda x: -len(x["content"]))[:10]:
        print(f"  {s['title']} {s['article_no']}: {len(s['content'])} 字")


if __name__ == "__main__":
    main()
