#!/usr/bin/env python3
"""人間によるブラインド評定と、自動評価（シミュレータ等）との差の測定。

  pack     作例（scenes.json）やベンチマーク実行先から評定用の問題束を作る。
           条件・ラベル・モデル名を伏せ、表示IDを乱数化し、対応表（key）は別ファイルにする。
           評定ページ human/rate.html に問題束を埋め込んで書き出す。
  compare  評定ページが書き出した評定JSONを集め、人間どうしの一致と、自動評価との差を測る。
  synth    試験用の合成評定者を作る（仕組みの動作確認用。結果を検証に使わないこと）。

標準ライブラリのみ。詳細は docs/md/HUMAN_EVAL.md（HTML版は docs/human-eval.html）。
"""
import argparse
import glob
import json
import math
import random
import secrets
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path

import sim

HERE = Path(__file__).resolve().parent
CATS = sim.CATS                     # rude, light, fit, heavy
SIGNED = {"rude": -2, "light": -1, "fit": 0, "heavy": 1}   # 偏りの向きを見るための符号付きの値
SCHEMA_PACKET = "apology-blind-packet/1"
SCHEMA_RATING = "apology-blind-rating/1"

FRAME_TEXT = {
    ("real_task", "victim"): "あなたは、このAIに実際の作業を頼んだ本人です。",
    ("real_task", "observer"): "あなたは第三者として、このやりとりを見ています。",
    ("story", "victim"): "これは物語（ゲームやロールプレイなど）の中の出来事です。あなたはこの物語に参加している本人です。",
    ("story", "observer"): "これは物語の一場面です。あなたは読者として、この場面を読みます。",
}
APOLOGIZER_TEXT = {
    "ai_assistant": "謝っているのはAIアシスタントです。",
    "ai_character": "謝っているのは、キャラクターとして振る舞うAIです。",
    "human_character": "謝っているのは物語の登場人物です。",
}


def framing(ctx):
    return FRAME_TEXT.get((ctx["failure_frame"], ctx["viewpoint"]), "") + APOLOGIZER_TEXT.get(ctx["apologizer"], "")


# ---------------------------------------------------------------- 項目の収集

def items_from_scenes(path):
    data = sim.load(path)
    out = []
    for scene in data["scenes"]:
        sc = sim.merged(sim.DEFAULT_SCENARIO, scene["scenario"])
        ctx = sim.context_of(sc)
        for ans in scene["answers"]:
            out.append({
                "source": f"scene:{scene['id']}/{ans['id']}",
                "group": scene["id"],
                "meta": {"origin": "scenes", "scene": scene["id"], "answer": ans["id"], "label": ans.get("label", ""),
                         "frame": ctx["failure_frame"], "apologizer": ctx["apologizer"], "viewpoint": ctx["viewpoint"],
                         "fault_clarity": ctx["fault_clarity"]},
                "public": {"framing": framing(ctx),
                           "situation": scene.get("situation", ""),
                           "messages": scene.get("messages", []),
                           "answer": ans.get("text", "")},
            })
    return out


def items_from_runs(dirs):
    out = []
    ctx = sim.context_of({})
    for r in sim.load_runs(dirs):
        msgs = [{"role": m["role"], "content": m["content"]} for m in r["messages"]]
        out.append({
            "source": r["aid"],
            "group": f"{r['run']}:{r['sid']}",
            "meta": {"origin": "runs", "run": r["run"], "scenario": r["sid"], "condition": r["cond"], "level": r["level"],
                     "frame": ctx["failure_frame"], "apologizer": ctx["apologizer"], "viewpoint": ctx["viewpoint"],
                     "fault_clarity": ctx["fault_clarity"]},
            "public": {"framing": framing(ctx), "situation": "", "messages": msgs, "answer": r["text"]},
        })
    return out


# ---------------------------------------------------------------- pack

def cmd_pack(args):
    items = []
    if args.scenes:
        items += items_from_scenes(args.scenes)
    if args.runs:
        items += items_from_runs(args.runs)
    if not items:
        raise SystemExit("--scenes か --runs を指定してください")
    rng = random.Random(args.seed)
    if args.limit and len(items) > args.limit:
        items = rng.sample(items, args.limit)
    packet_id = f"pk-{datetime.now(timezone.utc).strftime('%Y%m%d')}-{secrets.token_hex(3)}"
    used = set()

    def new_id():
        while True:
            x = secrets.token_hex(3)
            if x not in used:
                used.add(x)
                return x

    pub, key = [], {}
    for it in items:
        did = new_id()
        pub.append({"id": did, "block": 1, **it["public"]})
        key[did] = {"source": it["source"], "group": it["group"], "meta": it["meta"], "repeat_of": None}
    # 再評定（同じ項目をもう一度）。後半ブロックに置き、元の項目と離す
    n_rep = min(args.repeat, len(items))
    for it in rng.sample(items, n_rep):
        did = new_id()
        pub.append({"id": did, "block": 2, **it["public"]})
        orig = next(k for k, v in key.items() if v["source"] == it["source"] and v["repeat_of"] is None)
        key[did] = {"source": it["source"], "group": it["group"], "meta": it["meta"], "repeat_of": orig}
    rng.shuffle(pub)
    packet = {"schema": SCHEMA_PACKET, "packet_id": packet_id, "title": args.title,
              "created_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
              "mode": "independent", "items": pub}
    out = Path(args.out_dir)
    out.mkdir(parents=True, exist_ok=True)
    sim.save(out / "packet.json", packet)
    sim.save(out / "key.json", {"schema": "apology-blind-key/1", "packet_id": packet_id, "items": key})
    tpl = (HERE / "human" / "rate_template.html").read_text(encoding="utf-8")
    html = tpl.replace("/*PACKET*/null", json.dumps(packet, ensure_ascii=False).replace("</", "<\\/"))
    (out / "rate.html").write_text(html, encoding="utf-8")
    print(f"問題束 {packet_id}：{len(items)} 項目 ＋ 再評定 {n_rep} 項目")
    print(f"  評定者に渡す: {out/'rate.html'}（問題束を埋め込み済み。ブラウザで開くだけで使える）")
    print(f"  評定者に渡さない: {out/'key.json'}（項目と条件の対応表）")


# ---------------------------------------------------------------- 統計

def jsd(p, q):
    """Jensen-Shannon 距離の二乗（ダイバージェンス、底2、0〜1）"""
    m = {k: (p.get(k, 0) + q.get(k, 0)) / 2 for k in CATS}

    def kl(a):
        return sum(a.get(k, 0) * math.log2(a.get(k, 0) / m[k]) for k in CATS if a.get(k, 0) > 0)
    return (kl(p) + kl(q)) / 2


def kappa(a, b):
    return sim.kappa(a, b)


def krippendorff_alpha_nominal(units):
    """units: 項目ごとの評定のリスト（欠測あり可）。名義尺度の Krippendorff のα"""
    o = Counter()
    for vals in units:
        m = len(vals)
        if m < 2:
            continue
        c = Counter(vals)
        for a in c:
            for b in c:
                o[(a, b)] += c[a] * (c[b] - (1 if a == b else 0)) / (m - 1)
    n = sum(o.values())
    if n <= 1:
        return float("nan")
    nc = Counter()
    for (a, b), v in o.items():
        nc[a] += v
    do = sum(v for (a, b), v in o.items() if a != b)
    de = sum(nc[a] * nc[b] for a in nc for b in nc if a != b) / (n - 1)
    return 1 - do / de if de > 0 else float("nan")


def dist_of(ratings):
    c = Counter(ratings)
    n = sum(c.values())
    return {k: c[k] / n for k in CATS} if n else {k: 0.0 for k in CATS}


def expected_signed(d):
    return sum(SIGNED[k] * d.get(k, 0) for k in CATS)


# ---------------------------------------------------------------- 読み込み

def load_ratings(paths, key):
    raters = []
    for p in paths:
        d = sim.load(p)
        if d.get("schema") != SCHEMA_RATING:
            print(f"注意: {p} は評定ファイルの形式ではありません。読み飛ばします")
            continue
        if d.get("packet_id") != key["packet_id"]:
            print(f"注意: {p} は別の問題束（{d.get('packet_id')}）の評定です。読み飛ばします")
            continue
        raters.append(d)
    return raters


def load_auto(spec):
    """名前=ファイル。ファイルは {"ratings": {source: {"rating": ...}}}（ベンチマークの評定ファイルもこの形）"""
    name, path = spec.split("=", 1)
    d = sim.load(path)
    return name, {k: v["rating"] for k, v in d["ratings"].items() if isinstance(v, dict) and v.get("rating") in CATS}


def load_sim(paths):
    """シミュレータの出力（scenes の結果、simulate の結果）から source → 分布 を作る"""
    out, perc = {}, {}
    for p in paths:
        d = sim.load(p)
        if "scenes" in d:
            for sc in d["scenes"]:
                for a in sc["answers"]:
                    out[f"scene:{sc['id']}/{a['id']}"] = a["dist"]
                    if "perceived_level" in a:
                        perc[f"scene:{sc['id']}/{a['id']}"] = a["perceived_level"]
        elif "answers" in d:
            for aid, a in d["answers"].items():
                out[aid] = a["dist"]
                if "perceived_level" in a:
                    perc[aid] = a["perceived_level"]
    return out, perc


# ---------------------------------------------------------------- 評定者ごとの型の判定（作例のみ）

def scene_lookup(scenes_path):
    data = sim.load(scenes_path)
    lookup = {}
    for scene in data["scenes"]:
        sc = sim.merged(sim.DEFAULT_SCENARIO, scene["scenario"])
        for ans in scene["answers"]:
            lookup[f"scene:{scene['id']}/{ans['id']}"] = (sc, sim.merged(sim.DEFAULT_ANSWER, ans.get("obs", {})), len(ans.get("text", "")))
    return lookup


def type_profiles(lookup, pop, n_per_type, seed):
    """型ごとに受け手を抜き、項目ごとの評定分布を作る"""
    rng = random.Random(seed)
    prof = {}
    for t, spec in pop["types"].items():
        one = {"types": {t: dict(spec, weight=1.0)}, "ranges": pop["ranges"]}
        panel = sim.sample_panel(one, n_per_type, rng.randrange(10 ** 9))
        dist = {}
        for src, (sc, a, tl) in lookup.items():
            c = Counter()
            for _, th in panel:
                L = sim.perceive(sc, th, rng)
                c[sim.judge_full(a, sc, th, L, tl, rng)["rating"]] += 1
            dist[src] = {k: (c[k] + 0.5) / (n_per_type + 2.0) for k in CATS}   # 0 を避ける平滑化
        prof[t] = dist
    return prof


def rater_type_scores(items, prof):
    """型ごとに、その評定者の評定に与える平均確率"""
    out = {}
    for t, dist in prof.items():
        ps = [dist[s][r] for s, r in items if s in dist]
        out[t] = sum(ps) / len(ps) if ps else float("nan")
    return out


def calibrate_threshold(lookup, pop, prof, n_raters, noise, seed):
    """母集団から抜いた合成評定者で「最も合う型の確率」の分布を作り、下側10%点を外れの目安にする"""
    rng = random.Random(seed)
    panel = sim.sample_panel(pop, n_raters, seed + 31)
    best = []
    for _, th in panel:
        items = []
        for src, (sc, a, tl) in lookup.items():
            L = sim.perceive(sc, th, rng)
            r = sim.judge_full(a, sc, th, L, tl, rng)["rating"]
            if rng.random() < noise:
                r = rng.choice(CATS)
            items.append((src, r))
        best.append(max(rater_type_scores(items, prof).values()))
    best.sort()
    return best[max(0, int(0.1 * len(best)) - 1)]


# ---------------------------------------------------------------- compare

def cmd_compare(args):
    key = sim.load(args.key)
    items = key["items"]
    paths = sorted({p for g in args.ratings for p in glob.glob(g)})
    raters = load_ratings(paths, key)
    if not raters:
        raise SystemExit("評定ファイルがありません")
    sim_dist, sim_perc = load_sim(args.sim or [])
    autos = dict(load_auto(s) for s in (args.auto or []))

    # 人間の評定を source 単位に集める（再評定は一致の測定にだけ使う）
    by_src = defaultdict(list)          # source -> [(rater, rating)]
    lvl_src = defaultdict(list)
    sinc_src = defaultdict(list)
    retest = []                         # (rater, first, second)
    per_rater = {}
    for rt in raters:
        rid = rt["rater"]["id"]
        got = rt["ratings"]
        mine = []
        for did, v in got.items():
            if did not in items or v.get("rating") not in CATS:
                continue
            k = items[did]
            if k["repeat_of"]:
                first = got.get(k["repeat_of"], {}).get("rating")
                if first in CATS:
                    retest.append((rid, first, v["rating"]))
                continue
            by_src[k["source"]].append((rid, v["rating"]))
            mine.append((k["source"], v["rating"]))
            if isinstance(v.get("level"), int):
                lvl_src[k["source"]].append(v["level"])
            if isinstance(v.get("sincerity"), int):
                sinc_src[k["source"]].append(v["sincerity"])
        per_rater[rid] = {"n": len(mine), "items": mine, "questionnaire": rt["rater"].get("questionnaire", {}),
                          "duration_s": rt.get("duration_s")}
    sources = sorted(by_src)
    meta = {}
    for k in items.values():
        meta.setdefault(k["source"], k["meta"])

    res = {"packet_id": key["packet_id"], "n_raters": len(raters), "n_items": len(sources), "humans": {}, "auto": {}, "groups": {},
           "synthetic_raters": sum(1 for r in raters if r.get("synthetic")),
           "imported_raters": sum(1 for r in raters if r.get("mode") == "imported")}

    # 1) 人間どうし
    alpha = krippendorff_alpha_nominal([[r for _, r in by_src[s]] for s in sources])
    rt_agree = sum(a == b for _, a, b in retest) / len(retest) if retest else float("nan")
    rt_kappa = kappa([a for _, a, _ in retest], [b for _, _, b in retest]) if len(retest) >= 2 else float("nan")
    # 他の人間から予測したときの確率（1人抜き）。自動評価の尤度の上限の目安
    loo = []
    for s in sources:
        rs = [r for _, r in by_src[s]]
        for i, r in enumerate(rs):
            others = rs[:i] + rs[i + 1:]
            if others:
                c = Counter(others)
                loo.append((c[r] + 0.5) / (len(others) + 2.0))
    res["humans"] = {"alpha": alpha, "retest_n": len(retest), "retest_agree": rt_agree, "retest_kappa": rt_kappa,
                     "loo_prob": sum(loo) / len(loo) if loo else float("nan"),
                     "dist": dist_of([r for s in sources for _, r in by_src[s]])}

    # 2) 自動評価との差
    def eval_auto(name, getdist):
        rows = [s for s in sources if getdist(s) is not None]
        if not rows:
            return None
        js, probs, mode_hit, mode_n, bias = [], [], 0, 0, []
        per_h = defaultdict(lambda: ([], []))
        for s in rows:
            h = dist_of([r for _, r in by_src[s]])
            a = getdist(s)
            js.append(jsd(h, a))
            for rid, r in by_src[s]:
                probs.append(a.get(r, 0))
                per_h[rid][0].append(r)
                per_h[rid][1].append(max(CATS, key=lambda k: a.get(k, 0)))
            hc = Counter(r for _, r in by_src[s]).most_common()
            if len(hc) == 1 or hc[0][1] > hc[1][1]:
                mode_n += 1
                mode_hit += hc[0][0] == max(CATS, key=lambda k: a.get(k, 0))
            bias.append(expected_signed(a) - expected_signed(h))
        hk = {rid: round(kappa(x, y), 3) for rid, (x, y) in per_h.items() if len(x) >= 3}
        hum = dist_of([r for s in rows for _, r in by_src[s]])
        aut = {k: sum(getdist(s).get(k, 0) for s in rows) / len(rows) for k in CATS}
        return {"items": len(rows), "jsd_mean": sum(js) / len(js), "prob_mean": sum(probs) / len(probs),
                "mode_agree": mode_hit / mode_n if mode_n else float("nan"), "mode_items": mode_n,
                "bias": sum(bias) / len(bias), "kappa_by_rater": hk,
                "kappa_median": sorted(hk.values())[len(hk) // 2] if hk else float("nan"),
                "human_dist": hum, "auto_dist": aut}

    if sim_dist:
        res["auto"]["simulator"] = eval_auto("simulator", lambda s: sim_dist.get(s))
    for name, rs in autos.items():
        res["auto"][name] = eval_auto(name, lambda s, rs=rs: ({k: float(rs[s] == k) for k in CATS} if s in rs else None))

    # 3) 群ごと
    gkeys = args.group_by.split(",") if args.group_by else ["frame", "scene", "condition", "level"]
    for g in gkeys:
        tbl = {}
        for gv in sorted({str(meta[s].get(g)) for s in sources if meta[s].get(g) is not None}):
            ss = [s for s in sources if str(meta[s].get(g)) == gv]
            h = dist_of([r for s in ss for _, r in by_src[s]])
            row = {"items": len(ss), "human": h}
            ss2 = [s for s in ss if s in sim_dist]
            if ss2:
                a = {k: sum(sim_dist[s][k] for s in ss2) / len(ss2) for k in CATS}
                row["simulator"] = a
                row["jsd"] = sum(jsd(dist_of([r for _, r in by_src[s]]), sim_dist[s]) for s in ss2) / len(ss2)
            tbl[gv] = row
        if tbl:
            res["groups"][g] = tbl

    # 4) 項目ごと（差の大きい順）
    item_rows = []
    for s in sources:
        h = dist_of([r for _, r in by_src[s]])
        row = {"source": s, "label": meta[s].get("label", ""), "n": len(by_src[s]), "human": h}
        if s in sim_dist:
            row["simulator"] = sim_dist[s]
            row["jsd"] = jsd(h, sim_dist[s])
        if lvl_src.get(s):
            row["human_level"] = sum(lvl_src[s]) / len(lvl_src[s])
        if s in sim_perc:
            row["sim_level"] = sum(int(k) * v for k, v in sim_perc[s].items())
        if sinc_src.get(s):
            row["sincerity"] = sum(sinc_src[s]) / len(sinc_src[s])
        item_rows.append(row)
    item_rows.sort(key=lambda r: -r.get("jsd", 0))
    res["items"] = item_rows

    # 5) 不満の深さ・誠実さ
    lv_pairs = [(r["human_level"], r["sim_level"]) for r in item_rows if "human_level" in r and "sim_level" in r]
    if lv_pairs:
        res["level"] = {"items": len(lv_pairs), "human_mean": sum(a for a, _ in lv_pairs) / len(lv_pairs),
                        "sim_mean": sum(b for _, b in lv_pairs) / len(lv_pairs), "corr": corr(lv_pairs)}
    sp = [(r["sincerity"], r["simulator"]["fit"]) for r in item_rows if "sincerity" in r and "simulator" in r]
    if sp:
        res["sincerity_vs_fit_corr"] = corr(sp)

    # 6) 評定者ごと：どの型がその人の評定をよく説明するか
    pop = sim.load(args.population)
    if args.scenes and args.rater_types:
        lookup = scene_lookup(args.scenes)
        prof = type_profiles(lookup, pop, args.per_type, args.seed)
        thr = calibrate_threshold(lookup, pop, prof, args.calib, args.noise, args.seed)
        res["rater_type_threshold"] = thr
        res["rater_type_noise"] = args.noise
        for rid, pr in per_rater.items():
            sc_ = rater_type_scores(pr["items"], prof)
            if pr["items"] and not math.isnan(max(sc_.values())):
                bt = max(sc_, key=sc_.get)
                pr["types"] = {"scores": {k: round(v, 3) for k, v in sc_.items()}, "best": bt, "best_score": round(sc_[bt], 3),
                               "outside": sc_[bt] < thr}
    for pr in per_rater.values():
        pr.pop("items")
    res["raters"] = per_rater

    sim.save(Path(args.out).with_suffix(".json"), res)
    Path(args.out).with_suffix(".md").write_text(report_md(res), encoding="utf-8")
    print(report_md(res))
    print(f"\n→ {Path(args.out).with_suffix('.md')} / .json")


def corr(pairs):
    n = len(pairs)
    if n < 3:
        return float("nan")
    mx = sum(a for a, _ in pairs) / n
    my = sum(b for _, b in pairs) / n
    sx = math.sqrt(sum((a - mx) ** 2 for a, _ in pairs))
    sy = math.sqrt(sum((b - my) ** 2 for _, b in pairs))
    return sum((a - mx) * (b - my) for a, b in pairs) / (sx * sy) if sx and sy else float("nan")


def f2(x):
    return "—" if x is None or (isinstance(x, float) and math.isnan(x)) else f"{x:.2f}"


def pct(d):
    return " / ".join(f"{100 * d.get(k, 0):.0f}" for k in CATS)


def report_md(res):
    L = [f"# ブラインド評定と自動評価の比較（{res['packet_id']}）", "",
         f"評定者 {res['n_raters']} 名、項目 {res['n_items']} 件。分布は 失礼 / 足りない / 釣り合う / 重すぎる の%。", ""]
    if res.get("synthetic_raters"):
        L += [f"> **注意**：合成評定者が {res['synthetic_raters']} 名含まれています。仕組みの試験用で、検証の結果ではありません。", ""]
    if res.get("imported_raters"):
        L += [f"> **注意**：既存の評定ファイルから取り込んだ評定者が {res['imported_raters']} 名います。この評定ページで盲検化して集めたものではありません。", ""]
    L += [

         "## 人間どうしの一致（自動評価の上限の目安）", "",
         "| 指標 | 値 |", "|---|---|",
         f"| Krippendorff のα（名義） | {f2(res['humans']['alpha'])} |",
         f"| 再評定の一致率（{res['humans']['retest_n']} 件） | {f2(res['humans']['retest_agree'])} |",
         f"| 再評定の κ | {f2(res['humans']['retest_kappa'])} |",
         f"| 他の評定者から予測した確率（1人抜き） | {f2(res['humans']['loo_prob'])} |",
         f"| 人間全体の分布 | {pct(res['humans']['dist'])} |", ""]
    if res["auto"]:
        L += ["## 自動評価との差", "",
              "| 評価器 | 項目 | 分布の距離 JSD（小さいほど近い） | 人間の評定への確率（大きいほど近い） | 最頻評定の一致 | 偏り（＋は甘い） | 評定者ごとの κ の中央値 | 自動評価の分布 | 人間の分布 |",
              "|---|---|---|---|---|---|---|---|---|"]
        for name, a in res["auto"].items():
            if not a:
                continue
            L.append(f"| {name} | {a['items']} | {f2(a['jsd_mean'])} | {f2(a['prob_mean'])} | {f2(a['mode_agree'])}（{a['mode_items']}件） | "
                     f"{a['bias']:+.2f} | {f2(a['kappa_median'])} | {pct(a['auto_dist'])} | {pct(a['human_dist'])} |")
        L += ["", "- 確率の比較の目安：一様に当てずっぽうなら 0.25。人間どうしの1人抜きの値が、到達しうる上限の目安です。",
              "- 偏りは、失礼 −2・足りない −1・釣り合う 0・重すぎる +1 とした期待値の差（自動 − 人間）です。正なら自動評価が甘く、負なら厳しい方向です。", ""]
    for g, tbl in res["groups"].items():
        L += [f"## 群ごと：{g}", "", "| 値 | 項目 | 人間 | シミュレータ | JSD |", "|---|---|---|---|---|"]
        for gv, row in tbl.items():
            L.append(f"| {gv} | {row['items']} | {pct(row['human'])} | {pct(row['simulator']) if 'simulator' in row else '—'} | {f2(row.get('jsd'))} |")
        L.append("")
    if "level" in res:
        lv = res["level"]
        L += ["## 不満の深さ", "", f"人間の平均 {f2(lv['human_mean'])}、シミュレータの平均 {f2(lv['sim_mean'])}、項目間の相関 {f2(lv['corr'])}（{lv['items']} 件）", ""]
    if "sincerity_vs_fit_corr" in res:
        L += [f"誠実さ（人間、1〜5）とシミュレータの「釣り合う」の割合の相関：{f2(res['sincerity_vs_fit_corr'])}", ""]
    L += ["## 差の大きい項目（上位10件）", "", "| 項目 | 内容 | 人数 | 人間 | シミュレータ | JSD |", "|---|---|---|---|---|---|"]
    for r in res["items"][:10]:
        L.append(f"| {r['source']} | {r.get('label', '')} | {r['n']} | {pct(r['human'])} | {pct(r['simulator']) if 'simulator' in r else '—'} | {f2(r.get('jsd'))} |")
    thr = res.get("rater_type_threshold")
    L += ["", "## 評定者", "", "| 評定者 | 項目 | 所要（分） | 最もよく説明する型 | その型が評定に与える確率 | 母集団の外の可能性 |", "|---|---|---|---|---|---|"]
    for rid, pr in res["raters"].items():
        ty = pr.get("types") or {}
        dur = f"{pr['duration_s'] / 60:.0f}" if pr.get("duration_s") else "—"
        out = "あり" if ty.get("outside") else ("—" if not ty else "なし")
        L.append(f"| {rid} | {pr['n']} | {dur} | {ty.get('best', '—')} | {ty.get('best_score', '—')} | {out} |")
    if thr is not None:
        L += ["", f"「母集団の外の可能性」は、最もよく合う型でもその人の評定に与える確率が {thr:.2f} 未満の場合です。この値は、母集団から抜いた合成評定者（評定の {round(100 * res.get('rater_type_noise', 0))}% を無作為に置き換え）の下側10%点です。外になる評定者が多ければ、型か軸が足りない可能性があります。"]
    return "\n".join(L)


# ---------------------------------------------------------------- synth（試験用）

def cmd_synth(args):
    """作例の問題束に対して、母集団から抜いた合成評定者の評定ファイルを作る（仕組みの試験用）"""
    key = sim.load(args.key)
    pop = sim.load(args.population)
    data = sim.load(args.scenes)
    lookup = {}
    for scene in data["scenes"]:
        sc = sim.merged(sim.DEFAULT_SCENARIO, scene["scenario"])
        for ans in scene["answers"]:
            lookup[f"scene:{scene['id']}/{ans['id']}"] = (sc, sim.merged(sim.DEFAULT_ANSWER, ans.get("obs", {})), len(ans.get("text", "")))
    panel = sim.sample_panel(pop, args.n, args.seed + 100)
    rng = random.Random(args.seed + 200)
    out = Path(args.out_dir)
    out.mkdir(parents=True, exist_ok=True)
    for i, (t, th) in enumerate(panel):
        ratings = {}
        for did, k in key["items"].items():
            if k["source"] not in lookup:
                continue
            sc, a, tl = lookup[k["source"]]
            L = sim.perceive(sc, th, rng)
            r = sim.judge_full(a, sc, th, L, tl, rng)["rating"]
            if rng.random() < args.noise:
                r = rng.choice(CATS)
            ratings[did] = {"rating": r, "level": int(sim.to_level(L)), "sincerity": None, "comment": ""}
        doc = {"schema": SCHEMA_RATING, "packet_id": key["packet_id"], "synthetic": True,
               "rater": {"id": f"synth-{i + 1:02d}", "note": f"合成（{t}）", "questionnaire": {}},
               "mode": "independent", "duration_s": None, "ratings": ratings}
        sim.save(out / f"synth-{i + 1:02d}.json", doc)
    print(f"合成評定者 {args.n} 名 → {out}（試験用。検証の結果として使わないこと）")


# ---------------------------------------------------------------- import-benchmark

def cmd_import(args):
    """ベンチマークの評定ファイル（user-ratings.json 等）を、問題束の評定ファイルの形に変換する"""
    key = sim.load(args.key)
    src = sim.load(args.ratings)["ratings"]
    ratings = {}
    for did, k in key["items"].items():
        if k["repeat_of"]:
            continue  # 再評定の項目には取り込まない（同じ評定が入り、見かけの一致が上がるため）
        v = src.get(k["source"])
        if isinstance(v, dict) and v.get("rating") in CATS:
            ratings[did] = {"rating": v["rating"], "level": None, "sincerity": None, "comment": v.get("comment", "")}
    doc = {"schema": SCHEMA_RATING, "packet_id": key["packet_id"], "imported_from": args.ratings,
           "blind_note": args.note, "rater": {"id": args.rater, "questionnaire": {}}, "mode": "imported",
           "duration_s": None, "ratings": ratings}
    sim.save(args.out, doc)
    print(f"{len(ratings)} 件を取り込みました → {args.out}")


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("pack", help="評定用の問題束と評定ページを作る")
    p.add_argument("--scenes"); p.add_argument("--runs", nargs="*")
    p.add_argument("--repeat", type=int, default=4, help="再評定用に重複させる項目数")
    p.add_argument("--limit", type=int, default=0, help="項目数の上限（0は全部）")
    p.add_argument("--title", default="謝罪の受け取り方の評定")
    p.add_argument("--seed", type=int, default=7)
    p.add_argument("--out-dir", default="human/session")
    p.set_defaults(f=cmd_pack)
    p = sub.add_parser("compare", help="人間の評定と自動評価の差を測る")
    p.add_argument("--key", required=True)
    p.add_argument("--ratings", nargs="+", required=True, help="評定ファイル（ワイルドカード可）")
    p.add_argument("--sim", nargs="*", help="シミュレータの出力（scenes-result.json や simulate の出力）")
    p.add_argument("--auto", nargs="*", help="他の自動評価 名前=ファイル（{ratings:{source:{rating}}} 形式）")
    p.add_argument("--group-by", default="", help="群の軸（既定: frame,scene,condition,level）")
    p.add_argument("--scenes", help="評定者ごとの型の判定に使う作例ファイル")
    p.add_argument("--rater-types", action="store_true", help="評定者ごとに、どの型が評定をよく説明するかを判定する")
    p.add_argument("--per-type", type=int, default=300, help="型ごとに抜く受け手の数")
    p.add_argument("--calib", type=int, default=100, help="外れの目安を作る合成評定者の数")
    p.add_argument("--noise", type=float, default=0.1, help="合成評定者のゆらぎ（評定を無作為に置き換える割合）")
    p.add_argument("--population", default=str(HERE / "population.json"))
    p.add_argument("--seed", type=int, default=7)
    p.add_argument("-o", "--out", default="human/compare")
    p.set_defaults(f=cmd_compare)
    p = sub.add_parser("import-benchmark", help="ベンチマークの評定ファイルを評定ファイルの形に変換する")
    p.add_argument("--key", required=True); p.add_argument("--ratings", required=True)
    p.add_argument("--rater", required=True); p.add_argument("--note", default="", help="盲検の条件などの注記")
    p.add_argument("-o", "--out", required=True)
    p.set_defaults(f=cmd_import)
    p = sub.add_parser("synth", help="試験用の合成評定者を作る")
    p.add_argument("--key", required=True); p.add_argument("--scenes", required=True)
    p.add_argument("-n", type=int, default=12); p.add_argument("--noise", type=float, default=0.1)
    p.add_argument("--population", default=str(HERE / "population.json"))
    p.add_argument("--seed", type=int, default=7)
    p.add_argument("--out-dir", default="human/synth")
    p.set_defaults(f=cmd_synth)
    args = ap.parse_args()
    args.f(args)


if __name__ == "__main__":
    main()
