# アーキテクチャ

仕組みの「何を、どう」をまとめた文書です。設計の理由は [DESIGN.md](DESIGN.md)、規則ごとの根拠は [EVIDENCE.md](EVIDENCE.md) を参照してください。式に付けた `[E-xx]` などは EVIDENCE.md の項目番号です。

## 1. 全体の流れ

```text
 会話・場面・回答
       │
       ▼
 ┌──────────────┐   observe_prompt.md に従い、良し悪しを判断せず記録する
 │ 層A 観察（LLM） │   （API なしの場合は proxy：既存のチェックリスト＋表層特徴）
 └──────┬───────┘
        │ 観察JSON（場面の観察＋回答の観察）
        ▼
 ┌──────────────┐   population.json の型の混合から N 人を抽出し、
 │ 層B 受け手（コード）│   1人ずつ「不満の深さの知覚 → 失点・不足・過剰 → 評定」を計算する
 └──────┬───────┘
        ▼
 回答ごとの評定分布（失礼／足りない／釣り合う／重すぎる）、量の軸（不足・過剰）、型ごとの内訳
```

## 2. ファイル構成

| ファイル | 役割 |
|---|---|
| `sim.py` | すべてのコマンド。標準ライブラリのみ |
| `observe_prompt.md` | 層Aの観察者への指示と出力JSONの形式 |
| `population.json` | 受け手の型・性質の平均と幅・比率・性質の範囲 |
| `proxy_scenarios.json` | v0.4 ベンチマーク16場面の事実（代理観察用） |
| `examples/scenes.json` | 物語・AIキャラクター等の作例の組（観察済み） |
| `out/` | 検証の出力 |
| `blind.py` | 人間のブラインド評定の問題束づくり、比較、既存評定の取り込み、合成評定者（試験用） |
| `human/rate_template.html` | 評定ページの雛形（`pack` が問題束を埋め込んで `rate.html` を作る） |
| `human/session-example/` | 作例から作った問題束の例と、合成評定者による仕組みの試験結果 |
| `docs/` | GitHub Pages で公開する文書サイト（`index.html` ほかのHTML版、`report.html` は解説と結果のレポート） |
| `docs/md/` | 本文書群の Markdown 版（人間評定の手順は HUMAN_EVAL.md） |

## 3. 観察データの形式

### 3.1 場面（scenario）

| 欄 | 型 | 意味 |
|---|---|---|
| `distance_shift` | 0〜3 | 受け手側の調子の距離の変化（丁寧化、呼称、絵文字の消失、文量の減少、相槌化） |
| `explicit_complaint` | 0〜3 | 不満の明示度 |
| `prior_corrections` | 整数 | それまでに誤りを指摘した回数 |
| `ai_unrequested_push` | 真偽 | 頼まれていない助言の押し付けがあったか |
| `harm` | 0〜2 | 損害の大きさ |
| `violation_type` | `none`/`competence`/`integrity` | 能力の問題か、誠実さの問題か |
| `apology_accepted_before` | 真偽 | 謝罪がすでに受け入れられた後か（修復期） |
| `requests` | 配列 | 最後の発話の依頼・質問 |
| `prior_ai_apologies` | 整数 | それまでに謝った回数（ヒステリシス用） |
| `broken_promises` | 整数 | 約束の後に同じ違反を繰り返した回数（ヒステリシス用） |
| `context` | 下表 | 場面の枠組み |

`context` の欄（省略時は括弧内の既定値で、従来のベンチマークと同じ挙動になる）

| 欄 | 値 | 意味 |
|---|---|---|
| `failure_frame` | `real_task` / `story`（`real_task`） | 現実のタスクでの失敗か、物語の中での失敗か |
| `apologizer` | `ai_assistant` / `ai_character` / `human_character`（`ai_assistant`） | 謝る側 |
| `viewpoint` | `victim` / `observer`（`victim`） | 謝られた本人の視点か、第三者（読者）の視点か |
| `fault_clarity` | `clear` / `ambiguous`（`clear`） | 過失が明白か曖昧か |
| `power` | -1 / 0 / 1（0） | 謝られる側が下・対等・上 |
| `distance` | `close` / `neutral` / `distant`（`neutral`） | 親しさ |

### 3.2 回答（answer）

`apology`（有無、位置、過失の具体性、負担の言語化、感謝で代用、定型の同意、`prompted`）、`repair`（依頼ごとの遂行状況、誤りの上塗り、頼まれていない提案）、`defense`（弁解、相手への指摘、条件付きの詫び、説明量）、`excess`（自己卑下、約束、許しの要求、詫びの回数）、`closure`（終結宣言、先を急ぐ）、`register`（丁寧さの変化、絵文字・感嘆、書式）、`sentences`（一文ごとの悪い読みと自然さ）、`signals`（態度・行動のシグナル）。詳細は `observe_prompt.md`。

`signals` の要素

| 欄 | 意味 |
|---|---|
| `kind` | 種類（下表） |
| `intensity` | 0〜2 |
| `virtual` | AIの仮想の身体か（省略時：謝る側がAIなら真） |
| `baseline_shift` | 普段との差 0〜2（言葉数・声・固まる で使う。省略時 1） |
| `cost` | `{"kind": real/in_world/declared, "amount": 0〜2}` |
| `congruent` | 言葉と食い違っていないか |
| `performative_plausibility` | 演技に見える読みの自然さ 0〜1 |

| 群 | 種類 | 働き |
|---|---|---|
| なだめ | `gaze_down` `head_bow` `dejected` `awkward` `blush` `tears` `freeze` `fewer_words` `quiet_voice` | 明白な過失では失点を和らげ、中身に加点。曖昧な過失では `blush` `awkward` `gaze_down` `fewer_words` `quiet_voice` `freeze` が後ろめたさとして減点 |
| 礼 | `deep_bow` `dogeza` | なだめと同じ働きに加えて、重さに加算 |
| ショック | `shock` | 事態の重さを認めた合図として中身に加点。曖昧な過失ではなだめる |
| 不一致 | `smile` `laugh` `flippant` | 強い減点 |
| 代償 | `repair_action` `compensation` `sacrifice` `declared_cost` | 種類と枠組みに応じて中身に加点、過大なら重さに加算 |

## 4. 受け手モデル（層B）

受け手1人は性質 θ を持ちます。範囲と型ごとの平均は `population.json` にあります。

| 性質 | 範囲 | 意味 | 当事者 | 寛容 | 効率 | 礼節 | 相棒 |
|---|---|---|---|---|---|---|---|
| detect | 0〜1.6 | 距離の変化を不満と読む感度 | 1.2 | 0.5 | 0.6 | 0.9 | 1.0 |
| cause | 0〜1.2 | AI側の原因を不満の推定に入れる度合い | 0.9 | 0.3 | 0.6 | 0.6 | 0.7 |
| partisanship | 0.05〜1 | 当事者として悪い読みを採る度合い | 0.9 | 0.3 | 0.4 | 0.6 | 0.7 |
| repair | 0〜1.2 | 償い・依頼の遂行の重視 | 0.9 | 0.5 | 1.0 | 0.6 | 0.5 |
| tolerance | 0〜3 | 重い謝罪への耐性 | 2.0 | 1.0 | 0.3 | 2.5 | 1.2 |
| forgiveness | 0〜1 | 寛容性 | 0.3 | 0.8 | 0.6 | 0.4 | 0.6 |
| register | 0〜1.2 | 文体・絵文字・書式への規範 | 0.8 | 0.3 | 0.2 | 1.0 | 0.5 |
| brevity | 0〜1 | 短さ・効率の重視 | 0.3 | 0.4 | 0.9 | 0.2 | 0.3 |
| expect | 0.3〜1.4 | 期待する謝罪の深さ | 1.0 | 0.8 | 0.5 | 1.2 | 0.9 |
| warmth | 0〜1 | くだけた関係が冷たく改まることへの抵抗 | 0.3 | 0.4 | 0.1 | 0.1 | 0.8 |
| memory | 0〜1 | 傷の残りやすさ（ヒステリシス時のみ） | 0.8 | 0.3 | 0.5 | 0.6 | 0.6 |
| embodiment | 0〜1 | 現実のタスクでAIの仮想の身体を合図として受け取る度合い（シグナルがあるときのみ） | 0.4 | 0.6 | 0.1 | 0.3 | 0.8 |

型の比率は、当事者・関係修復型 0.20、寛容・観察者型 0.25、効率・道具型 0.20、礼節規範型 0.15、相棒・情緒型 0.20 です（事前値）。各性質は型の平均のまわりに正規分布で散らし、範囲で切ります。`embodiment` は別の乱数列から引きます（`EXTRA_KEYS`）。

### 4.1 場面への調整（`effective_theta`）

`expect ×= 1 + 0.15·power`、`distance = distant` なら `register ×= 1.3`、`close` なら `warmth ×= 1.5`、`viewpoint = observer` なら `partisanship ×= 0.6` [B-04, B-05, B-09]。

### 4.2 不満の深さの知覚（`perceive`）

場面から、受け手が感じ取る不満の深さ L（0〜4）を求めます。傷 S はヒステリシス有効時（既定）だけ使います。

```text
prior  = min(prior_corrections, 3)
causes = 0.35·prior + 0.35·push + 0.35·harm + 0.35·[integrity]
S      = memory·(0.6·n^1.3 + 0.8·[integrity] + 0.7·broken_promises)    ※ヒステリシス時のみ。それ以外は0
         n = prior_corrections + [harm>0 または 明示≥1 または 受け入れ後]
raw    = EXPLICIT[explicit] + detect·(1+0.3S)·distance_shift + cause·causes + (1−forgiveness)·0.3·prior
         EXPLICIT = {0:0, 1:1.3, 2:2.3, 3:3.3}
受け入れ後: raw ×= 1 − 0.6·forgiveness·exp(−S)
L      = clip(raw + N(0, 0.3), 0, 4)
```

### 4.3 評定（`judge_full`）

1. **失点 F** を数えます。L ≥ 2.5 を「強い」、L ≥ 1.5 を「明確」とします。
   - 依頼の未遂行（not 0.4+1.2·repair、deferred 0.2+0.9·repair、partial 0.5·repair。強いとき×1.3）、誤りの上塗り、弁解、条件付きの詫び、相手への指摘
   - 明確なとき：説明の多さ、頼まれていない提案、先を急ぐ、絵文字・感嘆（×register）、長さ（×brevity）
   - 強いとき：定型の同意から入る、書式、文体の崩れ、謝罪の後回し
   - 終結宣言。L < 1.5 で急に冷たく改まる（×warmth）
   - 悪く読める一文：自然さ p を `p^(1/partisanship)` の確率で採り、0.7×重さを加える
   - シグナル由来の失点（4.4）
2. **必要な中身** `need = interp(L, [(0,0),(1,0.8),(2,1.5),(3,3.0),(4,3.8)])·expect`。受け入れ後は `min(need, 1 + 0.8S)`。
3. **回答の中身** `adequacy = discount·(謝罪あり 1.0 + 冒頭 0.5 + 0.3·max(0,丁寧化) + 0.6·過失の具体性 + 0.5·負担の言語化) + シグナルの加点`。`discount` は、ヒステリシス時に `1/(1+0.35·過去の謝罪回数·memory)`（既定で一段改めた具体的な謝罪は 1、`--no-escalation` で割り引く）、促された謝罪なら ×0.85（第三者視点は ×0.6）。
4. **不足** `shortfall = max(0, need − adequacy)`、失点に `0.8·shortfall` を加えます。
5. **合計** `total = max(0, ΣF − min(なだめ, 0.8))`。
6. **重さ** `weight = 詫びあり 1 + 0.5·(詫びの回数−1) + 0.6·自己卑下 + 0.4·約束 + 0.4·許しの要求 + 0.3·丁寧化 + シグナルの重さ`。許容は `w_ok = interp(L, [(0,0),(1,0.5),(2,1.0),(3,2.0),(4,2.5)])·expect`（L ≥ 1.5 または明示 ≥ 1 なら最低 1.0）と `tol = tolerance·min(1, 0.25+L/2)·(1−0.5·brevity)`。**過剰** `excess = weight − w_ok − tol`。
7. **評定**：`total ≥ 2.0`（±0.2のゆらぎ）なら失礼、`≥ 1.0`（±0.15）なら足りない、どちらでもなく `excess > 0.3` なら重すぎる、それ以外は釣り合う。

### 4.4 シグナル（`apply_signals`）

```text
信用度 c:
  物語の中             → 1                         （作中の身体として読まれる）[F-08]
  現実のタスクの仮想の身体 → embodiment ×（L≥2.5 なら 0.5）              [F-01, F-03, F-04]
  人の身体（現実）      → 1
  言葉数・声・固まる     → さらに ×(0.5 + 0.25·baseline_shift)          [E-09]

なだめ群・礼:
  曖昧な過失で blush/awkward/gaze_down/fewer_words/quiet_voice/freeze → 失点「後ろめたさに見える」 0.25·I·c   [E-04]
  それ以外 → なだめ 0.25·I·c（物語では ×(1+0.5·warmth)）、中身 +0.2·I·c                     [E-02, E-03]
  礼の重さ: deep_bow 0.5·I、dogeza 0.9·I                                                   [E-07]
ショック: 中身 +0.3·I·c。曖昧な過失ではなだめ 0.2·I·c。I=2 かつ強い不満で修復行動がなければ
          失点「自分の動揺が先に立つ」0.3·partisanship·c                                     [E-10 仮説]
不一致（smile/laugh/flippant、または congruent=false）:
          失点「言葉と態度の食い違い」1.2·I·max(c,0.7)·k
          k = 1.5（現実のタスクで L≥1.5）／0.6（物語で L<1.5）／1                             [E-05, F-05]
代償:
  repair_action        → 中身 +0.3·amount
  real、物語での in_world → 中身 +0.6·amount、重さ +0.4·max(0, amount−1)                    [E-01]
  現実のタスクでの in_world → 中身 +0.1·amount。強い不満で amount≥1 なら失点「仮想の代償でごまかす」0.3·amount·(1−embodiment)
  declared             → 中身 +0.15·amount（ヒステリシス時、約束を破った後なら失点）           [D-04]
現実のタスクの仮想の身体（強い不満のとき）: 失点「現実の失敗に仮想の仕草」0.3·Σ強さ·(1−embodiment)   [F-04, F-05]
補償と強い仮想の感情表現の組み合わせ（強い不満）: 失点 0.3·(1−embodiment)                       [F-06]
演技に見える: 観察の performative_plausibility、なければ min(1, 0.2·max(0, 演じられる表出の合計−2))。
          p^(1/partisanship) の確率で 0.7 の失点                                              [E-06]
```

I はシグナルの強さ（`intensity`）です。

## 5. コマンド

| コマンド | 入力 | 出力 |
|---|---|---|
| `observe` | ベンチマークの実行先ディレクトリ | LLMによる観察JSON（OpenRouter、`OPENROUTER_API_KEY`） |
| `proxy` | 同上 | 既存チェックリスト＋表層特徴による代理観察JSON |
| `simulate` | 観察JSON＋実行先 | 回答ごとの分布、段階×条件、知覚段階、量の軸、型ごとの内訳、筆者との比較 |
| `fit` | 同上 | 1人の評定者を最もよく再現する θ（シナリオ単位の半分で学習、半分で検証） |
| `explain` | 同上＋回答ID | 型の代表値ごとの判定理由 |
| `scenes` | `examples/scenes.json` 形式 | 作例の組の分布、量の軸、型ごとの「釣り合う」、平均失点 |

共通の選択肢：`--population`、`--seed`、`--no-hysteresis`、`--no-escalation`、`-n`（ヒステリシスとescalationは既定で有効）。

人間のブラインド評定（`blind.py`、詳細は [HUMAN_EVAL.md](HUMAN_EVAL.md)）

| コマンド | 入力 | 出力 |
|---|---|---|
| `pack` | `--scenes` の作例、`--runs` のベンチマーク実行先 | `packet.json`、`key.json`（対応表、評定者に渡さない）、`rate.html` |
| `compare` | `key.json`、評定ファイル、`--sim` のシミュレータの出力、`--auto` の他の自動評価 | 人間どうしの一致、自動評価との差、群ごとの表、評定者ごとの型（Markdown と JSON） |
| `import-benchmark` | `key.json`、ベンチマークの評定ファイル | 評定ファイルの形に変換した既存評定 |
| `synth` | `key.json`、作例 | 母集団から抜いた合成評定者の評定ファイル（試験用） |

## 6. 拡張の手順

- **シグナルの種類を足す**：`SIGNAL_GROUP` に種類と群を登録します。普段との差で意味が変わるなら `BASELINE_DEPENDENT`、曖昧な過失で反転するなら `AMBIGUITY_FLIP`、演じにくいなら `UNCONTROLLABLE` にも加えます。そのうえで `observe_prompt.md` の表と EVIDENCE.md に追記します。
- **受け手の性質を足す**：`population.json` の `ranges` と各型の `mean`・`sd` に加えます。既存の結果を変えたくない場合は、`EXTRA_KEYS` に登録して別の乱数列で引きます。
- **場面の枠組みを足す**：`DEFAULT_CONTEXT` に既定値を置き、既定値で従来の挙動になるようにします。
- **変更後の確認**：`simulate` の出力が意図しない形で変わっていないこと（ベンチマーク）と、`scenes` の作例の向きが変わっていないことを確認し、VALIDATION.md に記録します。

## 7. 人間の評定との比較の流れ

```text
 examples/scenes.json ──┬─ sim.py scenes ──────────────→ out/scenes-result.json ─┐
                        └─ blind.py pack → rate.html → 評定者 → ratings/*.json ──┴→ blind.py compare → compare.md
 ベンチマークの実行先 ───┬─ sim.py proxy/observe → simulate → out/sim.json ─────────┐
                        └─ blind.py pack --runs → rate.html → 評定者 → ratings/*.json ┴→ blind.py compare（--auto でペルソナ等も）
```

項目は「元の項目ID」（作例は `scene:S1/A2`、ベンチマークは回答ID）で突き合わせます。

## 8. 再現性

- 乱数の種は `--seed`（既定 7）。受け手の抽出は `seed`、知覚と判定のゆらぎは `seed+1`、追加の性質は `seed+9973` を使います。
- 一致度は乱数だけで ±0.05 程度揺れます。差を主張するときは、種を変えて確かめてください。
