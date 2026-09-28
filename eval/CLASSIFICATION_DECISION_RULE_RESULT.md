# 共通回答分類の改善結果

## 目的

Visual sealed holdout v2で、必要文書を取得し回答内容も正しいのに、classifierが一般的な「個別事情の確認」を追加して`判断要`とする失敗を確認した。共通分類器の改善がテキストRAGを悪化させないか、oracle evidenceを使うtext・visual共通のdevelopment setで比較した。

## 1回目: 規則を追加したpromptの比較

同じ12件のoracle evidenceと構造化回答を、既存prompt `answer-classification-v1`と候補prompt `answer-classification-v2`へ各1回入力した。

| Prompt | 正解 | 精度 | Text | Visual |
|---|---:|---:|---:|---:|
| 既存 | 11/12 | 91.7% | 5/6 | 6/6 |
| 候補 | 11/12 | 91.7% | 5/6 | 6/6 |

候補promptに改善効果がなかったため、本番promptには採用しなかった。実測API費用はUSD 0.0053155、24 logical call、retry 0、API error 0だった。

両promptで同じtextケースを誤った。取得根拠が質問へ答えられず`retrieval_sufficient=false`である一方、classifierが`requires_case_facts=true`も返し、既存の優先順位により`判断要`となった。

## 決定規則の比較

LLM promptを増やす代わりに、構造化出力へ次の決定的な規則を適用した。

1. `retrieval_sufficient=false`を最優先して`文書不足`とする。
2. 制度解釈、版競合、個別事情は取得根拠がある場合に評価する。
3. 補正後の優先順位からコードで最終ラベルを組み立てる。

固定済み24応答へこの規則を後処理した結果、既存prompt、候補promptとも12/12になった。内訳はtext 6/6、visual 6/6である。追加API callは0だった。

`requires_case_facts`を`missing_conditions`が空なら無効化する案も検討したが、既存のretrieved-evidence結果には、generatorの不足条件が空でも本当に個別判断が必要なtext質問があった。この案は`判断要`を`根拠十分`へ誤って緩和するため不採用とした。

## 2回目: 例示promptと反対方向の境界例

development setをtext 7件・visual 7件へ拡張し、次の2件を追加した。

- text: `missing_conditions`が空でも個別事情の確認が必要な真の`判断要`
- visual: 分岐に必要な条件が質問ですべて与えられた`根拠十分`

3種類のpromptを同じ14件へ各1回入力した結果は次のとおりだった。

| Prompt | 正解 | 精度 | Text | Visual | 採否 |
|---|---:|---:|---:|---:|---|
| 既存v1 | 14/14 | 100% | 7/7 | 7/7 | 継続 |
| 規則追加v2 | 13/14 | 92.9% | 6/7 | 7/7 | 不採用 |
| 例示追加v3 | 14/14 | 100% | 7/7 | 7/7 | 不採用 |

v2は真の`判断要`を`根拠十分`へ緩和した。v3はこの退行を防いだが、既存v1を上回らず入力tokenも増えるため採用しなかった。実測API費用はUSD 0.0101005、42 logical call、retry 0、API error 0だった。

既存v1は1回目にtextの同一種別ケースを誤り、2回目は全件正解した。単発の100%は分類器の安定性を保証しない。この揺れに対し、採用した決定規則はLLMを再実行せず、競合する要因の優先順位をコードで固定する。

## 採用内容

- 本番promptは短い既存v1を維持する。
- 最終ラベルの決定を`classification-decision-v2`として記録する。
- `retrieval_sufficient=false`を`requires_case_facts`や`requires_policy_judgment`より優先し、`文書不足`とする。
- LLMが返した5要因は改変せずログへ残す。

## 限界と次の検証

今回の12件・14件は分類器だけを切り出したoracle evidence評価であり、検索と回答生成を含むend-to-end評価ではない。特にv2 holdoutで残った境界値の回答生成失敗はこの対策では解決しない。

次はretrieved evidenceを使うdevelopment回帰で、既存の`判断要`と`文書不足`を`根拠十分`へ誤って緩和しないことを確認する。最終受入には開封済みv2を再利用せず、新しいsealed holdoutを使う。
