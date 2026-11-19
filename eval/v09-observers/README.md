# v0.9 観察者の集団の観察

ベンチマーク192回答を、観察方針3水準（neutral / literal / context）× モデル2系統（Claude の上位モデル・中位モデル）= 6変種のサブエージェントで観察したもの。外部の LLM API の代わりにサブエージェントを使った。各観察者は `observe_prompt.md`（＋方針の追記。`sim.POLICIES`）に従い、条件・評定・既存の観察を見ずに、文 ID（`sim.py segment`）ごとに手で観察した。

- `batches/`：観察者に渡した資料（会話と回答。発話に番号、回答に文 ID）
- `raw/<変種>/`：観察者の出力（1行1場面の JSONL）
- `obs-<変種>.json`：観察JSONの形にまとめたもの。`obs-ensemble.json` は6変種の集約（`sim.py ensemble`）

注意：モデルの系統は2つとも Claude（上位モデルと中位モデル）で、設計（6.2節）の「別系統のモデル」は満たしていない。
