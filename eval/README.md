# 総合評価のデータ

[docs/md/EVALUATION.md](../docs/md/EVALUATION.md) の評価に使ったデータです。外部の LLM API を使う役割は、Claude のサブエージェントで代替しました。

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

## v0.9

[docs/md/IMPROVEMENT_V09.md](../docs/md/IMPROVEMENT_V09.md) 13章の評価です。観察は v0.8 と同じもの（修復期の控えの欄はなく、既定値で評価）。

| ファイル | 内容 |
|---|---|
| `eval-v09.txt` / `.json` | v0.9 と v0.8 を同じ観察・同じ手続きで比較（受け手1000名、ブートストラップ2000回）。v0.8 は `名前=観察@v0.8 のディレクトリ` で読み込んだ |
| `eval-v09-calibrated.txt` / `.json` | 所属度関数の中心も交差検証の内側で当てはめた結果（受け手500名、ブートストラップ1000回） |

```text
git worktree add /tmp/v08 <v0.8 のコミット>
python3 tools/evaluate.py runs/* --obs v09-proxy=out/obs-proxy.json --obs v08-proxy=out/obs-proxy.json@/tmp/v08 \
  --obs v09-subagent=eval/obs-subagent.json --obs v08-subagent=eval/obs-subagent.json@/tmp/v08 -o eval/eval-v09.json
python3 tools/evaluate.py runs/* --calibrate -n 500 --boot 1000 --obs v09-proxy=out/obs-proxy.json \
  --obs v09-subagent=eval/obs-subagent.json -o eval/eval-v09-calibrated.json
```

## v0.9 の総合評価

[docs/md/EVALUATION_V09.md](../docs/md/EVALUATION_V09.md)。再現は `sh tools/run_eval_v09.sh`。

| ファイル | 内容 |
|---|---|
| `v09-observers/` | 観察者の集団（6変種）の観察と作例の盲検の観察（[README](v09-observers/README.md)） |
| `eval-v09-full.txt` / `.json` | 6変種・集団・代理観察のベンチマークの評価（較正なし） |
| `eval-v09-full-calibrated.txt` / `.json` | 出どころごとの較正つき |
| `v09-observer-agreement.md` | 観察者間の一致（α）と、観察方針・モデルの主効果 |
| `v09-scenes-obs.md` | 作例での、LLM の観察と手の観察の一致、仮説の対比の向き |
| `v09-sensitivity.md` | 新しい事前値の感度 |
| `v09-kit/` | 評価キットの合成評定者による試験（`session-synth/`）と検出力（`power-x1`、`power-x05`） |

## Jev 評価

[docs/md/EVALUATION_JEV.md](../docs/md/EVALUATION_JEV.md)。実際の Jev（OpenRouter の Decisions API、`~typesafe/jev-latest`）で、ベンチマーク192回答と作例106回答を観察した。Jev 以外の LLM の役割はサブエージェントで代替。ファイルの一覧と再現の手順は同文書の7章。

| ファイル | 内容 |
|---|---|
| `jev/cache/`、`jev/cache-run1/` | Jev の生の答え（2回分）。API なしで再集計できる |
| `jev/obs-*-jev-pp-cal.json` | 最終の観察（前処理の修正・欄ごとの較正つき） |
| `jev/jev_calibration.json` | 欄ごとの閾値（`sim.py check --calibration`、`tools/observe_s1_batches.py --calibration`） |
| `jev/direct-*.json` | Jev に直接4値で評定させた結果（比較用） |
| `jev/llm-s1-subagent/` | 同じ質問の組にサブエージェントが答えたもの（作例の日程53回答） |
