#!/usr/bin/env python3
"""ベンチマークでの総合評価（v0.9）。シミュレータの予測分布を、真に適正なスコアリング規則で採点する。

  python3 tools/evaluate.py --obs proxy=out/obs-proxy.json --obs subagent=eval/obs-subagent.json runs/* -o out/eval.json
  python3 tools/evaluate.py --obs v09=eval/obs-subagent.json --obs v08=eval/obs-subagent.json@/path/to/v08 runs/*

予測分布：受け手一人の所属度 μ を、反応モデル P(k|μ) = softmax(β·μ) で選択に変え、母集団で平均する。
主指標：多クラス Brier と対数損失。基準（一様、常に釣り合う、周辺分布、条件だけ）と同じ規則で採点し、
スキルスコア（1 − 自分 ÷ 基準）で報告する。
手続き：β（と --calibrate のときの所属度関数の中心）は、場面単位の4分割交差検証の学習側で当てはめ、
分割の外側で採点する。区間は場面単位のブートストラップ。評価器どうしは同じ再標本での差の区間で比べる。
κ・一致・近さは記述用の副指標で、順位づけには使わない。

名前=観察JSON@シミュレータのディレクトリ と書くと、別の版の sim.py で同じ観察を評価する（版の比較用）。
標準ライブラリのみ。
"""
import argparse
import importlib.util
import json
import math
import random
import sys
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import sim  # noqa: E402

CATS = sim.CATS
CONDS = sim.CONDS
BETAS = [1, 2, 3, 4, 6, 8, 12, 16, 24, 32]
EPS = 1e-4


def load_sim(path):
    spec = importlib.util.spec_from_file_location(f"sim_{abs(hash(path))}", str(Path(path) / "sim.py"))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


# ---------------------------------------------------------------- 予測

def person_axes(S, obs, rows, pop_path, n, seed, hyst=True):
    """回答ごとに、受け手一人ずつの (失点, 不足, 過剰) を返す。所属度関数を変えても再計算せずに済むようにする。"""
    pop = S.load_population(pop_path)
    if hasattr(S, "use_source"):
        S.use_source(obs.get("source"))
    panel = S.sample_panel(pop, n, seed)
    out = {}
    for r in rows:
        if r["aid"] not in obs["answers"] or r["sid"] not in obs["scenarios"]:
            continue
        sc = S.merged(S.DEFAULT_SCENARIO, obs["scenarios"][r["sid"]])
        a = S.merged(S.DEFAULT_ANSWER, obs["answers"][r["aid"]])
        ax = []
        for _, th in panel:
            L = S.perceive(sc, th, hyst)
            j = S.judge_full(a, sc, th, L, len(r["text"]), hyst)
            ax.append((j["offense"], j["shortfall"], j["excess"]))
        out[r["aid"]] = ax
    return out


def lg(x, c, w):
    z = max(-60.0, min(60.0, (x - c) / w))
    return 1.0 / (1.0 + math.exp(-z))


def person_mu(axes, J):
    """所属度関数の設定 J で、受け手一人ずつの所属度を作る。"""
    prod = J.get("tnorm") == "product"
    out = []
    for o, s, e in axes:
        r, l, h = lg(o, J["rude"]["center"], J["rude"]["width"]), lg(s, J["light"]["center"], J["light"]["width"]), \
            lg(e, J["heavy"]["center"], J["heavy"]["width"])
        f = (1 - r) * (1 - l) * (1 - h) if prod else min(1 - r, 1 - l, 1 - h)
        out.append((r, l, f, h))
    return out


def predict(mus, beta):
    """反応モデルで予測分布を作る。beta=None は一人ずつ最大の所属度を選ぶ（非ファジィ化）。"""
    acc = [0.0] * 4
    for m in mus:
        if beta is None:
            k = max((0, 1, 3, 2), key=lambda i: m[i])
            acc[k] += 1
            continue
        ex = [math.exp(beta * (v - max(m))) for v in m]
        z = sum(ex)
        for i in range(4):
            acc[i] += ex[i] / z
    n = len(mus)
    return [x / n for x in acc]


def brier(p, y):
    return sum((p[i] - (CATS[i] == y)) ** 2 for i in range(4))


def logloss(p, y):
    return -math.log(max(EPS, p[CATS.index(y)]))


def freq(labels, smooth=0.5):
    c = Counter(labels)
    tot = len(labels) + 4 * smooth
    return [(c[k] + smooth) / tot for k in CATS]


# ---------------------------------------------------------------- 交差検証

def folds_by_key(rows, k=4, seed=11):
    keys = sorted({r["key"] for r in rows})
    random.Random(seed).shuffle(keys)
    return {key: i % k for i, key in enumerate(keys)}


def calib_grid(J0, calibrate):
    if not calibrate:
        return [J0]
    grid = []
    for rc in (0.9, 1.2, 1.5, 1.8, 2.1, 2.4, 2.7, 3.0):
        for lc in (0.7, 1.0, 1.3, 1.6, 1.9, 2.2):
            J = json.loads(json.dumps(J0))
            J["rude"]["center"], J["light"]["center"] = rc, lc
            grid.append(J)
    return grid


def cross_validate(axes, rows, J0, calibrate, k=4):
    """分割の外側の予測と、各分割で選んだ設定を返す。"""
    fold = folds_by_key(rows, k)
    grid = calib_grid(J0, calibrate)
    mus = [{r["aid"]: person_mu(axes[r["aid"]], J) for r in rows} for J in grid]
    preds = {(gi, b): {r["aid"]: predict(mus[gi][r["aid"]], b) for r in rows} for gi in range(len(grid)) for b in BETAS}
    oof, chosen = {}, []
    for f in range(k):
        train = [r for r in rows if fold[r["key"]] != f]
        test = [r for r in rows if fold[r["key"]] == f]
        best = min(preds, key=lambda gb: sum(logloss(preds[gb][r["aid"]], r["user"]) for r in train))
        chosen.append({"beta": best[1], "rude_center": grid[best[0]]["rude"]["center"],
                       "light_center": grid[best[0]]["light"]["center"]})
        for r in test:
            oof[r["aid"]] = preds[best][r["aid"]]
    best_all = min(preds, key=lambda gb: sum(logloss(preds[gb][r["aid"]], r["user"]) for r in rows))
    insample = preds[best_all]
    labels = {r["aid"]: predict(mus[0][r["aid"]], None) for r in rows}
    return oof, chosen, insample, {"beta": best_all[1], "rude_center": grid[best_all[0]]["rude"]["center"],
                                   "light_center": grid[best_all[0]]["light"]["center"]}, labels


def baselines(rows, k=4):
    fold = folds_by_key(rows, k)
    out = {"一様": {}, "常に釣り合う": {}, "周辺分布": {}, "条件だけ": {}}
    for f in range(k):
        train = [r for r in rows if fold[r["key"]] != f]
        marg = freq([r["user"] for r in train])
        cond = {c: freq([r["user"] for r in train if r["cond"] == c]) for c in CONDS}
        for r in rows:
            if fold[r["key"]] != f:
                continue
            out["一様"][r["aid"]] = [0.25] * 4
            out["常に釣り合う"][r["aid"]] = [0.0, 0.0, 1.0, 0.0]
            out["周辺分布"][r["aid"]] = marg
            out["条件だけ"][r["aid"]] = cond[r["cond"]]
    return out


# ---------------------------------------------------------------- 採点

def scores(pred, rows):
    rs = [r for r in rows if r["aid"] in pred]
    return {"brier": sum(brier(pred[r["aid"]], r["user"]) for r in rs) / len(rs),
            "logloss": sum(logloss(pred[r["aid"]], r["user"]) for r in rs) / len(rs), "n": len(rs)}


def boot_ci(rows, preds, boot, seed=1):
    """場面単位のブートストラップ。preds: 名前→予測。各名前の Brier と、名前の組の差の 95% 区間を返す。"""
    by_key = defaultdict(list)
    for r in rows:
        by_key[r["key"]].append(r)
    keys = sorted(by_key)
    rng = random.Random(seed)
    names = list(preds)
    samples = defaultdict(list)
    for _ in range(boot):
        rs = [r for k in rng.choices(keys, k=len(keys)) for r in by_key[k]]
        b = {n: sum(brier(preds[n][r["aid"]], r["user"]) for r in rs) / len(rs) for n in names}
        for n in names:
            samples[n].append(b[n])
        samples["_rs"].append(b)

    def ci(xs):
        xs = sorted(xs)
        return [round(xs[int(0.025 * len(xs))], 4), round(xs[int(0.975 * len(xs)) - 1], 4)]
    return {n: ci(samples[n]) for n in names}, samples["_rs"], ci


def descriptive(pred_mu, rows):
    u = [r["user"] for r in rows]
    dz = [sim.defuzz(pred_mu[r["aid"]]) for r in rows]
    return {"kappa": round(sim.kappa(u, dz), 3), "agree": round(sum(a == b for a, b in zip(u, dz)) / len(u), 3),
            "closeness": round(sum(sim.closeness(pred_mu[r["aid"]], sim.onehot(r["user"])) for r in rows) / len(rows), 3)}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("runs", nargs="+")
    ap.add_argument("--obs", action="append", required=True, help="名前=観察JSON[@シミュレータのディレクトリ]")
    ap.add_argument("--population", default=str(sim.HERE / "population.json"))
    ap.add_argument("-n", type=int, default=1000)
    ap.add_argument("--seed", type=int, default=7)
    ap.add_argument("--boot", type=int, default=2000)
    ap.add_argument("--calibrate", action="store_true", help="所属度関数の中心も交差検証の内側で当てはめる（出どころごとの較正）")
    ap.add_argument("--no-hysteresis", action="store_true")
    ap.add_argument("-o", "--out", default="out/eval.json")
    args = ap.parse_args()
    rows = [r for r in sim.load_runs(args.runs) if r["user"]]
    report = {"n_answers": len(rows), "n_scenes": len({r["key"] for r in rows}), "betas": BETAS,
              "calibrate": args.calibrate, "evaluators": {}}
    preds = {}
    base = baselines(rows)
    for name, p in base.items():
        preds[name] = p
    for spec in args.obs:
        name, rest = spec.split("=", 1)
        path, _, simdir = rest.partition("@")
        S = load_sim(simdir) if simdir else sim
        pop_path = str(Path(simdir) / "population.json") if simdir else args.population
        obs = sim.load(path)
        axes = person_axes(S, obs, rows, pop_path, args.n, args.seed, not args.no_hysteresis)
        rs = [r for r in rows if r["aid"] in axes]
        # 出どころごとの較正（population.json の judgment_by_source）は同じデータで当てはめた値なので、ここでは使わない。
        # 較正の効果は --calibrate で交差検証の内側から測る
        J0 = json.loads(json.dumps(getattr(S, "JUDGMENT_BASE", None) or S.JUDGMENT))
        oof, chosen, insample, best_all, labels = cross_validate(axes, rs, J0, args.calibrate)
        mean_mu = {}
        for r in rs:
            m = person_mu(axes[r["aid"]], J0)
            mean_mu[r["aid"]] = {k: sum(x[i] for x in m) / len(m) for i, k in enumerate(CATS)}
        preds[name] = oof
        e = {"obs": path, "sim": simdir or "current", "source": obs.get("source"), "n": len(rs),
             "oof": scores(oof, rs), "insample": scores(insample, rs), "insample_choice": best_all,
             "fold_choice": chosen, "labels_only": scores(labels, rs), "descriptive": descriptive(mean_mu, rs),
             "repair": scores(oof, [r for r in rs if r["level"] == "repair"]),
             "by_cond": {c: scores(oof, [r for r in rs if r["cond"] == c]) for c in CONDS}}
        report["evaluators"][name] = e
    ci, reps, cif = boot_ci(rows, preds, args.boot)
    names = [s.split("=", 1)[0] for s in args.obs]
    report["baselines"] = {n: {**scores(base[n], rows), "brier_ci": ci[n]} for n in base}
    print(f"■ ベンチマーク {len(rows)} 回答・{report['n_scenes']} 場面。場面単位の4分割交差検証、分割の外側で採点。区間は場面単位のブートストラップ {args.boot} 回\n")
    print("  基準               Brier [95%区間]         対数損失")
    for n in base:
        b = report["baselines"][n]
        print(f"  {n.ljust(10, '　')}  {b['brier']:.3f} [{ci[n][0]:.3f}, {ci[n][1]:.3f}]   {b['logloss']:.3f}")
    print()
    for n in names:
        e = report["evaluators"][n]
        e["brier_ci"] = ci[n]
        e["skill"] = {}
        for bn in base:
            d = [1 - x[n] / x[bn] for x in reps]
            e["skill"][bn] = {"value": round(1 - e["oof"]["brier"] / report["baselines"][bn]["brier"], 4), "ci": cif(d)}
        print(f"■ {n}（{e['source']}、{e['sim']}）  Brier {e['oof']['brier']:.3f} [{ci[n][0]:.3f}, {ci[n][1]:.3f}]  対数損失 {e['oof']['logloss']:.3f}"
              f"  （標本内 {e['insample']['brier']:.3f}、非ファジィ化のみ {e['labels_only']['brier']:.3f}）")
        print("    スキル（1 − 自分÷基準、Brier）: " + "  ".join(
            f"{bn} {v['value']:+.3f} [{v['ci'][0]:+.3f}, {v['ci'][1]:+.3f}]" for bn, v in e["skill"].items()))
        print(f"    修復期 {e['repair']['n']} 回答 Brier {e['repair']['brier']:.3f}   条件別 " + "  ".join(
            f"{c} {v['brier']:.3f}" for c, v in e["by_cond"].items()))
        print("    分割ごとの選択 " + ", ".join(f"β={c['beta']}" + (f" 失礼{c['rude_center']} 足りない{c['light_center']}" if args.calibrate else "")
                                       for c in e["fold_choice"]))
        d = e["descriptive"]
        print(f"    記述用: κ {d['kappa']:.2f}  一致 {d['agree']:.2f}  近さ {d['closeness']:.2f}")
    if len(names) > 1:
        print("\n■ 評価器どうしの差（Brier、左 − 右。負なら左が良い）")
        report["differences"] = {}
        for i, a in enumerate(names):
            for b in names[i + 1:]:
                d = [x[a] - x[b] for x in reps]
                v = report["evaluators"][a]["oof"]["brier"] - report["evaluators"][b]["oof"]["brier"]
                report["differences"][f"{a}-{b}"] = {"value": round(v, 4), "ci": cif(d)}
                print(f"  {a} − {b}: {v:+.3f} {cif(d)}")
        # 修復期だけの差
        rep_rows = [r for r in rows if r["level"] == "repair"]
        if rep_rows:
            _, reps_r, _ = boot_ci(rep_rows, {n: preds[n] for n in names}, args.boot)
            for i, a in enumerate(names):
                for b in names[i + 1:]:
                    d = [x[a] - x[b] for x in reps_r]
                    v = report["evaluators"][a]["repair"]["brier"] - report["evaluators"][b]["repair"]["brier"]
                    report["differences"][f"{a}-{b}:repair"] = {"value": round(v, 4), "ci": cif(d)}
                    print(f"  修復期 {a} − {b}: {v:+.3f} {cif(d)}")
    sim.save(args.out, report)
    print(f"→ {args.out}")


if __name__ == "__main__":
    main()
