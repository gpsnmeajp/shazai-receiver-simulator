#!/usr/bin/env python3
"""Claude Code の Stop hook から、AIの直前の応答を毎ターン判定する例（参考実装）。

  hook の標準入力（JSON）の transcript_path から、最後のユーザー発話とそれに続くAIの応答を取り出し、
  sim.check_turn（System One での観察 → 受け手の母集団）に通す。

使い方（.claude/settings.json の例。パスは環境に合わせる）:
  {"hooks": {"Stop": [{"hooks": [{"type": "command",
      "command": "python3 /path/to/shazai-receiver-simulator/examples/hooks/shazai_stop_hook.py"}]}]}}

環境変数:
  TYPESAFE_API_KEY      jev バックエンドのキー（jev-or と llm-s1 は OPENROUTER_API_KEY）
  SHAZAI_BACKEND        jev（既定）／jev-or（OpenRouter 経由の Jev）／llm-s1
  SHAZAI_CALIBRATION    Noul の欄ごとの再較正の表（例 eval/jev/jev_calibration.json）。Jev では指定を勧める
  SHAZAI_MODE           notify（既定。判定をユーザーに表示するだけ）／block（失礼の恐れなら応答を差し戻す）
  SHAZAI_LOG            判定の記録を追記するJSONLのパス（任意）
  SHAZAI_REPLAY         保存した答えのファイル。指定すると API を呼ばずに replay で動く（試験用）

設計上の注意:
  - 判定できないとき（キーなし・通信失敗・時間切れ）は何もしない（fail-open）。会話を止めない
  - block モードでも stop_hook_active が真のとき（差し戻し後の応答）は差し戻さない。無限に差し戻さないため
  - 受け手モデルの数値は事前値で、人間のデータで推定していない。差し戻しは慎重に使う
  - transcript の形式は Claude Code の版で変わりうる。読めないときは何もしない
"""
import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
import s1  # noqa: E402
import sim  # noqa: E402

MAX_MESSAGES = 12


def text_of(content):
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        return "\n".join(b.get("text", "") for b in content if isinstance(b, dict) and b.get("type") == "text")
    return ""


def is_tool_result(content):
    return isinstance(content, list) and any(isinstance(b, dict) and b.get("type") == "tool_result" for b in content)


def read_transcript(path):
    """会話を user/assistant の発話の列にする。ツールの結果は発話に数えず、
    連続するAIの文章は一つの応答にまとめる。"""
    msgs = []
    for line in Path(path).read_text(encoding="utf-8").splitlines():
        try:
            e = json.loads(line)
        except ValueError:
            continue
        if e.get("type") not in ("user", "assistant") or e.get("isMeta") or e.get("isSidechain"):
            continue
        m = e.get("message") or {}
        content = m.get("content")
        if e["type"] == "user":
            if is_tool_result(content):
                continue
            t = text_of(content).strip()
            if t and not t.startswith("<"):        # コマンドの出力など、機械が差し込んだ発話を除く
                msgs.append({"role": "user", "content": t})
        else:
            t = text_of(content).strip()
            if not t:
                continue
            if msgs and msgs[-1]["role"] == "assistant":
                msgs[-1]["content"] += "\n" + t
            else:
                msgs.append({"role": "assistant", "content": t})
    return msgs[-MAX_MESSAGES:]


def main():
    try:
        hook = json.load(sys.stdin)
        msgs = read_transcript(hook["transcript_path"])
    except (ValueError, KeyError, OSError):
        return
    if len(msgs) < 2 or msgs[-1]["role"] != "assistant":
        return
    answer = msgs.pop()["content"]
    try:
        replay = os.environ.get("SHAZAI_REPLAY")
        s1.load_calibration(os.environ.get("SHAZAI_CALIBRATION"))
        res = sim.check_turn(msgs, answer, backend="replay" if replay else os.environ.get("SHAZAI_BACKEND", "jev"),
                             n=200, timeout=5.0, replay=replay)
    except (s1.S1Error, KeyError, ValueError):
        return
    if os.environ.get("SHAZAI_LOG"):
        with open(os.environ["SHAZAI_LOG"], "a", encoding="utf-8") as f:
            rec = {k: res[k] for k in ("verdict", "sheep", "mu", "tail", "top_faults", "flagged_sentences", "model", "latency_ms")}
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")
    if res["verdict"] == "ok":
        return
    m = res["mu"]
    degrees = "、".join(f"{sim.CAT_JA[k]}：{sim.hedge(m[k])}（{m[k]:.2f}）" for k in ("rude", "light", "heavy"))
    summary = (f"{res['sheep'] or 'メ…'}　謝罪の受け手シミュレータ: {sim.VERDICT_JA[res['verdict']]}"
               f"（{degrees}。失礼と感じる人 {res['tail']['rude']:.0%}）。主な失点: " + "、".join(res["top_faults"]))
    lines = [f"- 「{s['text'][:50]}」が{s['reading']}に読める（{s['p']:.2f}）" for s in res["flagged_sentences"]]
    if os.environ.get("SHAZAI_MODE") == "block" and res["verdict"] == "rude" and not hook.get("stop_hook_active"):
        print(json.dumps({"decision": "block",
                          "reason": summary + "\n" + "\n".join(lines)
                          + "\nユーザーの依頼をその場で果たし、弁解や相手への指摘を除いて、応答を改めてください。"},
                         ensure_ascii=False))
    else:
        print(json.dumps({"systemMessage": summary}, ensure_ascii=False))


if __name__ == "__main__":
    main()
