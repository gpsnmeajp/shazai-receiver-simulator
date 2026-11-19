#!/bin/sh
# v0.9 のフル評価（docs/md/EVALUATION_V09.md の再現）。runs/ にベンチマークの実行先を置いてから実行する。
set -e
cd "$(dirname "$0")/.."
O=eval/v09-observers
python3 tools/merge_observers.py
python3 sim.py proxy runs/* -o out/obs-proxy.json
python3 sim.py scenes examples/scenes-v09.json -o out/scenes-v09.json > out/scenes-v09.txt
# 1. ベンチマーク：6変種・集団・既存の観察・代理観察（較正なし）と v0.8 との比較は eval/eval-v09.txt
python3 tools/evaluate.py runs/* \
  --obs proxy=out/obs-proxy.json \
  --obs ensemble=$O/obs-ensemble.json \
  --obs top-neutral=$O/obs-opus-neutral.json --obs top-literal=$O/obs-opus-literal.json --obs top-context=$O/obs-opus-context.json \
  --obs mid-neutral=$O/obs-sonnet-neutral.json --obs mid-literal=$O/obs-sonnet-literal.json --obs mid-context=$O/obs-sonnet-context.json \
  -o eval/eval-v09-full.json > eval/eval-v09-full.txt
# 2. 出どころごとの較正（交差検証の内側）
python3 tools/evaluate.py runs/* --calibrate -n 500 --boot 1000 \
  --obs proxy=out/obs-proxy.json --obs ensemble=$O/obs-ensemble.json --obs top-literal=$O/obs-opus-literal.json \
  -o eval/eval-v09-full-calibrated.json > eval/eval-v09-full-calibrated.txt
# 3. 観察者の一致と主効果
python3 tools/observer_agreement.py $O/obs-opus-*.json $O/obs-sonnet-*.json -o eval/v09-observer-agreement.md > /dev/null
# 4. 作例の観察の再現
python3 tools/eval_scene_obs.py $O/obs-scenes-opus.json -o eval/v09-scenes-obs.md > /dev/null
# 5. 事前値の感度
python3 tools/sensitivity_v09.py -o eval/v09-sensitivity.md > /dev/null
# 6. 評価キットの検出力（合成評定者）
python3 blind.py power --scenes examples/scenes-v09.json --hypotheses human/hypotheses-v09.json --raters 20,40,60 --reps 200 -o eval/v09-kit/power-x1 > /dev/null
python3 blind.py power --scenes examples/scenes-v09.json --hypotheses human/hypotheses-v09.json --raters 20,40,60 --reps 200 --effect-scale 0.5 -o eval/v09-kit/power-x05 > /dev/null
echo "done"
