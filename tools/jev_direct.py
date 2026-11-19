#!/usr/bin/env python3
"""比較用：Jev に評定そのものを直接問う方式（JEV_DESIGN.md 7章の jev-direct。P1 を破る方式）。

1回答につき、4値の Choice（失礼／足りない／釣り合う／重すぎる）と、述語ごとの Noul（当てはまる確率）を問う。
出力は {回答ID: {"choice": {...}, "noul": {...}}}。母集団は通さない。

  python3 tools/jev_direct.py eval/observers/batches/scenes-*.json --cache eval/jev/cache -o eval/jev/direct-scenes.json
"""
import argparse
import json
import os
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import s1  # noqa: E402

LABELS = {
    "rude": "失礼：受け手が無礼だと感じる（弁解、相手への指摘、他人事、軽さ、要求の無視など）",
    "light": "足りない：失礼ではないが、謝罪や対応の中身が、受け手が必要とする深さに届かない",
    "fit": "釣り合う：失礼でも、足りなくも、重すぎもしない",
    "heavy": "重すぎる：失敗の大きさに比べて、詫びや自己卑下が過剰で、受け手が負担に感じる",
}
NOUL = {k: v.split("：", 1)[1] for k, v in LABELS.items()}
CTX = "日本語の会話で、`conversation` の最後のユーザーが、`answer` を受け取ったときの受け止め方として、"


def questions(order):
    q = {"direct": s1.choice(CTX + "最も当てはまるものはどれですか。", {k: LABELS[k] for k in order})}
    for k, desc in NOUL.items():
        q[f"is.{k}"] = s1.noul(CTX + f"「{desc}」は当てはまりますか。")
    return q


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("batches", nargs="+")
    ap.add_argument("--model", default=s1.DEFAULT_JEV_OR_MODEL)
    ap.add_argument("--cache", required=True)
    ap.add_argument("-o", "--out", required=True)
    args = ap.parse_args()
    key = os.environ.get("OPENROUTER_API_KEY")
    todo = []
    for p in args.batches:
        for g in json.loads(Path(p).read_text(encoding="utf-8"))["groups"]:
            conv = [{"role": m["role"], "text": m["content"][:800]} for m in g["conversation"]]
            for a in g["answers"]:
                todo.append((a["id"], {"conversation": conv, "answer": a["text"][:2000]}))

    def run(it):
        aid, state = it
        out = {}
        # Choice の順序の偏り（先頭に寄る）を、順序を逆にした2回の平均で抑える
        for order in (list(LABELS), list(LABELS)[::-1]):
            q = questions(order)
            ans, used, _, _ = s1.ask(state, q, "jev-or", args.model, {"jev-or": key}, 60, args.cache)
            for k, v in ans["direct"]["probabilities"].items():
                out.setdefault("choice", {}).setdefault(k, []).append(v)
            out["noul"] = {k: ans[f"is.{k}"]["noul"] for k in NOUL}
            out["model"] = used
        out["choice"] = {k: sum(v) / len(v) for k, v in out["choice"].items()}
        return aid, out

    with ThreadPoolExecutor(max_workers=6) as ex:
        res = dict(ex.map(run, todo))
    Path(args.out).write_text(json.dumps(res, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"{len(res)} 回答 → {args.out}", file=sys.stderr)


if __name__ == "__main__":
    main()
