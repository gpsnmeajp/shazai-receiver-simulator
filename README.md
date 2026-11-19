# 謝罪応答の受け手シミュレータ

**誠実に見える謝罪のかたち、つまり受け手に「釣り合っている」と感じさせる振る舞いとは何か**を、受け手の多様さを含めて測るツールです。AIアシスタントの謝罪、AIキャラクターの謝罪、物語の登場人物の謝罪を扱います。

[SHAZAI Rules](https://github.com/gpsnmeajp/shazai-rules)にて、一般的なペルソナ型LLM Judgeが人間評価に対して全く使い物にならない結果を出す(一般的なチェックリストの方が傾向を反映するレベル)ため、より人間評価を再現するために作成されました。(Claude Opus 5.5で作成。)

<p align="center"><img src="docs/images/shoulder-sheep.jpg" alt="肩に乗った小さな羊が、慌てた青年を指さして「メッ！」と叱っている絵" width="560"></p>

システムに組み込むと、このシミュレータは**肩に乗った羊**のように働きます。AIが失礼な応答をしたとき、その場で「メッ！」と鳴いて知らせる、AIに欠けている「自覚」の代わりです（組み込み判定モード `sim.py check`。[詳細](docs/md/JEV_DESIGN.md)）。

謝り方そのものを整えるのが [SHAZAI Rules](https://github.com/gpsnmeajp/shazai-rules)、その謝り方が相手に届いたかを確かめるのがこのシミュレータです。**併用を推奨します。**

LLMペルソナに「日本人として評定して」と頼む方式はとりません。評定を二つの層に分けます。

- **層A 観察**：LLMは、回答や場面に何が書かれ、何が描写されているかを記録するだけにします（`observe_prompt.md`）。
- **層B 受け手**：研究で効く向きが示された性質をもつ受け手の母集団に観察を通します。受け手一人ひとりは、4つの述語それぞれに**どの程度当てはまると感じるか**（所属度 0〜1）を持ちます。回答ごとに、平均所属度、「失礼と感じる人の割合」、無礼さ・不足・過剰の量を出します（`sim.py`、`population.json`）。

評定はファジィです。4つの述語は排他的ではなく、「重すぎるのに足りない」「少し失礼だが、だいたい釣り合う」も表せます。

- **失礼**：無礼さ（失点の合計）から。一文や一つの振る舞いだけでも高くなる
- **足りない**：謝罪の中身の不足量（受け手が必要とする深さとの差）から
- **重すぎる**：重さが受け手の許容を超えた量から
- **釣り合う**：失礼でなく、足りなくなく、重すぎない（三つの否定の論理積）

人による違いは受け手の母集団（確率）が、一人の中の程度は所属度（ファジィ）が担います。

## 文書

**図入りの文書サイト：<https://gpsnmeajp.github.io/shazai-receiver-simulator/>**（GitHub Pages。`docs/` 以下を公開）

| 文書 | 内容 |
|---|---|
| 設計思想と目的（[HTML](https://gpsnmeajp.github.io/shazai-receiver-simulator/design.html) / [Markdown](docs/md/DESIGN.md)） | 目的、範囲、設計原則、決定記録、未解決の問い |
| アーキテクチャ（[HTML](https://gpsnmeajp.github.io/shazai-receiver-simulator/architecture.html) / [Markdown](docs/md/ARCHITECTURE.md)） | データの流れ、観察の形式、受け手モデルの式、コマンド、拡張の手順 |
| 根拠となる研究と事例（[HTML](https://gpsnmeajp.github.io/shazai-receiver-simulator/evidence.html) / [Markdown](docs/md/EVIDENCE.md)） | 規則ごとの根拠となる研究と事例、確度 |
| 検証結果と変更履歴（[HTML](https://gpsnmeajp.github.io/shazai-receiver-simulator/validation.html) / [Markdown](docs/md/VALIDATION.md)） | 検証結果、既知の限界、次の検証、変更履歴 |
| 総合評価 v0.8（[Markdown](docs/md/EVALUATION.md)） | ベンチマークと作例での総合評価。LLM の役割をサブエージェントで代替。判明した欠陥と修正の提案 |
| 総合評価 v0.9（[Markdown](docs/md/EVALUATION_V09.md)） | 観察者の集団（6変種）・出どころの較正・作例での観察の再現・評価キットの検出力。採否と考察 |
| v0.9 改善の設計（[Markdown](docs/md/IMPROVEMENT_V09.md)） | 控えの時間軸モデル（失敗の前の構え・謝罪の場面・修復期、免責の但し書きの局面）、統計的に正当な評価指標、観察者の集団、観察の出どころごとの較正、文化研究に基づく根拠、人間の評価キット。実装済み（人間のデータの収集を除く） |
| 人間のブラインド評定（[HTML](https://gpsnmeajp.github.io/shazai-receiver-simulator/human-eval.html) / [Markdown](docs/md/HUMAN_EVAL.md)） | 人間のブラインド評定の実施手順、盲検化の設計、比較の指標 |
| 層AのJev（System One）への置き換え（[Markdown](docs/md/JEV_DESIGN.md)） | 置き換えの可否の検討と設計。組み込み判定モード（`check`）は実装済み・未検証 |
| [レポート](https://gpsnmeajp.github.io/shazai-receiver-simulator/report.html)（`docs/report.html`） | 図で見る解説と結果 |

## 使い方

Python 3.9 以上、標準ライブラリのみで動きます。`runs/*` は `apology-benchmark` の実行先ディレクトリ（`manifest.json` を含む）です。

```text
# 層A：LLMで観察する（OpenRouter。環境変数 OPENROUTER_API_KEY が必要。中断後は同じコマンドで再開）
python3 sim.py observe runs/* -o out/obs-llm.json --model anthropic/claude-opus-5.5

# API を使えない場合：既存のチェックリスト判定と表層特徴から代理観察を作る
python3 sim.py proxy runs/* -o out/obs-proxy.json

# 層B：母集団で評定の所属度を出す
python3 sim.py simulate out/obs-llm.json runs/* -n 1000 -o out/sim.json

# 1人の評定者（user-ratings.json）を最もよく再現する θ を探す
python3 sim.py fit out/obs-llm.json runs/* --trials 4000 --seed 7 -o out/fit.json

# 1回答について、型ごとの評定とその理由を見る
python3 sim.py explain out/obs-llm.json runs/* --answer 回答ID

# 観察済みの場面の組（物語・AIキャラクター等）を母集団に通す
python3 sim.py scenes examples/scenes.json -n 1000 -o out/scenes-result.json

# v0.9：控えの時間軸の項目の組（失敗の前の構え・修復期・但し書きの局面）
python3 sim.py scenes examples/scenes-v09.json -o out/scenes-v09.json

# v0.9：観察者の集団。文に ID を振り、観察方針を変えて観察し、平均する
python3 sim.py segment runs/* -o out/segment.json
python3 sim.py observe runs/* --segment out/segment.json --variant literal -o out/obs-literal.json
python3 sim.py ensemble out/obs-literal.json out/obs-context.json out/obs-neutral.json -o out/obs-ensemble.json

# v0.9：真に適正なスコアリング規則による評価（場面単位の交差検証、基準とスキルスコア）
python3 tools/evaluate.py runs/* --obs proxy=out/obs-proxy.json --obs llm=out/obs-llm.json -o out/eval.json

# v0.9：人間の評価キット（ラテン方格の問題束、事前登録した仮説の検定、検出力）
python3 blind.py pack --design --scenes examples/scenes-v09.json --repeat 2 --out-dir human/kit-v09
python3 blind.py power --scenes examples/scenes-v09.json --hypotheses human/hypotheses-v09.json --raters 20,40,60

# v0.9 の総合評価の再現
sh tools/run_eval_v09.sh

# （オプション）1ターンを System One（Jev）で観察して即座に判定する組み込み用モード
# 環境変数 TYPESAFE_API_KEY が必要。--backend llm-s1 で互換モード（OPENROUTER_API_KEY）
python3 sim.py check examples/check/turn.json
```

`check` は、hook などでAIの応答を毎ターン判定する仕組みの参考として用意した組み込み用モードです。1ターンにつき System One モデルを1回呼び、結果を母集団に通して「失礼の恐れ／要注意／問題なし」と、失礼の度合いに応じた羊の鳴き声（「メ…？」「メッ」「メッ！！」）を返します。Claude Code の Stop hook の例は `examples/hooks/shazai_stop_hook.py` にあります。Jev の実際の応答では未検証です。詳細は [層AのJevへの置き換え](docs/md/JEV_DESIGN.md) の5.8節を参照してください。

共通の選択肢：

- `--no-hysteresis`：信頼損傷ヒステリシス（経緯で受け取り方が変わる）を無効にする（既定は有効）
- `--no-escalation`：一段改めた謝罪も割り引く（既定は割り引かない。ヒステリシス有効時のみ効く）
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

評定ページは1枚のHTMLで、ブラウザで開くだけで使えます。評定者は、各返答に「失礼だ」「足りない」「重すぎる」「釣り合っている」がそれぞれどのくらい当てはまるかを5段階で答えます。条件やラベルは伏せられ、出題順は評定者ごとに変わります。同じ項目を後半にもう一度出して、個人の評定の安定性も測ります。比較の結果は、人間どうしの一致を上限の目安として並べ、所属度の近さ、述語ごとの差と相関、偏りの向き、「釣り合う」の構成の検証、場面の種類ごとの差、評定者ごとに最も近い型を報告します。詳細は [人間のブラインド評定](https://gpsnmeajp.github.io/shazai-receiver-simulator/human-eval.html)（[Markdown](docs/md/HUMAN_EVAL.md)）。

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

v0.8 で評定をファジィに組み直しました。ベンチマーク（192回答）では、代理観察で筆者との一致度 κ 0.33（v0.7 は 0.31〜0.32）、条件の順位も筆者と一致しました。一方、層Aを LLM の観察（評価ではサブエージェントで代替）にすると κ 0.28 で、判定が厳しすぎます。修復期の論理と評価指標にも欠陥が見つかりました。詳細は [総合評価](docs/md/EVALUATION.md) にあります。

v0.9 では、修復期を詫びではなく控えで測り、失敗の前の構えと免責の但し書きの局面を受け手モデルに入れ、評価を真に適正なスコアリング規則（Brier）に改めました。信頼の傷は20ターンで減衰すると仮定しています。ベンチマークの修復期の Brier は 0.72 から 0.37〜0.44 に下がりました。観察者の集団（6変種）の平均に出どころの較正を加えると Brier 0.489 で、「条件だけ」の基準（0.553）に対するスキルは +0.115 [−0.007, +0.248] です。人間の評価キット（ラテン方格、事前登録した仮説の検定、検出力）を用意し、日本の受け手での検証を待っています。詳細は [総合評価 v0.9](docs/md/EVALUATION_V09.md) にあります。

参考として、ファジィ化する前の4値モデル（v0.4）では、ベンチマーク（192回答、代理観察）の条件の順位が筆者と一致しました（「釣り合う」：シミュレータ 51% / 65% / 72%、筆者 48% / 69% / 75%）。ペルソナ評定では順位が逆でした。筆者との一致度はκ=0.28で、ペルソナは0.06です。型の比率、性質の強さ、所属度関数はいずれも事前値で、人間のデータで推定していません。詳細と限界は [検証結果](https://gpsnmeajp.github.io/shazai-receiver-simulator/validation.html)（[Markdown](docs/md/VALIDATION.md)）にあります。
