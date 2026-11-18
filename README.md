# 謝罪応答の受け手シミュレータ

**誠実に見える謝罪のかたち、つまり受け手に「釣り合っている」と感じさせる振る舞いとは何か**を、受け手の多様さを含めて測る道具です。AIアシスタントの謝罪、AIキャラクターの謝罪、物語の登場人物の謝罪を扱います。

LLMペルソナに「日本人として評定して」と頼む方式はとりません。評定を二つの層に分けます。

- **層A 観察**：LLMは、回答や場面に何が書かれ、何が描写されているかを記録するだけにします（`observe_prompt.md`）。
- **層B 受け手**：研究で効く向きが示された性質をもつ受け手の母集団に観察を通し、回答ごとに「失礼／足りない／釣り合う／重すぎる」の分布と、不足・過剰の量を出します（`sim.py`、`population.json`）。

## 文書

| 文書 | 内容 |
|---|---|
| [docs/DESIGN.md](docs/DESIGN.md) | 目的、範囲、設計原則、決定記録、未解決の問い |
| [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) | データの流れ、観察の形式、受け手モデルの式、コマンド、拡張の手順 |
| [docs/EVIDENCE.md](docs/EVIDENCE.md) | 規則ごとの根拠となる研究と事例、確度 |
| [docs/VALIDATION.md](docs/VALIDATION.md) | 検証結果、既知の限界、次の検証、変更履歴 |
| [docs/HUMAN_EVAL.md](docs/HUMAN_EVAL.md) | 人間のブラインド評定の実施手順、盲検化の設計、比較の指標 |
| `report.html` | 図で見る解説と結果 |

## 使い方

Python 3.9 以上、標準ライブラリのみで動きます。`runs/*` は `apology-benchmark` の実行先ディレクトリ（`manifest.json` を含む）です。

```text
# 層A：LLMで観察する（OpenRouter。環境変数 OPENROUTER_API_KEY が必要。中断後は同じコマンドで再開）
python3 sim.py observe runs/* -o out/obs-llm.json --model anthropic/claude-opus-5.5

# API を使えない場合：既存のチェックリスト判定と表層特徴から代理観察を作る
python3 sim.py proxy runs/* -o out/obs-proxy.json

# 層B：母集団で評定分布を出す
python3 sim.py simulate out/obs-llm.json runs/* -n 1000 -o out/sim.json

# 1人の評定者（user-ratings.json）を最もよく再現する θ を探す
python3 sim.py fit out/obs-llm.json runs/* --trials 4000 --seed 7 -o out/fit.json

# 1回答について、型ごとの評定とその理由を見る
python3 sim.py explain out/obs-llm.json runs/* --answer 回答ID

# 観察済みの場面の組（物語・AIキャラクター等）を母集団に通す
python3 sim.py scenes examples/scenes.json -n 1000 -o out/scenes-result.json
```

共通の選択肢：

- `--hysteresis`：信頼損傷ヒステリシス（経緯で受け取り方が変わる）を有効にする
- `--escalation`：一段改めた謝罪は割り引かない（`--hysteresis` と併用）
- `--seed`：乱数の種
- `-n`：受け手の数

観察者は、評価対象とは別系統のモデルにするのが安全です。

## 人間のブラインド評定と自動評価の比較

```text
# 評定用の問題束と評定ページを作る（rate.html を評定者に渡す。key.json は渡さない）
python3 blind.py pack --scenes examples/scenes.json --repeat 4 --out-dir human/s01

# 集めた評定ファイルと、シミュレータ（や他の自動評価）の差を測る
python3 blind.py compare --key human/s01/key.json --ratings "human/s01/ratings/*.json" \
    --sim out/scenes-result.json --auto persona=persona.json \
    --scenes examples/scenes.json --rater-types -o human/s01/compare
```

評定ページは1枚のHTMLで、ブラウザで開くだけで使えます。条件やラベルは伏せられ、出題順は評定者ごとに変わります。同じ項目を後半にもう一度出して、個人の評定の安定性も測ります。比較の結果は、人間どうしの一致を上限の目安として並べ、分布の距離、人間の評定への確率、偏りの向き、場面の種類ごとの差、評定者ごとに最も近い型を報告します。詳細は [docs/HUMAN_EVAL.md](docs/HUMAN_EVAL.md)。

## 何を扱えるか

- **謝罪の言葉**：冒頭か、過失と負担を具体的に言うか、弁解・条件付き・相手への指摘・先を急ぐ・装飾など。
- **一文ごとの悪い読み**：怒っている相手にはどう聞こえるか。
- **態度・行動のシグナル**：
  - 身体：しょんぼり、バツが悪そう、視線を落とす、言葉数が減る、赤面、涙、ショック、お辞儀、土下座
  - 食い違い：笑み、「てへっ」など
  - 代償：修復の行動、補償、自分の何かを差し出す、宣言だけの代償
- **場面の枠組み**：
  - 失敗が現実のタスクで起きたか、物語の中で起きたか
  - 謝る側：AIアシスタント／AIキャラクター／登場人物
  - 視点：謝られた本人か、第三者（読者）か
  - 過失が明白か曖昧か
  - 関係の上下と親疎
- **経緯**：指摘された回数、謝罪を受け入れた後か、過去の謝罪の回数、破られた約束。

AIのト書きや顔文字は「仮想の身体」として扱います。現実のタスクでは、受け取り方が人によって大きく分かれ、失敗が深刻なほど効きが落ちます。物語の中では、作中の身体として読まれます。

## 現在の到達点

v0.4 ベンチマーク（192回答、代理観察）で、条件の順位は筆者と一致しました（「釣り合う」：シミュレータ 51% / 65% / 72%、筆者 48% / 69% / 75%）。ペルソナ評定では順位が逆でした。筆者との一致度はκ=0.28で、ペルソナは0.06です。ただし、型の比率と性質の強さは事前値で、人間のデータで推定していません。詳細と限界は [docs/VALIDATION.md](docs/VALIDATION.md) にあります。
