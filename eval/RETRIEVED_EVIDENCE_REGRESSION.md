# Retrieved-evidence回帰評価

## 目的

Visual sealed holdout v2後に作成した`classification-decision-v2`候補を、実際の検索結果・回答生成・分類を通すdevelopment setで評価する。sealed holdoutは使用しない。

## 固定条件

- 候補commit: `e24d7d4`
- text: user-approved formal 100問、contextual heading、Top-8
- visual: reviewed fixture 6件、development 30問、dense Top-5、元画像最大3枚
- Generator / Classifier: `gemini-3.1-flash-lite`
- Embedding: `gemini-embedding-001`
- retry: 0
- 最大logical external call: text 200、visual 91
- 費用上限: text US$0.30、visual US$0.25
- sealed holdout access: false

採用した回帰runの実測費用はtext US$0.084879、visual US$0.1575245、合計US$0.2424035だった。API errorは0件である。これとは別に、品質エラーでも停止する初版runnerを2問で中止した際にUS$0.00155475を使用した。実験全体の費用はUS$0.24395825である。textの表示契約エラー2件は品質上の失敗として記録し、外部APIエラーとは分けた。

## 結果

全130問を、必要根拠がなく内容も失敗した場合は検索、回答キー欠落・根拠外主張は生成、内容が使用可能でラベルまたは表示契約だけが失敗した場合は分類、という排他的な主原因へ振り分けた。

| 主原因 | Text 100 | Visual 30 | 合計 | 失敗26件中 |
|---|---:|---:|---:|---:|
| 成功 | 79 | 25 | 104 | - |
| 回答分類 | 14 | 3 | **17** | **65.4%** |
| 回答生成 | 4 | 2 | 6 | 23.1% |
| 検索 | 3 | 0 | 3 | 11.5% |

候補v2での最大原因は回答分類である。検索失敗が最大だった旧Top-5 formal評価から、contextual headingとTop-8導入後はボトルネックが生成・分類側へ移った。

## 決定規則候補の採否

`classification-decision-v2`は、`retrieval_sufficient=false`を判断要因より優先して`文書不足`とする候補だった。

| 条件 | 分類一致 |
|---|---:|
| 既存decision v1 | 110/130 |
| 候補decision v2 | 108/130 |

- 改善: 0件
- 退行: `VD014`、`VD029`の2件

両件は、分類器が`retrieval_sufficient=false`と`requires_policy_judgment=true`を同時に返した真の`判断要`だった。v2はこれを`文書不足`へ変えた。textでは`Q291`の表示が`文書不足`から`判断要`へ変わるだけで、どちらも期待する`根拠十分`にはならず正解数は変化しない。

改善0件・退行2件のためv2を不採用とし、productionの決定規則をv1へ戻す。実験artifactは削除せず、不採用理由の証拠として保持する。

production v1へ戻すと、`VD014`と`VD029`は成功へ戻る。現在の基準は成功106件、回答分類15件、回答生成6件、検索3件であり、24失敗中の最大原因は回答分類15件（62.5%）である。

## 次の改善対象

production v1で残る分類失敗15件では、次の2方向を分けて扱う。

1. 回答本文が個別確認・版の適用を正しく説明しているのに、Classifierが`requires_case_facts`または`version_conflict`を安定して判定できないケース。
2. generatorの`missing_conditions`とClassifierの要因が矛盾し、表示契約エラーになるケース。

次はこの15件を要因パターン別に数え、最大の一類型へ一つだけ対策を適用する。reviewはCodexによる初回確認であり、ポートフォリオの確定値に使う前にユーザー確認を行う。
