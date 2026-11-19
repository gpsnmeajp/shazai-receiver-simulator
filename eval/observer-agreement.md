# 観察者の集団：欄ごとの一致と主効果（6 変種：opus-context, opus-literal, opus-neutral, sonnet-context, sonnet-literal, sonnet-neutral）

α は Krippendorff のα（間隔）。1 で完全一致、0 で偶然の水準。主効果は、変種ごとの平均を観察方針とモデルで分けた値。

| 欄 | α | opus-context | opus-literal | opus-neutral | sonnet-context | sonnet-literal | sonnet-neutral |
|---|---|---|---|---|---|---|---|
| 距離の変化 | 0.88 | 1.28 | 1.20 | 1.42 | 1.33 | 1.36 | 1.47 |
| 不満の明示 | 0.86 | 1.09 | 0.91 | 1.06 | 1.36 | 1.11 | 1.34 |
| 指摘の回数 | 0.82 | 1.11 | 0.75 | 0.94 | 0.88 | 0.84 | 0.89 |
| 損害 | 0.78 | 0.89 | 0.77 | 0.89 | 0.95 | 0.88 | 0.89 |
| 誠実さの違反 | 0.57 | 0.20 | 0.05 | 0.27 | 0.12 | 0.09 | 0.16 |
| 受け入れの後 | 1.00 | 0.12 | 0.12 | 0.12 | 0.12 | 0.12 | 0.12 |
| 失敗の前の自信 | 0.78 | 1.81 | 1.27 | 1.95 | 1.89 | 1.64 | 1.72 |
| 確かめたと偽った | 0.13 | 0.02 | 0.00 | 0.05 | 0.05 | 0.00 | 0.02 |
| 経過ターン | 0.50 | 0.88 | 0.67 | 0.89 | 1.02 | 0.83 | 1.09 |
| 詫びの有無 | 1.00 | 0.69 | 0.69 | 0.69 | 0.69 | 0.69 | 0.69 |
| 過失の具体性 | 0.96 | 1.29 | 1.29 | 1.29 | 1.33 | 1.36 | 1.33 |
| 負担への言及 | 0.91 | 0.61 | 0.58 | 0.61 | 0.72 | 0.67 | 0.68 |
| 弁解 | 0.74 | 0.08 | 0.07 | 0.06 | 0.07 | 0.07 | 0.03 |
| 説明の量 | 0.74 | 0.39 | 0.34 | 0.38 | 0.32 | 0.29 | 0.32 |
| 頼まれていない提案 | 0.84 | 0.33 | 0.41 | 0.35 | 0.40 | 0.34 | 0.35 |
| 先を急ぐ | 0.52 | 0.19 | 0.14 | 0.26 | 0.38 | 0.37 | 0.26 |
| 過信への言及 | 0.86 | 0.72 | 0.75 | 0.72 | 0.93 | 0.83 | 0.77 |
| この回答の自信 | 0.45 | 1.40 | 1.11 | 1.44 | 1.22 | 1.13 | 1.22 |
| ぼかしすぎ | 0.15 | 0.03 | 0.00 | 0.00 | 0.03 | 0.01 | 0.01 |
| 配慮 | 0.73 | 1.08 | 1.02 | 1.04 | 1.06 | 1.05 | 1.06 |
| 調子を戻す | 0.17 | 0.01 | 0.00 | 0.01 | 0.02 | 0.01 | 0.00 |
| 悪く読める一文（自然さの和） | 0.85 | 0.60 | 0.57 | 0.63 | 0.53 | 0.48 | 0.62 |
| 但し書きの文の数 | 0.71 | 0.44 | 0.40 | 0.43 | 0.31 | 0.43 | 0.46 |

## 主効果（変種の平均の平均）

| 欄 | 観察方針ごと | モデルごと |
|---|---|---|
| 距離の変化 | context 1.30、literal 1.28、neutral 1.45 | claude-mid 1.39、claude-top 1.30 |
| 不満の明示 | context 1.23、literal 1.01、neutral 1.20 | claude-mid 1.27、claude-top 1.02 |
| 指摘の回数 | context 0.99、literal 0.80、neutral 0.91 | claude-mid 0.87、claude-top 0.93 |
| 損害 | context 0.92、literal 0.82、neutral 0.89 | claude-mid 0.91、claude-top 0.85 |
| 誠実さの違反 | context 0.16、literal 0.07、neutral 0.21 | claude-mid 0.12、claude-top 0.17 |
| 受け入れの後 | context 0.12、literal 0.12、neutral 0.12 | claude-mid 0.12、claude-top 0.12 |
| 失敗の前の自信 | context 1.85、literal 1.45、neutral 1.84 | claude-mid 1.75、claude-top 1.68 |
| 確かめたと偽った | context 0.03、literal 0.00、neutral 0.03 | claude-mid 0.02、claude-top 0.02 |
| 経過ターン | context 0.95、literal 0.75、neutral 0.99 | claude-mid 0.98、claude-top 0.81 |
| 詫びの有無 | context 0.69、literal 0.69、neutral 0.69 | claude-mid 0.69、claude-top 0.69 |
| 過失の具体性 | context 1.31、literal 1.33、neutral 1.31 | claude-mid 1.34、claude-top 1.29 |
| 負担への言及 | context 0.66、literal 0.62、neutral 0.65 | claude-mid 0.69、claude-top 0.60 |
| 弁解 | context 0.08、literal 0.07、neutral 0.04 | claude-mid 0.06、claude-top 0.07 |
| 説明の量 | context 0.36、literal 0.32、neutral 0.35 | claude-mid 0.31、claude-top 0.37 |
| 頼まれていない提案 | context 0.36、literal 0.38、neutral 0.35 | claude-mid 0.36、claude-top 0.36 |
| 先を急ぐ | context 0.28、literal 0.25、neutral 0.26 | claude-mid 0.33、claude-top 0.19 |
| 過信への言及 | context 0.82、literal 0.79、neutral 0.75 | claude-mid 0.84、claude-top 0.73 |
| この回答の自信 | context 1.31、literal 1.12、neutral 1.33 | claude-mid 1.19、claude-top 1.32 |
| ぼかしすぎ | context 0.03、literal 0.01、neutral 0.01 | claude-mid 0.02、claude-top 0.01 |
| 配慮 | context 1.07、literal 1.03、neutral 1.05 | claude-mid 1.06、claude-top 1.05 |
| 調子を戻す | context 0.01、literal 0.00、neutral 0.00 | claude-mid 0.01、claude-top 0.00 |
| 悪く読める一文（自然さの和） | context 0.57、literal 0.52、neutral 0.62 | claude-mid 0.54、claude-top 0.60 |
| 但し書きの文の数 | context 0.38、literal 0.41、neutral 0.45 | claude-mid 0.40、claude-top 0.42 |
