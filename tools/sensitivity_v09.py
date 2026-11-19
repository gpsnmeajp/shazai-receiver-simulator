#!/usr/bin/env python3
"""v0.9 の新しい事前値の感度分析。項目の組（手の観察）で、仮説の対比のシミュレータの予測が、
傷の減衰のターン数・過失の承認の割合・欺瞞の傷の残り・所属度関数の中心でどう変わるかを見る。

  python3 tools/sensitivity_v09.py -o eval/v09-sensitivity.md
"""
import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import blind  # noqa: E402
import sim  # noqa: E402

VARIANTS = [
    ("既定（T=20、share_fault=0.5、floor=0.5）", {}, {}),
    ("傷の減衰 T=10", {"scar_decay_turns": 10}, {}),
    ("傷の減衰 T=40", {"scar_decay_turns": 40}, {}),
    ("減衰なし", {"scar_decay_turns": 0}, {}),
    ("過失の承認の割合 0.3", {"share_fault": 0.3}, {}),
    ("過失の承認の割合 0.7", {"share_fault": 0.7}, {}),
    ("欺瞞の傷の残り 0", {"deception_floor": 0.0}, {}),
    ("欺瞞の傷の残り 1（減衰しない）", {"deception_floor": 1.0}, {}),
    ("失礼の中心 1.5", {}, {"rude": {"center": 1.5}}),
    ("LLM の較正（失礼 2.4、足りない 1.6）", {}, {"rude": {"center": 2.4}, "light": {"center": 1.6}}),
]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--scenes", default=str(ROOT / "examples" / "scenes-v09.json"))
    ap.add_argument("--hypotheses", default=str(ROOT / "human" / "hypotheses-v09.json"))
    ap.add_argument("-n", type=int, default=300)
    ap.add_argument("-o", "--out", default="eval/v09-sensitivity.md")
    args = ap.parse_args()
    pop = sim.load_population(str(ROOT / "population.json"))
    base_tl, base_j = json.loads(json.dumps(sim.TIMELINE)), json.loads(json.dumps(sim.JUDGMENT))
    panel = sim.sample_panel(pop, args.n, 7)
    spec = sim.load(args.hypotheses)
    data = sim.load(args.scenes)
    items = []
    for scene in data["scenes"]:
        d = scene.get("design") or {}
        sc = sim.merged(sim.DEFAULT_SCENARIO, scene["scenario"])
        for ans in scene["answers"]:
            items.append((dict(d, answer=ans["id"], scene=scene["id"]), sc, sim.merged(sim.DEFAULT_ANSWER, ans.get("obs", {})),
                          len(ans.get("text", ""))))
    cols, decay_rows = [], []
    for label, tl, jd in VARIANTS:
        sim.TIMELINE.clear(); sim.TIMELINE.update(base_tl); sim.TIMELINE.update(tl)
        sim.JUDGMENT.clear(); sim.JUDGMENT.update(json.loads(json.dumps(base_j)))
        for k, v in jd.items():
            sim.JUDGMENT[k] = dict(sim.JUDGMENT[k], **v)
        rows = []
        for meta, sc, a, tlen in items:
            r = sim.assess(a, sc, panel, tlen)
            rows.append((meta, {"mu": r["mu"], "trust": 1 + 4 * r["reliability"]}))
            if meta.get("kind") == "decay" and meta["answer"] == "b3":
                decay_rows.append((label, meta["turns_since_incident"], r["mu"]["rude"]))
        cols.append((label, blind.predictions(spec, rows)))
    ids = [h["id"] for h in spec["hypotheses"] if h["measure"] not in ("remorse", "recurrence")]
    L = ["# v0.9 の事前値の感度分析（項目の組・手の観察）", "",
         "各仮説の対比について、シミュレータの予測値（所属度の差、信頼意図は reliability の差）。"
         "事前登録の効果の最小の大きさは 0.10。符号が既定と変わる値に ※ を付けた。", "",
         "| 仮説 | " + " | ".join(c[0] for c in cols) + " |", "|---|" + "---|" * len(cols)]
    for h in ids:
        base = cols[0][1][h]
        cells = []
        for _, pr in cols:
            v = pr[h]
            flip = base is not None and v is not None and abs(base) >= 0.02 and abs(v) >= 0.02 and (v > 0) != (base > 0)
            cells.append("—" if v is None else f"{v:+.2f}{'※' if flip else ''}")
        L.append(f"| {h} | " + " | ".join(cells) + " |")
    L += ["", "## 傷の減衰：約束を破った後の修復期の軽口（b3）の「失礼」", "",
          "| 設定 | " + " | ".join(f"{t} ターン" for t in sorted({t for _, t, _ in decay_rows})) + " |",
          "|---|" + "---|" * len({t for _, t, _ in decay_rows})]
    for label, _, _ in VARIANTS:
        vals = {t: v for lb, t, v in decay_rows if lb == label}
        L.append(f"| {label} | " + " | ".join(f"{vals[t]:.2f}" for t in sorted(vals)) + " |")
    md = "\n".join(L) + "\n"
    Path(args.out).write_text(md, encoding="utf-8")
    print(md)


if __name__ == "__main__":
    main()
