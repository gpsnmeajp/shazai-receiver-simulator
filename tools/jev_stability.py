#!/usr/bin/env python3
"""Jev の答えの安定性：(1) 同じ問いを2回聞いたときの再現性（旧いキャッシュとの比較）、
(2) 場面の欄が、同じ会話で回答だけが違うときに揺れるか、(3) 直接評定の Choice の選択肢の順序の偏り。

  python3 tools/jev_stability.py --old-cache eval/jev/cache-run1 --cache eval/jev/cache -o eval/jev/stability.md
"""
import argparse
import glob
import json
import statistics
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tools"))
import jev_direct as J  # noqa: E402
import s1  # noqa: E402

BATCHES = {"bench": "eval/v09-observers/batches/bench-*.json", "scenes": "eval/v09-observers/batches/scenes-*.json"}


def groups(name):
    for p in sorted(glob.glob(str(ROOT / BATCHES[name]))):
        yield from json.loads(Path(p).read_text(encoding="utf-8"))["groups"]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--old-cache", required=True)
    ap.add_argument("--cache", required=True)
    ap.add_argument("-o", "--out", required=True)
    args = ap.parse_args()
    model = s1.DEFAULT_JEV_OR_MODEL
    L = ["# Jev の答えの安定性", ""]
    # (1) 再テスト
    L += ["## 同じ問いを2回聞いたとき（2回目は数分後）", "",
          "| 資料 | 問い | 完全に同じ答え | Noul の差の平均 | Noul の差の最大 | 0.5 をまたいだ Noul | Choice・Score の最頻が変わった |",
          "|---|---|---|---|---|---|---|"]
    for name in BATCHES:
        same = tot = flips = top = nn = 0
        diffs = []
        for g in groups(name):
            msgs = [{"role": m["role"], "content": m["content"]} for m in g["conversation"]]
            for a in g["answers"]:
                state, own = s1.build_state(msgs, a["text"])
                q = s1.build_questions(state, s1.surface(msgs, own))
                f_old = Path(args.old_cache) / f"{s1.request_hash_v1(state, q, model)}.json"
                f_new = Path(args.cache) / f"{s1.request_hash(state, q, model)}.json"
                if not (f_old.exists() and f_new.exists()):
                    continue
                A = json.loads(f_old.read_text())["answers"]
                B = json.loads(f_new.read_text())["answers"]
                for k in q:
                    x, y = A.get(k), B.get(k)
                    if not x or not y:
                        continue
                    tot += 1
                    same += json.dumps(x, sort_keys=True) == json.dumps(y, sort_keys=True)
                    if x["type"] == "noul":
                        nn += 1
                        d = abs(x["noul"] - y["noul"])
                        diffs.append(d)
                        flips += (x["noul"] >= 0.5) != (y["noul"] >= 0.5)
                    else:
                        px, py = x["probabilities"], y["probabilities"]
                        top += max(px, key=px.get) != max(py, key=py.get)
        if tot:
            L.append(f"| {name} | {tot} | {same / tot:.3f} | {statistics.mean(diffs):.4f} | {max(diffs):.3f} | "
                     f"{flips}（{flips / nn:.4f}） | {top} |")
    # (2) 場面の欄の揺れ
    F = ["distance_shift", "explicit_complaint", "prior_corrections", "prior_ai_apologies", "broken_promises", "harm",
         "violation_type", "apology_accepted_before", "ai_unrequested_push"]
    L += ["", "## 場面の欄：同じ会話で、state の回答だけが違うとき", "",
          "場面の質問は回答ごとに同じものを問う。回答によらず同じ値になった場面の割合（較正つきの観察）。", "",
          "| 欄 | " + " | ".join(BATCHES) + " |", "|---|" + "---|" * len(BATCHES)]
    cells = {f: [] for f in F}
    for name in BATCHES:
        o = json.loads((ROOT / f"eval/jev/obs-{name}-jev-cal.json").read_text())
        for f in F:
            ok = n = 0
            for per in o["_scene_per_answer"].values():
                if len(per) < 2:
                    continue
                n += 1
                ok += len({json.dumps(v.get(f)) for v in per.values()}) == 1
            cells[f].append(f"{ok}/{n}")
    for f in F:
        L.append(f"| {f} | " + " | ".join(cells[f]) + " |")
    # (3) 順序の偏り
    L += ["", "## 直接評定の Choice：選択肢の順序を逆にしたとき", "",
          "| 資料 | 件数 | 分布の全変動距離の平均 | 最大 | 最頻が変わった | 先頭に置いた選択肢の確率の上乗せ（平均） |", "|---|---|---|---|---|---|"]
    for name in BATCHES:
        tv, bias, flip = [], [], 0
        for g in groups(name):
            conv = [{"role": m["role"], "text": m["content"][:800]} for m in g["conversation"]]
            for a in g["answers"]:
                st = {"conversation": conv, "answer": a["text"][:2000]}
                ps = []
                for order in (list(J.LABELS), list(J.LABELS)[::-1]):
                    f = Path(args.cache) / f"{s1.request_hash(st, J.questions(order), model)}.json"
                    if not f.exists():
                        break
                    ps.append((order, json.loads(f.read_text())["answers"]["direct"]["probabilities"]))
                if len(ps) < 2:
                    continue
                (o1, p1), (o2, p2) = ps
                tv.append(sum(abs(p1[k] - p2[k]) for k in p1) / 2)
                bias.append(((p1[o1[0]] - p2[o1[0]]) + (p2[o2[0]] - p1[o2[0]])) / 2)
                flip += max(p1, key=p1.get) != max(p2, key=p2.get)
        if tv:
            L.append(f"| {name} | {len(tv)} | {statistics.mean(tv):.3f} | {max(tv):.3f} | {flip} | {statistics.mean(bias):+.3f} |")
    md = "\n".join(L) + "\n"
    Path(args.out).write_text(md, encoding="utf-8")
    print(md)


if __name__ == "__main__":
    main()
