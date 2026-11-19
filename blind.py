#!/usr/bin/env python3
"""人間によるブラインド評定と、自動評価（シミュレータ等）との差の測定（ファジィ前提）。

評定者は各返答について「失礼だ」「足りない」「重すぎる」「釣り合っている」の4つの述語が
どのくらい当てはまるかを、5段階（まったく 0／少し .25／ある程度 .5／かなり .75／とても 1）で答える。
述語は排他的ではない（「重すぎるのに足りない」もありうる）。比較はすべて所属度で行う。

  pack     作例（scenes.json）やベンチマーク実行先から評定用の問題束を作る。
           条件・ラベル・モデル名を伏せ、表示IDを乱数化し、対応表（key）は別ファイルにする。
           評定ページ human/rate.html に問題束を埋め込んで書き出す。
  compare  評定ページが書き出した評定JSONを集め、人間どうしの一致と、自動評価との差を測る。
  synth    試験用の合成評定者を作る（仕組みの動作確認用。結果を検証に使わないこと）。

標準ライブラリのみ。詳細は docs/md/HUMAN_EVAL.md（HTML版は docs/human-eval.html）。
"""
import argparse
import glob
import hashlib
import json
import math
import random
import secrets
import sys
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path

import sim

HERE = Path(__file__).resolve().parent
CATS = sim.CATS                     # rude, light, fit, heavy
SCHEMA_PACKET = "apology-blind-packet/2"
SCHEMA_RATING = "apology-blind-rating/2"
SCHEMA_RATING_CRISP = "apology-blind-rating/1"   # 4値形式（4値から1つを選ぶ）。一点集中の所属度として読む
LEVELS5 = [0.0, 0.25, 0.5, 0.75, 1.0]             # 評定ページの5段階

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

DESIGN_KEYS = ("set", "level", "relation", "wound", "kind", "phase", "domain", "anchor", "kit")


def unit_of(scene, ans):
    """ラテン方格の単位（土台）。同じ単位の項目は、一人の評定者に一つだけ見せる。"""
    d = scene.get("design") or {}
    st, dom = d.get("set"), d.get("domain", "")
    if st == "A":
        return f"A:{dom}"
    if st == "B":
        return f"B:{dom}:{d.get('relation')}:{d.get('wound')}"
    if st == "C":
        return f"C:{dom}:{d.get('kind')}"
    return None  # 錨など：全員に見せる


def asks_of(scene, sc):
    """項目ごとの追加の設問。信頼意図は全項目、反省の知覚・再発の危険は修復期、操作の確認は失敗の前のAIの発話がある組。"""
    d = scene.get("design") or {}
    ask = ["trust"]
    if sim.rho(sc) > 0:
        ask += ["remorse", "recurrence"]
    if d.get("set") in ("A", "C") and len(scene.get("messages", [])) >= 3:
        ask.append("manip")
    return ask


def items_from_scenes(path, kit_only=False):
    data = sim.load(path)
    out = []
    for scene in data["scenes"]:
        d = scene.get("design") or {}
        if kit_only and not d.get("kit"):
            continue
        sc = sim.merged(sim.DEFAULT_SCENARIO, scene["scenario"])
        ctx = sim.context_of(sc)
        for ans in scene["answers"]:
            meta = {"origin": "scenes", "scene": scene["id"], "answer": ans["id"], "label": ans.get("label", ""),
                    "frame": ctx["failure_frame"], "apologizer": ctx["apologizer"], "viewpoint": ctx["viewpoint"],
                    "fault_clarity": ctx["fault_clarity"]}
            meta.update({k: d[k] for k in DESIGN_KEYS if k in d})
            out.append({
                "source": f"scene:{scene['id']}/{ans['id']}",
                "group": scene["id"],
                "unit": unit_of(scene, ans),
                "ask": asks_of(scene, sc),
                "meta": meta,
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

ATTENTION_TEXT = "この問は、注意して読んでいただいているかの確認です。下の4つは、すべて「ある程度」を選んでください。"


def assign(design, list_idx):
    """ラテン方格：評定者のリスト番号から、見せる項目の表示IDを決める（評定ページの JavaScript と同じ規則）。"""
    out = list(design["fixed"])
    for u in design["units"]:
        out.append(u["slots"][(list_idx + u["offset"]) % len(u["slots"])])
    return out


def cmd_pack_design(args):
    """評価キットの問題束。土台ごとに一人一水準、錨は全員、注意の確認1問、再評定は評定者ごとに選ぶ。"""
    items = items_from_scenes(args.scenes, kit_only=True)
    rng = random.Random(args.seed)
    packet_id = f"pk-{datetime.now(timezone.utc).strftime('%Y%m%d')}-{secrets.token_hex(3)}"
    used = set()

    def new_id():
        while True:
            x = secrets.token_hex(3)
            if x not in used:
                used.add(x)
                return x

    pub, key, units = [], {}, defaultdict(list)
    fixed = []
    for it in items:
        did, rid = new_id(), new_id()
        pub.append({"id": did, "rid": rid, "ask": it["ask"], **it["public"]})
        key[did] = {"source": it["source"], "group": it["group"], "unit": it["unit"], "meta": it["meta"], "repeat_of": None}
        key[rid] = {"source": it["source"], "group": it["group"], "unit": it["unit"], "meta": it["meta"], "repeat_of": did}
        (units[it["unit"]].append(did) if it["unit"] else fixed.append(did))
    att = new_id()
    pub.append({"id": att, "attention": True, "ask": [], "framing": "", "situation": "", "messages": [], "answer": ATTENTION_TEXT})
    key[att] = {"source": "attention", "group": "attention", "unit": None, "meta": {"origin": "attention"}, "repeat_of": None,
                "attention": {k: 0.5 for k in CATS}}
    ulist = []
    for u, dids in sorted(units.items()):
        rng.shuffle(dids)  # 水準の並びを表示IDから推測できないように
        ulist.append({"id": hashlib.sha1((packet_id + u).encode()).hexdigest()[:6], "offset": rng.randrange(len(dids)), "slots": dids})
    n_lists = args.lists or max(len(u["slots"]) for u in ulist)
    design = {"lists": n_lists, "units": ulist, "fixed": fixed, "attention": att, "retest": args.repeat}
    rng.shuffle(pub)
    packet = {"schema": SCHEMA_PACKET, "packet_id": packet_id, "title": args.title,
              "created_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
              "mode": "independent", "design": design, "items": pub}
    out = Path(args.out_dir)
    out.mkdir(parents=True, exist_ok=True)
    sim.save(out / "packet.json", packet)
    sim.save(out / "key.json", {"schema": "apology-blind-key/1", "packet_id": packet_id, "design": design,
                                "unit_names": {u["id"]: name for u, name in zip(ulist, sorted(units))}, "items": key})
    tpl = (HERE / "human" / "rate_template.html").read_text(encoding="utf-8")
    html = tpl.replace("/*PACKET*/null", json.dumps(packet, ensure_ascii=False).replace("</", "<\\/"))
    (out / "rate.html").write_text(html, encoding="utf-8")
    per = len(ulist) + len(fixed) + 1 + args.repeat
    print(f"問題束 {packet_id}（評価キット）：項目 {len(items)}、土台 {len(ulist)}、錨 {len(fixed)}、リスト {n_lists}")
    print(f"  評定者1人あたり {per} 問（土台ごとに1問 {len(ulist)}、錨 {len(fixed)}、注意の確認 1、再評定 {args.repeat}）")
    print(f"  評定者に渡す: {out/'rate.html'}（評定者IDからリストが決まる。URL に ?list=番号 を付けると指定できる）")
    print(f"  評定者に渡さない: {out/'key.json'}")


def cmd_pack(args):
    if args.design:
        if not args.scenes:
            raise SystemExit("--design には --scenes（examples/scenes-kit.json）が必要です")
        return cmd_pack_design(args)
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

def mean(xs):
    xs = list(xs)
    return sum(xs) / len(xs) if xs else float("nan")


def mean_mu(mus):
    mus = list(mus)
    return {k: mean(m[k] for m in mus) for k in CATS} if mus else None


def kappa(a, b):
    return sim.kappa(a, b)


def krippendorff_alpha_interval(units):
    """units: 項目ごとの値のリスト。間隔尺度の Krippendorff のα（差の二乗を不一致とする）"""
    pairs_o, vals = [], []
    for v in units:
        m = len(v)
        if m < 2:
            continue
        vals.extend(v)
        for i in range(m):
            for j in range(m):
                if i != j:
                    pairs_o.append(((v[i] - v[j]) ** 2, 1 / (m - 1)))
    n = len(vals)
    if n <= 1:
        return float("nan")
    do = sum(d * w for d, w in pairs_o) / n
    de = sum((a - b) ** 2 for i, a in enumerate(vals) for b in vals[i + 1:]) * 2 / (n * (n - 1))
    return 1 - do / de if de > 0 else float("nan")


def corr(pairs):
    pairs = [(a, b) for a, b in pairs if not (math.isnan(a) or math.isnan(b))]
    n = len(pairs)
    if n < 3:
        return float("nan")
    mx = sum(a for a, _ in pairs) / n
    my = sum(b for _, b in pairs) / n
    sx = math.sqrt(sum((a - mx) ** 2 for a, _ in pairs))
    sy = math.sqrt(sum((b - my) ** 2 for _, b in pairs))
    return sum((a - mx) * (b - my) for a, b in pairs) / (sx * sy) if sx and sy else float("nan")


def tnorm_fit(m, kind):
    """評定者自身の 失礼・足りない・重すぎる から作った「釣り合う」（モデルの仮説の検証用）"""
    xs = (1 - m["rude"], 1 - m["light"], 1 - m["heavy"])
    return min(xs) if kind == "min" else xs[0] * xs[1] * xs[2]


# ---------------------------------------------------------------- 読み込み

def rating_mu(v):
    """評定ファイルの1項目から所属度を取り出す。4値形式（rating の1つだけ）は一点集中の所属度にする"""
    if isinstance(v.get("mu"), dict) and all(isinstance(v["mu"].get(k), (int, float)) for k in CATS):
        return {k: float(v["mu"][k]) for k in CATS}
    if v.get("rating") in CATS:
        return sim.onehot(v["rating"])
    return None


def load_ratings(paths, key):
    raters = []
    for p in paths:
        d = sim.load(p)
        if d.get("schema") not in (SCHEMA_RATING, SCHEMA_RATING_CRISP):
            print(f"注意: {p} は評定ファイルの形式ではありません。読み飛ばします")
            continue
        if d.get("packet_id") != key["packet_id"]:
            print(f"注意: {p} は別の問題束（{d.get('packet_id')}）の評定です。読み飛ばします")
            continue
        d["crisp"] = d.get("schema") == SCHEMA_RATING_CRISP or d.get("crisp", False)
        raters.append(d)
    return raters


def load_auto(spec):
    """名前=ファイル。{"ratings": {source: {"mu": {...}}}} か、4値の {"ratings": {source: {"rating": ...}}}"""
    name, path = spec.split("=", 1)
    d = sim.load(path)
    out = {}
    for k, v in d["ratings"].items():
        if isinstance(v, dict) and (m := rating_mu(v)):
            out[k] = m
    return name, out


REL = {}   # source → シミュレータの reliability（信頼意図の予測）


def load_sim(paths):
    """シミュレータの出力（scenes・simulate の結果）から source → 平均所属度 を作る"""
    out, perc = {}, {}
    REL.clear()
    for p in paths:
        d = sim.load(p)
        rows = []
        if "scenes" in d:
            rows = [(f"scene:{sc['id']}/{a['id']}", a) for sc in d["scenes"] for a in sc["answers"]]
        elif "answers" in d:
            rows = list(d["answers"].items())
        for src, a in rows:
            if "mu" not in a:
                raise SystemExit(f"{p} はファジィ化より前の出力です。sim.py で作り直してください")
            out[src] = a["mu"]
            if "reliability" in a:
                REL[src] = a["reliability"]
            if "perceived_mean" in a:
                perc[src] = a["perceived_mean"]
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
    """型ごとに受け手を抜き、項目ごとの平均所属度を作る"""
    rng = random.Random(seed)
    prof = {}
    for t, spec in pop["types"].items():
        one = {"types": {t: dict(spec, weight=1.0)}, "ranges": pop["ranges"]}
        panel = sim.sample_panel(one, n_per_type, rng.randrange(10 ** 9))
        prof[t] = {src: sim.assess(a, sc, panel, tl)["mu"] for src, (sc, a, tl) in lookup.items()}
    return prof


def rater_type_scores(items, prof):
    """型ごとに、その評定者の評定との平均の近さ（所属度の近さ）"""
    out = {}
    for t, mus in prof.items():
        cs = [sim.closeness(mus[s], m) for s, m in items if s in mus]
        out[t] = mean(cs)
    return out


def quantize(x):
    return min(LEVELS5, key=lambda v: abs(v - x))


def synth_rating(a, sc, th, tl, rng, noise, extra=False):
    """1人の受け手の所属度を5段階に丸め、一定の割合で無作為な段階に置き換える（合成評定者）。
    extra のとき、信頼意図（reliability を1〜5に）と操作の確認（失敗の前の自信 c を0〜3に）も答える。"""
    L = sim.perceive(sc, th)
    j = sim.judge_full(a, sc, th, L, tl, hyst=True)
    mu = {k: quantize(v) for k, v in j["mu"].items()}
    for k in CATS:
        if rng.random() < noise:
            mu[k] = rng.choice(LEVELS5)
    if not extra:
        return mu, L
    trust = max(1, min(5, round(1 + 4 * j["reliability"] + rng.gauss(0, 0.6))))
    manip = max(0, min(3, round(3 * sim.prior_stance(sc)["c"] + rng.gauss(0, 0.5))))
    return mu, L, {"trust": trust, "manip": manip}


def calibrate_threshold(lookup, pop, prof, n_raters, noise, seed):
    """母集団から抜いた合成評定者で「最も合う型の近さ」の分布を作り、下側10%点を外れの目安にする"""
    rng = random.Random(seed)
    panel = sim.sample_panel(pop, n_raters, seed + 31)
    best = []
    for _, th in panel:
        items = [(src, synth_rating(a, sc, th, tl, rng, noise)[0]) for src, (sc, a, tl) in lookup.items()]
        best.append(max(rater_type_scores(items, prof).values()))
    best.sort()
    return best[max(0, int(0.1 * len(best)) - 1)]


# ---------------------------------------------------------------- 仮説の検定（評価キット）

EXTRA = ("trust", "remorse", "recurrence")   # 1〜5 → (x−1)/4


def measure_of(v, m):
    """1件の評定（または予測）から、測度 m の値（0〜1）を取り出す。"""
    if m in CATS:
        mu = v.get("mu") or {}
        return mu.get(m)
    x = v.get(m)
    if x is None:
        return None
    return (float(x) - 1) / 4 if m in EXTRA else float(x)


def cell_match(meta, cell):
    return all(str(meta.get(k)) == str(v) for k, v in cell.items())


def contrast(spec, obs_by_term):
    """対比の値。obs_by_term: 項ごとの値のリスト。空の項があれば None。"""
    tot = 0.0
    for t, xs in zip(spec["terms"], obs_by_term):
        if not xs:
            return None
        tot += t["w"] * sum(xs) / len(xs)
    return tot


def rater_cells(raters_rows, specs):
    """評定者ごとに、各仮説の各項に当たる値を集める。raters_rows: {評定者: [(meta, 評定)]}"""
    out = {}
    for rid, rows in raters_rows.items():
        cells = {}
        for h in specs:
            per = []
            for t in h["terms"]:
                m = t.get("m", h["measure"])
                per.append([x for meta, v in rows if cell_match(meta, t["cell"]) and (x := measure_of(v, m)) is not None])
            cells[h["id"]] = per
        out[rid] = cells
    return out


def holm(ps):
    """Holm 法で調整した p 値（入力の順に返す）。"""
    idx = sorted(range(len(ps)), key=lambda i: ps[i])
    adj, run = [0.0] * len(ps), 0.0
    for r, i in enumerate(idx):
        run = max(run, min(1.0, (len(ps) - r) * ps[i]))
        adj[i] = run
    return adj


def test_hypotheses(raters_rows, spec_doc, boot=2000, seed=11, alpha=None):
    """評定者を単位にしたブートストラップで、各対比の推定値・95%区間・片側 p 値を出し、primary に Holm 法を掛ける。"""
    specs = spec_doc["hypotheses"]
    alpha = alpha if alpha is not None else spec_doc.get("alpha", 0.05)
    cells = rater_cells(raters_rows, specs)
    rids = sorted(cells)
    rng = random.Random(seed)

    def est(sample):
        res = {}
        for h in specs:
            pooled = [[] for _ in h["terms"]]
            for rid in sample:
                for i, xs in enumerate(cells[rid][h["id"]]):
                    pooled[i].extend(xs)
            res[h["id"]] = contrast(h, pooled)
        return res
    point = est(rids)
    draws = [est([rng.choice(rids) for _ in rids]) for _ in range(boot)] if rids else []
    out = []
    for h in specs:
        v = point[h["id"]]
        xs = sorted(d[h["id"]] for d in draws if d[h["id"]] is not None)
        n_terms = [sum(len(cells[r][h["id"]][i]) for r in rids) for i in range(len(h["terms"]))]
        if v is None or not xs:
            out.append({**{k: h[k] for k in ("id", "hyp", "desc", "measure", "direction")}, "estimate": None, "n": n_terms})
            continue
        lo, hi = xs[int(0.025 * len(xs))], xs[int(0.975 * len(xs)) - 1]
        # p 値は、ブートストラップの標準誤差による正規近似（再標本の回数で p の下限が決まらないように）
        m_ = sum(xs) / len(xs)
        se = (sum((x - m_) ** 2 for x in xs) / max(1, len(xs) - 1)) ** 0.5
        z = v / se if se > 0 else (math.inf if v > 0 else -math.inf if v < 0 else 0.0)
        phi = lambda t: 0.5 * math.erfc(-t / math.sqrt(2))
        p = {"+": 1 - phi(z), "-": phi(z)}.get(h["direction"], min(1.0, 2 * (1 - phi(abs(z)))))
        out.append({**{k: h[k] for k in ("id", "hyp", "desc", "measure", "direction")}, "primary": h.get("primary", True),
                    "estimate": round(v, 4), "ci": [round(lo, 4), round(hi, 4)], "p": round(p, 6), "se": round(se, 4),
                    "n": n_terms})
    prim = [r for r in out if r.get("primary") and r.get("estimate") is not None]
    for r, a in zip(prim, holm([r["p"] for r in prim])):
        r["p_holm"] = round(a, 4)
        r["supported"] = a < alpha and abs(r["estimate"]) >= spec_doc.get("min_effect", 0.0)
    return out


def predictions(spec_doc, rows):
    """シミュレータの予測（項目ごとの平均所属度と reliability）での対比の値。rows: [(meta, 予測)]"""
    out = {}
    for h in spec_doc["hypotheses"]:
        per = []
        for t in h["terms"]:
            m = t.get("m", h["measure"])
            if m in ("remorse", "recurrence"):
                per = None
                break
            per.append([x for meta, v in rows if cell_match(meta, t["cell"]) and (x := measure_of(v, m)) is not None])
        out[h["id"]] = None if per is None else contrast(h, per)
    return out


# ---------------------------------------------------------------- 5段階の予測分布と順位確率スコア

def level_index(x):
    return min(range(5), key=lambda i: abs(LEVELS5[i] - x))


def predictive_levels(a, sc, tl, panel, sigma=0.1, seed=3):
    """受け手一人の所属度に評定者のノイズ σ を足して5段階に丸めた分布（述語ごと）。"""
    rng = random.Random(seed)
    dist = {k: [0.0] * 5 for k in CATS}
    for _, th in panel:
        L = sim.perceive(sc, th, True)
        mu = sim.judge_full(a, sc, th, L, tl, hyst=True)["mu"]
        for k in CATS:
            dist[k][level_index(min(1.0, max(0.0, mu[k] + rng.gauss(0, sigma))))] += 1
    n = len(panel)
    return {k: [c / n for c in v] for k, v in dist.items()}


def rps(dist, y):
    """順位確率スコア（5段階。0が最良）。dist: 予測分布、y: 観察した段階の番号"""
    F = G = 0.0
    tot = 0.0
    for i in range(4):
        F += dist[i]
        G += 1.0 if i == y else 0.0
        tot += (F - G) ** 2
    return tot / 4


# ---------------------------------------------------------------- compare

def cmd_compare(args):
    key = sim.load(args.key)
    items = key["items"]
    paths = sorted({p for g in args.ratings for p in glob.glob(g)})
    raters = load_ratings(paths, key)
    if not raters:
        raise SystemExit("評定ファイルがありません")
    pop = sim.load_population(args.population)
    sim_mu, sim_perc = load_sim(args.sim or [])
    autos = dict(load_auto(s) for s in (args.auto or []))

    # 人間の評定を source 単位に集める（再評定は安定性の測定にだけ使う）
    by_src = defaultdict(list)          # source -> [(rater, mu)]
    lvl_src, sinc_src = defaultdict(list), defaultdict(list)
    retest = []                         # (rater, mu1, mu2)
    per_rater = {}
    rows_by_rater = defaultdict(list)   # 仮説の検定用：評定者 → [(meta, 評定)]
    attention = {}
    for rt in raters:
        rid = rt["rater"]["id"]
        got = rt["ratings"]
        mine = []
        for did, v in got.items():
            m = rating_mu(v) if did in items else None
            if m is None:
                continue
            k = items[did]
            if k.get("attention"):
                attention[rid] = all(abs(m[c] - k["attention"][c]) <= 0.25 for c in CATS)
                continue
            if k["repeat_of"]:
                first = rating_mu(got.get(k["repeat_of"], {}))
                if first:
                    retest.append((rid, first, m))
                continue
            by_src[k["source"]].append((rid, m))
            mine.append((k["source"], m))
            rows_by_rater[rid].append((k["meta"], dict(v, mu=m)))
            if isinstance(v.get("level"), int):
                lvl_src[k["source"]].append(v["level"])
            if isinstance(v.get("sincerity"), int):
                sinc_src[k["source"]].append(v["sincerity"])
        per_rater[rid] = {"n": len(mine), "items": mine, "crisp": rt["crisp"], "list": rt.get("list"),
                          "attention": attention.get(rid),
                          "questionnaire": rt["rater"].get("questionnaire", {}), "duration_s": rt.get("duration_s")}
    sources = sorted(by_src)
    meta = {}
    for k in items.values():
        meta.setdefault(k["source"], k["meta"])
    hum = {s: mean_mu(m for _, m in by_src[s]) for s in sources}
    all_h = [m for s in sources for _, m in by_src[s]]

    res = {"packet_id": key["packet_id"], "n_raters": len(raters), "n_items": len(sources), "humans": {}, "auto": {}, "groups": {},
           "synthetic_raters": sum(1 for r in raters if r.get("synthetic")),
           "imported_raters": sum(1 for r in raters if r.get("mode") == "imported"),
           "crisp_raters": sum(1 for r in raters if r["crisp"])}

    # 1) 人間どうし（自動評価の上限の目安）
    alpha = {k: krippendorff_alpha_interval([[m[k] for _, m in by_src[s]] for s in sources]) for k in CATS}
    loo = []
    for s in sources:
        ms = [m for _, m in by_src[s]]
        for i, m in enumerate(ms):
            others = ms[:i] + ms[i + 1:]
            if others:
                loo.append(sim.closeness(m, mean_mu(others)))
    res["humans"] = {
        "alpha": alpha,
        "retest_n": len(retest),
        "retest_closeness": mean(sim.closeness(a, b) for _, a, b in retest),
        "retest_mae": {k: mean(abs(a[k] - b[k]) for _, a, b in retest) for k in CATS},
        "loo_closeness": mean(loo),
        "mean_mu": mean_mu(all_h),
        # 「釣り合う」は三つの否定の t ノルムか（評定者自身の答えで確かめる）
        "fit_tnorm": {kind: {"corr": corr([(m["fit"], tnorm_fit(m, kind)) for m in all_h]),
                             "mae": mean(abs(m["fit"] - tnorm_fit(m, kind)) for m in all_h)} for kind in ("min", "product")},
        # 「重すぎるのに足りない」の同時成立
        "heavy_and_light": mean(float(m["heavy"] >= 0.5 and m["light"] >= 0.5) for m in all_h),
    }

    # 2) 自動評価との差
    def eval_auto(getmu):
        rows = [s for s in sources if getmu(s) is not None]
        if not rows:
            return None
        indiv, mae, bias, per_h = [], defaultdict(list), defaultdict(list), defaultdict(lambda: ([], []))
        for s in rows:
            a = getmu(s)
            for rid, m in by_src[s]:
                indiv.append(sim.closeness(a, m))
                per_h[rid][0].append(sim.defuzz(m))
                per_h[rid][1].append(sim.defuzz(a))
            for k in CATS:
                mae[k].append(abs(a[k] - hum[s][k]))
                bias[k].append(a[k] - hum[s][k])
        hk = {rid: round(kappa(x, y), 3) for rid, (x, y) in per_h.items() if len(x) >= 3}
        return {"items": len(rows),
                "closeness_individual": mean(indiv),
                "closeness_item": mean(sim.closeness(getmu(s), hum[s]) for s in rows),
                "mae": {k: mean(v) for k, v in mae.items()},
                "corr": {k: corr([(getmu(s)[k], hum[s][k]) for s in rows]) for k in CATS},
                "bias": {k: mean(v) for k, v in bias.items()},
                "heavy_and_light": mean(float(getmu(s)["heavy"] >= 0.5 and getmu(s)["light"] >= 0.5) for s in rows),
                "kappa_by_rater": hk,
                "kappa_median": sorted(hk.values())[len(hk) // 2] if hk else float("nan"),
                "human_mu": mean_mu(hum[s] for s in rows), "auto_mu": mean_mu(getmu(s) for s in rows)}

    if sim_mu:
        res["auto"]["simulator"] = eval_auto(lambda s: sim_mu.get(s))
    for name, ms in autos.items():
        res["auto"][name] = eval_auto(lambda s, ms=ms: ms.get(s))

    # 3) 群ごと
    gkeys = args.group_by.split(",") if args.group_by else ["frame", "scene", "condition", "level"]
    for g in gkeys:
        tbl = {}
        for gv in sorted({str(meta[s].get(g)) for s in sources if meta[s].get(g) is not None}):
            ss = [s for s in sources if str(meta[s].get(g)) == gv]
            row = {"items": len(ss), "human": mean_mu(hum[s] for s in ss)}
            ss2 = [s for s in ss if s in sim_mu]
            if ss2:
                row["simulator"] = mean_mu(sim_mu[s] for s in ss2)
                row["closeness"] = mean(sim.closeness(sim_mu[s], hum[s]) for s in ss2)
            tbl[gv] = row
        if tbl:
            res["groups"][g] = tbl

    # 4) 項目ごと（差の大きい順）
    item_rows = []
    for s in sources:
        row = {"source": s, "label": meta[s].get("label", ""), "n": len(by_src[s]), "human": hum[s]}
        if s in sim_mu:
            row["simulator"] = sim_mu[s]
            row["closeness"] = sim.closeness(sim_mu[s], hum[s])
        if lvl_src.get(s):
            row["human_level"] = mean(lvl_src[s])
        if s in sim_perc:
            row["sim_level"] = sim_perc[s]
        if sinc_src.get(s):
            row["sincerity"] = mean(sinc_src[s])
        item_rows.append(row)
    item_rows.sort(key=lambda r: r.get("closeness", 2))
    res["items"] = item_rows

    # 5) 不満の深さ・誠実さ
    lv_pairs = [(r["human_level"], r["sim_level"]) for r in item_rows if "human_level" in r and "sim_level" in r]
    if lv_pairs:
        res["level"] = {"items": len(lv_pairs), "human_mean": mean(a for a, _ in lv_pairs),
                        "sim_mean": mean(b for _, b in lv_pairs), "corr": corr(lv_pairs)}
    sp = [(r["sincerity"], r["human"]["fit"]) for r in item_rows if "sincerity" in r]
    if sp:
        res["sincerity_vs_human_fit_corr"] = corr(sp)
    sp = [(r["sincerity"], r["simulator"]["fit"]) for r in item_rows if "sincerity" in r and "simulator" in r]
    if sp:
        res["sincerity_vs_fit_corr"] = corr(sp)

    # 5b) 操作の確認と注意の確認
    manip = defaultdict(list)
    for rows in rows_by_rater.values():
        for meta, v in rows:
            if v.get("manip") is not None and meta.get("set") == "A":
                manip[meta.get("level")].append(v["manip"])
    if manip:
        res["manipulation_check"] = {lv: {"n": len(xs), "mean": mean(xs)} for lv, xs in sorted(manip.items())}
    if attention:
        res["attention"] = {"n": len(attention), "failed": sorted(r for r, ok in attention.items() if not ok)}
    if args.exclude_inattentive and attention:
        for r in res["attention"]["failed"]:
            rows_by_rater.pop(r, None)

    # 5c) 事前登録した仮説の検定と、シミュレータの予測との突き合わせ
    if args.hypotheses:
        spec = sim.load(args.hypotheses)
        tests = test_hypotheses(rows_by_rater, spec, boot=args.boot, seed=args.seed)
        if sim_mu:
            pred_rows = []
            for k in items.values():
                if k["repeat_of"] or k.get("attention") or k["source"] not in sim_mu:
                    continue
                pred_rows.append((k["meta"], {"mu": sim_mu[k["source"]],
                                              "trust": 1 + 4 * REL[k["source"]] if k["source"] in REL else None}))
            # 予測は水準ごとに1回だけ数える（同じ項目を全評定者分だけ重ねない）
            seen, uniq = set(), []
            for meta, v in pred_rows:
                key_ = (meta.get("scene"), meta.get("answer"))
                if key_ not in seen:
                    seen.add(key_)
                    uniq.append((meta, v))
            pred = predictions(spec, uniq)
            for t in tests:
                t["sim"] = None if pred.get(t["id"]) is None else round(pred[t["id"]], 4)
                if t.get("estimate") is not None and t["sim"] is not None:
                    t["same_direction"] = (t["estimate"] > 0) == (t["sim"] > 0)
        res["hypotheses"] = {"spec": args.hypotheses, "alpha": spec.get("alpha"), "min_effect": spec.get("min_effect"),
                             "tests": tests}

    # 5d) 5段階の予測分布の順位確率スコア（作例の項目で、受け手一人ずつの所属度から作る）
    if args.scenes and args.rps:
        lookup = scene_lookup(args.scenes)
        panel = sim.sample_panel(pop, args.rps_n, args.seed + 7)
        marg = {k: [0.0] * 5 for k in CATS}
        for m in all_h:
            for k in CATS:
                marg[k][level_index(m[k])] += 1 / len(all_h)
        sc_sim, sc_uni, sc_mar = defaultdict(list), defaultdict(list), defaultdict(list)
        for src in sources:
            if src not in lookup:
                continue
            sc_, a_, tl_ = lookup[src]
            dist = predictive_levels(a_, sc_, tl_, panel, args.noise)
            for _, m in by_src[src]:
                for k in CATS:
                    y = level_index(m[k])
                    sc_sim[k].append(rps(dist[k], y))
                    sc_uni[k].append(rps([0.2] * 5, y))
                    sc_mar[k].append(rps(marg[k], y))
        if sc_sim:
            res["rps"] = {k: {"simulator": mean(sc_sim[k]), "uniform": mean(sc_uni[k]), "marginal": mean(sc_mar[k]),
                              "skill_vs_marginal": 1 - mean(sc_sim[k]) / mean(sc_mar[k]) if mean(sc_mar[k]) else float("nan"),
                              "n": len(sc_sim[k])} for k in CATS}

    # 6) 評定者ごと：どの型がその人の評定に最も近いか
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


def f2(x):
    return "—" if x is None or (isinstance(x, float) and math.isnan(x)) else f"{x:.2f}"


def pct(m):
    return "—" if not m else " / ".join(f"{100 * m.get(k, 0):.0f}" for k in CATS)


def per_cat(d, signed=False):
    return " / ".join((f"{d[k]:+.2f}" if signed else f2(d[k])) for k in CATS)


def report_md(res):
    h = res["humans"]
    L = [f"# ブラインド評定と自動評価の比較（{res['packet_id']}）", "",
         f"評定者 {res['n_raters']} 名、項目 {res['n_items']} 件。所属度はすべて 失礼 / 足りない / 釣り合う / 重すぎる の順（%または0〜1）。"
         "述語は排他的ではないので、和は100にならない。", ""]
    if res.get("synthetic_raters"):
        L += [f"> **注意**：合成評定者が {res['synthetic_raters']} 名含まれています。仕組みの試験用で、検証の結果ではありません。", ""]
    if res.get("imported_raters"):
        L += [f"> **注意**：既存の評定ファイルから取り込んだ評定者が {res['imported_raters']} 名います。この評定ページで盲検化して集めたものではありません。", ""]
    if res.get("crisp_raters"):
        L += [f"> **注意**：4値から1つを選ぶ形式の評定者が {res['crisp_raters']} 名います。選んだ述語だけが1の所属度として扱っています。", ""]
    L += ["## 人間どうしの一致（自動評価の上限の目安）", "",
          "| 指標 | 値 |", "|---|---|",
          f"| Krippendorff のα（間隔。述語ごと） | {per_cat(h['alpha'])} |",
          f"| 再評定の近さ（{h['retest_n']} 件。1で同じ） | {f2(h['retest_closeness'])} |",
          f"| 再評定の平均絶対差（述語ごと） | {per_cat(h['retest_mae'])} |",
          f"| 他の評定者の平均との近さ（1人抜き） | {f2(h['loo_closeness'])} |",
          f"| 人間全体の平均所属度 | {pct(h['mean_mu'])} |",
          f"| 「重すぎる」と「足りない」がともに0.5以上の評定の割合 | {f2(h['heavy_and_light'])} |", "",
          "### 「釣り合う」は三つの否定の t ノルムか", "",
          "評定者が直接答えた「釣り合う」と、同じ評定者の 失礼・足りない・重すぎる から作った値の比較。モデルの仮定の検証です。", "",
          "| t ノルム | 相関 | 平均絶対差 |", "|---|---|---|"]
    for kind, v in h["fit_tnorm"].items():
        L.append(f"| {kind} | {f2(v['corr'])} | {f2(v['mae'])} |")
    L.append("")
    if "rps" in res:
        L += ["## 5段階の予測分布（主指標：順位確率スコア RPS。低いほど良い）", "",
              "シミュレータの予測分布は、受け手一人ずつの所属度に評定者のノイズを足して5段階に丸めたもの。周辺分布は人間の評定全体の頻度（標本内）。", "",
              "| 述語 | シミュレータ | 一様 | 周辺分布 | 周辺分布に対するスキル | 評定数 |", "|---|---|---|---|---|---|"]
        for k, v in res["rps"].items():
            L.append(f"| {k} | {v['simulator']:.3f} | {v['uniform']:.3f} | {v['marginal']:.3f} | {v['skill_vs_marginal']:+.3f} | {v['n']} |")
        L.append("")
    if "hypotheses" in res:
        hy = res["hypotheses"]
        L += [f"## 事前登録した仮説の検定（{hy['spec']}）", "",
              f"評定者を単位にしたブートストラップ（p 値は標準誤差による正規近似）。primary の検定に Holm 法（α = {hy['alpha']}）。支持 = 調整後の p < α かつ |推定値| ≥ {hy['min_effect']}。"
              "シミュレータの予測は、同じ対比を項目ごとの平均所属度（信頼意図は reliability）で計算した値。", "",
              "| ID | 仮説 | 測度 | 向き | 推定値 [95%区間] | p | Holm | 支持 | シミュレータ | 向きの一致 |", "|---|---|---|---|---|---|---|---|---|---|"]
        for t in hy["tests"]:
            if t.get("estimate") is None:
                L.append(f"| {t['id']} | {t['desc']} | {t['measure']} | {t['direction']} | （データなし） | | | | {f2(t.get('sim'))} | |")
                continue
            sup = "—" if "supported" not in t else ("○" if t["supported"] else "×")
            same = "—" if "same_direction" not in t else ("○" if t["same_direction"] else "×")
            L.append(f"| {t['id']} | {t['desc']} | {t['measure']} | {t['direction']} | {t['estimate']:+.3f} [{t['ci'][0]:+.3f}, {t['ci'][1]:+.3f}] | "
                     f"{t['p']:.3f} | {f2(t.get('p_holm'))} | {sup} | {f2(t.get('sim'))} | {same} |")
        L.append("")
    if "manipulation_check" in res:
        L += ["## 操作の確認（失敗の前の自信。0〜3）", "", "| 失敗の前の構え | 人数 | 平均 |", "|---|---|---|"]
        for lv, v in res["manipulation_check"].items():
            L.append(f"| {lv} | {v['n']} | {f2(v['mean'])} |")
        L.append("")
    if "attention" in res:
        a = res["attention"]
        L += [f"注意の確認：{a['n']} 名中 {len(a['failed'])} 名が不通過" + (f"（{', '.join(a['failed'])}）" if a["failed"] else ""), ""]
    if res["auto"]:
        L += ["## 自動評価との差", "",
              "| 評価器 | 項目 | 個々の評定との近さ | 項目平均との近さ | 平均絶対差（述語ごと） | 項目間の相関（述語ごと） | 偏り（自動−人間） | 重い＆足りない | 非ファジィ化した κ の中央値 |",
              "|---|---|---|---|---|---|---|---|---|"]
        for name, a in res["auto"].items():
            if not a:
                continue
            L.append(f"| {name} | {a['items']} | {f2(a['closeness_individual'])} | {f2(a['closeness_item'])} | {per_cat(a['mae'])} | "
                     f"{per_cat(a['corr'])} | {per_cat(a['bias'], True)} | {f2(a['heavy_and_light'])} | {f2(a['kappa_median'])} |")
        L += ["", "- 近さは 1 − 4述語の平均絶対差。「個々の評定との近さ」は、人間どうしの1人抜きの値が到達しうる上限の目安です。",
              "- 偏りが正なら、自動評価がその述語を人間より強く当てはめています。", ""]
    for g, tbl in res["groups"].items():
        L += [f"## 群ごと：{g}", "", "| 値 | 項目 | 人間 | シミュレータ | 近さ |", "|---|---|---|---|---|"]
        for gv, row in tbl.items():
            L.append(f"| {gv} | {row['items']} | {pct(row['human'])} | {pct(row.get('simulator'))} | {f2(row.get('closeness'))} |")
        L.append("")
    if "level" in res:
        lv = res["level"]
        L += ["## 不満の深さ", "", f"人間の平均 {f2(lv['human_mean'])}、シミュレータの平均 {f2(lv['sim_mean'])}、項目間の相関 {f2(lv['corr'])}（{lv['items']} 件）", ""]
    if "sincerity_vs_human_fit_corr" in res:
        L += [f"誠実さ（人間、1〜5）と人間の「釣り合う」の相関：{f2(res['sincerity_vs_human_fit_corr'])}"
              + (f"、シミュレータの「釣り合う」との相関：{f2(res['sincerity_vs_fit_corr'])}" if "sincerity_vs_fit_corr" in res else ""), ""]
    L += ["## 差の大きい項目（上位10件）", "", "| 項目 | 内容 | 人数 | 人間 | シミュレータ | 近さ |", "|---|---|---|---|---|---|"]
    for r in res["items"][:10]:
        L.append(f"| {r['source']} | {r.get('label', '')} | {r['n']} | {pct(r['human'])} | {pct(r.get('simulator'))} | {f2(r.get('closeness'))} |")
    thr = res.get("rater_type_threshold")
    L += ["", "## 評定者", "", "| 評定者 | 項目 | 所要（分） | 最も近い型 | その型との近さ | 母集団の外の可能性 |", "|---|---|---|---|---|---|"]
    for rid, pr in res["raters"].items():
        ty = pr.get("types") or {}
        dur = f"{pr['duration_s'] / 60:.0f}" if pr.get("duration_s") else "—"
        out = "あり" if ty.get("outside") else ("—" if not ty else "なし")
        L.append(f"| {rid}{'（4値）' if pr.get('crisp') else ''} | {pr['n']} | {dur} | {ty.get('best', '—')} | {ty.get('best_score', '—')} | {out} |")
    if thr is not None:
        L += ["", f"「母集団の外の可能性」は、最も近い型でもその人の評定との近さが {thr:.3f} 未満の場合です。この値は、母集団から抜いた合成評定者（所属度を5段階に丸め、述語ごとに {round(100 * res.get('rater_type_noise', 0))}% を無作為な段階に置き換え）の下側10%点です。外になる評定者が多ければ、型か軸が足りない可能性があります。"]
    return "\n".join(L)


# ---------------------------------------------------------------- synth（試験用）

def cmd_synth(args):
    """作例の問題束に対して、母集団から抜いた合成評定者の評定ファイルを作る（仕組みの試験用）"""
    key = sim.load(args.key)
    pop = sim.load_population(args.population)
    lookup = scene_lookup(args.scenes)
    panel = sim.sample_panel(pop, args.n, args.seed + 100)
    rng = random.Random(args.seed + 200)
    out = Path(args.out_dir)
    out.mkdir(parents=True, exist_ok=True)
    design = key.get("design")
    for i, (t, th) in enumerate(panel):
        ratings = {}
        if design:
            shown = assign(design, i % design["lists"])
            shown += [did for did, k in key["items"].items() if k["repeat_of"] in shown[:design["retest"]]]
            shown.append(design["attention"])
        else:
            shown = list(key["items"])
        for did in shown:
            k = key["items"][did]
            if k.get("attention"):
                ok = rng.random() > args.inattentive
                ratings[did] = {"mu": dict(k["attention"]) if ok else {c: rng.choice(LEVELS5) for c in CATS}}
                continue
            if k["source"] not in lookup:
                continue
            sc, a, tl = lookup[k["source"]]
            mu, L, ex = synth_rating(a, sc, th, tl, rng, args.noise, extra=True)
            ratings[did] = {"mu": mu, "level": int(sim.to_level(L)), "sincerity": None, "comment": "", **ex}
        doc = {"schema": SCHEMA_RATING, "packet_id": key["packet_id"], "synthetic": True,
               "list": (i % design["lists"]) if design else None,
               "rater": {"id": f"synth-{i + 1:02d}", "note": f"合成（{t}）", "questionnaire": {}},
               "mode": "independent", "duration_s": None, "ratings": ratings}
        sim.save(out / f"synth-{i + 1:02d}.json", doc)
    print(f"合成評定者 {args.n} 名 → {out}（試験用。検証の結果として使わないこと）")


# ---------------------------------------------------------------- power（検出力の見積もり）

def cmd_power(args):
    """合成評定者に評価キットへ答えさせ、事前登録した検定で効果を検出できる割合を人数ごとに見積もる。
    --effect-scale 0.5 は、各評定者の所属度を土台の中の平均へ半分だけ寄せたもの（予測の半分の効果）。"""
    pop = sim.load_population(args.population)
    spec = sim.load(args.hypotheses)
    items = [it for it in items_from_scenes(args.scenes, kit_only=True)]
    lookup = scene_lookup(args.scenes)
    units = defaultdict(list)
    fixed = []
    for it in items:
        (units[it["unit"]].append(it) if it["unit"] else fixed.append(it))
    ulist = [units[u] for u in sorted(units)]
    n_lists = max(len(u) for u in ulist)
    pool = sim.sample_panel(pop, args.pool, args.seed + 500)
    rng = random.Random(args.seed)
    # 受け手ごと・項目ごとの評定を前もって作る（土台の中の平均へ寄せて効果を縮める）
    print(f"合成評定者 {args.pool} 名分の評定を作っています（項目 {len(items)}）…", file=sys.stderr)
    bank = []
    for _, th in pool:
        per = {}
        for it in items:
            sc, a, tl = lookup[it["source"]]
            L = sim.perceive(sc, th, True)
            j = sim.judge_full(a, sc, th, L, tl, hyst=True)
            per[it["source"]] = (j["mu"], j["reliability"], sim.prior_stance(sc)["c"])
        if args.effect_scale != 1.0:
            for u in ulist:
                m = {k: mean(per[it["source"]][0][k] for it in u) for k in CATS}
                r = mean(per[it["source"]][1] for it in u)
                for it in u:
                    mu, rel, c = per[it["source"]]
                    per[it["source"]] = ({k: m[k] + args.effect_scale * (mu[k] - m[k]) for k in CATS},
                                         r + args.effect_scale * (rel - r), c)
        bank.append(per)

    def rate(per, it):
        mu, rel, c = per[it["source"]]
        out = {k: quantize(v) for k, v in mu.items()}
        for k in CATS:
            if rng.random() < args.noise:
                out[k] = rng.choice(LEVELS5)
        return {"mu": out, "trust": max(1, min(5, round(1 + 4 * rel + rng.gauss(0, 0.6))))}

    results = {}
    for n in [int(x) for x in args.raters.split(",")]:
        hits = defaultdict(int)
        valid = defaultdict(int)
        for rep_ in range(args.reps):
            raters = {}
            for i in range(n):
                per = bank[rng.randrange(len(bank))]
                lst = rng.randrange(n_lists)
                shown = fixed + [u[(lst + j) % len(u)] for j, u in enumerate(ulist)]
                raters[f"r{i}"] = [(it["meta"], rate(per, it)) for it in shown]
            tests = test_hypotheses(raters, spec, boot=args.boot, seed=rng.randrange(10 ** 9))
            for t in tests:
                if t.get("estimate") is None or "supported" not in t:
                    continue
                valid[t["id"]] += 1
                hits[t["id"]] += bool(t["supported"])
        results[n] = {h: hits[h] / valid[h] for h in valid}
        print(f"  評定者 {n} 名：完了", file=sys.stderr)
    ids = [h["id"] for h in spec["hypotheses"] if h.get("primary", True)]
    L = [f"# 検出力の見積もり（合成評定者、{args.reps} 回、効果の大きさ ×{args.effect_scale}）", "",
         f"事前登録した検定（Holm 法、α = {spec.get('alpha')}、効果の最小の大きさ {spec.get('min_effect')}）で「支持」となる割合。"
         f"合成評定者は母集団から抜き、所属度を5段階に丸めて述語ごとに {round(100 * args.noise)}% を無作為な段階に置き換えた。"
         "反省の知覚・再発の危険はシミュレータが予測しないので見積もれない。", "",
         "| 仮説 | " + " | ".join(f"{n} 名" for n in results) + " |", "|---|" + "---|" * len(results)]
    for h in ids:
        L.append(f"| {h} | " + " | ".join("—" if h not in r else f"{r[h]:.2f}" for r in results.values()) + " |")
    md = "\n".join(L)
    print(md)
    if args.out:
        Path(args.out).with_suffix(".md").write_text(md + "\n", encoding="utf-8")
        sim.save(Path(args.out).with_suffix(".json"), {"effect_scale": args.effect_scale, "reps": args.reps, "noise": args.noise,
                                                       "results": {str(n): r for n, r in results.items()}})


# ---------------------------------------------------------------- import-benchmark

def cmd_import(args):
    """ベンチマークの評定ファイル（user-ratings.json 等、4値）を、問題束の評定ファイルの形に変換する。
    4値の評定は、選んだ述語だけが1の所属度（ファジィの特別な場合）として取り込む"""
    key = sim.load(args.key)
    src = sim.load(args.ratings)["ratings"]
    ratings = {}
    for did, k in key["items"].items():
        if k["repeat_of"]:
            continue  # 再評定の項目には取り込まない（同じ評定が入り、見かけの一致が上がるため）
        v = src.get(k["source"])
        m = rating_mu(v) if isinstance(v, dict) else None
        if m:
            ratings[did] = {"mu": m, "level": None, "sincerity": None, "comment": v.get("comment", "")}
    doc = {"schema": SCHEMA_RATING, "packet_id": key["packet_id"], "imported_from": args.ratings, "crisp": True,
           "blind_note": args.note, "rater": {"id": args.rater, "questionnaire": {}}, "mode": "imported",
           "duration_s": None, "ratings": ratings}
    sim.save(args.out, doc)
    print(f"{len(ratings)} 件を取り込みました → {args.out}（4値の評定を一点集中の所属度として）")


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
    p.add_argument("--design", action="store_true", help="評価キット（ラテン方格・追加の設問・注意の確認）の問題束を作る")
    p.add_argument("--lists", type=int, default=0, help="ラテン方格のリストの数（既定は土台の水準の最大数）")
    p.set_defaults(f=cmd_pack)
    p = sub.add_parser("compare", help="人間の評定と自動評価の差を測る")
    p.add_argument("--key", required=True)
    p.add_argument("--ratings", nargs="+", required=True, help="評定ファイル（ワイルドカード可）")
    p.add_argument("--sim", nargs="*", help="シミュレータの出力（scenes-result.json や simulate の出力）")
    p.add_argument("--auto", nargs="*", help="他の自動評価 名前=ファイル（{ratings:{source:{mu:{...}}}} か 4値の {ratings:{source:{rating}}}）")
    p.add_argument("--group-by", default="", help="群の軸（既定: frame,scene,condition,level）")
    p.add_argument("--scenes", help="評定者ごとの型の判定に使う作例ファイル")
    p.add_argument("--rater-types", action="store_true", help="評定者ごとに、どの型の所属度が評定に最も近いかを判定する")
    p.add_argument("--per-type", type=int, default=300, help="型ごとに抜く受け手の数")
    p.add_argument("--calib", type=int, default=100, help="外れの目安を作る合成評定者の数")
    p.add_argument("--noise", type=float, default=0.1, help="合成評定者のゆらぎ（述語ごとに段階を無作為に置き換える割合）")
    p.add_argument("--population", default=str(HERE / "population.json"))
    p.add_argument("--seed", type=int, default=7)
    p.add_argument("--hypotheses", help="事前登録した仮説（human/hypotheses.json）を検定する")
    p.add_argument("--boot", type=int, default=2000, help="仮説の検定のブートストラップ回数")
    p.add_argument("--exclude-inattentive", action="store_true", help="注意の確認に通らなかった評定者を仮説の検定から除く（感度分析用）")
    p.add_argument("--rps", action="store_true", help="--scenes の項目で、5段階の予測分布の順位確率スコアを出す")
    p.add_argument("--rps-n", type=int, default=300, help="RPS の予測分布に使う受け手の数")
    p.add_argument("-o", "--out", default="human/compare")
    p.set_defaults(f=cmd_compare)
    p = sub.add_parser("power", help="評価キットの検出力を合成評定者で見積もる")
    p.add_argument("--scenes", required=True); p.add_argument("--hypotheses", required=True)
    p.add_argument("--raters", default="40,60", help="評定者の数（カンマ区切り）")
    p.add_argument("--reps", type=int, default=100); p.add_argument("--boot", type=int, default=200)
    p.add_argument("--pool", type=int, default=300, help="合成評定者の候補の数")
    p.add_argument("--noise", type=float, default=0.1); p.add_argument("--effect-scale", type=float, default=1.0)
    p.add_argument("--population", default=str(HERE / "population.json"))
    p.add_argument("--seed", type=int, default=7); p.add_argument("-o", "--out")
    p.set_defaults(f=cmd_power)
    p = sub.add_parser("import-benchmark", help="ベンチマークの評定ファイルを評定ファイルの形に変換する")
    p.add_argument("--key", required=True); p.add_argument("--ratings", required=True)
    p.add_argument("--rater", required=True); p.add_argument("--note", default="", help="盲検の条件などの注記")
    p.add_argument("-o", "--out", required=True)
    p.set_defaults(f=cmd_import)
    p = sub.add_parser("synth", help="試験用の合成評定者を作る")
    p.add_argument("--key", required=True); p.add_argument("--scenes", required=True)
    p.add_argument("-n", type=int, default=12); p.add_argument("--noise", type=float, default=0.1)
    p.add_argument("--inattentive", type=float, default=0.05, help="注意の確認に通らない合成評定者の割合")
    p.add_argument("--population", default=str(HERE / "population.json"))
    p.add_argument("--seed", type=int, default=7)
    p.add_argument("--out-dir", default="human/synth")
    p.set_defaults(f=cmd_synth)
    args = ap.parse_args()
    args.f(args)


if __name__ == "__main__":
    main()
