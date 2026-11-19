#!/usr/bin/env python3
"""互換の判定器（サブエージェント等）が書き出した答え {質問ID: 答え} を、Jev の答えと同じ形にそろえ、
--backend replay で読める形（<回答IDの / を __ にした名前>.json）で保存する。

  python3 tools/import_llm_s1_answers.py <in_dir> <out_dir> <dest_dir>
  in_dir: NN.json（{"id", "state", "questions"}）、out_dir: NN.json（答え）
"""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import s1  # noqa: E402


def main():
    src, ans, dest = map(Path, sys.argv[1:4])
    dest.mkdir(parents=True, exist_ok=True)
    rows = []
    for f in sorted(src.glob("*.json")):
        item = json.loads(f.read_text(encoding="utf-8"))
        g = ans / f.name
        if not g.exists():
            rows.append((f.name, item["id"], len(item["questions"]), 0))
            continue
        raw = json.loads(g.read_text(encoding="utf-8"))
        got = sum(1 for q in item["questions"] if q in raw)
        norm = s1.normalize_llm_answers(raw, item["questions"])
        (dest / (item["id"].replace("/", "__") + ".json")).write_text(
            json.dumps({"answers": norm}, ensure_ascii=False), encoding="utf-8")
        rows.append((f.name, item["id"], len(item["questions"]), got))
    miss = [r for r in rows if r[3] < r[2]]
    print(f"{len(rows)} 件、問い {sum(r[2] for r in rows)}、答え {sum(r[3] for r in rows)}、欠けのある件 {len(miss)}")
    for r in miss:
        print("  欠け:", r)


if __name__ == "__main__":
    main()
