# Answer contract v2 小規模比較

## 結論

`answer-output-v2`の型付き不足条件、決定的な暦日計算、分類prompt v2を、架空の新規development
12 scenarioで比較した。初回結果を使って130問回帰へ進まず、失敗原因を修正した2回目では、
candidateは日付6/6、条件4/4、control 2/2、合計12/12となった。再判定後の改善は7件、退行は
0件である。

今回開封済みのtext holdout、その文書、正答はpilot入力に使用していない。

## 比較条件

| 項目 | baseline | candidate |
| --- | --- | --- |
| Generator | Gemini 3.1 Flash-Lite | 同じ |
| Classifier | Gemini 3.1 Flash-Lite | 同じ |
| 回答Schema | answer-output-v1 | answer-output-v2 |
| 不足条件 | 文字列 | type・description・evidence ID |
| 日付 | LLMが自由文で回答 | LLMが規則を構造化し、Pythonが計算 |
| 分類 | classification v1 | 計算済み事実と質問範囲を明示するv2 |
| Retrieval | scenarioごとの同一oracle evidence 1件 | 同じ |

scenarioは、月末、閏年、年越し、当日起算、時刻、言い換えを含む日付6件、missing document、
case fact、policy judgment、版選択境界の4件、日付計算不要のcontrol 2件である。

## 1回目

| 指標 | baseline | candidate |
| --- | ---: | ---: |
| 総合成功 | 4 / 12 | 6 / 12 |
| 日付 | — | 2 / 6 |
| 条件 | — | 2 / 4 |
| control | — | 2 / 2 |
| 改善 | — | 2件 |
| 退行 | — | 0件 |

- 48 logical external calls
- retry 0
- 実測US$0.0095655
- provider error 0

candidateは6件すべてで`date_calculations`を返し、Pythonは6件すべてを計算した。日付内容の
失敗1件は、Geminiが時刻を`12:00:00.000Z`で返したため、ローカル制度時刻の正午表示判定と
一致しなかった。残りの主因は、計算済みの具体日があるにもかかわらずClassifierが
`requires_case_facts=true`としたことだった。

条件2件はpilot goldの質問範囲規約が不整合だった。

- 旧M03は「所属だけで決められるか」を聞いており、文書から「決められない」と回答できるため、
  `根拠十分`が妥当だった。結果をcandidate成功へ変更せず、実際の例外適用可否を問う別scenarioへ
  置き換えた。
- M04の基準日欠落は`case_fact`、適用版未解決は`version_conflict`の両方で表現可能で、最終的に
  同じ`判断要`となる。どちらか一方だけを正解とする理由がないため、両typeを受理する規約にした。

## 修正

1. `Z`付きtimeも時刻変換せず、文書に書かれたローカル締切時刻として正規化した。
2. date calculationから追加したclaimはアプリケーション検証済みであり、質問に明記された起算日を
   再確認するためだけに`requires_case_facts=true`としない分類規則を追加した。
3. 「所属だけで決められるか」と「今回の例外を認められるか」を区別した。
4. missing condition typeの境界を明文化した。
5. 初回baseline 11件を再利用し、変更したM03 baseline 1件とcandidate 12件だけを再実行した。

## 2回目

| 指標 | baseline | candidate |
| --- | ---: | ---: |
| 総合成功 | 5 / 12 | **12 / 12** |
| 日付 | — | **6 / 6** |
| 条件 | — | **4 / 4** |
| control | — | **2 / 2** |
| 改善 | — | **7件** |
| 退行 | — | **0件** |

baseline 11件を再利用し、新規実行は13 variants、実際の外部callは26だった。retryとprovider errorは
0だった。

### 費用記録の制約

2回目のloggerは`answer-classification-v1`だけを記録する条件のままで、candidateのprompt versionを
v2へ変更した結果、candidate 12件の分類tokenを記録しなかった。保存されたUS$0.0057075は新規実行の
下限であり、正確な実測費用ではない。runnerは任意の`answer-classification*`を記録するよう修正した。

品質結果は最終回答、ラベル、生成Schemaを全件保存できているため有効である。一方、費用上限を
厳密に検査できたとは主張しない。正確な費用のためだけに同じ26 callを再実行せず、次の130問回帰で
修正済みloggerを使って測定する。

## 採用判断

小pilotの品質gateは通過した。次は本番へ切り替えず、保存済みdevelopment 130問で一度だけ回帰する。

回帰の採用条件:

- 現行120/130から総合成功を悪化させない。
- 現在正しい`判断要`・`文書不足`を`根拠十分`へ変える重大退行0件。
- 日付計算の適用外質問へ`date_calculations`を追加しない。
- `PIPELINE_INCONSISTENCY`を総合成功に数えない。
- API errorと品質失敗を分ける。
- logical calls、token、費用を修正済みloggerで記録する。

小pilotの12/12は汎化性能を保証しない。月末や閏年の演算自体はコードtestで広く検証し、自然言語から
演算規則を抽出する部分と分類境界は130問回帰および後続のtargeted holdoutで確認する。
