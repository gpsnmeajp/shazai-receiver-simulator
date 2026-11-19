#!/usr/bin/env python3
"""作例（examples/scenes-kit.json）の回答を、複数の観察の出どころ（手の観察・LLM・Jev など）で母集団に通し、
4つの述語の平均所属度、不満の深さ、無礼さ・不足・過剰の量、主な失点を出どころごとに並べる。

  python3 tools/compare_scene_sources.py hand jev=eval/jev/obs-scenes-jev.json sub=eval/observers/obs-scenes-opus.json
  （hand は手の観察。名前=ファイル で観察JSONを足す。名前=ファイル@較正区分 で所属度関数の較正を指定）
"""
import argparse
import json
import sys
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import sim  # noqa: E402

CATS = sim.CATS


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("sources", nargs="+")
    ap.add_argument("--scenes", default=str(ROOT / "examples" / "scenes-kit.json"))
    ap.add_argument("-n", type=int, default=300)
    ap.add_argument("--by", default="family", choices=["family", "scene", "answer"])
    ap.add_argument("--json", help="回答ごとの結果を書き出す")
    args = ap.parse_args()
    data = sim.load(args.scenes)
    pop = sim.load_population(str(ROOT / "population.json"))
    panel = sim.sample_panel(pop, args.n, 7)
    srcs = []
    for s in args.sources:
        if s == "hand":
            srcs.append(("hand", None, None))
            continue
        name, path = s.split("=", 1)
        calib = None
        if "@" in path:
            path, calib = path.split("@", 1)
        o = sim.load(path)
        srcs.append((name, o, calib if calib is not None else o.get("source")))
    ids = None
    for _, o, _ in srcs:
        if o is not None:
            got = set(o["answers"])
            ids = got if ids is None else ids & got
    res = defaultdict(dict)
    for name, o, calib in srcs:
        sim.use_source(calib if o is not None else None)
        for scene in data["scenes"]:
            for ans in scene["answers"]:
                aid = f"{scene['id']}/{ans['id']}"
                if ids is not None and aid not in ids:
                    continue
                if o is None:
                    sc, a = scene["scenario"], ans["obs"]
                else:
                    if scene["id"] not in o["scenarios"]:
                        continue
                    sc, a = o["scenarios"][scene["id"]], o["answers"][aid]
                sc = sim.merged(sim.DEFAULT_SCENARIO, sc)
                a = sim.merged(sim.DEFAULT_ANSWER, a)
                a["restraint"] = sim.restraint_of(a)
                r = sim.assess(a, sc, panel, len(ans.get("text", "")))
                res[aid][name] = r
    sim.use_source(None)
    names = [n for n, _, _ in srcs]

    def key(aid):
        sid = aid.split("/")[0]
        return {"family": sid.split("-")[0], "scene": sid, "answer": aid}[args.by]

    groups = defaultdict(list)
    for aid in res:
        groups[key(aid)].append(aid)
    print(f"{len(res)} 回答。値は平均所属度（失礼/足りない/重すぎる/釣り合う）、不満の深さ、無礼さ・不足・過剰\n")
    print("| 区分 | 件数 | " + " | ".join(names) + " |")
    print("|---|---|" + "---|" * len(names))
    for g in sorted(groups):
        cells = []
        for n in names:
            rs = [res[a][n] for a in groups[g] if n in res[a]]
            mu = {k: sum(r["mu"][k] for r in rs) / len(rs) for k in CATS}
            lv = sum(r["perceived_mean"] for r in rs) / len(rs)
            ax = {k: sum(r["axes"][k] for r in rs) / len(rs) for k in ("offense", "under", "over")}
            cells.append(f"{mu['rude']:.2f}/{mu['light']:.2f}/{mu['heavy']:.2f}/{mu['fit']:.2f} 深{lv:.1f} "
                         f"無{ax['offense']:.1f}不{ax['under']:.1f}過{ax['over']:.1f}")
        print(f"| {g} | {len(groups[g])} | " + " | ".join(cells) + " |")
    print("\n主な失点（全回答の平均）\n")
    for n in names:
        c = Counter()
        for a in res:
            c.update(res[a][n]["mean_faults"])
        tot = len(res)
        print(f"- {n}: " + "、".join(f"{k} {v / tot:.2f}" for k, v in c.most_common(8)))
    if args.json:
        Path(args.json).write_text(json.dumps({a: {n: {"mu": r["mu"], "axes": r["axes"], "perceived": r["perceived_mean"],
                                                         "faults": r["mean_faults"]} for n, r in d.items()}
                                               for a, d in res.items()}, ensure_ascii=False, indent=1), encoding="utf-8")


if __name__ == "__main__":
    main()
