#!/usr/bin/env python3
"""観察者に渡した資料（eval/v09-observers/batches/*.json）を、System One 経路（s1.py）で一括観察する。

1回答1リクエスト（sim.py check と同じ質問の組）。場面の観察は、その場面の回答ごとに同じ質問を問うので、
回答の数だけ繰り返し測ったことになる。観察JSONの scenarios には先頭の回答のものを入れ、
回答ごとの場面の観察は `_scene_per_answer` に残す（場面の欄の揺れを測るため）。

  python3 tools/observe_s1_batches.py eval/v09-observers/batches/bench-*.json --backend jev-or \\
      --cache eval/jev/cache -o eval/jev/obs-bench-jev.json
  python3 tools/observe_s1_batches.py ... --backend replay-dir --replay-dir eval/s1-answers  # 保存した答えで組み立て直す

標準ライブラリのみ。
"""
import argparse
import json
import os
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import s1  # noqa: E402


def items(paths):
    for p in paths:
        for g in json.loads(Path(p).read_text(encoding="utf-8"))["groups"]:
            msgs = [{"role": m["role"], "content": m["content"]} for m in g["conversation"]]
            for a in g["answers"]:
                yield g["group"], a["id"], msgs, a["text"]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("batches", nargs="+")
    ap.add_argument("--backend", default="jev-or", choices=["jev", "jev-or", "llm-s1", "replay"])
    ap.add_argument("--model")
    ap.add_argument("--cache", help="答えの保存先（質問のハッシュで引く。再実行で再利用）")
    ap.add_argument("--replay-dir", help="--backend replay のとき、<回答ID の / を __ にした名前>.json を読む")
    ap.add_argument("--only", help="この回答IDだけ（カンマ区切り）")
    ap.add_argument("--workers", type=int, default=6)
    ap.add_argument("--timeout", type=float, default=90.0)
    ap.add_argument("--no-context", action="store_true", help="過失の明白さ・親しさを問わない")
    ap.add_argument("--calibration", help="欄ごとの再較正の表（tools/calibrate_s1.py の出力）")
    ap.add_argument("--source", help="観察JSONの source（既定 s1:<backend>:<答えた版>）")
    ap.add_argument("-o", "--out", required=True)
    args = ap.parse_args()

    s1.load_calibration(args.calibration)
    keys = {"jev": os.environ.get("TYPESAFE_API_KEY"), "jev-or": os.environ.get("OPENROUTER_API_KEY"),
            "llm-s1": os.environ.get("OPENROUTER_API_KEY")}
    only = set(args.only.split(",")) if args.only else None
    todo = [it for it in items(args.batches) if not only or it[1] in only]

    def run(it):
        sid, aid, msgs, text = it
        replay = None
        if args.backend == "replay":
            replay = str(Path(args.replay_dir) / (aid.replace("/", "__") + ".json"))
            if not Path(replay).exists():
                return it, None, None, None, "答えなし"
        last = None
        for _ in range(4):
            try:
                sc, a, meta = s1.observe_turn(msgs, text, args.backend, args.model, keys, args.timeout,
                                              args.cache, replay, ask_context=not args.no_context)
                return it, sc, a, meta, None
            except s1.S1Error as e:
                last = str(e)
        return it, None, None, None, last

    obs = {"source": None, "scenarios": {}, "answers": {}, "unsure": {}, "_scene_per_answer": {},
           "_meta": {"backend": args.backend, "models": {}, "n_questions": 0, "latency_ms": [], "cost": 0.0, "errors": {}}}
    order = {it[1]: i for i, it in enumerate(todo)}
    results = []
    with ThreadPoolExecutor(max_workers=args.workers) as ex:
        futs = [ex.submit(run, it) for it in todo]
        for k, f in enumerate(as_completed(futs), 1):
            it, sc, a, meta, err = f.result()
            if err:
                obs["_meta"]["errors"][it[1]] = err
                print(f"[{k}/{len(todo)}] {it[1]}: {err}", file=sys.stderr)
                continue
            results.append((order[it[1]], it, sc, a, meta))
            if k % 20 == 0:
                print(f"[{k}/{len(todo)}]", file=sys.stderr)
    results.sort(key=lambda r: r[0])
    for _, (sid, aid, _m, _t), sc, a, meta in results:
        obs["scenarios"].setdefault(sid, sc)
        obs["_scene_per_answer"].setdefault(sid, {})[aid] = sc
        obs["answers"][aid] = a
        if meta["unsure"]:
            obs["unsure"][aid] = meta["unsure"]
        m = obs["_meta"]
        m["models"][meta["model"]] = m["models"].get(meta["model"], 0) + 1
        m["n_questions"] += meta["n_questions"]
        m["latency_ms"].append(meta["latency_ms"])
        m["cost"] += float((meta["usage"] or {}).get("cost", 0) or 0)
    used = max(obs["_meta"]["models"], key=obs["_meta"]["models"].get) if obs["_meta"]["models"] else "?"
    obs["source"] = args.source or f"s1:{args.backend}:{used}" + (":calibrated" if args.calibration else "")
    obs["_meta"]["calibration"] = args.calibration
    lat = sorted(obs["_meta"]["latency_ms"]) or [0]
    obs["_meta"]["latency_ms"] = {"median": lat[len(lat) // 2], "max": lat[-1], "n": len(lat)}
    Path(args.out).parent.mkdir(parents=True, exist_ok=True)
    Path(args.out).write_text(json.dumps(obs, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"{len(obs['answers'])} 回答、{obs['_meta']['n_questions']} 問、誤り {len(obs['_meta']['errors'])}、"
          f"費用 ${obs['_meta']['cost']:.4f}、応答の中央値 {lat[len(lat) // 2]}ms → {args.out}", file=sys.stderr)


if __name__ == "__main__":
    main()
