#!/usr/bin/env python3
"""作例で、Jev に直接評定させた結果（tools/jev_direct.py）が、手の観察を母集団に通した予測
（仮説の対比、述語の平均所属度）をどれだけ再現するかを、層A→層Bの経路と並べて比べる。

  python3 tools/eval_jev_direct.py --direct eval/jev/direct-scenes.json \\
      --obs jev-cal=eval/jev/obs-scenes-jev-cal.json --obs sub=eval/v09-observers/obs-scenes-opus.json -o eval/jev/direct-scenes.md
"""
import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import blind  # noqa: E402
import sim  # noqa: E402

CATS = sim.CATS


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--direct", required=True)
    ap.add_argument("--obs", action="append", default=[], help="名前=観察JSON（層A→層Bの経路）")
    ap.add_argument("--scenes", default=str(ROOT / "examples" / "scenes-v09.json"))
    ap.add_argument("--hypotheses", default=str(ROOT / "human" / "hypotheses-v09.json"))
    ap.add_argument("-n", type=int, default=500)
    ap.add_argument("-o", "--out", required=True)
    args = ap.parse_args()
    data = sim.load(args.scenes)
    direct = sim.load(args.direct)
    obs = [(n, sim.load(p)) for n, p in (s.split("=", 1) for s in args.obs)]
    panel = sim.sample_panel(sim.load_population(str(ROOT / "population.json")), args.n, 7)
    cols = {"手の観察→母集団": [], "Jev 直接（Choice）": [], "Jev 直接（Noul）": []}
    for n, _ in obs:
        cols[f"{n}→母集団"] = []
    for scene in data["scenes"]:
        for ans in scene["answers"]:
            aid = f"{scene['id']}/{ans['id']}"
            if aid not in direct or any(aid not in o["answers"] for _, o in obs):
                continue
            meta = dict(scene.get("design") or {}, answer=ans["id"], scene=scene["id"])
            tl = len(ans.get("text", ""))
            sim.use_source(None)
            a = sim.merged(sim.DEFAULT_ANSWER, ans["obs"])
            a["restraint"] = sim.restraint_of(a)
            r = sim.assess(a, sim.merged(sim.DEFAULT_SCENARIO, scene["scenario"]), panel, tl)
            cols["手の観察→母集団"].append((meta, {"mu": r["mu"], "trust": 1 + 4 * r["reliability"]}))
            d = direct[aid]
            cols["Jev 直接（Choice）"].append((meta, {"mu": {k: d["choice"][k] for k in CATS}, "trust": None}))
            cols["Jev 直接（Noul）"].append((meta, {"mu": {k: d["noul"][k] for k in CATS}, "trust": None}))
            for n, o in obs:
                sim.use_source(o.get("source"))
                a = sim.merged(sim.DEFAULT_ANSWER, o["answers"][aid])
                a["restraint"] = sim.restraint_of(a)
                r = sim.assess(a, sim.merged(sim.DEFAULT_SCENARIO, o["scenarios"][scene["id"]]), panel, tl)
                cols[f"{n}→母集団"].append((meta, {"mu": r["mu"], "trust": 1 + 4 * r["reliability"]}))
    sim.use_source(None)
    names = list(cols)
    base = cols[names[0]]
    L = [f"# 作例での Jev 直接評定と層A→層Bの比較（{len(base)} 回答）", "",
         "基準は「手の観察→母集団」。近さは 1 − 4述語の平均絶対差。Jev 直接は母集団を通さない。", "",
         "## 平均所属度と基準への近さ", "",
         "近さは「常に釣り合う」でも高く出る（v0.8 の評価 6章）。非ファジィ化（最大の述語）した評定の一致と κ も並べる。", "",
         "| 方式 | 失礼 | 足りない | 釣り合う | 重すぎる | 基準への近さ（平均） | 非ファジィ化の一致 | κ |", "|---|---|---|---|---|---|---|---|"]
    label = lambda m: max(CATS, key=lambda k: m[k])
    blab = [label(b["mu"]) for _, b in base]
    for n in names:
        rows = cols[n]
        mu = {k: sum(v["mu"][k] for _, v in rows) / len(rows) for k in CATS}
        cl = sum(sim.closeness(v["mu"], b["mu"]) for (_, v), (_, b) in zip(rows, base)) / len(rows)
        lab = [label(v["mu"]) for _, v in rows]
        po = sum(x == y for x, y in zip(lab, blab)) / len(lab)
        pe = sum(lab.count(k) * blab.count(k) for k in CATS) / len(lab) ** 2
        kap = (po - pe) / (1 - pe) if pe < 1 else float("nan")
        L.append(f"| {n} | {mu['rude']:.2f} | {mu['light']:.2f} | {mu['fit']:.2f} | {mu['heavy']:.2f} | {cl:.3f} | "
                 f"{sum(x == y for x, y in zip(lab, blab))}/{len(lab)} | {kap:.2f} |")
    alw = {k: float(k == "fit") for k in CATS}
    cl = sum(sim.closeness(alw, b["mu"]) for _, b in base) / len(base)
    L.append(f"| （参考）常に釣り合う | 0.00 | 0.00 | 1.00 | 0.00 | {cl:.3f} | {blab.count('fit')}/{len(blab)} | 0.00 |")
    spec = sim.load(args.hypotheses)
    preds = {n: blind.predictions(spec, cols[n]) for n in names}
    L += ["", "## 仮説の対比", "", "向き：基準と符号が同じなら ○（両方が ±0.02 未満でも ○）。信頼意図の仮説は、直接評定では測れないので —。", "",
          "| 仮説 | " + " | ".join(names) + " |", "|---|" + "---|" * len(names)]
    agree = {n: [0, 0] for n in names[1:]}
    detect = {n: [0, 0] for n in names[1:]}
    for h in spec["hypotheses"]:
        b = preds[names[0]].get(h["id"])
        if b is None:
            continue
        cells = [f"{b:+.3f}"]
        for n in names[1:]:
            v = preds[n].get(h["id"])
            if v is None:
                cells.append("—")
                continue
            same = (v > 0) == (b > 0) or (abs(v) < 0.02 and abs(b) < 0.02)
            agree[n][0] += same
            agree[n][1] += 1
            if abs(b) >= 0.1:
                detect[n][0] += (v > 0) == (b > 0) and abs(v) >= 0.05
                detect[n][1] += 1
            cells.append(f"{v:+.3f} {'○' if same else '×'}")
        L.append(f"| {h['id']} {h['desc']} | " + " | ".join(cells) + " |")
    L += ["", "向きの一致：" + "、".join(f"{n} {a}/{t}" for n, (a, t) in agree.items()),
          "", "効果の検出（基準の対比が ±0.1 以上の仮説のうち、同じ向きで ±0.05 以上を出せた数）："
          + "、".join(f"{n} {a}/{t}" for n, (a, t) in detect.items())]
    md = "\n".join(L) + "\n"
    Path(args.out).write_text(md, encoding="utf-8")
    print(md)


if __name__ == "__main__":
    main()
