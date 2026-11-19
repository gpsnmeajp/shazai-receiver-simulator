# 総合評価のデータ

[docs/md/EVALUATION.md](../docs/md/EVALUATION.md) の評価に使ったデータと出力です。外部の LLM API を使う役割（層Aの観察、System One 互換の判定器）は、Claude のサブエージェントで代替しました。再現は `sh tools/run_eval.sh`（ベンチマークの実行先は SHAZAI Rules リポジトリの `supplement/apology-benchmark_example/runs/` を `runs/` に置く）。

## 観察

| ファイル | 内容 |
|---|---|
| `observers/` | 観察者の集団（観察方針3 × モデル2 = 6変種）のベンチマークの観察と、項目の組の盲検の観察（[README](observers/README.md)） |
| `obs-subagent.json` | ベンチマーク192回答の単一の観察（サブエージェント8体、盲検）。控えの時間軸の欄を含まない観察指示によるもの。`population.json` の出どころ `llm` の較正に使った |
| `obs-scenes-subagent.json` | 作例23問の観察（手の観察を見せずに作成） |
| `obs-s1-subagent.json` | System One 経路（`check`）で組み立てた12回答の観察 |
| `s1-answers/` | System One 互換の判定器（サブエージェント）の答え。`sim.py check --backend replay --replay` で再生できる（`_map.json` は項目番号と回答IDの対応） |

## 出力

| ファイル | 内容 |
|---|---|
| `bench.txt` / `.json` | 6変種・集団・代理観察のベンチマークの評価（較正なし。受け手1000名、ブートストラップ2000回） |
| `bench-calibrated.txt` / `.json` | 出どころごとの較正つき（受け手500名、ブートストラップ1000回） |
| `single-calibrated.txt` / `.json` | 単一の観察（`obs-subagent.json`）と代理観察の、較正つきの評価 |
| `observer-agreement.md` | 観察者間の一致（α）と、観察方針・モデルの主効果 |
| `scenes-obs.md` | 項目の組での、LLM の観察と手の観察の一致、仮説の対比の向き |
| `sensitivity.md` | 控えの時間軸の事前値の感度 |
| `kit/` | 評価キットの合成評定者による試験（`session-synth/`）と検出力（`power-x1`、`power-x05`） |

`single-calibrated` の再現：

```text
python3 sim.py proxy runs/* -o out/obs-proxy.json
python3 tools/evaluate.py runs/* --calibrate -n 500 --boot 1000 --obs proxy=out/obs-proxy.json \
  --obs subagent=eval/obs-subagent.json -o eval/single-calibrated.json
```

## 過去の版の出力（`history/`）

| ファイル | 内容 |
|---|---|
| `history/eval-v08.json` | v0.8 の総合評価の `tools/evaluate.py` の出力（代理観察とサブエージェント観察。感度分析つき） |
| `history/bench-compare-v08.md` | v0.8 の `blind.py compare` の出力（筆者の評定を人間側、シミュレータとペルソナを自動評価側に） |
| `history/eval-v09.txt` / `.json` | v0.9 と v0.8 を同じ観察・同じ手続きで比べた出力（v0.8 は `名前=観察@v0.8 のチェックアウト` で読み込んだ） |

経緯は [HISTORY.md](../HISTORY.md) 3.4節・4.2節にあります。
