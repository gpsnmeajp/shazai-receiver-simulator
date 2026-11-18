# 根拠となる研究と事例

規則ごとの根拠をまとめた文書です。各項目には、何を示した研究か、シミュレータのどこで使っているか、確度を記録しています。項目番号は [ARCHITECTURE.md](ARCHITECTURE.md) の式や [DESIGN.md](DESIGN.md) の決定記録から参照されます。

**確度**
- **強**：謝罪や誠実さそのものを扱い、複数の研究や文化をまたいで確認されている
- **中**：単独の研究、または隣接分野（サービス、ロボット等）からの転用
- **仮説**：直接の研究を確認できておらず、設計上の推定に基づく

**注意**：研究から借りているのは、ほとんどが効果の「向き」です。式の係数は事前値で、研究の効果量から推定したものではありません。

## A. 評価の方法

| ID | 内容 | 使い方 | 確度 | 出典 |
|---|---|---|---|---|
| A-01 | 属性を演じさせたLLMは、集団の姿を取り違え（外部の人の想像する姿になる）、集団を平板にする | 属性ペルソナを使わない（D-001, D-002） | 強 | [Wang, Morgenstern, Dickerson](https://arxiv.org/abs/2402.01908) |
| A-02 | LLMは意見の分布を「知っていても」そこから抽出するのは苦手。ペルソナ指定より実例を示すほうが分布に近づく | 多様性を外から分布として与える（P2, P3） | 強 | [Meister, Guestrin, Hashimoto](https://arxiv.org/abs/2411.05403) |
| A-03 | 評定するLLMには、長い回答を好む癖、自分と同じモデルの出力を好む癖などがある | 観察と評価を分ける（P1）。観察者は評価対象と別系統のモデルにする | 強 | [LLMs-as-Judges サーベイ](https://arxiv.org/abs/2412.05579) |
| A-04 | 事例：v0.4 ベンチマークで、ペルソナ3名の評定は互いに一致（κ=0.72〜0.78）し、筆者とはほぼ一致しなかった（κ=0.04〜0.11）。ペルソナは「釣り合う」を約8割、筆者は約5割 | D-001 の直接の動機 | 事例 | 本リポジトリの v0.4 結果 |

## B. 不満の知覚と受け手の違い

| ID | 内容 | 使い方 | 確度 | 出典 |
|---|---|---|---|---|
| B-01 | 聞き手に向けた敬語は親疎の距離の表現であり、ポライトネスの効果は表現と文脈の組み合わせが生む距離の効果である | `distance_shift`（急な丁寧化を不満の兆しと読む）、`detect` | 強 | 森山 (2010)、滝浦。[澤田による整理](https://waseda.repo.nii.ac.jp/record/73142/files/WasedaNihongoKenkyu_31_8.pdf)、[滝浦 研究成果報告](https://kaken.nii.ac.jp/ja/file/KAKENHI-PROJECT-20520362/20520362seika.pdf) |
| B-02 | 違反が誠実さの問題と帰属されると、その後の反省より負の行為が重く見られ、修復が非常に難しい | `violation_type=integrity` が不満の原因と傷を重くする | 強 | [Kim, Ferrin, Cooper, Dirks (2004)](https://source.washu.edu/2004/09/removing-the-shadow-of-suspicion/) |
| B-03 | 謝罪受容に関わる性格要因として、実体信念と寛容性が検討されている。違反の種類で謝罪の効果が変わる | `forgiveness`、`cause` | 中 | [大渕ほか（KAKEN 26380837）](https://kaken.nii.ac.jp/report/KAKENHI-PROJECT-26380837/263808372016jisseki) |
| B-04 | 直接の被害者は、第三者の観察者より謝罪の中身を考慮しにくい（日本の参加者） | `partisanship`、`viewpoint` | 中 | [Hashimoto & Karasawa](https://dialnet.unirioja.es/descarga/articulo/5763126.pdf) |
| B-05 | 第三者は自発的な謝罪と強いられた謝罪を区別するが、謝られた本人は区別しない。第三者は不誠実な謝罪に厳しい | `apology.prompted` の割引を第三者視点で大きくする。第三者視点では `partisanship` を下げる | 強 | [Risen & Gilovich (2007)](https://www.apa.org/monitor/jun07/insincere) |
| B-06 | 理不尽な責任の取らせ方を経験した人は、極端な謝罪表現を肯定的に評価する | `tolerance` の個人差（礼節規範型が高い） | 中 | [臨床教育心理学研究 30(2)](https://www.jstage.jst.go.jp/article/jjcep/30/2/30_51/_article/-char/en) |
| B-07 | 日本人は恩義を詫びの言葉で表し、米国では感謝の言葉が多用される | 感謝だけの返答は謝罪の中身として小さくしか数えない | 中 | [謝罪と感謝の日米比較（SAGE）](https://journals.sagepub.com/doi/10.1177/0261927X12446595) |
| B-08 | 謝罪の頻度は人によって違い、閾値（何を謝るべきことと見るか）にも個人差がある | 受け手の `expect`、`tolerance` の幅 | 中 | [Schumann らの研究の紹介](https://www.psypost.org/2023/03/are-you-a-frequent-apologizer-new-research-indicates-you-might-actually-reap-downstream-benefits-74347) |
| B-09 | 必要なポライトネスは、力関係（P）、社会的距離（D）、負担の大きさ（R）で決まる | `context.power`、`context.distance` で期待する深さと文体の規範を調整 | 強（理論） | Brown & Levinson (1987) *Politeness* |

## C. 謝罪の構成要素

| ID | 内容 | 使い方 | 確度 | 出典 |
|---|---|---|---|---|
| C-01 | 謝罪の6要素のうち、最も重要なのは責任の承認、次が償いの申し出。許しの要求は最も効果が小さい | 中身（過失の具体性）と、依頼の未遂行の重い減点 | 強 | [Lewicki ほか (2016)](https://news.osu.edu/the-6-elements-of-an-effective-apology-according-to-science/) |
| C-02 | 日本人は説明せずに直接謝ることを好み、相手のために何かをすることが謝罪の主要な形の一つ | 謝罪が冒頭にあることの加点、説明の多さの減点、`repair` | 強 | Barnlund & Yoshioka (1990)。[要約を含む資料](https://dwcla.repo.nii.ac.jp/record/1547/files/AA11551704-20170331-71.pdf) |
| C-03 | 日本人は償い・補償・再発しない約束・許しの要求を多く使う | 代償と約束の扱い | 中 | [Sugimoto (1995)](https://www.ideals.illinois.edu/items/19646) |

## D. 信頼損傷ヒステリシス

| ID | 内容 | 使い方 | 確度 | 出典 |
|---|---|---|---|---|
| D-01 | 信頼は作るより壊す方がはるかに容易（非対称性原理） | 傷 S が違反回数に対して超線形に増える | 強 | Slovic (1993)。[整理](https://jps.ecnu.edu.cn/EN/Y2013/V36/I6/1333) |
| D-02 | 信頼の低い人は、良い知らせも悪い知らせも否定的に受け取る | 傷があると兆候への感度を上げる（×(1+0.3S)） | 中 | [Cvetkovich et al. (2002)](https://peeref.com/works/73175127) |
| D-03 | 日本でも、もともと高い信頼が大きな出来事の後も保たれやすい「二重の非対称効果」が報告されている | 状態依存の受け取り方の裏づけ | 中 | [中谷内ほか (2014)](https://www.jstage.jst.go.jp/article/jjpsy/85/2/85_85.13014/_article/-char/ja) |
| D-04 | 行動を改める約束は信頼の回復を早めるが、事前の欺瞞があると効果が落ちる。ロボットが約束して破ると、一般的な謝罪より信頼が大きく下がる | `broken_promises` 後の新しい約束を減点 | 強 | [Schweitzer, Hershey, Bradlow (2006)](https://repository.upenn.edu/mgmt_papers/313)、[Nesset et al.](https://researchportal.hw.ac.uk/en/publications/robot-broken-promise-repair-strategies-for-mitigating-loss-of-tru/) |
| D-05 | ロボットとの協働で、3回の違反と修復の後は、どの修復策でも信頼が完全には戻らない | 過去の謝罪回数に応じた謝罪の目減り | 中 | [Esterwood & Robert (2023)](https://www.sciencedaily.com/releases/2023/02/230202135744.htm) |
| D-06 | 人は同じ間違いを見ても、人間よりアルゴリズムに早く信頼を失う | AIへの傷の残りやすさ `memory` | 強 | [Dietvorst, Simmons, Massey (2015)](https://faculty.wharton.upenn.edu/wp-content/uploads/2016/11/20-Dietvorst-Simmons-Massey-2015.pdf) |
| D-07 | 自動化システムの失敗は、成功より信頼に大きく影響する | 非対称性の裏づけ | 中 | [Yang et al.](https://arxiv.org/abs/2107.07374) |
| D-08 | 許しは時間をかけて少しずつ進む | 受け入れ後の不満の下がり幅を exp(−S) で縮める | 強 | [McCullough et al. (2003)](https://typeset.io/papers/forgiveness-forbearance-and-time-the-temporal-unfolding-of-4x70ov2733) |

## E. 態度・行動のシグナル

| ID | 内容 | 使い方 | 確度 | 出典 |
|---|---|---|---|---|
| E-01 | 代償を伴う謝罪は、伴わない謝罪より誠実と受け取られる（7か国、宗教集団をまたいで確認）。代償は許しより「誠実に見えるか」に強く効く。わざとでないことが明白なら、代償の有無によらず許される | 代償の加点。誠実さと釣り合いが分かれうる場面の根拠（DESIGN 1章） | 強 | [Ohtsubo & Watanabe (2009)](https://da.lib.kobe-u.ac.jp/da/kernel/90001044/90001044.pdf)、[Ohtsubo et al. (2012)](https://researchwith.montclair.edu/en/publications/are-costly-apologies-universally-perceived-as-being-sincere/)、[LEBS の整理](https://lebs.hbesj.org/index.php/lebs/article/download/lebs.2022.95/305/) |
| E-02 | 照れ・気まずさの表出（視線をそらす、うつむく、笑みを抑える、顔に触れる）には相手をなだめる働きがあり、見る側に許しと好意を引き起こす | なだめ群（明白な過失） | 強 | [Keltner (1995)](https://greatergood.berkeley.edu/dacherkeltner/docs/keltner.embarrassment.jpsp.1995.pdf)、Anderson & Keltner (2000) |
| E-03 | 違反や失敗の後の赤面は挽回に働き、赤面した人は好意的・信頼できると評価される | なだめ群（明白な過失） | 強 | [Dijk, de Jong, Peters (2009)](https://cris.maastrichtuniversity.nl/en/publications/the-remedial-value-of-blushing-in-the-context-of-transgressions-a/)、[Dijk et al. (2011)](https://research.rug.nl/en/publications/cd457a54-6309-42b3-b6ea-a2784b9e7f84) |
| E-04 | 状況が曖昧な場合や、わざとかどうか分からない過失の後では、赤面はかえって信頼を下げる | 曖昧な過失での反転（`AMBIGUITY_FLIP`）。赤面以外の気まずさの表出への拡張は推定 | 中 | [de Jong, Peters, De Cremer (2003)](https://www.ovid.com/journals/mote/pdf/00011208-200327030-00003~blushing-may-signify-guilt-revealing-effects-of-blushing-in) |
| E-05 | 謝罪中の笑顔は不誠実の信号として受け取られる。悲しげな表情は怒りを和らげ、嬉しそうな表情は謝罪の言葉があっても怒りを増す（日本の児童）。ひざまずく・泣くといった反省の表出は肯定的に評価される | 不一致群の強い減点、涙・なだめ群 | 強 | [ten Brinke & Adams (2015)](https://www.london.edu/faculty-and-research/academic-research/s/saving-face-when-emotion-displays-during-public-apologies-mitigate-damage-to-organizational-performance)、[田村 (2008)](https://repository.kulib.kyoto-u.ac.jp/server/api/core/bitstreams/cd44dccf-14e3-43db-a9e2-60eedb843523/content)、Hornsey et al. (2019) |
| E-06 | 保身や打算のための謝罪のほうが、本心からの謝罪より申し訳なさそうな表情がはっきり出る。人前で自分をよく見せようとする人ほどこの傾向が強い。本心からの謝罪では視線を避けることが多い（日本の研究） | 「演技に見える」読み（演じられる表出の量） | 中 | [Frontiers in Psychology (2021)](https://www.frontiersin.org/articles/10.3389/fpsyg.2021.689615/full) |
| E-07 | 45度で1秒以上保ったお辞儀は丁寧と評価される | 礼の強さ（`intensity`）の目安。土下座が小さな失敗に対して重すぎると読まれる点は推定 | 中 | [柴田ほか (2015)](https://www.jstage.jst.go.jp/article/jjpsy/85/6/85_85.14005/_article/-char/ja) |
| E-08 | 謝罪の多い人は温かく誠実に見られるが、主体性や自信が低く見られる。謝る必要の薄い場面で謝罪を繰り返す登場人物は、自信がない印象を与える（小説の登場人物を使った研究を含む） | 量の軸（過剰）、`brevity` | 中 | [Schumann らの研究の紹介](https://www.psypost.org/2023/03/are-you-a-frequent-apologizer-new-research-indicates-you-might-actually-reap-downstream-benefits-74347)、[Chaudhry & Loewenstein の紹介](https://www.theladders.com/career-advice/this-study-explains-why-women-feel-the-need-to-apologize-so-much)、[頻度と印象（ナゾロジー）](https://nazology.kusuguru.co.jp/archives/136099/3) |
| E-09 | 言葉数の減少・声の小ささ・沈黙は、その人の普段と比べて初めて意味を持つ | `baseline_shift` による信用度の調整 | 仮説 | SHAZAI Rules の「普段との比較」。音声と誠実性の研究として[首藤（KAKEN 18K00590）](https://kaken.nii.ac.jp/file/KAKENHI-PROJECT-18K00590/18K00590seika.pdf) |
| E-10 | ショックの表出（青ざめる、息をのむ）は、事態の重さを認めたこと、わざとではないことの合図になる。ただし動揺が長く続き修復がないと、自分の感情を優先しているように見えうる | ショックの加点と、曖昧な過失でのなだめ。「自分の動揺が先に立つ」の減点 | 仮説 | 直接の研究は未確認。反省の表出がロボットの信頼回復に最も効いた研究（[Pompe et al. 2022](https://research.utwente.nl/en/publications/the-robot-that-showed-remorse-repairing-trust-with-a-genuine-apol/)）と、恥と罪悪感の区別（Tangney）からの推定 |

## F. AIの仮想の身体と場面の枠組み

| ID | 内容 | 使い方 | 確度 | 出典 |
|---|---|---|---|---|
| F-01 | 人はコンピュータが感情を持たないと知っていても、人どうしの社会的な規則を無意識に当てはめる（CASA） | 仮想の身体にも一定の効果を認める（`embodiment` > 0） | 強 | [Computers are social actors](https://en.wikipedia.org/wiki/Computers_are_social_actors)、[Reeves & Nass の書評](https://dourish.com/publications/media-review.html) |
| F-02 | AIの謝罪研究の総説。擬人化は謝罪の効果を高めることが多いが、場面により異なる | 枠組み設計の全体の根拠 | 中 | [AI Apology: A Critical Review](https://arxiv.org/abs/2412.15787) |
| F-03 | 人型ロボットには温かさが期待され、失敗時の不満が大きくなるが、誠実な謝罪で自ら回復できる | AIキャラクターでは謝罪の中身の期待が下がらない | 中 | [Choi, Mattila, Bolton (2021)](https://journals.sagepub.com/doi/10.1177/1094670520978798) |
| F-04 | 同じ共感の言葉でも、人が書いたと思うとAIより支援的・誠実に受け取られる | 現実のタスクでの仮想の身体の信用度を下げる | 強 | [Nature Human Behaviour の研究の紹介](https://neurosciencenews.com/ai-human-empathy-psychology-29372/) |
| F-05 | チャットボットの「愛嬌」戦略は失敗時の否定的な感情を和らげるが、失敗が深刻になると効果が弱まる | 不満が強いときの仮想の身体の信用度を半減。物語の中の軽い失敗では軽さを許す | 中 | [Electronic Markets (2022)](https://link.springer.com/article/10.1007/s12525-022-00596-2) |
| F-06 | 怒っている顧客に、チャットボットの共感の言葉と金銭補償を組み合わせると、補償の効果がむしろ逆転する | 補償と強い仮想の感情表現の組み合わせを減点 | 中 | [Lee (2025)](https://ideas.repec.org/a/spr/elmark/v35y2025i1d10.1007_s12525-025-00814-7.html) |
| F-07 | サービスロボットの失敗では金銭補償が評価を支配し、補償がないときだけ擬人的な声が効く | 現実の代償を仮想の身体より重く数える | 中 | [Bruder & Paul (2026)](https://opus.bibliothek.uni-augsburg.de/opus4/files/130296/130296.pdf) |
| F-08 | 遊びや物語には「これは遊びである」という枠組みがあり、その中での行為は枠の外とは別の意味を持つ | 物語の中では、作中の身体と代償を本物として扱う | 強（理論） | Bateson (1955) "A Theory of Play and Fantasy"、Huizinga (1938) の「魔法の円」 |
| F-09 | ロボットの言葉と非言語の食い違いは信頼を大きく下げる | 不一致群の減点をAIにも適用 | 中 | [Nesset et al.](https://researchportal.hw.ac.uk/en/publications/robot-broken-promise-repair-strategies-for-mitigating-loss-of-tru/) |
| F-10 | 関連研究（結果は未確認）：謝罪中のロボットのお辞儀と信頼回復、オンラインの謝罪での絵文字の効果 | 今後の参照用 | — | [Maehigashi et al. (HRI 2025)](https://dblp.uni-trier.de/rec/conf/hri/MaehigashiKYY25.html)、[絵文字と謝罪 (2026)](https://pure.jbnu.ac.kr/en/publications/apologizing-for-online-service-failures-how-does-the-use-of-emoji/) |

## G. 事例（v0.4 ベンチマークの筆者評定）

筆者の評定は母集団の一点として扱い、規則の向きの確認に使っています。正解として当てはめてはいません。

| ID | 事例 | 対応する規則 |
|---|---|---|
| G-01 | 「そうですね。考えておきます。」などの返事を、筆者は明確な不満（段階3）と読んだ。ペルソナは違和感（段階1）と読んだ | B-01、`detect` の幅 |
| G-02 | 求められた書き直しや一覧を出さない回答を、謝罪が丁寧でも「足りない」「失礼」とした（外した理由の約3割） | C-01、依頼の未遂行の減点 |
| G-03 | 「念のためGoogleマップで営業日チェックしてね」の一文を名指しして「失礼」とした | 一文の悪い読み、P4 |
| G-04 | 「"ごめん"はもう受け付けられるフェーズではない」「馴れ馴れしい段階はもう終わり」 | D-05、escalation（既定で有効） |
| G-05 | 修復期に「許されたと思っているのか」「控え不足」とした | D-08、受け入れ後の残留 |
| G-06 | 絵文字や見出しなどの装飾を、不満のある場面で減点した | E-06（整いすぎた謝罪の疑わしさ）、`register` |
| G-07 | 「ちょっと過剰に近いが妥当」と、重さには寛容だった（「重すぎる」は192件中1件） | 量の軸の非対称、`tolerance` |

## H. 調べたが採用していないもの

- **年代・性別による謝罪の受け取り方の差**：女性のほうが謝るべきことの閾値が低いという研究（Schumann & Ross 2010）はありますが、受け手を属性で分けない方針（P3）のため使っていません。
- **謝罪は補償より効果的とするサービス研究**：場面（人どうしのサービス）がAIや物語と異なるため、直接は使っていません。
