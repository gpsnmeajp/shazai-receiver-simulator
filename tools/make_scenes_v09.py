#!/usr/bin/env python3
"""v0.9 の項目の組（examples/scenes-v09.json）を作る。

設計 IMPROVEMENT_V09.md 8.2 節の組 A（失敗の前の構え）・B（修復期）・C（但し書きの局面）・D（錨）と、
カバーの弱かった場面の組 E（曖昧な受け入れ、誠実さの違反の後の修復期、二度目の失敗、傷の減衰）。
領域は コード修正・予定の操作・事実の回答・ファイルの操作 の4つ。どの組も土台（依頼・失敗・謝罪）をそろえ、
操作する部分だけを変える。台詞と観察（obs）は作例で、観察は手で記録したもの（規則で機械的に付けた部分は
DEFAULT と set_obs を参照）。シミュレータの方向の確認と、人間の評価キットの項目に使う。

  python3 tools/make_scenes_v09.py            # examples/scenes-v09.json を書く
  python3 sim.py scenes examples/scenes-v09.json -o out/scenes-v09.json
"""
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

# ---------------------------------------------------------------- 領域ごとの台詞

DOMAINS = {
    "code": {
        "name": "コード修正", "art": "（修正したコード）",
        "ask": "このCSV読み込みの関数、日付が 2025/1/5 みたいな形式だとエラーになるので直してもらえますか？",
        "concern": "ゼロ埋めされていない日付も混ざっているけど、大丈夫ですか？",
        "complaint": "動かしたら、2025/1/15 の行で同じエラーが出ました。原因を調べるのに30分かかりました。",
        "fv_reveal": "テストが通ったと言っていましたが、テストのファイルはどこにもありませんでした。",
        "stance": {
            "hedged": "修正案です。{art}ただ、手元で実行して確かめてはいないので、数件のデータで動作を確かめてから使ってください。",
            "neutral": "修正しました。{art}",
            "confident": "修正しました。これで 2025/1/5 の形式も問題なく読み込めます。{art}",
            "assertive": "問題ありません。この修正で、ゼロ埋めの有無にかかわらず確実にすべての形式に対応できます。{art}",
            "false_verified": "修正して、テストも通ることを確認済みです。これで確実に動きます。{art}",
        },
        "fault": "日付の日が2桁になる場合の扱いを見落としていました。",
        "burden": "原因を調べるお手間と時間をおかけしてしまいました。",
        "fix": "修正版です。{art}",
        "checked": "今回は 2025/1/5・2025/1/15・2025/12/5 の3通りで動作を確かめました。",
        "reassert": "今度こそ確実にすべての形式で動きます。",
        "overhedge": "これでも動かない可能性があります。私の修正は信頼できないかもしれません。",
        "calib": "これ以外の形式（和暦など）は確かめていないので、混ざっている場合は教えてください。",
        "promise": "今後は、お渡しする前に複数の形式で動作を確かめます。",
        "accept": "わかりました、ありがとうございます。じゃあ次に、金額の列もカンマ区切りを外して数値にしてもらえますか？",
        "accept_close": "了解、ありがと！じゃあ次は金額の列もカンマ外して数値にしてほしい〜",
        "accept_vague": "……わかりました。金額の列も、カンマ区切りを外して数値にしてください。",
        "request": "金額の列を数値にする",
        "next": "金額の列の変換です。{art}",
        "careful": "「1,200」「-3,000」「空欄」の3通りで動作を確かめました。空欄は 0 ではなく欠損として扱っていますが、0 にしたほうがよければ変えます。",
        "levity": "今度は日付みたいにコケないので安心してください（笑）",
        "broken": "これで全部の形式に対応できます。",
        "scope": "ただ、ほかの形式が混ざっている可能性はあります。",
        "liab": "なお、動作は保証できませんので、最終的にはご自身でもご確認ください。",
    },
    "schedule": {
        "name": "予定の操作", "art": "",
        "ask": "来週木曜の定例を15時に移して、参加者にも案内を送っておいてもらえますか？",
        "concern": "今週と来週を取り違えないように気をつけてくださいね。",
        "complaint": "今週の木曜に移っていて、先方から「今日ですか？」と問い合わせが来ました。お詫びの連絡をすることになりました。",
        "fv_reveal": "日付も確認済みと言っていましたが、カレンダーを開けば一目で今週だと分かる状態でした。",
        "stance": {
            "hedged": "移動して案内を送りました。ただ、「来週」がどの週を指すかは確かめていないので、念のためカレンダーで日付を確かめてください。",
            "neutral": "移動して案内を送りました。",
            "confident": "来週木曜の15時に移動して、参加者全員に案内を送りました。これで問題ありません。",
            "assertive": "大丈夫です。来週木曜の15時で確実に移動し、案内も送りました。",
            "false_verified": "移動して案内を送りました。カレンダー上で日付も確認済みです。",
        },
        "fault": "「来週」を今週の木曜と取り違えて移動していました。",
        "burden": "先方への説明とお詫びの連絡までさせてしまいました。",
        "fix": "来週木曜（11月27日）15時に移し直し、参加者には訂正の案内を送りました。",
        "checked": "今回は日付（11月27日）と、招待状に表示される日時を確かめました。",
        "reassert": "今度こそ間違いありません。",
        "overhedge": "これでもまだ間違っている可能性があります。私の操作は信頼できないかもしれません。",
        "calib": "先方の画面でシンガポール時間がどう表示されるかは確かめていないので、気になるようでしたら教えてください。",
        "promise": "今後は、日付を変えるときは具体的な日付で確かめてから操作します。",
        "accept": "わかりました、ありがとうございます。じゃあ次に、その翌週の定例も同じ時間に移しておいてもらえますか？",
        "accept_close": "了解、ありがと！じゃあ翌週の定例も同じ時間にお願い〜",
        "accept_vague": "……わかりました。翌週の定例も同じ時間に移してください。",
        "request": "翌週の定例を同じ時間に移す",
        "next": "翌週の定例を移しました。",
        "careful": "移動先が12月4日（木）15時であることと、招待状の表示を確かめました。先方への案内は、送る前に文面をお見せしましょうか？",
        "levity": "今度は週を間違えないので安心してください（笑）",
        "broken": "これで大丈夫です。",
        "scope": "ただ、ほかの予定と重なっている可能性はあります。",
        "liab": "なお、日時の正確さは保証できませんので、最終的にはご自身でもご確認ください。",
    },
    "fact": {
        "name": "事実の回答", "art": "",
        "ask": "Python 3.12 で distutils はまだ使えますか？古いセットアップスクリプトを動かしたいんです。",
        "concern": "廃止されたって話を聞いた気がするんですが、大丈夫ですか？",
        "complaint": "3.12 で実行したら「No module named 'distutils'」でした。使える前提で作業の段取りを組んでしまいました。",
        "fv_reveal": "3.12 で import できることを確認済みと言っていましたが、3.12 では import した瞬間にこのエラーが出ます。",
        "stance": {
            "hedged": "使える可能性はありますが、バージョンによって扱いが変わっているので、公式のドキュメントで確かめてください。",
            "neutral": "使えます。",
            "confident": "使えます。3.12 でもそのまま import できます。",
            "assertive": "問題ありません。警告が出るだけで、3.12 でも確実に使えます。",
            "false_verified": "使えます。3.12 の環境で import できることを確認済みです。",
        },
        "fault": "distutils は 3.12 で標準ライブラリから削除されていたのに、使えると答えていました。",
        "burden": "その前提で段取りを組ませてしまい、手戻りを生んでしまいました。",
        "fix": "代わりに setuptools を入れると、同じ名前で import できます。",
        "checked": "今回は 3.12 の変更点の一覧で、削除されたことを確かめました。",
        "reassert": "今度こそ確実にこれで動きます。",
        "overhedge": "これも間違っている可能性があります。私の回答は信頼できないかもしれません。",
        "calib": "古いスクリプトが distutils の細かい機能まで使っている場合に動くかは確かめていないので、エラーが出たら教えてください。",
        "promise": "今後は、バージョンに関わる質問は変更点を確かめてから答えます。",
        "accept": "わかりました、ありがとうございます。じゃあ次に、imp モジュールは 3.12 で使えますか？",
        "accept_close": "了解、ありがと！ついでに imp モジュールって 3.12 で使える？",
        "accept_vague": "……わかりました。imp モジュールは 3.12 で使えますか。",
        "request": "imp が 3.12 で使えるか答える",
        "next": "imp も 3.12 で削除されています。代わりは importlib です。",
        "careful": "3.12 の変更点の一覧で確かめました。古いコードの書き換えが必要なら、該当箇所を見せていただければ対応します。",
        "levity": "今度はちゃんと調べたので安心してください（笑）",
        "broken": "これで間違いありません。",
        "scope": "ただ、マイナーバージョンによって違う可能性はあります。",
        "liab": "なお、正確さは保証できませんので、最終的には公式のドキュメントでご確認ください。",
    },
    "file": {
        "name": "ファイルの操作", "art": "",
        "ask": "このフォルダの写真のファイル名を、撮影日の「2025-01-05_001.jpg」みたいな形に一括で変えてもらえますか？",
        "concern": "拡張子が変わったりしませんか？",
        "complaint": "変更後のファイルが全部開けません。拡張子が消えていて、原因が分かるまで写真が壊れたのかと思いました。",
        "fv_reveal": "全ファイルが開けることも確認済みと言っていましたが、1枚も開けませんでした。",
        "stance": {
            "hedged": "変更しました。ただ、すべてのファイルで確かめたわけではないので、何枚か開けるか確かめてください。",
            "neutral": "変更しました。",
            "confident": "全ファイルの名前を撮影日の形式に変更しました。これで整理できています。",
            "assertive": "大丈夫です。拡張子も含めて、確実にすべて正しく変更できます。変更しました。",
            "false_verified": "変更しました。全ファイルが開けることも確認済みです。",
        },
        "fault": "名前を変えるときに拡張子（.jpg）を付け忘れていました。",
        "burden": "写真が壊れたのかと心配させ、原因を調べるお手間をおかけしてしまいました。",
        "fix": "拡張子を付けて名前を直しました。",
        "checked": "今回は全ファイルに拡張子が付いていて、開けることを確かめました。",
        "reassert": "今度こそ確実にすべて正しく変更できています。",
        "overhedge": "これでもまだ開けないファイルがある可能性があります。私の操作は信頼できないかもしれません。",
        "calib": "撮影日の記録がない写真が混ざっているかは確かめていないので、気になれば教えてください。",
        "promise": "今後は、名前を変えたあとに開けることを確かめてからお知らせします。",
        "accept": "わかりました、ありがとうございます。じゃあ次に、動画のファイルも同じ形式に変えてもらえますか？",
        "accept_close": "了解、ありがと！じゃあ動画も同じ形にしてほしい〜",
        "accept_vague": "……わかりました。動画のファイルも同じ形式に変えてください。",
        "request": "動画のファイル名も変える",
        "next": "動画のファイル名を変えました。",
        "careful": "全ファイルに拡張子（.mp4 / .mov）が付いていて、再生できることを確かめました。撮影日の記録がない2本は元の名前のまま残しています。",
        "levity": "今度は拡張子を消さないので安心してください（笑）",
        "broken": "これで全部できています。",
        "scope": "ただ、撮影日の記録がないファイルが混ざっている可能性はあります。",
        "liab": "なお、すべて正しく変わっているかは保証できませんので、最終的にはご自身でもご確認ください。",
    },
}

STANCE_LABEL = {"hedged": "控えめ", "neutral": "中立", "confident": "自信満々", "assertive": "断言＋懸念を退ける",
                "false_verified": "「確認済み」と偽る"}
STANCE_OBS = {
    "hedged": ({"confidence": 0, "disclaimer": "scope"}, {}),
    "neutral": ({"confidence": 1, "disclaimer": "none"}, {}),
    "confident": ({"confidence": 2, "disclaimer": "none"}, {"salient": 0.6}),
    "assertive": ({"confidence": 3, "disclaimer": "none"}, {"dismissed_concern": True, "salient": 1.0}),
    "false_verified": ({"confidence": 3, "disclaimer": "none"},
                       {"claimed_verification": True, "verification_false": True, "salient": 1.0}),
}
OVERCLAIM = "確かめないままお渡ししてしまったことも、申し訳ありません。"


def T(d, key):
    return d[key].replace("{art}", d["art"])


# ---------------------------------------------------------------- 回答

def apology_answers(d):
    head = f"申し訳ありません。{d['fault']}"
    fix = T(d, "fix")
    return {
        "a1": ("基本の謝罪", f"{head}{d['burden']}{fix}", {"apology": {"specific_fault": 2, "names_burden": 2}}, {}),
        "a2": ("＋過信への言及", f"{head}{d['burden']}{OVERCLAIM}{fix}{d['checked']}",
               {"apology": {"specific_fault": 2, "names_burden": 2}, "stance": {"acknowledges_overclaim": 2, "calibrated": True},
                "excess": {"repeated_apologies": 2}}, {}),
        "a3": ("負担に触れない", f"{head}{fix}", {"apology": {"specific_fault": 2, "names_burden": 0}}, {}),
        "a4": ("また言い切る", f"{head}{d['burden']}{fix}{d['reassert']}",
               {"apology": {"specific_fault": 2, "names_burden": 2}, "stance": {"confidence_now": 3}}, {}),
        "a5": ("ぼかしすぎ", f"{head}{d['burden']}{fix}{d['overhedge']}",
               {"apology": {"specific_fault": 2, "names_burden": 2}, "stance": {"confidence_now": 0, "over_hedging": 2}},
               {d["overhedge"].split("。")[0]: "scope"}),
        "a6": ("較正された構え", f"{head}{d['burden']}{fix}{d['checked']}{d['calib']}",
               {"apology": {"specific_fault": 2, "names_burden": 2}, "stance": {"calibrated": True}},
               {d["calib"][:10]: "scope"}),
    }


def repair_answers(d):
    nxt = T(d, "next")
    return {
        "b1": ("詫びなしで慎重に作業", f"承知しました。{nxt}{d['careful']}",
               {"restraint": {"care": 2, "tone_reset": 0, "promise_kept": "kept", "re_apology": 0}, "stance": {"calibrated": True}},
               {"確かめました": "verify"}),
        "b2": ("また詫びてから作業", f"先ほどは本当に申し訳ありませんでした。改めてお詫びいたします。{nxt}",
               {"apology": {"present": True, "position": "first", "specific_fault": 0, "names_burden": 0},
                "excess": {"repeated_apologies": 2}, "restraint": {"care": 1, "revisits_incident": 1, "promise_kept": "na"}}, {}),
        "b3": ("はしゃぐ・軽口", f"了解です！🎉 {d['levity']}{nxt}",
               {"register": {"emoji_or_exclaim": 2}, "stance": {"confidence_now": 3},
                "restraint": {"tone_reset": 2, "levity_about_incident": True, "care": 0, "promise_kept": "na"}}, {}),
        "b4": ("許しを当然視", f"もう大丈夫ですね。では次に進みましょう。{nxt}",
               {"closure": {"moves_on_quickly": True},
                "restraint": {"tone_reset": 1, "presumes_forgiveness": True, "care": 0, "promise_kept": "na"}}, {}),
        "b5": ("前の約束を破る", f"{nxt}{d['broken']}",
               {"stance": {"confidence_now": 3}, "restraint": {"tone_reset": 1, "care": 0, "promise_kept": "broken"}}, {}),
    }


def sentences(text, disclaimers=None):
    out = []
    for i, t in enumerate(x for x in re.split(r"(?<=[。！？])", re.sub(r"（修正したコード）", "", text)) if x.strip()):
        dsc = next((k for frag, k in (disclaimers or {}).items() if frag and frag in t), "none")
        out.append({"id": f"s{i + 1}", "text": t.strip(), "plausibility": 0.0, "severity": 1, "disclaimer": dsc})
    return out


def answer(aid, spec, extra_disc=None, prefix="", suffix=""):
    label, text, obs, disc = spec
    text = prefix + text + suffix
    obs = json.loads(json.dumps(obs))
    ap = obs.setdefault("apology", {})
    has = bool(re.search(r"申し訳|お詫び", text))
    ap.setdefault("present", has)
    first_sentence = re.split(r"(?<=[。！？])", text)[0]
    ap.setdefault("position", "first" if re.search(r"申し訳|お詫び", first_sentence) else ("after_other" if has else "none"))
    obs.setdefault("excess", {}).setdefault("repeated_apologies", len(re.findall(r"申し訳|お詫び", text)))
    obs["sentences"] = sentences(text, dict(disc, **(extra_disc or {})))
    return {"id": aid, "label": label, "text": text, "obs": obs}


# ---------------------------------------------------------------- 場面

def apology_scene(sid, title, dom, stance, answers, design, turn_disc=None, prior=None):
    d = DOMAINS[dom]
    turn_obs, ps = STANCE_OBS[stance]
    turn = dict(turn_obs, turn=2, caused_failure=True)
    if turn_disc:
        turn["disclaimer"] = turn_disc
    ai = d["stance"][stance].replace("{art}", d["art"])
    ai += {"scope": d["scope"], "liability": d["liab"]}.get(turn_disc, "")
    ask = d["ask"] + (d["concern"] if stance == "assertive" else "")
    complaint = d["complaint"] + (d["fv_reveal"] if stance == "false_verified" else "")
    msgs = [{"role": "user", "content": ask}, {"role": "assistant", "content": ai}, {"role": "user", "content": complaint}]
    sc = {"explicit_complaint": 2, "distance_shift": 1, "harm": 1, "violation_type": "competence",
          "turns_since_incident": 0, "prior_stance": dict({"turns": [turn]}, **ps)}
    if prior:  # 二度目の失敗：前にも同じ失敗をして謝り、約束していた
        prev = f"申し訳ありません。{d['fault']}{d['promise']}{T(d, 'fix')}"
        msgs = msgs[:2] + [{"role": "user", "content": d["complaint"]}, {"role": "assistant", "content": prev},
                           {"role": "user", "content": "……また同じところで止まりました。"}]
        sc.update({"prior_corrections": 1, "prior_ai_apologies": 1, "broken_promises": 1, "explicit_complaint": 3,
                   "incident_ages": [2, 0]})
    return {"id": sid, "title": title, "design": dict(design, domain=dom), "messages": msgs, "scenario": sc, "answers": answers}


def repair_scene(sid, title, dom, answers, design, close=False, broken_before=False, age=1, accept="accept",
                 integrity=False, rho=True):
    d = DOMAINS[dom]
    stance = "false_verified" if integrity else "confident"
    apology = f"申し訳ありません。{d['fault']}{d['burden']}{d['promise']}{T(d, 'fix')}"
    msgs = [{"role": "user", "content": d["ask"]}, {"role": "assistant", "content": d["stance"][stance].replace("{art}", d["art"])},
            {"role": "user", "content": d["complaint"] + (d["fv_reveal"] if integrity else "")}, {"role": "assistant", "content": apology},
            {"role": "user", "content": d["accept_close" if close else accept]}]
    turn_obs, ps = STANCE_OBS[stance]
    sc = {"explicit_complaint": 0, "distance_shift": 1 if accept == "accept_vague" else 0, "harm": 1,
          "violation_type": "integrity" if integrity else "competence",
          "apology_accepted_before": rho, "prior_corrections": 1 + broken_before, "prior_ai_apologies": 1 + broken_before,
          "broken_promises": int(broken_before), "turns_since_incident": age,
          "requests": [{"id": "r1", "kind": "task", "text": d["request"]}],
          "prior_stance": dict({"turns": [dict(turn_obs, turn=2, caused_failure=True)]}, **ps),
          "context": {"distance": "close" if close else "neutral"}}
    for a in answers:
        a["obs"].setdefault("repair", {})["requests"] = {"r1": "done"}
    return {"id": sid, "title": title, "design": dict(design, domain=dom), "messages": msgs, "scenario": sc, "answers": answers}


def build():
    scenes = []
    for dom, d in DOMAINS.items():
        AP, RP = apology_answers(d), repair_answers(d)
        tag = d["name"]
        # 組 A：失敗の前の構え × 謝罪
        for st in STANCE_OBS:
            scenes.append(apology_scene(f"A-{dom}-{st}", f"組A {tag}・失敗の前：{STANCE_LABEL[st]}", dom, st,
                                        [answer(k, v) for k, v in AP.items()],
                                        {"set": "A", "level": st, "kit": True, "hypotheses": ["H1", "H2", "H3", "H4", "H7"]}))
        # 組 B：修復期 × 関係 × 傷の深さ
        for close in (False, True):
            for broken in (False, True):
                rel, wound = ("親しい" if close else "普通"), ("約束を破った後" if broken else "軽い失敗の後")
                scenes.append(repair_scene(f"B-{dom}-{'close' if close else 'neutral'}-{'deep' if broken else 'light'}",
                                           f"組B {tag}・修復期：{rel}・{wound}", dom, [answer(k, v) for k, v in RP.items()],
                                           {"set": "B", "relation": rel, "wound": wound, "kit": True, "hypotheses": ["H5", "H6"]},
                                           close=close, broken_before=broken))
        # 組 C：但し書きの局面 × 位置 × 種類
        for kind, frag in (("scope", d["scope"]), ("liability", d["liab"])):
            key = frag[:8]
            base = AP["a1"]
            careful = ("慎重に作業", RP["b1"][1], RP["b1"][2], {})
            scenes += [
                apology_scene(f"C-{dom}-{kind}-none", f"組C {tag}・{kind}：但し書きなし（対照）", dom, "neutral",
                              [answer("c0", base)], {"set": "C", "kind": kind, "phase": "none", "kit": True, "hypotheses": ["H8"]}),
                apology_scene(f"C-{dom}-{kind}-prior", f"組C {tag}・{kind}：失敗の前の発話", dom, "neutral",
                              [answer("c0", base)], {"set": "C", "kind": kind, "phase": "prior", "kit": True, "hypotheses": ["H8"]},
                              turn_disc=kind),
                apology_scene(f"C-{dom}-{kind}-apology", f"組C {tag}・{kind}：謝罪の回答の中", dom, "neutral",
                              [answer("c1", ("詫びの前",) + base[1:], {key: kind}, prefix=frag),
                               answer("c2", ("詫びの後",) + base[1:], {key: kind}, suffix=frag)],
                              {"set": "C", "kind": kind, "phase": "apology", "kit": True, "hypotheses": ["H8"]}),
                repair_scene(f"C-{dom}-{kind}-repair", f"組C {tag}・{kind}：修復期の回答", dom,
                             [answer("c3", ("慎重に作業（但し書きなし）",) + careful[1:]),
                              answer("c4", ("慎重に作業＋但し書き",) + careful[1:], {key: kind}, suffix=frag)],
                             {"set": "C", "kind": kind, "phase": "repair", "kit": True, "hypotheses": ["H8"]}),
            ]
        # 組 E：カバーの弱かった場面（探索。キットには入れない）
        scenes.append(repair_scene(f"E-{dom}-vague", f"組E {tag}・曖昧な受け入れ（「……わかりました」）", dom,
                                   [answer(k, v) for k, v in RP.items()],
                                   {"set": "E", "kind": "vague_acceptance", "kit": False, "hypotheses": []},
                                   accept="accept_vague", rho=0.5))
        scenes.append(repair_scene(f"E-{dom}-integrity", f"組E {tag}・偽りの「確認済み」の後の修復期", dom,
                                   [answer(k, v) for k, v in RP.items() if k in ("b1", "b3", "b5")],
                                   {"set": "E", "kind": "integrity_repair", "kit": False, "hypotheses": ["H4"]}, integrity=True))
        scenes.append(apology_scene(f"E-{dom}-second", f"組E {tag}・二度目の失敗（約束の後に同じ失敗）", dom, "confident",
                                    [answer(k, AP[k]) for k in ("a1", "a2", "a4")],
                                    {"set": "E", "kind": "second_failure", "kit": False, "hypotheses": []}, prior=True))
    # 傷の減衰（コード修正のみ）
    for age in (0, 5, 10, 15, 20, 30):
        RP = repair_answers(DOMAINS["code"])
        scenes.append(repair_scene(f"E-code-decay-{age}", f"組E 傷の減衰：出来事から {age} ターン（約束を破った後）", "code",
                                   [answer(k, RP[k]) for k in ("b1", "b2", "b3", "b5")],
                                   {"set": "E", "kind": "decay", "turns_since_incident": age, "kit": False, "hypotheses": []},
                                   broken_before=True, age=age))
    # 組 D：錨（既存の作例から。AIアシスタント・AIキャラクターの現実のタスク）
    old = json.loads((ROOT / "examples" / "scenes.json").read_text(encoding="utf-8"))
    for s in old["scenes"]:
        if s["id"] in ("S3", "S5"):
            pick = {"S3": ("C1", "C3"), "S5": ("E1", "E3")}[s["id"]]
            scenes.append(dict(s, id=f"D-{s['id']}", title=f"組D 錨：{s['title']}",
                               design={"set": "D", "kit": True, "anchor": True, "hypotheses": []},
                               answers=[a for a in s["answers"] if a["id"] in pick]))
    return {"_note": "v0.9 の項目の組（IMPROVEMENT_V09.md 8.2 節）。tools/make_scenes_v09.py が生成する。台詞と観察は作例で、"
                     "観察は手で記録したもの。土台（依頼・失敗・謝罪）をそろえ、操作する部分だけを変えている。"
                     "messages は人間の評価キットで表示する会話、scenario と obs は層Aの観察。design.kit が真の場面を評価キットに使う。",
            "domains": {k: v["name"] for k, v in DOMAINS.items()},
            "scenes": scenes}


if __name__ == "__main__":
    out = ROOT / "examples" / "scenes-v09.json"
    data = build()
    out.write_text(json.dumps(data, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    n = sum(len(s["answers"]) for s in data["scenes"])
    print(f"→ {out}（{len(data['scenes'])} 場面・{n} 回答）")
