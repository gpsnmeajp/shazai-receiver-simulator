#!/usr/bin/env python3
"""ベンチマークでの総合評価（v0.8）。観察JSONごとに、筆者の4値の評定と比べる。

  python3 tools/evaluate.py --obs proxy=out/obs-proxy.json --obs subagent=out/obs-subagent.json runs/* -o out/eval.json

出力：条件ごとの「釣り合う」、非ファジィ化した κ（場面単位のブートストラップ区間つき）、
筆者の評定の述語への所属度、近さ、混同行列、段階ごとの一致、ペルソナとの比較、所属度関数の感度。
標準ライブラリのみ。
"""
import argparse
import json
import random
import sys
from collections import Counter, defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import sim  # noqa: E402

CONDS = sim.CONDS
CATS = sim.CATS


def evaluate(obs, rows, pop, n, seed, hyst=True):
    panel = sim.sample_panel(pop, n, seed)
    out = {}
    for r in rows:
        if r["aid"] not in obs["answers"] or r["sid"] not in obs["scenarios"]:
            continue
        sc = sim.merged(sim.DEFAULT_SCENARIO, obs["scenarios"][r["sid"]])
        a = sim.merged(sim.DEFAULT_ANSWER, obs["answers"][r["aid"]])
        out[r["aid"]] = sim.assess(a, sc, panel, len(r["text"]), hyst)
    return out


def summarize(res, rows, boot=1000, seed=1):
    rows = [r for r in rows if r["aid"] in res and r["user"]]
    u = [r["user"] for r in rows]
    dz = [sim.defuzz(res[r["aid"]]["mu"]) for r in rows]
    s = {"n": len(rows), "kappa": sim.kappa(u, dz), "agree": sum(a == b for a, b in zip(u, dz)) / len(u),
         "author_membership": sum(res[r["aid"]]["mu"][r["user"]] for r in rows) / len(rows),
         "closeness": sum(sim.closeness(res[r["aid"]]["mu"], sim.onehot(r["user"])) for r in rows) / len(rows),
         "surprise": sum(1 for r in rows if res[r["aid"]]["mu"][r["user"]] < 0.1)}
    # 条件ごと：筆者の「釣り合う」の割合と、シミュレータの平均所属度・非ファジィ化の割合
    s["by_cond"] = {}
    for c in CONDS:
        rc = [r for r in rows if r["cond"] == c]
        if rc:
            s["by_cond"][c] = {"author_fit": sum(r["user"] == "fit" for r in rc) / len(rc),
                               "sim_fit_mu": sum(res[r["aid"]]["mu"]["fit"] for r in rc) / len(rc),
                               "sim_fit_label": sum(sim.defuzz(res[r["aid"]]["mu"]) == "fit" for r in rc) / len(rc),
                               "sim_rude_tail": sum(res[r["aid"]]["tail"]["rude"] for r in rc) / len(rc),
                               "persona_fit": sum((sim.majority(r) or "fit") == "fit" for r in rc) / len(rc)}
    order = [s["by_cond"][c]["sim_fit_mu"] for c in CONDS if c in s["by_cond"]]
    s["order_ok"] = all(x < y for x, y in zip(order, order[1:]))
    s["confusion"] = {a: dict(Counter(d for x, d in zip(u, dz) if x == a)) for a in CATS}
    s["by_level"] = {}
    for lv in sim.LEVELS:
        rl = [(x, d) for r, x, d in zip(rows, u, dz) if r["level"] == lv]
        if rl:
            s["by_level"][lv] = {"n": len(rl), "agree": sum(a == b for a, b in rl) / len(rl)}
    # 場面単位のブートストラップ（同じ場面の回答は独立でないため）
    keys = sorted({r["key"] for r in rows})
    by_key = defaultdict(list)
    for r, x, d in zip(rows, u, dz):
        by_key[r["key"]].append((x, d))
    rng = random.Random(seed)
    ks = []
    for _ in range(boot):
        pairs = [p for k in rng.choices(keys, k=len(keys)) for p in by_key[k]]
        ks.append(sim.kappa([a for a, _ in pairs], [b for _, b in pairs]))
    ks.sort()
    s["kappa_ci"] = [ks[int(0.025 * boot)], ks[int(0.975 * boot) - 1]]
    return s


def persona_summary(rows):
    rows = [r for r in rows if r["user"]]
    u = [r["user"] for r in rows]
    out = {}
    pm = [sim.majority(r) or "fit" for r in rows]
    out["majority"] = {"kappa": sim.kappa(u, pm), "agree": sum(a == b for a, b in zip(u, pm)) / len(u),
                       "closeness": sum(sim.closeness(sim.onehot(p), sim.onehot(x)) for p, x in zip(pm, u)) / len(u)}
    for p in ("P1", "P2", "P3"):
        ps = [r["personas"].get(p) for r in rows]
        if all(ps):
            out[p] = {"kappa": sim.kappa(u, ps), "agree": sum(a == b for a, b in zip(u, ps)) / len(u)}
    return out


SENSITIVITY = {
    "既定（失礼 1.2/0.3、足りない 1.0/0.3、重すぎる 0.3/0.25、min）": {},
    "失礼の中心 1.5（最初に置いた値）": {"rude": {"center": 1.5, "width": 0.35}},
    "失礼の中心 1.0": {"rude": {"center": 1.0}},
    "足りないの中心 0.8": {"light": {"center": 0.8}},
    "足りないの中心 1.25": {"light": {"center": 1.25}},
    "なだらかさ ×0.5（4値に近い）": {"rude": {"width": 0.15}, "light": {"width": 0.15}, "heavy": {"width": 0.125}},
    "なだらかさ ×2": {"rude": {"width": 0.6}, "light": {"width": 0.6}, "heavy": {"width": 0.5}},
    "釣り合う = 積": {"tnorm": "product"},
    "境界のなだらかさ 0.05（ほぼ段差）": {"gate_width": 0.05},
}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("runs", nargs="+")
    ap.add_argument("--obs", action="append", required=True, help="名前=観察JSON")
    ap.add_argument("--population", default=str(sim.HERE / "population.json"))
    ap.add_argument("-n", type=int, default=1000)
    ap.add_argument("--seed", type=int, default=7)
    ap.add_argument("--sensitivity", action="store_true")
    ap.add_argument("-o", "--out", default="out/eval.json")
    args = ap.parse_args()
    rows = sim.load_runs(args.runs)
    base = json.loads(json.dumps(sim.JUDGMENT))
    pop = sim.load_population(args.population)
    base = json.loads(json.dumps(sim.JUDGMENT))
    report = {"personas": persona_summary(rows), "observers": {}}
    for spec in args.obs:
        name, path = spec.split("=", 1)
        obs = sim.load(path)
        res = evaluate(obs, rows, pop, args.n, args.seed)
        entry = {"default": summarize(res, rows)}
        entry["no_hysteresis"] = summarize(evaluate(obs, rows, pop, args.n, args.seed, hyst=False), rows)
        if args.sensitivity:
            entry["sensitivity"] = {}
            for label, change in SENSITIVITY.items():
                sim.JUDGMENT.clear()
                sim.JUDGMENT.update(json.loads(json.dumps(base)))
                sim.configure({"judgment": change})
                entry["sensitivity"][label] = summarize(evaluate(obs, rows, pop, args.n, args.seed), rows, boot=0 or 200)
            sim.JUDGMENT.clear()
            sim.JUDGMENT.update(base)
        report["observers"][name] = entry
        d = entry["default"]
        print(f"■ {name}: {d['n']} 件  κ={d['kappa']:.2f} [{d['kappa_ci'][0]:.2f}, {d['kappa_ci'][1]:.2f}]  一致 {d['agree']:.2f}"
              f"  筆者の述語への所属度 {d['author_membership']:.2f}  近さ {d['closeness']:.2f}  想定外 {d['surprise']}  順位 {'○' if d['order_ok'] else '×'}")
        for c, v in d["by_cond"].items():
            print(f"    {c.ljust(17)} 筆者の釣り合う {v['author_fit']:.2f}  sim 平均所属度 {v['sim_fit_mu']:.2f}"
                  f"  非ファジィ化 {v['sim_fit_label']:.2f}  失礼と感じる人 {v['sim_rude_tail']:.2f}  ペルソナ {v['persona_fit']:.2f}")
        nh = entry["no_hysteresis"]
        print(f"    ヒステリシスなし κ={nh['kappa']:.2f}  所属度 {nh['author_membership']:.2f}")
        for label, v in entry.get("sensitivity", {}).items():
            print(f"    [感度] {label}: κ={v['kappa']:.2f}  所属度 {v['author_membership']:.2f}  近さ {v['closeness']:.2f}  順位 {'○' if v['order_ok'] else '×'}")
    p = report["personas"]
    print(f"■ ペルソナ多数決 κ={p['majority']['kappa']:.2f}  一致 {p['majority']['agree']:.2f}  近さ {p['majority']['closeness']:.2f}")
    sim.save(args.out, report)
    print(f"→ {args.out}")


if __name__ == "__main__":
    main()
