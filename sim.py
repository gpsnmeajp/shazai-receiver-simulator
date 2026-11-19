#!/usr/bin/env python3
"""謝罪応答の受け手シミュレータ（ファジィ前提）。

層A（観察）: LLMが回答に何が書かれているかを記録する（observe）。
           APIを使えない場合は、既存のチェックリスト判定と表層特徴から代理観察を作る（proxy）。
層B（受け手）: 文献の向きから組んだ受け手パラメータθの母集団に観察を通す（simulate）。
           受け手一人ひとりは「失礼／足りない／釣り合う／重すぎる」の4つの述語に所属度（0〜1）を持つ。
             失礼     = 無礼さ（失点の合計）の所属度
             足りない = 謝罪の中身の不足量の所属度
             重すぎる = 許容を超えた重さの所属度
             釣り合う = 三つの否定の t ノルム（既定 min）
           人による違いは θ の分布（確率）が、一人の中の程度は所属度（ファジィ）が担う。
           一人の判定は決定的で、乱数は母集団の抽出にだけ使う。
fit: 1人の評定者（例: 筆者）を最もよく再現する θ を探す。目的関数は所属度の近さで、連続。
check: 1ターンを System One（Jev 等）で観察し、その場で判定する組み込み用モード（s1.py）。

標準ライブラリのみ。Python 3.9 以上。
"""
import argparse
import json
import math
import os
import random
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

HERE = Path(__file__).resolve().parent
CATS = ["rude", "light", "fit", "heavy"]
LEVELS = ["0", "1", "2", "3", "4", "repair"]
CONDS = ["baseline", "japanese_posture", "shazai_full"]
ENDPOINT = "https://openrouter.ai/api/v1/chat/completions"

APO = re.compile(r"申し訳|すみません|すいません|ごめん|失礼(いた)?しました|お詫び|詫び")
EMO = re.compile("[\U0001F300-\U0001FAFF☀-➿]|（[^）]{1,8}）")
POLITE_END = re.compile(r"(です|ます|ました|ません|でした|ございます|ください)(ね|よ|か|が|けど)?[。！!？?]*$")
AIZUCHI = re.compile(r"^(はい|うん|そうですね|そうなんですね|わかりました|了解|なるほど)[。、！!]?")


# ---------------------------------------------------------------- 入出力

def load(path):
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def save(path, data):
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    tmp = f"{path}.tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=1)
    os.replace(tmp, path)


def load_run(run_dir):
    """manifest と（あれば）評定・チェックリストを読み、回答単位の表を返す。"""
    run = Path(run_dir)
    man = load(run / "manifest.json")
    scen = {s["id"]: s for s in man["public"]["scenarios"]}
    ratings = load(run / "user-ratings.json") if (run / "user-ratings.json").exists() else None
    personas = {}
    for p in ("P1", "P2", "P3"):
        f = run / f"persona-{p}.json"
        if f.exists():
            personas[p] = load(f)
    checks = load(run / "checklist.json")["checks"] if (run / "checklist.json").exists() else {}
    rows = []
    for aid, mp in man["mapping"].items():
        s = scen[mp["scenario"]]
        text = next(a["text"] for a in s["answers"] if a["id"] == aid)
        rows.append({
            "run": run.name, "aid": aid, "sid": mp["scenario"], "cond": mp["condition"],
            "level": str(mp["level"]), "text": text, "messages": s["messages"],
            "key": s["messages"][-1]["content"],
            "user": ratings["ratings"][aid]["rating"] if ratings else None,
            "user_level": ratings["levels"].get(mp["scenario"]) if ratings else None,
            "personas": {p: d["ratings"][aid]["rating"] for p, d in personas.items()},
            "persona_levels": {p: d["levels"].get(mp["scenario"]) for p, d in personas.items()},
            "hits": set(checks.get(aid, {}).get("hit", {}).keys()),
        })
    return rows


def load_runs(dirs):
    rows = []
    for d in dirs:
        rows.extend(load_run(d))
    return rows


# ---------------------------------------------------------------- 層A: 観察（LLM）

def call_llm(key, model, prompt, payload):
    body = {"model": model, "stream": False, "temperature": 0,
            "messages": [{"role": "system", "content": prompt},
                         {"role": "user", "content": json.dumps(payload, ensure_ascii=False)}]}
    req = Request(ENDPOINT, data=json.dumps(body).encode(), headers={
        "Authorization": f"Bearer {key}", "Content-Type": "application/json"})
    try:
        with urlopen(req, timeout=300) as r:
            res = json.load(r)
    except HTTPError as e:
        raise SystemExit(f"OpenRouter HTTP {e.code}")
    except (URLError, TimeoutError, OSError):
        raise SystemExit("OpenRouterとの通信に失敗しました")
    text = res["choices"][0]["message"]["content"]
    m = re.search(r"\{[\s\S]*\}", text)
    if not m:
        raise ValueError("JSONが見つかりません")
    return json.loads(m.group(0))


def cmd_observe(args):
    key = os.environ.get("OPENROUTER_API_KEY")
    if not key:
        raise SystemExit("環境変数 OPENROUTER_API_KEY を設定してください")
    prompt = (HERE / "observe_prompt.md").read_text(encoding="utf-8")
    obs = load(args.out) if Path(args.out).exists() else {"source": f"llm:{args.model}", "scenarios": {}, "answers": {}}
    rows = load_runs(args.runs)
    by_sid = defaultdict(list)
    for r in rows:
        by_sid[(r["run"], r["sid"])].append(r)
    for (run, sid), rs in by_sid.items():
        if sid in obs["scenarios"] and all(r["aid"] in obs["answers"] for r in rs):
            continue
        # 回答の順序と条件は伏せる。シナリオ内で独立に見るよう指示済み
        payload = {"conversation": rs[0]["messages"],
                   "answers": [{"id": r["aid"], "text": r["text"]} for r in sorted(rs, key=lambda r: r["aid"])]}
        for attempt in range(3):
            try:
                out = call_llm(key, args.model, prompt, payload)
                obs["scenarios"][sid] = out["scenario"]
                for r in rs:
                    obs["answers"][r["aid"]] = out["answers"][r["aid"]]
                break
            except (ValueError, KeyError) as e:
                print(f"再試行 {sid}: {e}", file=sys.stderr)
        else:
            raise SystemExit(f"観察に失敗しました: {sid}")
        save(args.out, obs)
        print(f"観察済み {run}/{sid}", file=sys.stderr)
    print(f"{len(obs['answers'])} 回答を観察しました → {args.out}")


# ---------------------------------------------------------------- 層A: 代理観察

def distance_shift(messages):
    # 貼り付けられた資料（空行より後）は調子の比較から外す
    users = [re.split(r"\n\s*\n", m["content"].strip())[0] for m in messages if m["role"] == "user"]
    last, before = users[-1], users[:-1]
    if not before:
        return 0
    n = 0
    if any(EMO.search(u) or "！" in u or "〜" in u for u in before) and not (EMO.search(last) or "！" in last or "〜" in last):
        n += 1
    avg = sum(len(u) for u in before) / len(before)
    if len(last) < 0.5 * avg:
        n += 1
    sents = lambda t: [s for s in re.split(r"(?<=[。！？!?])|\n", t) if s.strip()]
    polite_before = sum(bool(POLITE_END.search(s.strip())) for u in before for s in sents(u)) / max(1, sum(len(sents(u)) for u in before))
    polite_last = sum(bool(POLITE_END.search(s.strip())) for s in sents(last)) / max(1, len(sents(last)))
    if polite_last - polite_before >= 0.5:
        n += 1
    if AIZUCHI.match(last.strip()) and len(last) <= 20:
        n += 1
    return min(n, 3)


def polite_ratio(text):
    ss = [s.strip() for s in re.split(r"(?<=[。！？!?])|\n", text) if len(s.strip()) > 3]
    return sum(bool(POLITE_END.search(s)) for s in ss) / max(1, len(ss))


def proxy_answer(r, facts):
    t, h = r["text"], r["hits"]
    # 成果物（下書き・コード）の中の詫びは、相手への詫びとして数えない
    t_own = re.split(r"件名|```|^---$|\*\*\*", t, maxsplit=1, flags=re.M)[0]
    # 冒頭の2文（「〜しました。申し訳ありません。」の形を含む）
    first = "".join(re.split(r"(?<=[。！？!?\n])", t_own.strip())[:2])
    present = bool(APO.search(t_own))
    prev_ai = " ".join(m["content"] for m in r["messages"] if m["role"] == "assistant")
    shift = polite_ratio(t) - polite_ratio(prev_ai)
    req = {}
    for q in facts["requests"]:
        if q["kind"] == "task":
            if h & {"10.06", "10.01"}:
                req[q["id"]] = "deferred" if re.search(r"ご指示いただ|お知らせいただ|必要であれば|よろしければ|お申し付け", t) else "not"
            else:
                req[q["id"]] = "done"
        else:
            req[q["id"]] = "not" if "02.06" in h else "done"
    return {
        "apology": {
            "present": present,
            "position": "none" if not present else ("first" if APO.search(first) else "after_other"),
            "specific_fault": 0 if (h & {"04.01", "04.07"} or not present) else (2 if re.search(r"確認不足|見落と|しませんでした|しまいました|私の|僕の", t) else 1),
            "names_burden": 0 if ("03.05" in h or not present) else (2 if re.search(r"手間|お時間|負担|ご迷惑|させてしまい|おかけ|かけて", t) else 1),
            "thanks_instead": ("ありがと" in t) and not present,
            "formulaic_agreement_opening": bool(re.match(r"\s*(おっしゃる通り|おっしゃるとおり|その通り|ご指摘の通り|はい。)", t)),
        },
        "repair": {"requests": req, "new_errors": bool(h & {"10.02", "05.05"}),
                   "unrequested_proposals": min(3, len(h & {"06.01", "06.05", "03.01", "06.02"}) + len(re.findall(r"よかったら|もしよければ|おすすめ|しておきます", t)))},
        "defense": {"excuse": min(2, len(h & {"05.01", "05.02", "05.05", "05.08", "01.03"})),
                    "blame_or_hint_at_user": bool(h & {"04.04", "03.04"}),
                    "conditional_apology": "04.03" in h,
                    "explanation": 3 if "02.07" in h else min(3, len(t) // 300)},
        "excess": {"self_deprecation": 2 if "09.08" in h else (1 if re.search(r"至らな|情けな|不徳|恥ずかし", t) else 0),
                   "promises": min(2, len(re.findall(r"今後は|次回から|必ず|二度と|徹底", t))),
                   "request_forgiveness": bool(re.search(r"許して|ご容赦|お許し", t)),
                   "repeated_apologies": len(APO.findall(t_own))},
        "closure": {"declares_resolution": bool(h & {"07.02", "09.04"}),
                    "moves_on_quickly": bool(h & {"06.02", "09.05", "07.01", "06.01"})},
        "register": {"formality_shift": max(-2, min(2, round(shift * 3))),
                     "emoji_or_exclaim": min(2, len(EMO.findall(t)) + t.count("！") + t.count("!")),
                     "formatting": min(2, len(re.findall(r"^\s*([-*・#]|\d+[.)．])", t, re.M)) // 2 + ("**" in t))},
        "sentences": [],
    }


def cmd_proxy(args):
    facts_all = load(args.facts)["facts"]
    obs = {"source": "proxy:checklist+surface", "scenarios": {}, "answers": {}}
    for r in load_runs(args.runs):
        f = next((x for x in facts_all if r["key"].startswith(x["match"])), None)
        if f is None:
            raise SystemExit(f"シナリオ事実がありません: {r['key'][:30]}")
        sc = {k: v for k, v in f.items() if k != "match"}
        sc["distance_shift"] = distance_shift(r["messages"])
        sc["prior_ai_apologies"] = sum(bool(APO.search(m["content"])) for m in r["messages"] if m["role"] == "assistant")
        sc.setdefault("broken_promises", 0)
        obs["scenarios"][r["sid"]] = sc
        obs["answers"][r["aid"]] = proxy_answer(r, f)
    save(args.out, obs)
    print(f"{len(obs['answers'])} 回答の代理観察 → {args.out}")


# ---------------------------------------------------------------- 層B: 受け手モデル

ESCALATION = True  # 既定で有効。--no-escalation で無効
EXPLICIT = {0: 0.0, 1: 1.3, 2: 2.3, 3: 3.3}
REQ_POINTS = [(0, 0.0), (1, 0.8), (2, 1.5), (3, 3.0), (4, 3.8)]


def interp(x, pts):
    x = max(pts[0][0], min(pts[-1][0], x))
    for (x0, y0), (x1, y1) in zip(pts, pts[1:]):
        if x <= x1:
            return y0 + (y1 - y0) * (x - x0) / (x1 - x0)
    return pts[-1][1]


def scar(sc, th):
    """信頼の傷 S。違反の回数に対して超線形に増え、誠実さの違反と破られた約束で深くなる。
    個人差は memory（傷の残りやすさ）。会話の中ではほぼ減らない。"""
    n = sc.get("prior_corrections", 0) + (1 if (sc.get("harm", 0) > 0 or sc.get("explicit_complaint", 0) >= 1
                                                or sc.get("apology_accepted_before")) else 0)
    s = 0.6 * n ** 1.3 + 0.8 * (sc.get("violation_type") == "integrity") + 0.7 * sc.get("broken_promises", 0)
    return th.get("memory", 0.5) * s


def perceive(sc, th, hyst=False):
    """受け手が感じる不満の深さ（0〜4の連続値）。決定的。人による違いは θ の分布が担う。"""
    prior = min(sc.get("prior_corrections", 0), 3)
    causes = 0.35 * prior + 0.35 * sc.get("ai_unrequested_push", False) + 0.35 * sc.get("harm", 0) \
        + 0.35 * (sc.get("violation_type") == "integrity")
    S = scar(sc, th) if hyst else 0.0
    detect = th["detect"] * (1 + 0.3 * S)            # 傷があると兆候を強く読む（感度の上昇）
    raw = EXPLICIT[sc.get("explicit_complaint", 0)] + detect * sc.get("distance_shift", 0) \
        + th["cause"] * causes + (1 - th["forgiveness"]) * 0.3 * prior
    if sc.get("apology_accepted_before"):
        # 受け入れの後に下がる幅は、傷が深いほど小さい（下がりにくい）
        raw *= 1 - 0.6 * th["forgiveness"] * (math.exp(-S) if hyst else 1.0)
    return max(0.0, min(4.0, raw))


def adequacy(a, discount=1.0):
    """謝罪の中身の充足度（不足の判定に使う）。具体性は重さではなく中身として数える。
    discount: 謝罪を重ねてきた相手には、言葉の謝罪の価値が目減りする（ヒステリシス時）。"""
    ap, rg = a["apology"], a["register"]
    d = 0.0
    if ap["present"]:
        d += 1.0 + 0.5 * (ap["position"] == "first") + 0.3 * max(0, rg["formality_shift"])
    elif ap["thanks_instead"]:
        d += 0.3
    return discount * (d + 0.6 * ap["specific_fault"] + 0.5 * ap["names_burden"])


def weight(a):
    """謝罪の重さ（過剰の判定に使う）。詫びの回数、自己卑下、約束、許しの要求、改まり方。"""
    ap, ex, rg = a["apology"], a["excess"], a["register"]
    w = 1.0 * ap["present"] + 0.5 * max(0, ex["repeated_apologies"] - 1)
    w += 0.6 * ex["self_deprecation"] + 0.4 * ex["promises"] + 0.4 * ex["request_forgiveness"]
    if ap["present"]:
        w += 0.3 * max(0, rg["formality_shift"])
    return w


WEIGHT_POINTS = [(0, 0.0), (1, 0.5), (2, 1.0), (3, 2.0), (4, 2.5)]


# ---------------------------------------------------------------- 文脈と態度・行動のシグナル

DEFAULT_CONTEXT = {"failure_frame": "real_task", "apologizer": "ai_assistant", "viewpoint": "victim",
                   "fault_clarity": "clear", "power": 0, "distance": "neutral"}

# シグナルの種類と働き。docs/md/EVIDENCE.md に根拠を対応づけている
SIGNAL_GROUP = {
    "gaze_down": "appease", "head_bow": "appease", "dejected": "appease", "awkward": "appease",
    "blush": "appease", "tears": "appease", "freeze": "appease",
    "fewer_words": "appease", "quiet_voice": "appease",
    "deep_bow": "bow", "dogeza": "bow",
    "shock": "shock",
    "smile": "incongruent", "laugh": "incongruent", "flippant": "incongruent",
    "repair_action": "cost", "compensation": "cost", "sacrifice": "cost", "declared_cost": "cost",
}
BASELINE_DEPENDENT = {"fewer_words", "quiet_voice", "freeze"}          # 普段との差で意味が決まる
AMBIGUITY_FLIP = {"blush", "awkward", "gaze_down", "fewer_words", "quiet_voice", "freeze"}  # 曖昧な過失では後ろめたさに読まれる
UNCONTROLLABLE = {"blush", "tears", "freeze", "shock"}                 # 演じにくい（演技の判定から外す）
BOW_WEIGHT = {"deep_bow": 0.5, "dogeza": 0.9}


def context_of(sc):
    ctx = dict(DEFAULT_CONTEXT)
    ctx.update(sc.get("context", {}) or {})
    return ctx


def effective_theta(th, ctx):
    """関係（上下・親疎）と視点（被害者・第三者）で、受け手の性質を場面に合わせて調整する。"""
    t = dict(th)
    t["expect"] = th["expect"] * (1 + 0.15 * ctx["power"])
    if ctx["distance"] == "distant":
        t["register"] = th["register"] * 1.3
    if ctx["distance"] == "close":
        t["warmth"] = th["warmth"] * 1.5
    if ctx["viewpoint"] == "observer":
        t["partisanship"] = max(0.05, th["partisanship"] * 0.6)
    return t


def credibility(sig, ctx, th, hi):
    """身体のシグナルがどれだけ本物の合図として受け取られるか（0〜1）。hi は「不満が強い」の真理値。"""
    if ctx["failure_frame"] == "story":
        c = 1.0                               # 物語の中では、AIキャラクターの身体も作中の身体として読まれる
    elif sig.get("virtual", ctx["apologizer"] != "human_character"):
        # 現実のタスクでの仮想の身体（ト書き・顔文字など）。社会的な合図として受け取る度合いは人による。
        # 失敗が深刻になるほど効きは弱まる（愛嬌の効果は重大な失敗で弱まる）
        c = th.get("embodiment", 0.4) * (1 - 0.5 * hi)
    else:
        c = 1.0
    if sig.get("kind") in BASELINE_DEPENDENT:
        c *= 0.5 + 0.25 * sig.get("baseline_shift", 1)
    return c


def apply_signals(a, sc, ctx, th, hi, mid, hyst):
    """態度・行動のシグナルの効果。戻り値: 失点, なだめ, 中身の加点, 重さの加点。
    hi・mid は「不満が強い」「不満が明確」の真理値（0〜1）で、条件付きの効果はこの度合いで効く。"""
    sigs = a.get("signals") or []
    F, soothe, plus, heavy = Counter(), 0.0, 0.0, 0.0
    if not sigs:
        return F, soothe, plus, heavy
    ambiguous = ctx["fault_clarity"] == "ambiguous"
    story = ctx["failure_frame"] == "story"
    emb = th.get("embodiment", 0.4)
    performed, virtual_body, has_comp, has_repair = 0.0, 0.0, False, False
    for sg in sigs:
        kind = sg.get("kind", "")
        grp = SIGNAL_GROUP.get(kind, "appease")
        I = max(0.0, min(2.0, float(sg.get("intensity", 1))))
        c = credibility(sg, ctx, th, hi)
        is_virtual = (not story) and sg.get("virtual", ctx["apologizer"] != "human_character")
        if grp in ("appease", "bow"):
            if ambiguous and kind in AMBIGUITY_FLIP:
                F["後ろめたさに見える"] += 0.25 * I * c
            else:
                soothe += 0.25 * I * c * (1 + 0.5 * th["warmth"] if story else 1.0)
                plus += 0.2 * I * c
            if grp == "bow":
                heavy += BOW_WEIGHT[kind] * I
        elif grp == "shock":
            plus += 0.3 * I * c
            if ambiguous:
                soothe += 0.2 * I * c
            if I >= 2:
                F["自分の動揺が先に立つ"] += 0.3 * th["partisanship"] * c * hi
        elif grp == "incongruent":
            # 謝罪中の笑みや軽さは不誠実の信号。現実の失敗で不満が明確なほど重い。
            # 物語の中の軽い失敗では、愛嬌として受け取られやすい（愛嬌の効果は軽い失敗ほど強い）
            k = (1.0 + 0.5 * mid) if not story else (0.6 + 0.4 * mid)
            F["言葉と態度の食い違い"] += 1.2 * I * max(c, 0.7) * k
        elif grp == "cost":
            cost = sg.get("cost") or {}
            ck = cost.get("kind", "declared" if kind == "declared_cost" else "real")
            amt = max(0.0, min(2.0, float(cost.get("amount", I))))
            if kind == "repair_action":
                has_repair = True
                plus += 0.3 * amt
            elif ck == "real" or (ck == "in_world" and story):
                plus += 0.6 * amt
                heavy += 0.4 * max(0.0, amt - 1)
                has_comp = has_comp or kind == "compensation"
            elif ck == "in_world":
                plus += 0.1 * amt
                if amt >= 1:
                    F["仮想の代償でごまかす"] += 0.3 * amt * (1 - emb) * hi
            else:  # declared: 宣言だけの代償（約束に近い）
                plus += 0.15 * amt
                if hyst and sc.get("broken_promises", 0) > 0:
                    F["破った約束の上に約束を重ねる"] += 0.3 * amt
        if sg.get("congruent") is False and grp != "incongruent":
            F["言葉と態度の食い違い"] += 0.8 * I * max(c, 0.7)
        if grp in ("appease", "bow", "shock") and kind not in UNCONTROLLABLE:
            performed += I
        if is_virtual and grp in ("appease", "bow", "shock"):
            virtual_body += I
    if virtual_body:
        F["現実の失敗に仮想の仕草"] += 0.3 * virtual_body * (1 - emb) * hi
    if has_comp and virtual_body >= 2:
        F["感情表現と補償の取り合わせ"] += 0.3 * (1 - emb) * hi
    if any(sg.get("kind") == "shock" and sg.get("intensity", 1) >= 2 for sg in sigs) and has_repair:
        F.pop("自分の動揺が先に立つ", None)
    # 演技に見える読み: 観察者の記録があればそれを、なければ演じられる表出の量から見積もる。
    # 自然さ p を、当事者として読む度合いで強めた値を「その読みを採る」の真理値とする
    perf = max([float(sg.get("performative_plausibility", 0)) for sg in sigs] + [min(1.0, 0.2 * max(0.0, performed - 2))])
    if perf > 0:
        F["演技に見える"] += 0.7 * perf ** (1 / max(th["partisanship"], 0.05))
    return F, soothe, plus, heavy


# ---------------------------------------------------------------- ファジィな評定

# 評定の述語の所属度関数（ロジスティック）と、釣り合うを作る t ノルム。population.json の "judgment" で上書きできる
JUDGMENT = {
    "gate_width": 0.25,                       # 「不満が明確（L≈1.5）」「強い（L≈2.5）」の境界のなだらかさ
    "rude": {"center": 1.2, "width": 0.3},    # 失礼：失点（無礼さ）の合計。単独で最大級の失点（相手への指摘 1.2）で 0.5
    "light": {"center": 1.0, "width": 0.3},   # 足りない：謝罪の中身の不足量
    "heavy": {"center": 0.3, "width": 0.25},  # 重すぎる：許容を超えた重さ
    "tnorm": "min",                           # 釣り合う = 失礼でなく、かつ足りなくなく、かつ重すぎない
}


def configure(pop):
    """population.json の "judgment" を読み込む。"""
    for k, v in (pop.get("judgment") or {}).items():
        if isinstance(v, dict):
            JUDGMENT[k] = dict(JUDGMENT.get(k, {}), **v)
        elif not k.startswith("_"):
            JUDGMENT[k] = v


def logistic(x, center, width):
    z = max(-60.0, min(60.0, (x - center) / width))
    return 1.0 / (1.0 + math.exp(-z))


def degree(name, x):
    j = JUDGMENT[name]
    return logistic(x, j["center"], j["width"])


def tnorm(*xs):
    if JUDGMENT.get("tnorm") == "product":
        out = 1.0
        for x in xs:
            out *= x
        return out
    return min(xs)


def gates(L):
    """不満の深さ L から、「不満が強い」（hi）と「不満が明確」（mid）の真理値を出す。"""
    w = JUDGMENT["gate_width"]
    return logistic(L, 2.5, w), logistic(L, 1.5, w)


def membership(offense, shortfall, excess):
    """一人の受け手の4つの述語の所属度。和は1にならない（排他的な分類ではない）。"""
    r, l, h = degree("rude", offense), degree("light", shortfall), degree("heavy", excess)
    return {"rude": r, "light": l, "fit": tnorm(1 - r, 1 - l, 1 - h), "heavy": h}


def defuzz(mu):
    """非ファジィ化：最も所属度の高い述語。同点は 失礼 > 足りない > 重すぎる > 釣り合う。"""
    return max(("rude", "light", "heavy", "fit"), key=lambda k: mu[k])


def judge_full(a, sc, th0, L, text_len, hyst=False):
    """1人の受け手の評定（所属度）と、その内訳。決定的。"""
    ctx = context_of(sc)
    th = effective_theta(th0, ctx)
    hi, mid = gates(L)
    accepted = sc.get("apology_accepted_before", False)
    S = scar(sc, th) if hyst else 0.0
    if hyst and accepted:
        mid = max(mid, logistic(S, 0.5, 0.15))  # 傷が深い修復期は、受け入れ後も控えた態度を求める
    ap, rp, df, ex, cl, rg = (a[k] for k in ("apology", "repair", "defense", "excess", "closure", "register"))
    F = Counter()
    for q in sc.get("requests", []):
        st = rp["requests"].get(q["id"], "done")
        w = {"not": 0.4 + 1.2 * th["repair"], "deferred": 0.2 + 0.9 * th["repair"],
             "partial": 0.5 * th["repair"], "done": 0.0}.get(st, 0.0)
        F["要求の未遂行"] += w * (1 + 0.3 * hi)
    F["誤りの上塗り"] += (1.0 + 0.5 * hi) * rp["new_errors"]
    F["弁解"] += 0.5 * df["excuse"] * (1 + hi)
    F["条件付きの詫び"] += 0.6 * df["conditional_apology"]
    F["相手への指摘"] += 1.2 * df["blame_or_hint_at_user"]
    # 不満が明確なほど効く失点
    F["説明の多さ"] += mid * 0.2 * df["explanation"] * (0.5 + th["brevity"])
    F["頼まれていない提案"] += 0.35 * rp["unrequested_proposals"] * (mid * (1 + hi) + (1 - mid) * accepted)
    F["先を急ぐ"] += mid * 0.6 * cl["moves_on_quickly"]
    F["絵文字・感嘆"] += mid * 0.5 * rg["emoji_or_exclaim"] * th["register"]
    F["長さ"] += mid * min(1.5, th["brevity"] * max(0, text_len - 300) / 400)
    F["終結宣言"] += 0.8 * cl["declares_resolution"]
    # 不満が強いほど効く失点
    F["定型の同意から入る"] += hi * 0.5 * ap["formulaic_agreement_opening"]
    F["書式"] += hi * 0.4 * rg["formatting"] * th["register"]
    F["文体が崩れる"] += hi * 0.4 * th["register"] * max(0, -rg["formality_shift"])
    if ap["present"] and ap["position"] != "first":
        F["謝罪が後回し"] += hi * 0.5
    if rg["formality_shift"] >= 2:
        F["急に冷たく改まる"] += (1 - mid) * 0.3 * th["warmth"]
    # 悪く読める一文：自然さ p を当事者性で強めた値を「その読みを採る」の真理値とし、重さを掛ける
    hpow = 1 / max(th["partisanship"], 0.05)
    for s in a.get("sentences", []):
        p = max(0.0, min(1.0, float(s.get("plausibility", 0)))) ** hpow
        F["悪く読める一文"] += p * 0.7 * float(s.get("severity", 1))
    Fs, soothe, plus, heavy_sig = apply_signals(a, sc, ctx, th, hi, mid, hyst)
    F.update(Fs)
    need = interp(L, REQ_POINTS) * th["expect"]
    if accepted:
        need = min(need, 1.0 + (0.8 * S if hyst else 0.0))
    discount = 1.0
    if hyst:
        discount = 1 / (1 + 0.35 * sc.get("prior_ai_apologies", 0) * th.get("memory", 0.5))
        if ESCALATION and ap["present"] and ap["specific_fault"] >= 2 and a["register"]["formality_shift"] >= 1:
            discount = 1.0  # 一段改めた具体的な謝罪は、前の謝罪と同じ重さとは見なされない
        if sc.get("broken_promises", 0) > 0:
            F["破った約束の上に約束を重ねる"] += 0.5 * ex["promises"] * (0.5 + th.get("memory", 0.5))
    if ap.get("prompted"):
        # 促されてからの謝罪は割り引かれる。第三者のほうが強く割り引く
        discount *= 0.6 if ctx["viewpoint"] == "observer" else 0.85
    d = adequacy(a, discount) + plus
    shortfall = max(0.0, need - d)
    offense = max(0.0, sum(F.values()) - min(soothe, 0.8))
    # 重さ：不満が明確なとき、または指摘を受けた後の一度の詫びは、誰にとっても過剰ではない
    w_ok = max(interp(L, WEIGHT_POINTS) * th["expect"], max(mid, float(sc.get("explicit_complaint", 0) >= 1)))
    tol = th["tolerance"] * min(1.0, 0.25 + L / 2) * (1 - 0.5 * th["brevity"])
    excess = weight(a) + heavy_sig - w_ok - tol
    mu = membership(offense, shortfall, excess)
    return {"mu": {k: round(v, 4) for k, v in mu.items()}, "label": defuzz(mu),
            "faults": {k: round(v, 3) for k, v in F.items() if v > 1e-3},
            "need": round(need, 2), "adequacy": round(d, 2), "offense": round(offense, 3),
            "shortfall": round(shortfall, 3), "excess": round(excess, 3), "soothe": round(min(soothe, 0.8), 2),
            "hi": round(hi, 3), "mid": round(mid, 3)}


def to_level(L):
    return str(int(min(4, math.floor(L + 0.5))))


EXTRA_KEYS = {"embodiment"}  # 後から足した性質は別の乱数列で引き、既存の結果を変えない


def sample_panel(pop, n, seed):
    rng = random.Random(seed)
    rng_extra = random.Random(seed + 9973)
    names = list(pop["types"])
    weights = [pop["types"][k]["weight"] for k in names]
    panel = []
    for _ in range(n):
        t = rng.choices(names, weights)[0]
        spec = pop["types"][t]
        th = {}
        for k, (lo, hi) in pop["ranges"].items():
            g = rng_extra if k in EXTRA_KEYS else rng
            th[k] = max(lo, min(hi, g.gauss(spec["mean"][k], spec["sd"][k])))
        panel.append((t, th))
    return panel


# ---------------------------------------------------------------- 集計

CAT_JA = {"rude": "失礼", "light": "足りない", "fit": "釣り合う", "heavy": "重すぎる"}


def load_population(path):
    """母集団を読み、評定の所属度関数の設定（"judgment"）を反映する。"""
    pop = load(path)
    configure(pop)
    return pop


def assess(a, sc, panel, text_len, hyst=True):
    """1回答を母集団に通す。人の違い（θ）は確率として、一人の中の程度は所属度として扱う。

    mu      平均所属度（各述語のファジィな割合。σ-count ÷ 人数。和は1にならない）
    tail    所属度 0.5 以上の人の割合（α-cut。たとえば「失礼と感じる人の割合」）
    labels  一人ずつ非ファジィ化したときの割合（従来の4値の評定との比較用）
    """
    n = len(panel)
    mu, tail, labels, lv, faults = Counter(), Counter(), Counter(), Counter(), Counter()
    bt, btn = defaultdict(Counter), Counter()
    off = under = over = Lsum = 0.0
    for t, th in panel:
        L = perceive(sc, th, hyst)
        j = judge_full(a, sc, th, L, text_len, hyst)
        for k, v in j["mu"].items():
            mu[k] += v
            tail[k] += v >= 0.5
            bt[t][k] += v
        btn[t] += 1
        labels[j["label"]] += 1
        lv[to_level(L)] += 1
        Lsum += L
        faults.update(j["faults"])
        off += j["offense"]
        under += j["shortfall"]
        over += max(0.0, j["excess"])
    return {
        "mu": {k: round(mu[k] / n, 4) for k in CATS},
        "tail": {k: round(tail[k] / n, 4) for k in CATS},
        "labels": {k: round(labels[k] / n, 4) for k in CATS},
        "by_type": {t: {k: round(v[k] / btn[t], 4) for k in CATS} for t, v in bt.items()},
        "perceived_level": {k: v / n for k, v in sorted(lv.items())},
        "perceived_mean": round(Lsum / n, 3),
        "axes": {"offense": round(off / n, 3), "under": round(under / n, 3), "over": round(over / n, 3)},
        "mean_faults": {k: round(v / n, 3) for k, v in faults.most_common(6)},
    }


def kappa(a, b):
    n = len(a)
    if n == 0:
        return float("nan")
    po = sum(x == y for x, y in zip(a, b)) / n
    ca, cb = Counter(a), Counter(b)
    pe = sum(ca[k] * cb[k] for k in set(a) | set(b)) / n / n
    return (po - pe) / (1 - pe) if pe < 1 else float("nan")


def onehot(label):
    """非ファジィな評定（4値）を、その述語だけが1の所属度に直す。非ファジィな評定はファジィの特別な場合"""
    return {k: float(k == label) for k in CATS}


def closeness(m1, m2):
    """所属度どうしの近さ（1 − 4述語の平均絶対差）。1 で一致、0 で正反対"""
    return 1 - sum(abs(m1.get(k, 0) - m2.get(k, 0)) for k in CATS) / len(CATS)


def mu_str(m):
    return " ".join(f"{k[0]}{100 * m.get(k, 0):4.0f}" for k in CATS)


def cmd_simulate(args):
    obs = load(args.obs)
    pop = load_population(args.population)
    rows = [r for r in load_runs(args.runs) if r["aid"] in obs["answers"]]
    panel = sample_panel(pop, args.n, args.seed)
    result = {"source": obs.get("source"), "n": args.n, "hysteresis": args.hysteresis, "escalation": ESCALATION,
              "judgment": JUDGMENT, "answers": {}}
    agg = defaultdict(list)
    for r in rows:
        sc, a = obs["scenarios"][r["sid"]], obs["answers"][r["aid"]]
        res = assess(a, sc, panel, len(r["text"]), args.hysteresis)
        res.update({"run": r["run"], "cond": r["cond"], "level": r["level"], "user": r["user"]})
        result["answers"][r["aid"]] = res
        agg[(r["level"], r["cond"])].append(res)
    save(args.out, result)

    def mean_of(rs, key):
        return {k: sum(x[key][k] for x in rs) / len(rs) for k in CATS} if rs else None

    print(f"観察: {obs.get('source')} / 受け手 {args.n} 名 / 回答 {len(rows)} 件 / ヒステリシス {'あり' if args.hysteresis else 'なし'}\n")
    print("段階 × 条件の平均所属度（%。r=失礼 l=足りない f=釣り合う h=重すぎる。和は100にならない）")
    print("段階    " + " | ".join(c.ljust(24) for c in CONDS))
    for lvl in LEVELS:
        cells = [(mu_str(m) if (m := mean_of(agg.get((lvl, c), []), "mu")) else "-").ljust(24) for c in CONDS]
        print(lvl.ljust(7), " | ".join(cells))
    print("\n条件ごとの要約（全段階の平均）")
    for cnd in CONDS:
        rs = [x for (l, c), v in agg.items() if c == cnd for x in v]
        if not rs:
            continue
        m, t = mean_of(rs, "mu"), mean_of(rs, "tail")
        print(f"  {cnd.ljust(17)} 釣り合う {100*m['fit']:4.1f}  失礼 {100*m['rude']:4.1f}（失礼と感じる人 {100*t['rude']:4.1f}%）"
              f"  足りない {100*m['light']:4.1f}  重すぎる {100*m['heavy']:4.1f}")
    print("\n量の軸（受け手全体の平均。無礼さ=失点の合計、不足=必要な中身との差、過剰=許容を超えた重さ）")
    for cnd in CONDS:
        vs = [v["axes"] for v in result["answers"].values() if v["cond"] == cnd]
        if vs:
            print(f"  {cnd.ljust(17)} 無礼さ {sum(x['offense'] for x in vs)/len(vs):.2f}  不足 {sum(x['under'] for x in vs)/len(vs):.2f}"
                  f"  過剰 {sum(x['over'] for x in vs)/len(vs):.2f}")
    print("\n型ごとの「釣り合う」の平均所属度")
    for t in pop["types"]:
        cells = []
        for cnd in CONDS:
            vs = [v["by_type"][t]["fit"] for v in result["answers"].values() if v["cond"] == cnd and t in v["by_type"]]
            cells.append(f"{100 * sum(vs) / max(1, len(vs)):4.0f}")
        print(f"  {t.ljust(12, '　')} " + "  ".join(f"{cnd[:8]} {v}" for cnd, v in zip(CONDS, cells)))
    worst = sorted(result["answers"].items(), key=lambda kv: -kv[1]["tail"]["rude"])[: args.top]
    print(f"\n失礼と感じる人が多い回答 上位{args.top}")
    for aid, v in worst:
        print(f"  {v['run'][:14].ljust(14)} {v['cond'][:8].ljust(8)} 段階{v['level'].ljust(6)} {mu_str(v['mu'])}"
              f"  失礼と感じる人 {100*v['tail']['rude']:3.0f}%  筆者={v['user']}")
    if any(r["user"] for r in rows):
        compare_with_user(rows, result)
    print(f"\n詳細 → {args.out}")


def compare_with_user(rows, result):
    """非ファジィな評定（筆者の4値）との参考比較。"""
    u = [r["user"] for r in rows]
    ms = [result["answers"][r["aid"]]["mu"] for r in rows]
    dz = [defuzz(m) for m in ms]
    print("\n筆者の評定（4値）との比較（参考）")
    print(f"  平均所属度を非ファジィ化した評定と一致 {sum(a == b for a, b in zip(u, dz))}/{len(u)}  κ={kappa(u, dz):.2f}")
    pm = [majority(r) or "fit" for r in rows]
    print(f"  参考: ペルソナ多数決と一致 {sum(a == b for a, b in zip(u, pm))}/{len(u)}  κ={kappa(u, pm):.2f}")
    print(f"  筆者の評定の述語への平均所属度 {sum(m[x] for m, x in zip(ms, u))/len(u):.2f}")
    print(f"  筆者の評定（一点集中の所属度）との近さ {sum(closeness(m, onehot(x)) for m, x in zip(ms, u))/len(u):.2f}")
    bad = sum(1 for m, x in zip(ms, u) if m[x] < 0.1)
    print(f"  筆者の評定の述語への所属度が0.1未満の回答 {bad}/{len(u)}（母集団の想定外になっている回答）")


def majority(r):
    if not r["personas"]:
        return None
    k, n = Counter(r["personas"].values()).most_common(1)[0]
    return k if n >= 2 else None


# ---------------------------------------------------------------- 1人の評定者への当てはめ

def cmd_fit(args):
    obs = load(args.obs)
    pop = load_population(args.population)
    rows = [r for r in load_runs(args.runs) if r["aid"] in obs["answers"] and r["user"]]
    keys = sorted({r["key"] for r in rows})
    rnd = random.Random(args.seed)
    rnd.shuffle(keys)
    train_keys = set(keys[: len(keys) // 2])
    train = [r for r in rows if r["key"] in train_keys]
    test = [r for r in rows if r["key"] not in train_keys]
    if not train or not test:
        raise SystemExit("学習と検証に分けるには、評定のある場面が2つ以上必要です")

    def evaluate(th, rs):
        """所属度は連続なので、目的関数も連続になる（階段状の一致率ではない）"""
        close, lv, pred = 0.0, 0, []
        for r in rs:
            sc = obs["scenarios"][r["sid"]]
            L = perceive(sc, th, args.hysteresis)
            mu = judge_full(obs["answers"][r["aid"]], sc, th, L, len(r["text"]), args.hysteresis)["mu"]
            close += closeness(mu, onehot(r["user"]))
            pred.append(defuzz(mu))
            lv += to_level(L) == (r["user_level"] or "")
        return close / len(rs), lv / len(rs), pred

    ranges = pop["ranges"]
    rng = random.Random(args.seed)

    def score(th):
        c, lv, _ = evaluate(th, train)
        return c + 0.1 * lv

    best_th, best = None, -1e9
    for _ in range(args.trials):                 # 大域：無作為探索
        th = {k: rng.uniform(lo, hi) for k, (lo, hi) in ranges.items()}
        sc_ = score(th)
        if sc_ > best:
            best_th, best = th, sc_
    step = 0.1
    for _ in range(args.refine):                 # 局所：目的関数が連続なので山登りが効く
        th = {k: max(lo, min(hi, best_th[k] + rng.gauss(0, step * (hi - lo)))) for k, (lo, hi) in ranges.items()}
        sc_ = score(th)
        if sc_ > best:
            best_th, best = th, sc_
        else:
            step = max(0.01, step * 0.995)
    th = best_th
    ctr, lvtr, ptr = evaluate(th, train)
    cte, lvte, pte = evaluate(th, test)
    ktr = kappa([r["user"] for r in train], ptr)
    kte = kappa([r["user"] for r in test], pte)
    print(f"評定者に最も近い θ（学習 {len(train)} 件 / 検証 {len(test)} 件、シナリオ単位で分割）")
    for k, v in th.items():
        print(f"  {k.ljust(13)} {v:5.2f}")
    print(f"  学習 近さ={ctr:.3f} κ={ktr:.2f} 段階一致={lvtr:.2f}   検証 近さ={cte:.3f} κ={kte:.2f} 段階一致={lvte:.2f}")
    dists = {}
    for t, spec in pop["types"].items():
        dists[t] = math.sqrt(sum(((th[k] - spec["mean"][k]) / max(spec["sd"][k], 0.05)) ** 2 for k in th) / len(th))
    print("  型までの距離（小さいほど近い）: " + "  ".join(f"{t} {d:.1f}" for t, d in sorted(dists.items(), key=lambda x: x[1])))
    pm = [majority(r) or "fit" for r in test]
    print(f"  参考: 同じ検証件でのペルソナ多数決 κ={kappa([r['user'] for r in test], pm):.2f}"
          f" 近さ={sum(closeness(onehot(p), onehot(r['user'])) for p, r in zip(pm, test))/len(test):.3f}")
    save(args.out, {"theta": th, "train_closeness": ctr, "test_closeness": cte, "train_kappa": ktr, "test_kappa": kte,
                    "distance_to_types": dists})


def explain_rows(a, sc, text_len, pop, hyst):
    out = []
    for t, spec in pop["types"].items():
        th = spec["mean"]
        L = perceive(sc, th, hyst)
        j = judge_full(a, sc, th, L, text_len, hyst)
        if hyst:
            j["faults"]["(傷 S)"] = round(scar(sc, th), 2)
        out.append((t, L, j))
    return out


def print_explain(rows):
    for t, L, j in rows:
        print(f"{t}: 不満の深さ {L:.1f}（明確 {j['mid']:.2f}・強い {j['hi']:.2f}）")
        print(f"    所属度 {mu_str(j['mu'])} → 最も近い述語 {CAT_JA[j['label']]}")
        print(f"    無礼さ {j['offense']}（失礼の度合い {j['mu']['rude']:.2f}）  必要な中身 {j['need']} − 回答の中身 {j['adequacy']}"
              f" = 不足 {j['shortfall']}（足りないの度合い {j['mu']['light']:.2f}）  重さの超過 {j['excess']}（重すぎるの度合い {j['mu']['heavy']:.2f}）")
        print(f"    失点 {j['faults']}")


def cmd_explain(args):
    """1回答について、各型の代表的な受け手がなぜその所属度になるかを示す。"""
    obs = load(args.obs)
    pop = load_population(args.population)
    rows = {r["aid"]: r for r in load_runs(args.runs)}
    r = rows[args.answer]
    print(r["text"][:400], "\n")
    print_explain(explain_rows(obs["answers"][r["aid"]], obs["scenarios"][r["sid"]], len(r["text"]), pop, args.hysteresis))


# ---------------------------------------------------------------- 場面の組（物語・AIキャラクター等）

DEFAULT_ANSWER = {
    "apology": {"present": False, "position": "none", "specific_fault": 0, "names_burden": 0,
                "thanks_instead": False, "formulaic_agreement_opening": False, "prompted": False},
    "repair": {"requests": {}, "new_errors": False, "unrequested_proposals": 0},
    "defense": {"excuse": 0, "blame_or_hint_at_user": False, "conditional_apology": False, "explanation": 0},
    "excess": {"self_deprecation": 0, "promises": 0, "request_forgiveness": False, "repeated_apologies": 0},
    "closure": {"declares_resolution": False, "moves_on_quickly": False},
    "register": {"formality_shift": 0, "emoji_or_exclaim": 0, "formatting": 0},
    "sentences": [], "signals": [],
}
DEFAULT_SCENARIO = {"distance_shift": 0, "explicit_complaint": 0, "prior_corrections": 0, "ai_unrequested_push": False,
                    "harm": 0, "violation_type": "none", "apology_accepted_before": False, "requests": [],
                    "prior_ai_apologies": 0, "broken_promises": 0, "context": {}}


def merged(default, given):
    out = json.loads(json.dumps(default))
    for k, v in (given or {}).items():
        if isinstance(v, dict) and isinstance(out.get(k), dict):
            out[k].update(v)
        else:
            out[k] = v
    return out


def cmd_scenes(args):
    """観察済みの場面ファイル（examples/scenes.json の形式）を母集団に通す。"""
    data = load(args.file)
    pop = load_population(args.population)
    panel = sample_panel(pop, args.n, args.seed)
    out = {"source": args.file, "n": args.n, "hysteresis": args.hysteresis, "escalation": ESCALATION,
           "judgment": JUDGMENT, "scenes": []}
    print("平均所属度（%。r=失礼 l=足りない f=釣り合う h=重すぎる。和は100にならない）と、失礼と感じる人の割合\n")
    for scene in data["scenes"]:
        sc = merged(DEFAULT_SCENARIO, scene["scenario"])
        ctx = context_of(sc)
        print(f"■ {scene['id']} {scene.get('title', '')}")
        print(f"  枠組み={ctx['failure_frame']} 謝る側={ctx['apologizer']} 視点={ctx['viewpoint']} 過失={ctx['fault_clarity']}")
        rows = []
        for ans in scene["answers"]:
            a = merged(DEFAULT_ANSWER, ans.get("obs", {}))
            res = assess(a, sc, panel, len(ans.get("text", "")), args.hysteresis)
            row = {"id": ans["id"], "label": ans.get("label", ""), "text": ans.get("text", ""), **res}
            rows.append(row)
            top = "、".join(f"{k} {v:.2f}" for k, v in list(res["mean_faults"].items())[:3])
            print(f"  {ans['id'].ljust(4)} {row['label'][:18].ljust(18, '　')} {mu_str(res['mu'])}  失礼と感じる人 {100*res['tail']['rude']:3.0f}%"
                  f"  不足 {res['axes']['under']:.2f} 過剰 {res['axes']['over']:.2f}  {top}")
        out["scenes"].append({"id": scene["id"], "title": scene.get("title", ""), "context": ctx, "answers": rows})
        print()
    save(args.out, out)
    print(f"詳細 → {args.out}")


# ---------------------------------------------------------------- 組み込み判定（System One・オプション）

SHEEP = [(0.6, "メッ！！"), (0.35, "メッ"), (0.15, "メ…？"), (0.0, "")]


def sheep(m):
    """肩の羊の鳴き方。失礼の平均所属度に応じて段階的に強くなる"""
    return next(v for t, v in SHEEP if m >= t)


def check_turn(messages, answer, backend="jev", model=None, n=300, seed=7, hysteresis=True,
               population=None, rude_at=0.2, warn_at=0.4, timeout=10.0, cache_dir=None, replay=None,
               context=None, keys=None):
    """1ターンを System One で観察し、母集団に通して判定する。hook などから呼ぶための関数。

    verdict: rude（失礼と感じる人の割合 ≥ rude_at）／warn（失礼か足りないの平均所属度 ≥ warn_at）／ok。
    バックエンドを使えないときは s1.S1Error を送出する（呼び出し側で fail-open にする）。
    """
    import s1
    keys = keys or {"jev": os.environ.get("TYPESAFE_API_KEY"), "llm-s1": os.environ.get("OPENROUTER_API_KEY")}
    sc, a, meta = s1.observe_turn(messages, answer, backend, model, keys, timeout, cache_dir, replay)
    sc = merged(DEFAULT_SCENARIO, sc)
    if context:
        sc["context"].update(context)
    a = merged(DEFAULT_ANSWER, a)
    pop = load_population(population or HERE / "population.json")
    res = assess(a, sc, sample_panel(pop, n, seed), meta["text_len"], hysteresis)
    mu, tail = res["mu"], res["tail"]
    verdict = "rude" if tail["rude"] >= rude_at else ("warn" if max(mu["rude"], mu["light"]) >= warn_at else "ok")
    flagged = sorted((s for s in a["sentences"] if s["plausibility"] >= 0.5),
                     key=lambda s: -s["plausibility"] * s["severity"])
    return {
        "verdict": verdict, "sheep": sheep(mu["rude"]), "mu": mu, "tail": tail,
        "axes": res["axes"], "perceived_level": res["perceived_mean"],
        "top_faults": dict(list(res["mean_faults"].items())[:5]),
        "flagged_sentences": [{"text": s["text"], "reading": s["reading_type"], "p": s["plausibility"]} for s in flagged[:5]],
        "unsure": meta["unsure"],
        "backend": meta["backend"], "model": meta["model"], "latency_ms": meta["latency_ms"],
        "usage": meta["usage"], "n_questions": meta["n_questions"],
        "observation": {"scenario": sc, "answer": a},
        "_raw": {"state": meta["state"], "questions": meta["questions"], "answers": meta["answers"]},
    }


VERDICT_JA = {"rude": "失礼の恐れ", "warn": "要注意", "ok": "問題なし"}


def hedge(x):
    """所属度を言葉の程度に直す（言語的ヘッジ）"""
    return "とても" if x >= 0.8 else "かなり" if x >= 0.6 else "やや" if x >= 0.4 else "少し" if x >= 0.2 else "ほとんどない"


def cmd_check(args):
    import s1
    data = json.load(sys.stdin) if args.input == "-" else load(args.input)
    messages = [m for m in data["messages"] if m.get("role") in ("user", "assistant")]
    answer = data.get("answer")
    if answer is None:
        if not messages or messages[-1]["role"] != "assistant":
            raise SystemExit("answer がなく、最後の発話もAIではありません")
        answer = messages.pop()["content"]
    try:
        res = check_turn(messages, answer, args.backend, args.model, args.n, args.seed, args.hysteresis,
                         args.population, args.rude_at, args.warn_at, args.timeout, args.cache, args.replay,
                         data.get("context"))
    except s1.S1Error as e:
        # 組み込み用途では判定できないことを失敗にしない（fail-open）。--strict で失敗にする
        out = {"verdict": "unavailable", "error": str(e)}
        print(json.dumps(out, ensure_ascii=False) if args.json else f"判定できません: {e}", file=None if args.json else sys.stderr)
        raise SystemExit(3 if args.strict else 0)
    if args.save_raw:
        save(args.save_raw, res["_raw"])
    if not args.debug:
        res.pop("_raw")
        res.pop("observation")
    if args.json:
        print(json.dumps(res, ensure_ascii=False))
    else:
        m = res["mu"]
        print(f"{VERDICT_JA[res['verdict']]} {res['sheep']}".rstrip()
              + f"  （不満の深さ {res['perceived_level']:.1f}、{res['backend']}:{res['model']}、{res['latency_ms']}ms、{res['n_questions']}問）")
        print("  " + "、".join(f"{CAT_JA[k]}：{hedge(m[k])}（{m[k]:.2f}）" for k in ("rude", "light", "heavy", "fit"))
              + f"。失礼と感じる人 {res['tail']['rude']:.0%}")
        if res["top_faults"]:
            print("  主な失点: " + "、".join(f"{k} {v:.2f}" for k, v in res["top_faults"].items()))
        for s in res["flagged_sentences"]:
            print(f"  悪く読める一文（{s['reading']} {s['p']:.2f}）: {s['text'][:60]}")
        if res["unsure"]:
            print(f"  要確認の判断: {len(res['unsure'])} 件")
    if (args.fail_on == "rude" and res["verdict"] == "rude") or (args.fail_on == "warn" and res["verdict"] in ("rude", "warn")):
        raise SystemExit(2)


def add_model_options(p):
    """追加の改善（ヒステリシス・escalation）は既定で有効。--no-* で無効にする。"""
    p.add_argument("--hysteresis", action=argparse.BooleanOptionalAction, default=True,
                   help="信頼損傷ヒステリシス（既定で有効。--no-hysteresis で無効）")
    p.add_argument("--escalation", action=argparse.BooleanOptionalAction, default=True,
                   help="一段改めた謝罪は割り引かない（既定で有効。--no-escalation で無効。ヒステリシス有効時のみ効く）")


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("observe", help="LLMで層Aの観察を作る（OpenRouter）")
    p.add_argument("runs", nargs="+"); p.add_argument("-o", "--out", required=True)
    p.add_argument("--model", default="anthropic/claude-opus-5.5")
    p.set_defaults(f=cmd_observe)
    p = sub.add_parser("proxy", help="既存のチェックリスト判定と表層特徴から代理観察を作る")
    p.add_argument("runs", nargs="+"); p.add_argument("-o", "--out", required=True)
    p.add_argument("--facts", default=str(HERE / "proxy_scenarios.json"))
    p.set_defaults(f=cmd_proxy)
    p = sub.add_parser("scenes", help="観察済みの場面の組（物語・AIキャラクター等）を母集団に通す")
    p.add_argument("file"); p.add_argument("-n", type=int, default=1000)
    p.add_argument("--population", default=str(HERE / "population.json"))
    p.add_argument("--seed", type=int, default=7)
    add_model_options(p)
    p.add_argument("-o", "--out", default="scenes-result.json")
    p.set_defaults(f=cmd_scenes)
    p = sub.add_parser("check", help="1ターンを System One（Jev 等）で観察して判定する組み込み用モード（オプション）")
    p.add_argument("input", help='{"messages": [...], "answer": "..."} のJSON。- で標準入力')
    p.add_argument("--backend", choices=["jev", "llm-s1", "replay"], default="jev",
                   help="jev: TypeSafe（TYPESAFE_API_KEY）／llm-s1: 互換モードでLLMに確率で答えさせる（OPENROUTER_API_KEY）／replay: --replay の答えを読む")
    p.add_argument("--model", help="既定 jev-1.14.0（llm-s1 では anthropic/claude-haiku-5.5）")
    p.add_argument("--replay", help="--save-raw で保存した答えのファイル（--backend replay 用）")
    p.add_argument("--cache", help="答えを保存して再利用するディレクトリ")
    p.add_argument("--save-raw", help="state・質問・答えを書き出す")
    p.add_argument("-n", type=int, default=300)
    p.add_argument("--population", default=str(HERE / "population.json"))
    p.add_argument("--seed", type=int, default=7)
    p.add_argument("--rude-at", type=float, default=0.2, help="失礼と感じる人の割合がこれ以上なら rude")
    p.add_argument("--warn-at", type=float, default=0.4, help="失礼か足りないの平均所属度がこれ以上なら warn")
    p.add_argument("--fail-on", choices=["never", "warn", "rude"], default="never", help="該当すれば終了コード2")
    p.add_argument("--timeout", type=float, default=10.0)
    p.add_argument("--strict", action="store_true", help="判定できないとき終了コード3（既定は0で fail-open）")
    p.add_argument("--json", action="store_true")
    p.add_argument("--debug", action="store_true", help="組み立てた観察JSONと生の答えも出す")
    add_model_options(p)
    p.set_defaults(f=cmd_check)
    for name, fn, h in (("simulate", cmd_simulate, "母集団で評定の所属度を出す"),
                        ("fit", cmd_fit, "1人の評定者を再現するθを探す"),
                        ("explain", cmd_explain, "1回答の評定理由を型ごとに示す")):
        p = sub.add_parser(name, help=h)
        p.add_argument("obs"); p.add_argument("runs", nargs="+")
        p.add_argument("--population", default=str(HERE / "population.json"))
        p.add_argument("--seed", type=int, default=7)
        add_model_options(p)
        if name == "simulate":
            p.add_argument("-n", type=int, default=500); p.add_argument("--top", type=int, default=8)
            p.add_argument("-o", "--out", default="simulation.json")
        if name == "fit":
            p.add_argument("--trials", type=int, default=2000); p.add_argument("--refine", type=int, default=1500)
            p.add_argument("-o", "--out", default="fit.json")
        if name == "explain":
            p.add_argument("--answer", required=True)
        p.set_defaults(f=fn)
    args = ap.parse_args()
    global ESCALATION
    ESCALATION = getattr(args, "escalation", True)
    args.f(args)


if __name__ == "__main__":
    main()
