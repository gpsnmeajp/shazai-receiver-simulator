#!/usr/bin/env python3
"""ベンチマークの回答（観察者に渡した資料 eval/observers/batches/bench-*.json）を、
複数の観察の出どころで母集団に通し、平均所属度・非ファジィ化した評定の一致を比べる。
筆者の評定を使わない（runs/ がなくても動く）ので、観察者どうしの比較にとどまる。

  python3 tools/compare_bench_sources.py ref=eval/observers/obs-ensemble.json jev=eval/jev/obs-bench-jev.json \\
      --direct eval/jev/direct-bench.json -o eval/jev/bench-compare.md
最初の出どころを基準にする。
"""
import argparse
import glob
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import sim  # noqa: E402

CATS = sim.CATS
NAMES = {"rude": "失礼", "light": "足りない", "fit": "釣り合う", "heavy": "重すぎる"}


def kappa(a, b):
    n = len(a)
    po = sum(x == y for x, y in zip(a, b)) / n
    pe = sum((a.count(k) / n) * (b.count(k) / n) for k in CATS)
    return (po - pe) / (1 - pe) if pe < 1 else float("nan")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("sources", nargs="+", help="名前=観察JSON")
    ap.add_argument("--direct", help="tools/jev_direct.py の出力")
    ap.add_argument("--batches", default=str(ROOT / "eval/observers/batches/bench-*.json"))
    ap.add_argument("-n", type=int, default=500)
    ap.add_argument("-o", "--out", required=True)
    args = ap.parse_args()
    tl = {}
    for p in sorted(glob.glob(args.batches)):
        for g in json.loads(Path(p).read_text(encoding="utf-8"))["groups"]:
            for a in g["answers"]:
                tl[a["id"]] = (g["group"], len(a["text"]))
    panel = sim.sample_panel(sim.load_population(str(ROOT / "population.json")), args.n, 7)
    srcs = [(n, sim.load(p)) for n, p in (s.split("=", 1) for s in args.sources)]
    ids = sorted(set(tl).intersection(*[set(o["answers"]) for _, o in srcs]))
    mus = {}
    for name, o in srcs:
        sim.use_source(o.get("source"))
        mus[name] = {}
        for aid in ids:
            sid = tl[aid][0]
            sc = o["scenarios"].get(sid)
            if sc is None:
                continue
            a = sim.merged(sim.DEFAULT_ANSWER, o["answers"][aid])
            a["restraint"] = sim.restraint_of(a)
            mus[name][aid] = sim.assess(a, sim.merged(sim.DEFAULT_SCENARIO, sc), panel, tl[aid][1])["mu"]
    sim.use_source(None)
    if args.direct:
        d = sim.load(args.direct)
        mus["Jev 直接（Choice）"] = {aid: d[aid]["choice"] for aid in ids if aid in d}
    names = list(mus)
    ref = names[0]
    label = lambda m: max(CATS, key=lambda k: m[k])
    L = [f"# ベンチマークでの観察者どうしの比較（{len(ids)} 回答）", "",
         f"基準：{ref}。筆者の評定は使っていない。所属度関数は各観察の出どころの較正で通した（Jev は未較正）。", "",
         "| 出どころ | 失礼 | 足りない | 釣り合う | 重すぎる | 基準への近さ | 非ファジィ化の一致 | κ |", "|---|---|---|---|---|---|---|---|"]
    for n in names:
        common = [a for a in ids if a in mus[n] and a in mus[ref]]
        m = {k: sum(mus[n][a][k] for a in common) / len(common) for k in CATS}
        cl = sum(sim.closeness(mus[n][a], mus[ref][a]) for a in common) / len(common)
        la, lb = [label(mus[n][a]) for a in common], [label(mus[ref][a]) for a in common]
        L.append(f"| {n} | {m['rude']:.2f} | {m['light']:.2f} | {m['fit']:.2f} | {m['heavy']:.2f} | {cl:.3f} | "
                 f"{sum(x == y for x, y in zip(la, lb))}/{len(common)} | {kappa(la, lb):.2f} |")
    for n in names[1:]:
        common = [a for a in ids if a in mus[n] and a in mus[ref]]
        L += ["", f"### 混同行列（行＝{ref}、列＝{n}）", "", "| | " + " | ".join(NAMES[k] for k in CATS) + " |",
              "|---|" + "---|" * len(CATS)]
        for r in CATS:
            row = [sum(1 for a in common if label(mus[ref][a]) == r and label(mus[n][a]) == c) for c in CATS]
            L.append(f"| {NAMES[r]} | " + " | ".join(map(str, row)) + " |")
    md = "\n".join(L) + "\n"
    Path(args.out).write_text(md, encoding="utf-8")
    print(md)


if __name__ == "__main__":
    main()
