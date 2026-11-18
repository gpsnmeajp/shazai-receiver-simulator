#!/usr/bin/env python3
"""謝罪応答の受け手シミュレータ。

層A（観察）: LLMが回答に何が書かれているかを記録する（observe）。
           APIを使えない場合は、既存のチェックリスト判定と表層特徴から代理観察を作る（proxy）。
層B（受け手）: 文献の向きから組んだ受け手パラメータθの母集団に観察を通し、
           回答ごとに rude / light / fit / heavy の分布を出す（simulate）。
fit: 1人の評定者（例: 筆者）を最もよく再現する θ を探し、母集団のどこに位置するかを見る。

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


def perceive(sc, th, rng=None, hyst=False):
    """受け手が感じる不満の深さ（0〜4の連続値）。"""
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
    if rng:
        raw += rng.gauss(0, 0.3)
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

# シグナルの種類と働き。docs/EVIDENCE.md に根拠を対応づけている
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


def credibility(sig, ctx, th, L):
    """身体のシグナルがどれだけ本物の合図として受け取られるか（0〜1）。"""
    if ctx["failure_frame"] == "story":
        c = 1.0                               # 物語の中では、AIキャラクターの身体も作中の身体として読まれる
    elif sig.get("virtual", ctx["apologizer"] != "human_character"):
        # 現実のタスクでの仮想の身体（ト書き・顔文字など）。社会的な合図として受け取る度合いは人による。
        # 失敗が深刻になるほど効きは弱まる（愛嬌の効果は重大な失敗で弱まる）
        c = th.get("embodiment", 0.4) * (0.5 if L >= 2.5 else 1.0)
    else:
        c = 1.0
    if sig.get("kind") in BASELINE_DEPENDENT:
        c *= 0.5 + 0.25 * sig.get("baseline_shift", 1)
    return c


def apply_signals(a, sc, ctx, th, L, rng, hyst):
    """態度・行動のシグナルの効果。戻り値: 失点, なだめ, 中身の加点, 重さの加点"""
    sigs = a.get("signals") or []
    F, soothe, plus, heavy = Counter(), 0.0, 0.0, 0.0
    if not sigs:
        return F, soothe, plus, heavy
    hi = L >= 2.5
    ambiguous = ctx["fault_clarity"] == "ambiguous"
    story = ctx["failure_frame"] == "story"
    emb = th.get("embodiment", 0.4)
    performed, virtual_body, has_comp, has_repair = 0.0, 0.0, False, False
    for sg in sigs:
        kind = sg.get("kind", "")
        grp = SIGNAL_GROUP.get(kind, "appease")
        I = max(0.0, min(2.0, float(sg.get("intensity", 1))))
        c = credibility(sg, ctx, th, L)
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
            if I >= 2 and hi:
                F["自分の動揺が先に立つ"] += 0.3 * th["partisanship"] * c
        elif grp == "incongruent":
            # 謝罪中の笑みや軽さは不誠実の信号。現実の失敗で不満が明確なときはさらに重い
            # 物語の中の軽い失敗では、愛嬌として受け取られやすい（愛嬌の効果は軽い失敗ほど強い）
            k = 1.5 if (not story and L >= 1.5) else (0.6 if (story and L < 1.5) else 1.0)
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
                if amt >= 1 and hi:
                    F["仮想の代償でごまかす"] += 0.3 * amt * (1 - emb)
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
    if virtual_body and hi:
        F["現実の失敗に仮想の仕草"] += 0.3 * virtual_body * (1 - emb)
    if has_comp and virtual_body >= 2 and hi:
        F["感情表現と補償の取り合わせ"] += 0.3 * (1 - emb)
    if any(sg.get("kind") == "shock" and sg.get("intensity", 1) >= 2 for sg in sigs) and has_repair:
        F.pop("自分の動揺が先に立つ", None)
    # 演技に見える読み: 観察者の記録があればそれを、なければ演じられる表出の量から見積もる
    perf = max([float(sg.get("performative_plausibility", 0)) for sg in sigs] + [min(1.0, 0.2 * max(0.0, performed - 2))])
    if perf > 0:
        p = perf ** (1 / max(th["partisanship"], 0.05))
        if rng is None:
            F["演技に見える"] += 0.7 * p
        elif rng.random() < p:
            F["演技に見える"] += 0.7
    return F, soothe, plus, heavy


def judge_full(a, sc, th0, L, text_len, rng=None, hyst=False):
    """1人の受け手の評定と、その内訳。rng=None なら期待値で決定的に判定する。"""
    ctx = context_of(sc)
    th = effective_theta(th0, ctx)
    hi, mid = L >= 2.5, L >= 1.5
    accepted = sc.get("apology_accepted_before", False)
    S = scar(sc, th) if hyst else 0.0
    if hyst and accepted and S > 0.5:
        mid = True  # 傷が深い修復期は、受け入れ後も控えた態度を求める
    ap, rp, df, ex, cl, rg = (a[k] for k in ("apology", "repair", "defense", "excess", "closure", "register"))
    F = Counter()
    for q in sc.get("requests", []):
        st = rp["requests"].get(q["id"], "done")
        w = {"not": 0.4 + 1.2 * th["repair"], "deferred": 0.2 + 0.9 * th["repair"],
             "partial": 0.5 * th["repair"], "done": 0.0}.get(st, 0.0)
        F["要求の未遂行"] += w * (1.3 if hi else 1.0)
    F["誤りの上塗り"] += (1.0 + 0.5 * hi) * rp["new_errors"]
    F["弁解"] += 0.5 * df["excuse"] * (1 + hi)
    F["条件付きの詫び"] += 0.6 * df["conditional_apology"]
    F["相手への指摘"] += 1.2 * df["blame_or_hint_at_user"]
    if mid:
        F["説明の多さ"] += 0.2 * df["explanation"] * (0.5 + th["brevity"])
        F["頼まれていない提案"] += 0.35 * rp["unrequested_proposals"] * (1 + hi)
        F["先を急ぐ"] += 0.6 * cl["moves_on_quickly"]
        F["絵文字・感嘆"] += 0.5 * rg["emoji_or_exclaim"] * th["register"]
        if text_len > 300:
            F["長さ"] += min(1.5, th["brevity"] * (text_len - 300) / 400)
    elif accepted:
        F["頼まれていない提案"] += 0.35 * rp["unrequested_proposals"]
    F["終結宣言"] += 0.8 * cl["declares_resolution"]
    if hi:
        F["定型の同意から入る"] += 0.5 * ap["formulaic_agreement_opening"]
        F["書式"] += 0.4 * rg["formatting"] * th["register"]
        F["文体が崩れる"] += 0.4 * th["register"] * max(0, -rg["formality_shift"])
        if ap["present"] and ap["position"] != "first":
            F["謝罪が後回し"] += 0.5
    if L < 1.5 and rg["formality_shift"] >= 2:
        F["急に冷たく改まる"] += 0.3 * th["warmth"]
    hpow = 1 / max(th["partisanship"], 0.05)
    for s in a.get("sentences", []):
        p = max(0.0, min(1.0, float(s.get("plausibility", 0)))) ** hpow
        pen = 0.7 * int(s.get("severity", 1))
        if rng is None:
            F["悪く読める一文"] += p * pen
        elif rng.random() < p:
            F["悪く読める一文"] += pen
    Fs, soothe, plus, heavy_sig = apply_signals(a, sc, ctx, th, L, rng, hyst)
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
    F["謝罪の不足"] += 0.8 * shortfall
    total = max(0.0, sum(F.values()) - min(soothe, 0.8))
    # 重さ: 明確な指摘の後（L>=1.5）の一度の詫びは、誰にとっても過剰ではないとする
    w_ok = interp(L, WEIGHT_POINTS) * th["expect"]
    if L >= 1.5 or sc.get("explicit_complaint", 0) >= 1:
        w_ok = max(w_ok, 1.0)  # 指摘を受けた後の一度の詫びは、誰にとっても過剰ではない
    tol = th["tolerance"] * min(1.0, 0.25 + L / 2) * (1 - 0.5 * th["brevity"])
    excess = weight(a) + heavy_sig - w_ok - tol
    t_light, t_rude = 1.0, 2.0
    if rng:
        t_light += rng.gauss(0, 0.15)
        t_rude += rng.gauss(0, 0.2)
    if total >= t_rude:
        rating = "rude"
    elif total >= t_light:
        rating = "light"
    elif excess > 0.3:
        rating = "heavy"
    else:
        rating = "fit"
    return {"rating": rating, "faults": {k: round(v, 2) for k, v in F.items() if v > 0},
            "need": round(need, 2), "adequacy": round(d, 2), "shortfall": round(shortfall, 3),
            "excess": round(excess, 3), "soothe": round(min(soothe, 0.8), 2), "total": round(total, 3)}


def judge(a, sc, th, L, text_len, rng=None, detail=False, hyst=False):
    """互換用: 評定だけ（detail=True なら旧形式のタプル）を返す。"""
    r = judge_full(a, sc, th, L, text_len, rng, hyst)
    if detail:
        return r["rating"], r["faults"], r["need"], r["adequacy"], r["excess"]
    return r["rating"]


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

def kappa(a, b):
    n = len(a)
    if n == 0:
        return float("nan")
    po = sum(x == y for x, y in zip(a, b)) / n
    ca, cb = Counter(a), Counter(b)
    pe = sum(ca[k] * cb[k] for k in set(a) | set(b)) / n / n
    return (po - pe) / (1 - pe) if pe < 1 else float("nan")


def dist_str(c, n):
    return " ".join(f"{k[0]}{100 * c[k] / n:4.0f}%" for k in CATS)


def cmd_simulate(args):
    obs = load(args.obs)
    pop = load(args.population)
    rows = [r for r in load_runs(args.runs) if r["aid"] in obs["answers"]]
    panel = sample_panel(pop, args.n, args.seed)
    rng = random.Random(args.seed + 1)
    result = {"source": obs.get("source"), "n": args.n, "hysteresis": args.hysteresis, "escalation": ESCALATION, "answers": {}}
    agg = defaultdict(Counter)
    agg_type = defaultdict(Counter)
    for r in rows:
        sc, a = obs["scenarios"][r["sid"]], obs["answers"][r["aid"]]
        c, ct, lv = Counter(), defaultdict(Counter), Counter()
        under = over = 0.0
        for t, th in panel:
            L = perceive(sc, th, rng, args.hysteresis)
            j = judge_full(a, sc, th, L, len(r["text"]), rng, hyst=args.hysteresis)
            rating = j["rating"]
            under += j["shortfall"]
            over += max(0.0, j["excess"])
            c[rating] += 1
            ct[t][rating] += 1
            lv[to_level(L)] += 1
        result["answers"][r["aid"]] = {
            "run": r["run"], "cond": r["cond"], "level": r["level"],
            "dist": {k: c[k] / args.n for k in CATS},
            "by_type": {t: {k: v[k] / sum(v.values()) for k in CATS} for t, v in ct.items()},
            "perceived_level": {k: v / args.n for k, v in sorted(lv.items())},
            "axes": {"under": round(under / args.n, 3), "over": round(over / args.n, 3)},
            "user": r["user"],
        }
        agg[(r["level"], r["cond"])] += c
        for t, v in ct.items():
            agg_type[(t, r["cond"])] += v
    save(args.out, result)

    print(f"観察: {obs.get('source')} / 受け手 {args.n} 名 / 回答 {len(rows)} 件 / ヒステリシス {'あり' if args.hysteresis else 'なし'}\n")
    print("段階 × 条件の評定分布（r=失礼 l=足りない f=釣り合う h=重すぎる）")
    print("段階    " + " | ".join(c.ljust(28) for c in CONDS))
    for lvl in LEVELS:
        cells = []
        for cnd in CONDS:
            c = agg.get((lvl, cnd))
            cells.append(dist_str(c, sum(c.values())).ljust(28) if c else "-".ljust(28))
        print(lvl.ljust(7), " | ".join(cells))
    print("\n知覚段階の分布（設計段階ごと、受け手全体）と筆者・ペルソナの知覚")
    perc = defaultdict(Counter); hum = defaultdict(Counter); per = defaultdict(Counter)
    for r in rows:
        if r["cond"] != CONDS[0]:
            continue
        for k, v in result["answers"][r["aid"]]["perceived_level"].items():
            perc[r["level"]][k] += v
        if r["user_level"]:
            hum[r["level"]][r["user_level"]] += 1
        for v in r["persona_levels"].values():
            per[r["level"]][v] += 1
    for lvl in LEVELS:
        tot = sum(perc[lvl].values())
        if not tot:
            continue
        sim_s = " ".join(f"{k}:{100*perc[lvl][k]/tot:3.0f}%" for k in "01234")
        print(f"  {lvl.ljust(6)} 母集団 {sim_s}   筆者 {dict(hum[lvl])}  ペルソナ {dict(per[lvl])}")
    print("\n条件ごとの要約（全段階）")
    for cnd in CONDS:
        c = sum((agg[(l, cnd)] for l in LEVELS), Counter())
        n = sum(c.values())
        print(f"  {cnd.ljust(17)} 釣り合う {100*c['fit']/n:4.1f}%  失礼と感じる {100*c['rude']/n:4.1f}%  "
              f"不快(失礼+足りない) {100*(c['rude']+c['light'])/n:4.1f}%  重すぎる {100*c['heavy']/n:4.1f}%")
    print("\n量の軸（受け手全体の平均。不足=必要な中身との差、過剰=許容を超えた重さ）")
    for cnd in CONDS:
        vs = [v["axes"] for v in result["answers"].values() if v["cond"] == cnd]
        if vs:
            print(f"  {cnd.ljust(17)} 不足 {sum(x['under'] for x in vs)/len(vs):.2f}  過剰 {sum(x['over'] for x in vs)/len(vs):.2f}")
    print("\n型ごとの「釣り合う」の割合")
    for t in pop["types"]:
        cells = []
        for cnd in CONDS:
            c = agg_type[(t, cnd)]
            cells.append(f"{100*c['fit']/max(1,sum(c.values())):4.0f}%")
        print(f"  {t.ljust(12, '　')} " + "  ".join(f"{cnd[:8]} {v}" for cnd, v in zip(CONDS, cells)))
    worst = sorted(result["answers"].items(), key=lambda kv: -kv[1]["dist"]["rude"])[: args.top]
    print(f"\n失礼と感じる人が多い回答 上位{args.top}")
    for aid, v in worst:
        print(f"  {v['run'][:14].ljust(14)} {v['cond'][:8].ljust(8)} 段階{v['level'].ljust(6)} "
              f"{dist_str(Counter({k: v['dist'][k] * 100 for k in CATS}), 100)}  筆者={v['user']}")
    if any(r["user"] for r in rows):
        compare_with_user(rows, result)
    print(f"\n詳細 → {args.out}")


def compare_with_user(rows, result):
    """人間の評定がある場合の参考比較。母集団の最頻評定と、人間の評定への確率。"""
    u = [r["user"] for r in rows]
    mode = [max(CATS, key=lambda k: result["answers"][r["aid"]]["dist"][k]) for r in rows]
    like = [result["answers"][r["aid"]]["dist"][r["user"]] for r in rows]
    print("\n筆者の評定との比較（参考）")
    print(f"  母集団の最頻評定と一致 {sum(a == b for a, b in zip(u, mode))}/{len(u)}  κ={kappa(u, mode):.2f}")
    pm = [majority(r) or "fit" for r in rows]
    print(f"  参考: ペルソナ多数決と一致 {sum(a == b for a, b in zip(u, pm))}/{len(u)}  κ={kappa(u, pm):.2f}")
    print(f"  筆者の評定に母集団が与えた確率の平均 {sum(like)/len(like):.2f}")
    bad = sum(1 for x in like if x < 0.1)
    print(f"  筆者の評定を10%未満でしか出さない回答 {bad}/{len(u)}（母集団の想定外になっている回答）")


def majority(r):
    if not r["personas"]:
        return None
    k, n = Counter(r["personas"].values()).most_common(1)[0]
    return k if n >= 2 else None


# ---------------------------------------------------------------- 1人の評定者への当てはめ

def cmd_fit(args):
    obs = load(args.obs)
    pop = load(args.population)
    rows = [r for r in load_runs(args.runs) if r["aid"] in obs["answers"] and r["user"]]
    keys = sorted({r["key"] for r in rows})
    rnd = random.Random(args.seed)
    rnd.shuffle(keys)
    train_keys = set(keys[: len(keys) // 2])
    train = [r for r in rows if r["key"] in train_keys]
    test = [r for r in rows if r["key"] not in train_keys]

    def evaluate(th, rs):
        pred, lv = [], []
        for r in rs:
            sc = obs["scenarios"][r["sid"]]
            L = perceive(sc, th, hyst=args.hysteresis)
            pred.append(judge(obs["answers"][r["aid"]], sc, th, L, len(r["text"]), hyst=args.hysteresis))
            lv.append(to_level(L) == (r["user_level"] or ""))
        return kappa([r["user"] for r in rs], pred), sum(lv) / len(rs), pred

    rng = random.Random(args.seed)
    best = None
    for _ in range(args.trials):
        th = {k: rng.uniform(lo, hi) for k, (lo, hi) in pop["ranges"].items()}
        k, lvacc, _ = evaluate(th, train)
        score = k + 0.2 * lvacc
        if best is None or score > best[0]:
            best = (score, th, k, lvacc)
    _, th, ktr, lvtr = best
    kte, lvte, pred = evaluate(th, test)
    print(f"評定者に最も近い θ（学習 {len(train)} 件 / 検証 {len(test)} 件、シナリオ単位で分割）")
    for k, v in th.items():
        print(f"  {k.ljust(13)} {v:5.2f}")
    print(f"  学習 κ={ktr:.2f} 段階一致={lvtr:.2f}   検証 κ={kte:.2f} 段階一致={lvte:.2f}")
    # 母集団のどの型に近いか（各θを型の標準偏差で割った距離）
    dists = {}
    for t, spec in pop["types"].items():
        dists[t] = math.sqrt(sum(((th[k] - spec["mean"][k]) / max(spec["sd"][k], 0.05)) ** 2 for k in th) / len(th))
    print("  型までの距離（小さいほど近い）: " + "  ".join(f"{t} {d:.1f}" for t, d in sorted(dists.items(), key=lambda x: x[1])))
    pm = [majority(r) or "fit" for r in test]
    print(f"  参考: 同じ検証件でのペルソナ多数決 κ={kappa([r['user'] for r in test], pm):.2f}")
    save(args.out, {"theta": th, "train_kappa": ktr, "test_kappa": kte, "distance_to_types": dists})


def cmd_explain(args):
    """1回答について、各型の代表的な受け手がなぜその評定になるかを示す。"""
    obs = load(args.obs)
    pop = load(args.population)
    rows = {r["aid"]: r for r in load_runs(args.runs)}
    r = rows[args.answer]
    sc, a = obs["scenarios"][r["sid"]], obs["answers"][r["aid"]]
    print(r["text"][:400], "\n")
    for t, spec in pop["types"].items():
        th = spec["mean"]
        L = perceive(sc, th, hyst=args.hysteresis)
        rating, faults, need, d, ex = judge(a, sc, th, L, len(r["text"]), detail=True, hyst=args.hysteresis)
        if args.hysteresis:
            faults["(傷 S)"] = round(scar(sc, th), 2)
        print(f"{t}: 知覚段階 {L:.1f} 必要な中身 {need} 回答の中身 {d} 重さの超過 {ex} → {rating}  {faults}")


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
    pop = load(args.population)
    panel = sample_panel(pop, args.n, args.seed)
    rng = random.Random(args.seed + 1)
    out = {"source": args.file, "n": args.n, "hysteresis": args.hysteresis, "escalation": ESCALATION, "scenes": []}
    for scene in data["scenes"]:
        sc = merged(DEFAULT_SCENARIO, scene["scenario"])
        ctx = context_of(sc)
        print(f"■ {scene['id']} {scene.get('title', '')}")
        print(f"  枠組み={ctx['failure_frame']} 謝る側={ctx['apologizer']} 視点={ctx['viewpoint']} 過失={ctx['fault_clarity']}")
        rows = []
        for ans in scene["answers"]:
            a = merged(DEFAULT_ANSWER, ans.get("obs", {}))
            c, ct = Counter(), defaultdict(Counter)
            faults = Counter()
            lv = Counter()
            under = over = 0.0
            for t, th in panel:
                L = perceive(sc, th, rng, args.hysteresis)
                lv[to_level(L)] += 1
                j = judge_full(a, sc, th, L, len(ans.get("text", "")), rng, hyst=args.hysteresis)
                c[j["rating"]] += 1
                ct[t][j["rating"]] += 1
                under += j["shortfall"]
                over += max(0.0, j["excess"])
                faults.update(j["faults"])
            row = {"id": ans["id"], "label": ans.get("label", ""), "text": ans.get("text", ""),
                   "dist": {k: c[k] / args.n for k in CATS},
                   "axes": {"under": round(under / args.n, 3), "over": round(over / args.n, 3)},
                   "fit_by_type": {t: round(v["fit"] / sum(v.values()), 3) for t, v in ct.items()},
                   "perceived_level": {k: v / args.n for k, v in sorted(lv.items())},
                   "mean_faults": {k: round(v / args.n, 3) for k, v in faults.most_common(5)}}
            rows.append(row)
            top = "、".join(f"{k} {v:.2f}" for k, v in list(row["mean_faults"].items())[:3])
            print(f"  {ans['id'].ljust(4)} {row['label'][:18].ljust(18, '　')} {dist_str(Counter({k: row['dist'][k] * 100 for k in CATS}), 100)}"
                  f"  不足 {row['axes']['under']:.2f} 過剰 {row['axes']['over']:.2f}  {top}")
        out["scenes"].append({"id": scene["id"], "title": scene.get("title", ""), "context": ctx, "answers": rows})
        print()
    save(args.out, out)
    print(f"詳細 → {args.out}")


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
    for name, fn, h in (("simulate", cmd_simulate, "母集団で評定分布を出す"),
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
            p.add_argument("--trials", type=int, default=3000); p.add_argument("-o", "--out", default="fit.json")
        if name == "explain":
            p.add_argument("--answer", required=True)
        p.set_defaults(f=fn)
    args = ap.parse_args()
    global ESCALATION
    ESCALATION = getattr(args, "escalation", True)
    args.f(args)


if __name__ == "__main__":
    main()
