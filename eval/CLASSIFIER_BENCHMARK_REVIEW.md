# 分類器benchmark一括レビュー

## 1. 完了条件

モデル出力を見る前に、質問・取得根拠・生成済みclaims・不足条件を読み、5 factorと最終ラベルを固定する。質問が直接求めない後続条件は判断要因に含めない。

## 2. レビュー結果

| 項目 | 結果 |
|---|---:|
| レビュー済み | 36 / 36 |
| annotation承認 | 36 / 36 |
| 根拠十分 | 21 |
| 判断要 | 9 |
| 文書不足 | 6 |
| Text / Visual | 27 / 9 |

既存30件を一括レビューした結果、26件は提案どおり承認し、4件は質問範囲規約に合わせて訂正した。

| Case | 旧factor / label | 確定factor / label | 理由 |
|---|---|---|---|
| REG-Q006 | retrieval=false、文書不足 | 全判断要因=false、根拠十分 | 「この規程だけで確定できるか」は適用対象の記載で回答できる |
| REG-Q076 | retrieval=false、文書不足 | 全判断要因=false、根拠十分 | 「この規程だけで割合を判断できるか」は個別規程によるとの記載で回答できる |
| REG-Q176 | version=true、判断要 | 全判断要因=false、根拠十分 | 「必ず支給できるか」は複数要件があるため否定できる |
| REG-Q301 | case facts=true、判断要 | 全判断要因=false、根拠十分 | 「所属で即決できるか」は一律判断不可との記載で回答できる |

旧gold訂正により文書不足が4件へ減るため、取得根拠にも回答claimにも必要情報がないText・Visual controlを1件ずつ追加した。これにより、文書不足6件と全factorの正例・負例を維持した。

## 3. 公正性

- benchmarkはdevelopment専用で、sealed holdoutではない。
- goldは候補モデルを実行する前に固定した。
- モデル結果を見てannotationを変更しない。
- builderは保存済みTop-8の順序を照合し、入力が変われば停止する。
- 全ケースの`annotation_status`とdatasetの`review_status`は`approved`である。

## 4. 次の工程

1. Jevの利用条件、認証、入力長、費用、データ取扱いをread-onlyで確認する。
2. 多言語NLI候補がローカル環境で読み込めるか、model download前に依存関係と必要容量を確認する。
3. 現行Gemini、Jev、NLIへ同じ36入力を渡す有限runを個別に計画する。
4. factor別F1、最終ラベルmacro F1、重大誤分類、費用・遅延・失敗率で比較する。

外部API、有料設定、model download、sealed holdoutはこのレビューでは使用していない。
