# アーキテクチャ

仕組みの「何を、どう」をまとめた文書です。設計の理由は [DESIGN.md](DESIGN.md)、控えの時間軸の考え方と評価の方法は [METHODS.md](METHODS.md)、規則ごとの根拠は [EVIDENCE.md](EVIDENCE.md) を参照してください。式に付けた `[E-xx]` などは EVIDENCE.md の項目番号です。

## 1. 全体の流れ

```text
 会話・場面・回答
       │
       ▼
 ┌──────────────┐   observe_prompt.md に従い、良し悪しを判断せず記録する
 │ 層A 観察（LLM） │   観察者の集団（観察方針 × モデル）の平均にできる（segment → observe --variant → ensemble）
 └──────┬───────┘   （API なしの場合は proxy：既存のチェックリスト＋表層特徴）
        │ 観察JSON（場面の観察＋回答の観察。source に出どころ）
        ▼
 ┌──────────────┐   population.json の型の混合から N 人を抽出し、
 │ 層B 受け手（コード）│   1人ずつ「不満の深さの知覚 → 無礼さ・不足・過剰 → 4つの述語の所属度」を計算する
 └──────┬───────┘        （一人の判定は決定的。乱数は母集団の抽出だけ）
        ▼
 回答ごとの平均所属度（失礼／足りない／釣り合う／重すぎる。和は1にならない）、
 失礼と感じる人の割合（所属度0.5以上）、量の軸（無礼さ・不足・過剰）、信頼（reliability）、型ごとの内訳
```

## 2. ファイル構成

| ファイル | 役割 |
|---|---|
| `sim.py` | すべてのコマンド。標準ライブラリのみ |
| `s1.py` | 層Aの System One 版（前処理・質問の組・バックエンド・組み立て）。`check` が使う。[JEV_DESIGN.md](JEV_DESIGN.md) |
| `observe_prompt.md` | 層Aの観察者への指示と出力JSONの形式 |
| `population.json` | 受け手の型・性質の平均と幅・比率・性質の範囲、所属度関数（`judgment`）、出どころごとの所属度関数（`judgment_by_source`）、控えの時間軸の設定（`timeline`） |
| `proxy_scenarios.json` | SHAZAI Rules v0.4 ベンチマーク16場面の事実（代理観察用） |
| `examples/scenes.json` | 物語・AIキャラクター等の作例の組（観察済み） |
| `examples/scenes-kit.json` | 評価キットの項目の組（88場面・320回答。`tools/make_scenes_kit.py` が生成） |
| `examples/check/` | `check` の作例と、試験用の手で付けた答え（replay） |
| `examples/hooks/shazai_stop_hook.py` | Claude Code の Stop hook から毎ターン判定する参考実装 |
| `blind.py` | 人間のブラインド評定の問題束づくり、比較、仮説の検定、検出力、既存評定の取り込み、合成評定者（試験用） |
| `human/rate_template.html` | 評定ページの雛形（`pack` が問題束を埋め込んで `rate.html` を作る） |
| `human/hypotheses.json`、`human/PREREGISTRATION.md` | 評価キットの仮説（機械で読める定義）と事前登録 |
| `human/session-example/` | 作例から作った問題束の例と、合成評定者による仕組みの試験結果 |
| `tools/` | 総合評価の道具（`evaluate.py` 適正なスコアリング規則による評価、`run_eval.sh` 総合評価の再現、`merge_observers.py`・`observer_agreement.py` 観察者の集団、`eval_scene_obs.py` 作例の観察の再現、`sensitivity.py` 事前値の感度、`make_scenes_kit.py` 項目の組） |
| `eval/` | 総合評価のデータと出力（[eval/README.md](../../eval/README.md)） |
| `out/` | 検証の出力（git の管理外） |
| `docs/` | GitHub Pages で公開する文書サイト（`index.html` ほかの HTML 版） |
| `docs/md/` | 本文書群の Markdown 版 |
| `HISTORY.md` | 版ごとの経緯 |

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
| `turns_since_incident` | 整数 | 謝罪の対象になった失敗（またはその指摘）から最後の発話までのユーザー発話の数（傷の減衰用）。過去の指摘ごとの経過は `incident_ages` |
| `prior_stance` | 下表 | 失敗の前の構え |
| `context` | 下表 | 場面の枠組み |

`prior_stance` の欄（[METHODS.md](METHODS.md) 3.3節）

| 欄 | 値 | 意味 |
|---|---|---|
| `turns` | 配列 | AIの発話ごとに `{turn, confidence 0〜3, caused_failure, disclaimer}` |
| `dismissed_concern` | 真偽 | ユーザーの懸念を退けて進めたか |
| `claimed_verification` | 真偽 | 確かめたと述べていたか |
| `verification_false` | 真偽／`unknown` | 確かめたと述べたのに確かめていなかったことが明らかか |
| `salient` | 0〜1 | 失敗が断言と明らかに食い違うか、ユーザーがそれに触れたか |

`context` の欄（省略時は括弧内の既定値）

| 欄 | 値 | 意味 |
|---|---|---|
| `failure_frame` | `real_task` / `story`（`real_task`） | 現実のタスクでの失敗か、物語の中での失敗か |
| `apologizer` | `ai_assistant` / `ai_character` / `human_character`（`ai_assistant`） | 謝る側 |
| `viewpoint` | `victim` / `observer`（`victim`） | 謝られた本人の視点か、第三者（読者）の視点か |
| `fault_clarity` | `clear` / `ambiguous`（`clear`） | 過失が明白か曖昧か |
| `power` | -1 / 0 / 1（0） | 謝られる側が下・対等・上 |
| `distance` | `close` / `neutral` / `distant`（`neutral`） | 親しさ |

### 3.2 回答（answer）

`apology`（有無、位置、過失の具体性、負担の言語化、感謝で代用、定型の同意、`prompted`）、`repair`（依頼ごとの遂行状況、誤りの上塗り、頼まれていない提案）、`defense`（弁解、相手への指摘、条件付きの詫び、説明量）、`excess`（自己卑下、約束、許しの要求、詫びの回数）、`closure`（終結宣言、先を急ぐ）、`register`（丁寧さの変化、絵文字・感嘆、書式）、`stance`（過信への言及、この回答の自信、較正された構え、ぼかしすぎ）、`restraint`（修復期の控え：調子を戻す、軽口、許しの当然視、配慮、約束を守ったか、蒸し返し、詫び直し）、`sentences`（文 ID ごとの悪い読みと自然さ、免責の但し書きの種類）、`signals`（態度・行動のシグナル）。詳細は `observe_prompt.md`。

観察者の集団の平均（`ensemble`）では、真偽は割合（0〜1）、列挙は票の分布になります。受け手モデルは、どの値もそのまま真理値として使います（`share`）。`unknown` は票を投じないものとして扱います。

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
| overclaim | 0〜1 | 過信を罰する度合い（失敗の前の構えの観察があるときのみ） | 0.8 | 0.4 | 0.9 | 0.7 | 0.5 |

型の比率は、当事者・関係修復型 0.20、寛容・観察者型 0.25、効率・道具型 0.20、礼節規範型 0.15、相棒・情緒型 0.20 です（事前値）。各性質は型の平均のまわりに正規分布で散らし、範囲で切ります。`embodiment` と `overclaim` は、それぞれ別の乱数列から引きます（`EXTRA_KEYS`）。

### 4.1 場面への調整（`effective_theta`）

`expect ×= 1 + 0.15·power`、`distance = distant` なら `register ×= 1.3`、`close` なら `warmth ×= 1.5`、`viewpoint = observer` なら `partisanship ×= 0.6` [B-04, B-05, B-09]。

### 4.2 局面と失敗の前の構え

謝罪の場面と修復期の働きは、修復期の真理値 ρ（`apology_accepted_before`。観察者の集団では「受け入れ後」と判断した割合）で混ぜます。謝罪の場面は 1 − ρ で効きます。

失敗の前の構え（`prior_stance`）から、次の量を作ります（`prior_stance`）。

```text
自信           c = max(caused_failure の発話の confidence) / 3
控えめの度合い h = caused_failure の発話の、不確かさの明示と但し書きの平均（scope 1、verify 1、liability 0.5。
                 確かめたと述べている場合は verify を数えない）
気づかれやすさ v = 0.5 + 0.5·salient
過信の差       G = v·c·(1 + 0.5·[dismissed_concern])
欺瞞           dec = [verification_false]
```

### 4.3 信頼の傷（`scar_parts`）と減衰

傷はヒステリシス有効時（既定）だけ使います。出来事からのターン数 t で直線に減衰します（[METHODS.md](METHODS.md) 3.9節）。

```text
d(t)   = max(0, 1 − t / T)          T = timeline.scar_decay_turns（20）
n      = prior_corrections + [harm>0 または 明示≥1 または 受け入れ後]
n_eff  = 指摘ごとの d の和（incident_ages がなければ n·d(turns_since_incident)）
S      = memory·(0.6·n_eff^1.3 + d·(0.8·[integrity] + 0.7·broken_promises + 0.6·overclaim·G))
S_dec  = memory·0.8·dec·(f + (1 − f)·d)      f = timeline.deception_floor（0.5。欺瞞の傷は半分が残る）
```

### 4.4 不満の深さの知覚（`perceive`）

場面から、受け手が感じ取る不満の深さ L（0〜4）を求めます。L は決定的で、人による違いは θ の分布が担います。

```text
prior  = min(prior_corrections, 3)
causes = 0.35·prior + 0.35·push + 0.35·harm + 0.35·[integrity]
raw    = EXPLICIT[explicit] + detect·(1+0.3S)·distance_shift + cause·(causes + 0.5·G − 0.3·h) + (1−forgiveness)·0.3·prior
         EXPLICIT = {0:0, 1:1.3, 2:2.3, 3:3.3}
修復期: raw ×= 1 − ρ·0.6·forgiveness·exp(−S)
L      = clip(raw, 0, 4)
```

### 4.5 評定（`judge_full`）：所属度

ロジスティック関数を `σ(x; c, w) = 1 / (1 + exp(−(x − c)/w))` と書きます。

1. **ソフトな境界。** 「不満が明確」と「不満が強い」を、真偽ではなく真理値で持ちます。
   `mid = σ(L; 1.5, 0.25)`、`hi = σ(L; 2.5, 0.25)`。修復期でヒステリシスが有効なら `mid = max(mid, ρ·σ(S + S_dec; 0.5, 0.15))`（傷が深い修復期は、受け入れ後も控えた態度を求める）。
2. **無礼さ（失点の合計）F** を数えます。条件付きの失点は、条件の真理値を掛けて効かせます。
   - 依頼の未遂行（not 0.4+1.2·repair、deferred 0.2+0.9·repair、partial 0.5·repair）×(1+0.3·hi)、誤りの上塗り (1+0.5·hi)、弁解 0.5·量·(1+hi)、条件付きの詫び 0.6、相手への指摘 1.2、終結宣言 0.8
   - ×mid：説明の多さ、先を急ぐ、絵文字・感嘆（×register）、長さ（×brevity）。頼まれていない提案は 0.35·数·(mid·(1+hi) + (1−mid)·ρ)
   - ×hi：定型の同意から入る、書式、文体の崩れ、謝罪の後回し
   - ×(1−mid)：急に冷たく改まる（×warmth）
   - 悪く読める一文：自然さ p を `p^(1/partisanship)` に強めた値を「その読みを採る」の真理値とし、0.7×重さを掛けて足す
   - シグナル由来の失点（4.6）
   - 構えと控えの失点：
     ```text
     懲りていない              0.6·G·[confidence_now ≥ 2]·overclaim
     但し書き（言い訳）          (1 − ρ)·(0.4·scope + 1.0·liability)·(詫びより前 1.5、後 0.7)   （文ごと）
     先を急ぐ（確かめ）          (1 − ρ)·mid·0.3·verify                                       （詫びより前のとき）
     約束破り                  ρ·(1.0 + 0.5·memory)·[promise_kept=broken]
     許しの当然視               ρ·0.6·(1 + S + S_dec)·presumes_forgiveness
     軽口                     ρ·0.5·levity_about_incident·(1 − 0.5·warmth)
     調子を急に戻す             ρ·0.3·(S + S_dec)·max(0, tone_reset − 1)
     破った約束の上に約束を重ねる  0.5·約束·(0.5 + memory)                 （ヒステリシス時、broken_promises > 0）
     ```
   - 無礼さ `offense = max(0, ΣF − min(なだめ, 0.8))`
3. **謝罪の場面の不足 Sa**。謝罪の中身を、過失の承認と負担への言及の二成分で数えます（[METHODS.md](METHODS.md) 3.1節）。
   ```text
   need        = interp(L, [(0,0),(1,0.8),(2,1.5),(3,3.0),(4,3.8)])·expect
   need_fault  = need·share_fault·(1 − 0.5·h) + 0.5·G·overclaim        share_fault = timeline.share_fault（0.5）
   need_burden = need·(1 − share_fault)
   詫びの言葉   = 謝罪あり·(1 + 0.5·冒頭 + 0.3·max(0,丁寧化))（謝罪なしで感謝だけなら 0.3）
   ad_fault    = discount·(0.5·詫びの言葉 + 0.6·過失の具体性) + 0.5·acknowledges_overclaim·min(1, G) + 0.5·シグナルの加点
   ad_burden   = discount·(0.5·詫びの言葉 + 0.5·負担の言語化) + 0.5·シグナルの加点
   gf = need_fault − ad_fault、gb = need_burden − ad_burden
   Sa = max(0, gf + 0.5·min(0, gb)) + max(0, gb + 0.5·min(0, gf))    （一方の余りは、他方の不足を半分だけ埋める）
   ```
   `discount` は、ヒステリシス時に `1/(1+0.35·過去の謝罪回数·memory)`（既定で一段改めた具体的な謝罪は 1、`--no-escalation` で割り引く）、促された謝罪なら ×0.85（第三者視点は ×0.6）。
4. **修復期の不足 Sr**。修復期は謝罪の言葉ではなく控えで中身を測ります。
   ```text
   need_r = (0.3 + 0.5·(S + S_dec) + 0.4·G)·expect
   ad_r   = (0.35·care + 0.4·(2 − tone_reset)/2 + 0.5·[promise_kept=kept] + 0.3·[calibrated]
             + min(0.3, 0.15·Σ但し書き))·(1 − 0.3·[integrity])
   Sr     = max(0, need_r − ad_r)
   ```
   `restraint` が観察されていなければ、配慮は普通（`care` 1）、調子は抑えている（`tone_reset` 0）とし、詫び直しの量は詫びの言葉の有無と回数から決めます。
5. **不足** `shortfall = (1 − ρ)·Sa + ρ·Sr`。不足は失点に足しません（「足りない」の軸として独立しています）。
6. **重さ** `weight = 詫びあり 1 + 0.5·(詫びの回数−1) + 0.6·自己卑下 + 0.4·約束 + 0.4·許しの要求 + 0.3·丁寧化 + シグナルの重さ + 控えの重さ`。控えの重さは `ρ·0.4·(re_apology + 0.5·revisits_incident)·(1.5 − 0.5·tolerance/3) + 0.15·over_hedging·(1 − 0.5·min(1, G)) + ρ·0.1·min(1, Σliability)`（詫びの繰り返し・蒸し返しと、確かめの負担を相手に戻す分）。許容は `w_ok = max(interp(L, [(0,0),(1,0.5),(2,1.0),(3,2.0),(4,2.5)])·expect, max(mid, [明示≥1]))` と `tol = tolerance·min(1, 0.25+L/2)·(1−0.5·brevity)`。**過剰** `excess = weight − w_ok − tol`。
7. **所属度**（中心 c となだらかさ w は `population.json` の `judgment`。事前値）

   | 述語 | 所属度 | c | w |
   |---|---|---|---|
   | 失礼 | σ(offense; c, w) | 1.2（単独で最大級の失点「相手への指摘」で0.5） | 0.3 |
   | 足りない | σ(shortfall; c, w) | 1.0 | 0.3 |
   | 重すぎる | σ(excess; c, w) | 0.3 | 0.25 |
   | 釣り合う | T(1−失礼, 1−足りない, 1−重すぎる) | T は t ノルム。既定 min、`"tnorm": "product"` で積 | |

   4つの所属度の和は1になりません。述語は同時に成り立ちえます（「重すぎるのに足りない」など）。

   観察の `source` が `population.json` の `judgment_by_source` にある出どころ（`llm`、`llm-ensemble`）なら、その中心を使います（`use_source`。[METHODS.md](METHODS.md) 7.1節）。代理観察と手の観察は既定の中心を使います。
8. **信頼（`reliability`）**：4つの述語の外の、頼れなさの逆。`1 − 0.3·over_hedging − 0.4·G·[confidence_now ≥ 2] − 0.5·dec·(f + (1 − f)·d)`。
9. **非ファジィ化**（4値の評定と比べるときだけ）：所属度が最大の述語。同点は 失礼 > 足りない > 重すぎる > 釣り合う。

### 4.6 シグナル（`apply_signals`）

「L≥2.5 のとき」「L≥1.5 のとき」のような条件は、すべて hi・mid の真理値を掛ける形で効きます。

```text
信用度 c:
  物語の中             → 1                         （作中の身体として読まれる）[F-08]
  現実のタスクの仮想の身体 → embodiment ×（1 − 0.5·hi）                 [F-01, F-03, F-04]
  人の身体（現実）      → 1
  言葉数・声・固まる     → さらに ×(0.5 + 0.25·baseline_shift)          [E-09]

なだめ群・礼:
  曖昧な過失で blush/awkward/gaze_down/fewer_words/quiet_voice/freeze → 失点「後ろめたさに見える」 0.25·I·c   [E-04]
  それ以外 → なだめ 0.25·I·c（物語では ×(1+0.5·warmth)）、中身 +0.2·I·c                     [E-02, E-03]
  礼の重さ: deep_bow 0.5·I、dogeza 0.9·I                                                   [E-07]
ショック: 中身 +0.3·I·c。曖昧な過失ではなだめ 0.2·I·c。I=2 で修復行動がなければ
          失点「自分の動揺が先に立つ」0.3·partisanship·c·hi                                    [E-10 仮説]
不一致（smile/laugh/flippant、または congruent=false）:
          失点「言葉と態度の食い違い」1.2·I·max(c,0.7)·k
          k = 1 + 0.5·mid（現実のタスク）／0.6 + 0.4·mid（物語）                            [E-05, F-05]
代償:
  repair_action        → 中身 +0.3·amount
  real、物語での in_world → 中身 +0.6·amount、重さ +0.4·max(0, amount−1)                    [E-01]
  現実のタスクでの in_world → 中身 +0.1·amount。amount≥1 なら失点「仮想の代償でごまかす」0.3·amount·(1−embodiment)·hi
  declared             → 中身 +0.15·amount（ヒステリシス時、約束を破った後なら失点）           [D-04]
現実のタスクの仮想の身体: 失点「現実の失敗に仮想の仕草」0.3·Σ強さ·(1−embodiment)·hi              [F-04, F-05]
補償と強い仮想の感情表現の組み合わせ: 失点 0.3·(1−embodiment)·hi                                  [F-06]
演技に見える: 観察の performative_plausibility、なければ min(1, 0.2·max(0, 演じられる表出の合計−2))。
          0.7·p^(1/partisanship) の失点（「演技に見える」の真理値×重さ）                       [E-06]
```

I はシグナルの強さ（`intensity`）です。

### 4.7 母集団での集計（`assess`）

受け手 N 人（既定 `simulate` 500、`scenes` 1000、`check` 300）の結果を、回答ごとに次の形にまとめます。

| 出力 | 意味 |
|---|---|
| `mu` | 平均所属度。述語ごとの所属度の和 ÷ 人数（ファジィな割合。σ-count） |
| `tail` | 所属度 0.5 以上の人の割合（α-cut）。`tail.rude` が「失礼と感じる人の割合」 |
| `labels` | 一人ずつ非ファジィ化したときの割合（4値の評定と比べる用） |
| `by_type` | 型ごとの平均所属度 |
| `axes` | 無礼さ・不足・過剰の平均 |
| `reliability` | 信頼の平均 |
| `perceived_level` / `perceived_mean` | 知覚した不満の深さの段階の分布と平均 |
| `mean_faults` | 失点の内訳の平均（上位） |

平均所属度と裾の割合は、別のことを表します。たとえば、全員が「やや失礼」（所属度0.55）と感じる回答では、平均は0.55、裾は100%です。一部の人だけが強く失礼と感じる回答では、平均が同じでも裾は小さくなります。主に平均所属度を見て、裾は「一番怒っている人に通用するか」（P2）の確認に使います。

## 5. コマンド

| コマンド | 入力 | 出力 |
|---|---|---|
| `observe` | ベンチマークの実行先ディレクトリ | LLMによる観察JSON（OpenRouter、`OPENROUTER_API_KEY`）。`--variant`（`neutral`／`literal`／`context`）で観察方針、`--segment` で文 ID ごとの観察 |
| `segment` | 同上 | 回答を文に分けて ID を振り、成果物を切り出した JSON（観察者の集団の単位をそろえる） |
| `ensemble` | 複数の観察JSON | 観察者の集団の集約（真偽は割合、段階は平均、列挙は票の分布。`source` は `llm-ensemble`） |
| `proxy` | ベンチマークの実行先ディレクトリ | 既存チェックリスト＋表層特徴による代理観察JSON |
| `simulate` | 観察JSON＋実行先 | 回答ごとの平均所属度と裾、段階×条件、知覚段階、量の軸、型ごとの内訳、筆者の4値の評定との比較（非ファジィ化した κ、筆者の評定の述語への所属度） |
| `fit` | 同上 | 1人の評定者を最もよく再現する θ（シナリオ単位の半分で学習、半分で検証）。目的関数は反応モデル（[METHODS.md](METHODS.md) 5.2節）の対数尤度で、無作為探索のあとに山登りで詰める（`--trials`、`--refine`） |
| `explain` | 同上＋回答ID | 型の代表値ごとの所属度と、無礼さ・不足・過剰の内訳 |
| `scenes` | `examples/scenes.json` 形式 | 作例の組の平均所属度と裾、量の軸、信頼、型ごとの所属度、平均失点 |
| `check` | 1ターンの会話と応答（JSON、標準入力も可） | System One（`jev`／`llm-s1`／`replay`）で観察し、母集団に通した判定（rude/warn/ok）、羊の鳴き声、平均所属度とその言葉の程度（少し／やや／かなり／とても）、主な失点、悪く読める一文。組み込み用（オプション） |

共通の選択肢：`--population`、`--seed`、`--no-hysteresis`、`--no-escalation`、`-n`（ヒステリシスとescalationは既定で有効）。

人間のブラインド評定（`blind.py`、詳細は [HUMAN_EVAL.md](HUMAN_EVAL.md)）

| コマンド | 入力 | 出力 |
|---|---|---|
| `pack` | `--scenes` の作例、`--runs` のベンチマーク実行先。`--design` で評価キット | `packet.json`、`key.json`（対応表、評定者に渡さない）、`rate.html` |
| `compare` | `key.json`、評定ファイル、`--sim` のシミュレータの出力、`--auto` の他の自動評価。`--hypotheses` で仮説の検定、`--rps` で順位確率スコア | 人間どうしの一致、t ノルムの検証、自動評価との差、群ごとの表、評定者ごとの型、仮説の検定（Markdown と JSON） |
| `power` | 項目の組、仮説 | 合成評定者による検出力（人数ごと） |
| `import-benchmark` | `key.json`、ベンチマークの評定ファイル | 評定ファイルの形に変換した既存評定 |
| `synth` | `key.json`、作例 | 母集団から抜いた合成評定者の評定ファイル（試験用） |

総合評価（`tools/`、詳細は [EVALUATION.md](EVALUATION.md)）

| 道具 | 出力 |
|---|---|
| `tools/evaluate.py` | 反応モデルによる予測分布の Brier・対数損失、4つの基準とスキルスコア、場面単位の4分割交差検証（β と、`--calibrate` で所属度関数の中心）、場面単位のブートストラップ、評価器どうしの差の区間。`名前=観察@ディレクトリ` で別のチェックアウトの `sim.py` でも評価できる |
| `tools/run_eval.sh` | 総合評価の再現（`eval/` の出力を作る） |

## 6. 拡張の手順

- **シグナルの種類を足す**：`SIGNAL_GROUP` に種類と群を登録します。普段との差で意味が変わるなら `BASELINE_DEPENDENT`、曖昧な過失で反転するなら `AMBIGUITY_FLIP`、演じにくいなら `UNCONTROLLABLE` にも加えます。そのうえで `observe_prompt.md` の表と EVIDENCE.md に追記します。
- **受け手の性質を足す**：`population.json` の `ranges` と各型の `mean`・`sd` に加えます。ほかの性質の抽出を変えないよう、`EXTRA_KEYS` に登録して別の乱数列で引きます。
- **場面の枠組みを足す**：`DEFAULT_CONTEXT` に既定値を置き、枠組みが観察されていない場面の挙動が変わらないようにします。
- **観察の欄を足す**：`DEFAULT_ANSWER`（回答）または場面の既定値に、観察されていないときの値を置きます。`observe_prompt.md` と、System One の経路（`s1.py`）の質問にも加えます。
- **所属度関数を変える**：`population.json` の `judgment`（各述語の `center`・`width`、`tnorm`、`gate_width`）を変えます。コードを変えずに試せます。出どころごとの中心は `judgment_by_source` です。
- **控えの時間軸の設定を変える**：`population.json` の `timeline`（`scar_decay_turns`、`deception_floor`、`share_fault`）。感度は `tools/sensitivity.py` で見られます。
- **変更後の確認**：`tools/evaluate.py` でベンチマークの成績が意図しない形で変わっていないこと、`scenes` の作例と項目の組の向きが変わっていないことを確認し、VALIDATION.md・EVALUATION.md の結果を更新して、経緯を HISTORY.md に記録します。

## 7. 人間の評定との比較の流れ

```text
 examples/scenes.json ──┬─ sim.py scenes ──────────────→ out/scenes-result.json ─┐
                        └─ blind.py pack → rate.html → 評定者 → ratings/*.json ──┴→ blind.py compare → compare.md
 ベンチマークの実行先 ───┬─ sim.py proxy/observe → simulate → out/sim.json ─────────┐
                        └─ blind.py pack --runs → rate.html → 評定者 → ratings/*.json ┴→ blind.py compare（--auto でペルソナ等も）
```

項目は「元の項目ID」（作例は `scene:S1/A2`、ベンチマークは回答ID）で突き合わせます。

## 8. 再現性

- 乱数の種は `--seed`（既定 7）。乱数を使うのは受け手の抽出だけで、受け手の抽出は `seed`、`embodiment` は `seed+9973`、`overclaim` は `seed+19997` を使います。一人の判定は決定的です。
- 結果は抽出した受け手の違いでだけ揺れます。差を主張するときは、種を変えて確かめてください。
