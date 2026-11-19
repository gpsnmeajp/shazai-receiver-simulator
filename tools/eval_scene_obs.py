#!/usr/bin/env python3
"""項目の組（examples/scenes-v09.json）で、LLM の観察が手の観察をどれだけ再現するか、
またその観察を通したシミュレータの予測（仮説の対比）が手の観察のときと同じ向きになるかを調べる。

  python3 tools/eval_scene_obs.py eval/v09-observers/obs-scenes-opus.json -o eval/v09-scenes-obs.md
"""
import argparse
import json
import sys
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import blind  # noqa: E402
import sim  # noqa: E402

NUM = {  # 欄 → 取り出し方
    "失敗の前の自信（失敗の発話）": ("sc", lambda sc: next((float(t.get("confidence", 1)) for t in sc.get("prior_stance", {}).get("turns", [])
                                                     if t.get("caused_failure")), None)),
    "経過ターン": ("sc", lambda sc: sc.get("turns_since_incident")),
    "過信への言及": ("a", lambda a: a.get("stance", {}).get("acknowledges_overclaim", 0)),
    "この回答の自信": ("a", lambda a: a.get("stance", {}).get("confidence_now", 1)),
    "ぼかしすぎ": ("a", lambda a: a.get("stance", {}).get("over_hedging", 0)),
    "調子を戻す": ("a", lambda a: a.get("restraint", {}).get("tone_reset", 0)),
    "配慮": ("a", lambda a: a.get("restraint", {}).get("care", 1)),
    "詫び直し": ("a", lambda a: a.get("restraint", {}).get("re_apology")),
}
BOOL = {
    "懸念を退けた": ("sc", lambda sc: sc.get("prior_stance", {}).get("dismissed_concern", False)),
    "確かめたと偽った": ("sc", lambda sc: sc.get("prior_stance", {}).get("verification_false", False)),
    "受け入れの後": ("sc", lambda sc: sc.get("apology_accepted_before", False)),
    "較正された構え": ("a", lambda a: a.get("stance", {}).get("calibrated", False)),
    "軽口": ("a", lambda a: a.get("restraint", {}).get("levity_about_incident", False)),
    "許しの当然視": ("a", lambda a: a.get("restraint", {}).get("presumes_forgiveness", False)),
}
ENUM = {"約束を守ったか": ("a", lambda a: a.get("restraint", {}).get("promise_kept", "na"))}


def tobool(x):
    if x in (None, "unknown"):
        return None
    return float(x) >= 0.5 if not isinstance(x, bool) else x


def corr(pairs):
    pairs = [(a, b) for a, b in pairs if a is not None and b is not None]
    if len(pairs) < 3:
        return float("nan")
    return blind.corr(pairs)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("obs")
    ap.add_argument("--scenes", default=str(ROOT / "examples" / "scenes-v09.json"))
    ap.add_argument("--hypotheses", default=str(ROOT / "human" / "hypotheses-v09.json"))
    ap.add_argument("-n", type=int, default=500)
    ap.add_argument("-o", "--out", default="eval/v09-scenes-obs.md")
    args = ap.parse_args()
    obs = sim.load(args.obs)
    data = sim.load(args.scenes)
    pop = sim.load_population(str(ROOT / "population.json"))
    sim.use_source(obs.get("source"))
    panel = sim.sample_panel(pop, args.n, 7)
    pairs = defaultdict(list)
    sent_pairs = []
    rows_hand, rows_obs, close = [], [], []
    for scene in data["scenes"]:
        if scene["id"] not in obs["scenarios"]:
            continue
        sc_h = sim.merged(sim.DEFAULT_SCENARIO, scene["scenario"])
        sc_o = sim.merged(sim.DEFAULT_SCENARIO, obs["scenarios"][scene["id"]])
        for name, (where, get) in {**NUM, **BOOL, **ENUM}.items():
            if where == "sc":
                pairs[name].append((get(sc_h), get(sc_o)))
        meta_base = dict(scene.get("design") or {})
        for ans in scene["answers"]:
            aid = f"{scene['id']}/{ans['id']}"
            if aid not in obs["answers"]:
                continue
            a_h = sim.merged(sim.DEFAULT_ANSWER, ans["obs"])
            a_o = sim.merged(sim.DEFAULT_ANSWER, obs["answers"][aid])
            a_h["restraint"] = sim.restraint_of(a_h)
            a_o["restraint"] = sim.restraint_of(a_o)
            for name, (where, get) in {**NUM, **BOOL, **ENUM}.items():
                if where == "a":
                    pairs[name].append((get(a_h), get(a_o)))
            by_id = {x.get("id"): x for x in a_o.get("sentences", [])}
            for x in a_h.get("sentences", []):
                y = by_id.get(x["id"])
                if y is not None:
                    sent_pairs.append((x.get("disclaimer", "none"), y.get("disclaimer", "none")))
            tl = len(ans.get("text", ""))
            r_h = sim.assess(a_h, sc_h, panel, tl)
            r_o = sim.assess(a_o, sc_o, panel, tl)
            meta = dict(meta_base, answer=ans["id"], scene=scene["id"])
            rows_hand.append((meta, {"mu": r_h["mu"], "trust": 1 + 4 * r_h["reliability"]}))
            rows_obs.append((meta, {"mu": r_o["mu"], "trust": 1 + 4 * r_o["reliability"]}))
            close.append(sim.closeness(r_h["mu"], r_o["mu"]))
    L = [f"# 項目の組での観察の再現（{args.obs}）", "",
         f"手の観察（`examples/scenes-v09.json`）と、盲検の LLM 観察（`{obs.get('source')}`）の比較。{len(close)} 回答。", "",
         "## 欄ごとの一致", "", "| 欄 | 件数 | 一致率 / 平均絶対差 | 相関 |", "|---|---|---|---|"]
    for name in NUM:
        ps = [(float(a), float(b)) for a, b in pairs[name] if a is not None and b is not None]
        if ps:
            mae = sum(abs(a - b) for a, b in ps) / len(ps)
            L.append(f"| {name} | {len(ps)} | 平均絶対差 {mae:.2f} | {corr(ps):.2f} |")
    for name in BOOL:
        ps = [(tobool(a), tobool(b)) for a, b in pairs[name]]
        ok = [a == b for a, b in ps if a is not None and b is not None]
        unk = sum(1 for _, b in ps if b is None)
        if ok:
            L.append(f"| {name} | {len(ok)} | 一致率 {sum(ok) / len(ok):.2f}（観察の unknown {unk}） | — |")
    for name in ENUM:
        ps = [(a, b if not isinstance(b, dict) else max(b, key=b.get)) for a, b in pairs[name]]
        ok = [a == b for a, b in ps]
        L.append(f"| {name} | {len(ok)} | 一致率 {sum(ok) / len(ok):.2f} | — |")
    if sent_pairs:
        ok = [a == b for a, b in sent_pairs]
        pos = [(a, b) for a, b in sent_pairs if a != "none"]
        L.append(f"| 文ごとの但し書きの種類 | {len(ok)} | 一致率 {sum(ok) / len(ok):.2f}（手で但し書きとした {len(pos)} 文のうち、種類まで一致 "
                 f"{sum(a == b for a, b in pos)}、但し書きと見た {sum(b != 'none' for _, b in pos)}） | — |")
    L += ["", f"シミュレータの平均所属度の近さ（手の観察 vs LLM の観察）：平均 {sum(close) / len(close):.3f}、最小 {min(close):.3f}", "",
          "## 仮説の対比（シミュレータの予測）", "",
          "同じ項目（この観察で見た回答だけ）で、手の観察と LLM の観察のそれぞれからシミュレータが予測する対比の値。", "",
          "| 仮説 | 手の観察 | LLM の観察 | 向き |", "|---|---|---|---|"]
    spec = sim.load(args.hypotheses)
    ph, po = blind.predictions(spec, rows_hand), blind.predictions(spec, rows_obs)
    agree = 0
    tot = 0
    for h in spec["hypotheses"]:
        a, b = ph.get(h["id"]), po.get(h["id"])
        if a is None or b is None:
            continue
        tot += 1
        same = (a > 0) == (b > 0) or (abs(a) < 0.02 and abs(b) < 0.02)
        agree += same
        L.append(f"| {h['id']} {h['desc']} | {a:+.3f} | {b:+.3f} | {'○' if same else '×'} |")
    L += ["", f"向きの一致：{agree} / {tot}（両方が ±0.02 未満なら一致とみなす）"]
    md = "\n".join(L) + "\n"
    Path(args.out).write_text(md, encoding="utf-8")
    print(md)


if __name__ == "__main__":
    main()
