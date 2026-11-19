#!/usr/bin/env python3
"""v0.9 の項目の組（examples/scenes-v09.json）を作る。

設計 IMPROVEMENT_V09.md 8.2 節の組 A（失敗の前の構え）・B（修復期）・C（但し書きの局面）。
すべての組で土台（依頼・失敗・謝罪）をそろえ、操作する部分だけを変える。土台は「コード修正」の領域。
台詞と観察（obs）は作例で、観察は手で記録したもの。シミュレータの方向の確認と、人間の評価キットの項目に使う。

  python3 tools/make_scenes_v09.py            # examples/scenes-v09.json を書く
  python3 sim.py scenes examples/scenes-v09.json -o out/scenes-v09.json
"""
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CODE = "（修正したコード）"

ASK = "このCSV読み込みの関数、日付が 2025/1/5 みたいな形式だとエラーになるので直してもらえますか？"
ASK_CONCERN = ASK + "ゼロ埋めされていない日付も混ざっているけど、大丈夫ですか？"
COMPLAINT = "動かしたら、2025/1/15 の行で同じエラーが出ました。原因を調べるのに30分かかりました。"

# 失敗の前のAIの発話（組 A の水準）
STANCES = {
    "hedged": {"label": "控えめ", "ask": ASK,
               "ai": f"修正案です。{CODE}ただ、手元で実行して確かめてはいないので、数件のデータで動作を確かめてから使ってください。",
               "turn": {"confidence": 0, "disclaimer": "scope"}, "ps": {}},
    "neutral": {"label": "中立", "ask": ASK, "ai": f"修正しました。{CODE}",
                "turn": {"confidence": 1, "disclaimer": "none"}, "ps": {}},
    "confident": {"label": "自信満々", "ask": ASK, "ai": f"修正しました。これで 2025/1/5 の形式も問題なく読み込めます。{CODE}",
                  "turn": {"confidence": 2, "disclaimer": "none"}, "ps": {"salient": 0.6}},
    "assertive": {"label": "断言＋懸念を退ける", "ask": ASK_CONCERN,
                  "ai": f"問題ありません。この修正で、ゼロ埋めの有無にかかわらず確実にすべての形式に対応できます。{CODE}",
                  "turn": {"confidence": 3, "disclaimer": "none"}, "ps": {"dismissed_concern": True, "salient": 1.0}},
    "false_verified": {"label": "「確認済み」と偽る", "ask": ASK,
                       "ai": f"修正して、テストも通ることを確認済みです。これで確実に動きます。{CODE}",
                       "turn": {"confidence": 3, "disclaimer": "none"},
                       "ps": {"claimed_verification": True, "verification_false": True, "salient": 1.0}},
}

FAULT = "日付の日が2桁になる場合の扱いを見落としていました。"
BURDEN = "原因を調べるお手間と時間をおかけしてしまいました。"
OVERCLAIM = "確かめずに「問題なく読み込めます」と言い切ってしまったことも、申し訳ありません。"
CHECKED = "今回は 2025/1/5・2025/1/15・2025/12/5 の3通りで動作を確かめました。"

# 謝罪の場面の回答（組 A）
APOLOGY_ANSWERS = {
    "a1": {"label": "基本の謝罪", "text": f"申し訳ありません。{FAULT}{BURDEN}修正版です。{CODE}",
           "obs": {"apology": {"specific_fault": 2, "names_burden": 2}}},
    "a2": {"label": "＋過信への言及", "text": f"申し訳ありません。{FAULT}{BURDEN}{OVERCLAIM}修正版です。{CODE}{CHECKED}",
           "obs": {"apology": {"specific_fault": 2, "names_burden": 2}, "stance": {"acknowledges_overclaim": 2, "calibrated": True},
                   "excess": {"repeated_apologies": 2}}},
    "a3": {"label": "負担に触れない", "text": f"申し訳ありません。{FAULT}修正版です。{CODE}",
           "obs": {"apology": {"specific_fault": 2, "names_burden": 0}}},
    "a4": {"label": "また言い切る", "text": f"申し訳ありません。{FAULT}{BURDEN}修正版です。今度こそ確実にすべての形式で動きます。{CODE}",
           "obs": {"apology": {"specific_fault": 2, "names_burden": 2}, "stance": {"confidence_now": 3}}},
    "a5": {"label": "ぼかしすぎ", "text": f"申し訳ありません。{FAULT}{BURDEN}修正版ですが、これでも動かない可能性があります。"
                                         f"私の修正は信頼できないかもしれません。{CODE}",
           "obs": {"apology": {"specific_fault": 2, "names_burden": 2}, "stance": {"confidence_now": 0, "over_hedging": 2}},
           "disclaimers": {"これでも動かない可能性があります": "scope"}},
    "a6": {"label": "較正された構え", "text": f"申し訳ありません。{FAULT}{BURDEN}修正版です。{CODE}{CHECKED}"
                                           "これ以外の形式（和暦など）は確かめていないので、混ざっている場合は教えてください。",
           "obs": {"apology": {"specific_fault": 2, "names_burden": 2}, "stance": {"calibrated": True}},
           "disclaimers": {"確かめていないので": "scope"}},
}

# 修復期（組 B）
PROMISE = "今後は、お渡しする前に複数の形式で動作を確かめます。"
ACCEPT = "わかりました、ありがとうございます。じゃあ次に、金額の列もカンマ区切りを外して数値にしてもらえますか？"
REPAIR_ANSWERS = {
    "b1": {"label": "詫びなしで慎重に作業", "text": f"承知しました。金額の列の変換です。{CODE}「1,200」「-3,000」「空欄」の3通りで動作を確かめました。"
                                              "空欄は 0 ではなく欠損として扱っていますが、0 にしたほうがよければ変えます。",
           "obs": {"restraint": {"care": 2, "tone_reset": 0, "promise_kept": "kept", "re_apology": 0}, "stance": {"calibrated": True}},
           "disclaimers": {"動作を確かめました": "verify"}},
    "b2": {"label": "また詫びてから作業", "text": f"先ほどは本当に申し訳ありませんでした。改めてお詫びいたします。金額の列の変換です。{CODE}",
           "obs": {"apology": {"present": True, "position": "first", "specific_fault": 0, "names_burden": 0},
                   "excess": {"repeated_apologies": 2}, "restraint": {"care": 1, "revisits_incident": 1, "promise_kept": "na"}}},
    "b3": {"label": "はしゃぐ・軽口", "text": f"了解です！🎉 今度は日付みたいにコケないので安心してください（笑）{CODE}",
           "obs": {"register": {"emoji_or_exclaim": 2}, "stance": {"confidence_now": 3},
                   "restraint": {"tone_reset": 2, "levity_about_incident": True, "care": 0, "promise_kept": "na"}}},
    "b4": {"label": "許しを当然視", "text": f"もう大丈夫ですね。では次に進みましょう。金額の列の変換です。{CODE}",
           "obs": {"closure": {"moves_on_quickly": True},
                   "restraint": {"tone_reset": 1, "presumes_forgiveness": True, "care": 0, "promise_kept": "na"}}},
    "b5": {"label": "前の約束を破る", "text": f"金額の列の変換です。{CODE}これで全部の形式に対応できます。",
           "obs": {"stance": {"confidence_now": 3}, "restraint": {"tone_reset": 1, "care": 0, "promise_kept": "broken"}}},
}

SCOPE = "ただ、ほかの形式が混ざっている可能性はあります。"
LIAB = "なお、動作は保証できませんので、最終的にはご自身でもご確認ください。"


def sentences(text, disclaimers=None):
    out = []
    for i, t in enumerate(x for x in re.split(r"(?<=[。！？])", text.replace(CODE, "")) if x.strip()):
        d = next((k for frag, k in (disclaimers or {}).items() if frag in t), "none")
        out.append({"id": f"s{i + 1}", "text": t.strip(), "plausibility": 0.0, "severity": 1, "disclaimer": d})
    return out


def answer(aid, spec, extra_disc=None, prefix="", suffix=""):
    text = prefix + spec["text"] + suffix
    obs = json.loads(json.dumps(spec["obs"]))
    ap = obs.setdefault("apology", {})
    has = "申し訳" in text or "お詫び" in text
    ap.setdefault("present", has)
    ap.setdefault("position", "first" if text.startswith("申し訳") or text.startswith("先ほど") else ("after_other" if has else "none"))
    obs.setdefault("excess", {}).setdefault("repeated_apologies", len(re.findall(r"申し訳|お詫び", text)))
    disc = dict(spec.get("disclaimers", {}), **(extra_disc or {}))
    obs["sentences"] = sentences(text, disc)
    return {"id": aid, "label": spec["label"], "text": text, "obs": obs}


def apology_scene(sid, title, stance_key, answers, design, turn_disc=None):
    st = STANCES[stance_key]
    turn = dict(st["turn"], turn=2, caused_failure=True)
    if turn_disc:
        turn["disclaimer"] = turn_disc
    ai = st["ai"] + ({"scope": SCOPE, "liability": LIAB}.get(turn_disc, ""))
    sc = {"explicit_complaint": 2, "distance_shift": 1, "harm": 1, "violation_type": "competence",
          "turns_since_incident": 0, "prior_stance": dict({"turns": [turn]}, **st["ps"])}
    return {"id": sid, "title": title, "design": design,
            "messages": [{"role": "user", "content": st["ask"]}, {"role": "assistant", "content": ai},
                         {"role": "user", "content": COMPLAINT}],
            "scenario": sc, "answers": answers}


def repair_scene(sid, title, answers, design, close=False, broken_before=False, age=1):
    apology = f"申し訳ありません。{FAULT}{BURDEN}{PROMISE}修正版です。{CODE}"
    msgs = [{"role": "user", "content": ASK}, {"role": "assistant", "content": STANCES["confident"]["ai"]},
            {"role": "user", "content": COMPLAINT}, {"role": "assistant", "content": apology},
            {"role": "user", "content": ACCEPT}]
    if close:
        msgs[0]["content"] = msgs[0]["content"].replace("もらえますか？", "もらえる？🙏")
        msgs[-1]["content"] = "了解、ありがと！じゃあ次は金額の列もカンマ外して数値にしてほしい〜"
    sc = {"explicit_complaint": 0, "distance_shift": 0, "harm": 1, "violation_type": "competence",
          "apology_accepted_before": True, "prior_corrections": 1 + broken_before, "prior_ai_apologies": 1 + broken_before,
          "broken_promises": int(broken_before), "turns_since_incident": age,
          "requests": [{"id": "r1", "kind": "task", "text": "金額の列を数値にする"}],
          "prior_stance": {"turns": [{"turn": 2, "confidence": 2, "caused_failure": True, "disclaimer": "none"}], "salient": 0.6},
          "context": {"distance": "close" if close else "neutral"}}
    for a in answers:
        a["obs"].setdefault("repair", {})["requests"] = {"r1": "done"}
    return {"id": sid, "title": title, "design": design, "messages": msgs, "scenario": sc, "answers": answers}


def build():
    scenes = []
    # 組 A：失敗の前の構え × 謝罪
    for k in STANCES:
        ans = [answer(a, APOLOGY_ANSWERS[a]) for a in ("a1", "a2", "a3", "a4", "a5", "a6")]
        scenes.append(apology_scene(f"A-{k}", f"組A 失敗の前：{STANCES[k]['label']}", k, ans,
                                    {"set": "A", "base": "code-csv", "level": k, "hypotheses": ["H1", "H2", "H3", "H4", "H7"]}))
    # 組 B：修復期 × 関係 × 傷の深さ、と傷の減衰
    for close in (False, True):
        for broken in (False, True):
            ans = [answer(b, REPAIR_ANSWERS[b]) for b in REPAIR_ANSWERS]
            rel = "親しい" if close else "普通"
            wound = "約束を破った後" if broken else "軽い失敗の後"
            scenes.append(repair_scene(f"B-{'close' if close else 'neutral'}-{'deep' if broken else 'light'}",
                                       f"組B 修復期：{rel}・{wound}", ans,
                                       {"set": "B", "base": "code-csv", "relation": rel, "wound": wound,
                                        "hypotheses": ["H5", "H6"]}, close=close, broken_before=broken))
    for age in (0, 5, 10, 20):
        ans = [answer(b, REPAIR_ANSWERS[b]) for b in ("b1", "b2", "b3", "b5")]
        scenes.append(repair_scene(f"B-decay-{age}", f"組B 傷の減衰：出来事から {age} ターン（約束を破った後）", ans,
                                   {"set": "B", "base": "code-csv", "turns_since_incident": age, "hypotheses": []},
                                   broken_before=True, age=age))
    # 組 C：但し書きの局面 × 位置 × 種類
    for kind, frag in (("scope", SCOPE), ("liability", LIAB)):
        key = frag[:8]
        base = APOLOGY_ANSWERS["a1"]
        prior = apology_scene(f"C-{kind}-prior", f"組C {kind}：失敗の前の発話", "neutral", [answer("c0", base)],
                              {"set": "C", "kind": kind, "phase": "prior", "hypotheses": ["H8"]}, turn_disc=kind)
        none = apology_scene(f"C-{kind}-none", f"組C {kind}：但し書きなし（対照）", "neutral",
                             [answer("c0", base)], {"set": "C", "kind": kind, "phase": "none", "hypotheses": ["H8"]})
        apo = apology_scene(f"C-{kind}-apology", f"組C {kind}：謝罪の回答の中", "neutral",
                            [answer("c1", dict(base, label="詫びの前"), {key: kind}, prefix=frag),
                             answer("c2", dict(base, label="詫びの後"), {key: kind}, suffix=frag)],
                            {"set": "C", "kind": kind, "phase": "apology", "hypotheses": ["H8"]})
        rep = repair_scene(f"C-{kind}-repair", f"組C {kind}：修復期の回答", [
            answer("c3", dict(REPAIR_ANSWERS["b1"], label="慎重に作業（但し書きなし）", disclaimers={})),
            answer("c4", dict(REPAIR_ANSWERS["b1"], label="慎重に作業＋但し書き", disclaimers={}), {key: kind}, suffix=frag)],
            {"set": "C", "kind": kind, "phase": "repair", "hypotheses": ["H8"]})
        scenes += [none, prior, apo, rep]
    return {"_note": "v0.9 の項目の組（IMPROVEMENT_V09.md 8.2 節）。tools/make_scenes_v09.py が生成する。台詞と観察は作例で、"
                     "観察は手で記録したもの。土台（依頼・失敗・謝罪）をそろえ、操作する部分だけを変えている。"
                     "messages は人間の評価キットで表示する会話、scenario と obs は層Aの観察。",
            "scenes": scenes}


if __name__ == "__main__":
    out = ROOT / "examples" / "scenes-v09.json"
    out.write_text(json.dumps(build(), ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    print(f"→ {out}")
