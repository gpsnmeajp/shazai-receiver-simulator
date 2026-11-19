#!/usr/bin/env python3
"""System One の答え（Noul の確率）を、欄ごとの閾値で再較正する表を作る（JEV_DESIGN.md 5.6節）。

参照の観察（銀ラベル。既定は観察者の集団 eval/observers/obs-ensemble.json）を正解とみなし、
回答単位で「その族の確率の最大（文ごとの問いは文の最大）」と参照の真偽を突き合わせ、
一致率が最大になる閾値 t を族ごとに選ぶ。場面単位の一つ抜き交差検証で、選び方そのものの一致率も出す。

  python3 tools/calibrate_s1.py eval/observers/batches/bench-*.json --cache eval/jev/cache \\
      -o eval/jev/jev_calibration.json --report eval/jev/calibration.md

正例が少ない族（既定 5 件未満）は、閾値を上限（0.95）に置く。標準ライブラリのみ。
"""
import argparse
import json
import sys
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import s1  # noqa: E402

# 族 → 参照の観察の欄（真偽に直す）
TARGETS = {
    "s.apology": "apology.present",
    "s.excuse": "defense.excuse",
    "s.blame": "defense.blame_or_hint_at_user",
    "s.conditional": "defense.conditional_apology",
    "s.explain": "defense.explanation",
    "s.forgive": "excess.request_forgiveness",
    "s.self_dep": "excess.self_deprecation",
    "s.promise": "excess.promises",
    "s.resolution": "closure.declares_resolution",
    "s.proposal": "repair.unrequested_proposals",
    "ans.moves_on": "closure.moves_on_quickly",
    "ans.new_errors": "repair.new_errors",
    "ans.prompted": "apology.prompted",
    "ans.thanks": "apology.thanks_instead",
    "s.read": "sentences.max_plausibility",
}
# 族 → 参照の観察の場面の欄（会話の履歴への問い。場面の値が正なら真）
SCENE_TARGETS = {
    "a.apology": "prior_ai_apologies",
    "u.corrects": "prior_corrections",
    "u.repeat": "broken_promises",
    "sc.push": "ai_unrequested_push",
    "sc.accepted": "apology_accepted_before",
}
GRID = [x / 100 for x in range(5, 96)]


def num(x):
    if isinstance(x, bool):
        return float(x)
    if isinstance(x, dict):
        return float(x.get("true", 0))
    try:
        return float(x)
    except (TypeError, ValueError):
        return 0.0


def ref_value(a, path):
    if path == "sentences.max_plausibility":
        return max([num(s.get("plausibility", 0)) for s in a.get("sentences", [])] or [0])
    x = a
    for k in path.split("."):
        x = x.get(k) if isinstance(x, dict) else None
    return num(x) if x is not None else 0.0


def collect(batches, backend, model, cache, ref):
    rows = []  # (場面, 族, Jev の最大確率, 参照の真偽)
    for p in batches:
        for g in json.loads(Path(p).read_text(encoding="utf-8"))["groups"]:
            msgs = [{"role": m["role"], "content": m["content"]} for m in g["conversation"]]
            for a in g["answers"]:
                if a["id"] not in ref["answers"]:
                    continue
                _, _, meta = s1.observe_turn(msgs, a["text"], backend, model, {}, 60, cache)
                fam_max = defaultdict(float)
                for qid, v in meta["answers"].items():
                    if v.get("type") == "noul":
                        f = s1.qfamily(qid)
                        fam_max[f] = max(fam_max[f], float(v["noul"]))
                for f, path in TARGETS.items():
                    if f in fam_max:
                        rows.append((g["group"], f, fam_max[f], ref_value(ref["answers"][a["id"]], path) >= 0.5))
                rsc = ref.get("scenarios", {}).get(g["group"])
                if rsc:
                    for f, key in SCENE_TARGETS.items():
                        if f in fam_max:
                            rows.append((g["group"], f, fam_max[f], num(rsc.get(key, 0)) >= 0.5))
    return rows


def best_t(ps, min_pos):
    if sum(l for _, l in ps) < min_pos:
        return 0.95
    return max(GRID, key=lambda t: (sum((p >= t) == l for p, l in ps), -abs(t - 0.5)))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("batches", nargs="+")
    ap.add_argument("--ref", default=str(ROOT / "eval" / "observers" / "obs-ensemble.json"))
    ap.add_argument("--backend", default="jev-or")
    ap.add_argument("--model")
    ap.add_argument("--cache", required=True, help="答えのキャッシュ（新たな問い合わせはしない前提）")
    ap.add_argument("--min-pos", type=int, default=5)
    ap.add_argument("-o", "--out", required=True)
    ap.add_argument("--report")
    args = ap.parse_args()
    ref = json.loads(Path(args.ref).read_text(encoding="utf-8"))
    rows = collect(args.batches, args.backend, args.model, args.cache, ref)
    by_f = defaultdict(list)
    for sid, f, p, l in rows:
        by_f[f].append((sid, p, l))
    table, L = {}, ["| 族 | 件数 | 参照で真 | 閾値 t | 0.5 での一致率 | t での一致率（学習） | 一つ抜き交差検証の一致率 |",
                    "|---|---|---|---|---|---|---|"]
    for f in list(TARGETS) + list(SCENE_TARGETS):
        xs = by_f.get(f)
        if not xs:
            continue
        ps = [(p, l) for _, p, l in xs]
        t = best_t(ps, args.min_pos)
        table[f] = t
        acc = lambda t_, d: sum((p >= t_) == l for p, l in d) / len(d)
        cv_ok = 0
        for sid in sorted({s for s, _, _ in xs}):
            train = [(p, l) for s, p, l in xs if s != sid]
            test = [(p, l) for s, p, l in xs if s == sid]
            tt = best_t(train, args.min_pos)
            cv_ok += sum((p >= tt) == l for p, l in test)
        L.append(f"| {f} | {len(ps)} | {sum(l for _, l in ps)} | {t:.2f} | {acc(0.5, ps):.2f} | {acc(t, ps):.2f} | {cv_ok / len(ps):.2f} |")
    out = {"_note": "logit(p') = logit(p) − logit(t)。t は参照の観察（" + Path(args.ref).name + "）との一致率が最大になる閾値。"
                    "tools/calibrate_s1.py で作成。版を上げたら作り直す",
           "model": sorted({m for m in [args.model or s1.DEFAULT_JEV_OR_MODEL]}),
           "noul_threshold": table}
    Path(args.out).write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")
    md = "\n".join(L) + "\n"
    if args.report:
        Path(args.report).write_text(md, encoding="utf-8")
    print(md)


if __name__ == "__main__":
    main()
