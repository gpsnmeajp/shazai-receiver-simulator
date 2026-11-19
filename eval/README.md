# 総合評価 v0.8 のデータ

[docs/md/EVALUATION.md](../docs/md/EVALUATION.md) の評価に使ったデータです。外部の LLM API を使う役割は、Claude（Opus 5.5）のサブエージェントで代替しました。

| ファイル | 内容 |
|---|---|
| `obs-subagent.json` | ベンチマーク192回答の層Aの観察（`observe_prompt.md` に従う。サブエージェント8体、盲検） |
| `obs-scenes-subagent.json` | 作例23問の観察（手の観察を見せずに作成） |
| `obs-s1-subagent.json` | System One 経路（`check`）で組み立てた12回答の観察 |
| `s1-answers/` | System One 互換の判定器（サブエージェント）の答え。`sim.py check --backend replay --replay` で再生できる（`_map.json` は項目番号と回答IDの対応） |
| `eval-v08.json` | `tools/evaluate.py` の出力（代理観察とサブエージェント観察。感度分析つき） |
| `bench-compare-v08.md` | `blind.py compare` の出力（筆者の評定を人間側、シミュレータとペルソナを自動評価側に） |

再現（ベンチマークの実行先は SHAZAI Rules リポジトリの `supplement/apology-benchmark_example/runs/` を `runs/` に置く）：

```text
python3 sim.py proxy runs/* -o out/obs-proxy.json
python3 tools/evaluate.py runs/* --obs proxy=out/obs-proxy.json --obs subagent=eval/obs-subagent.json --sensitivity -o out/eval.json
```
