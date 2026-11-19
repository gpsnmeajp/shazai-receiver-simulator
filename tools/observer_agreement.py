#!/usr/bin/env python3
"""観察者の集団の評価（METHODS.md 6.5節）。欄ごとの観察者間の一致（Krippendorff のα、間隔）と、
観察方針・モデルの系統ごとの平均（主効果）を出す。

  python3 tools/observer_agreement.py eval/observers/obs-*.json -o eval/observer-agreement.md
"""
import argparse
import sys
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import blind  # noqa: E402
import sim  # noqa: E402


def num(x, default=0.0):
    if isinstance(x, bool):
        return float(x)
    if isinstance(x, (int, float)):
        return float(x)
    if isinstance(x, dict):
        return float(x.get("true", 0))
    try:
        return float(x)
    except (TypeError, ValueError):
        return default


SCEN = {
    "距離の変化": lambda s: num(s.get("distance_shift")),
    "不満の明示": lambda s: num(s.get("explicit_complaint")),
    "指摘の回数": lambda s: num(s.get("prior_corrections")),
    "損害": lambda s: num(s.get("harm")),
    "誠実さの違反": lambda s: float(s.get("violation_type") == "integrity"),
    "受け入れの後": lambda s: num(s.get("apology_accepted_before")),
    "失敗の前の自信": lambda s: max([num(t.get("confidence"), 1) for t in (s.get("prior_stance") or {}).get("turns", [])
                                   if t.get("caused_failure")] or [0.0]),
    "確かめたと偽った": lambda s: num((s.get("prior_stance") or {}).get("verification_false"), 0.0),
    "経過ターン": lambda s: num(s.get("turns_since_incident")),
}
ANS = {
    "詫びの有無": lambda a: num(a.get("apology", {}).get("present")),
    "過失の具体性": lambda a: num(a.get("apology", {}).get("specific_fault")),
    "負担への言及": lambda a: num(a.get("apology", {}).get("names_burden")),
    "弁解": lambda a: num(a.get("defense", {}).get("excuse")),
    "説明の量": lambda a: num(a.get("defense", {}).get("explanation")),
    "頼まれていない提案": lambda a: num(a.get("repair", {}).get("unrequested_proposals")),
    "先を急ぐ": lambda a: num(a.get("closure", {}).get("moves_on_quickly")),
    "過信への言及": lambda a: num(a.get("stance", {}).get("acknowledges_overclaim")),
    "この回答の自信": lambda a: num(a.get("stance", {}).get("confidence_now"), 1),
    "ぼかしすぎ": lambda a: num(a.get("stance", {}).get("over_hedging")),
    "配慮": lambda a: num(a.get("restraint", {}).get("care"), 1),
    "調子を戻す": lambda a: num(a.get("restraint", {}).get("tone_reset")),
    "悪く読める一文（自然さの和）": lambda a: sum(num(x.get("plausibility")) for x in a.get("sentences", [])),
    "但し書きの文の数": lambda a: float(sum(1 for x in a.get("sentences", []) if x.get("disclaimer", "none") not in ("none", None))),
}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("observations", nargs="+")
    ap.add_argument("-o", "--out", default="eval/observer-agreement.md")
    args = ap.parse_args()
    obs = {Path(p).stem.replace("obs-", ""): sim.load(p) for p in args.observations}
    obs = {k: v for k, v in obs.items() if v.get("variant") and len(v["answers"]) == 192}
    names = sorted(obs)
    L = [f"# 観察者の集団：欄ごとの一致と主効果（{len(names)} 変種：{', '.join(names)}）", "",
         "α は Krippendorff のα（間隔）。1 で完全一致、0 で偶然の水準。主効果は、変種ごとの平均を観察方針とモデルで分けた値。", "",
         "| 欄 | α | " + " | ".join(names) + " |", "|---|---|" + "---|" * len(names)]
    by_policy, by_model = defaultdict(lambda: defaultdict(list)), defaultdict(lambda: defaultdict(list))
    for kind, fields in (("sc", SCEN), ("a", ANS)):
        keys = sorted(set.intersection(*[set(o["scenarios" if kind == "sc" else "answers"]) for o in obs.values()]))
        for fname, get in fields.items():
            units = [[get(obs[n]["scenarios" if kind == "sc" else "answers"][k]) for n in names] for k in keys]
            alpha = blind.krippendorff_alpha_interval(units)
            means = [sum(u[i] for u in units) / len(units) for i in range(len(names))]
            for n, m in zip(names, means):
                by_policy[fname][obs[n]["variant"]["policy"]].append(m)
                by_model[fname][obs[n]["variant"]["model"]].append(m)
            L.append(f"| {fname} | {alpha:.2f} | " + " | ".join(f"{m:.2f}" for m in means) + " |")
    L += ["", "## 主効果（変種の平均の平均）", "", "| 欄 | 観察方針ごと | モデルごと |", "|---|---|---|"]
    for fname in list(SCEN) + list(ANS):
        p = "、".join(f"{k} {sum(v) / len(v):.2f}" for k, v in sorted(by_policy[fname].items()))
        m = "、".join(f"{k} {sum(v) / len(v):.2f}" for k, v in sorted(by_model[fname].items()))
        L.append(f"| {fname} | {p} | {m} |")
    md = "\n".join(L) + "\n"
    Path(args.out).write_text(md, encoding="utf-8")
    print(md)


if __name__ == "__main__":
    main()
