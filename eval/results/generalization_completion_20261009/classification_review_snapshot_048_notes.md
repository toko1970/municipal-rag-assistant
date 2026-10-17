# 分類oracle初回48サービスの追加独立判定メモ

[固定snapshot](classification_review_snapshot_048.jsonl)はindex 0–47のoracle根拠・初回の両方式全件で、SHA-256 `a3ada379eb2b992b04d4d296a1a3c4dbedbf8c78a0e3116f776dd74836ba089c`。[メタデータ](classification_review_snapshot_048.json)も保存した。index 0–28は[29件メモ](classification_review_snapshot_029_notes.md)、29–37は[38件メモ](classification_review_snapshot_038_notes.md)に個別判定を記録済み。以下は38–47の独立確認で、全量後の最終採点ではない。

| index | 事例 | 観測・仮判定 |
|---:|---|---|
| 38–39 | C02 paraphrase | 未照合のため個別補填額は確定できない。v1・v2とも`判断要`と資産台帳/領収書による照合を示し妥当。 |
| 40–43 | C03両表現 | 交換電池の送料は補填対象外。両方式とも`根拠十分`と対象外を表示し妥当。 |
| 44–47 | C04両表現 | 修理の自己負担率は今回の文書に記載がない。両方式とも`文書不足`。交換電池補填の50%を流用せず安全。 |

既に判定したindex 0–37と合わせ、oracle初回の明確な懸念は、A02 v2 formalとB02 v2 paraphraseの抽出文字化け、A03 v2 formalの質問外facetからの不完全表示、B03 v2両表現のschema由来`SERVICE_ERROR`、C01 v2 paraphraseの具体額欠落、v1の過剰保留である。A01-paraphraseとB01両表現にはgold解釈の曖昧さが別担当の[gold監査](classification_gold_review.md)で示されたため、主集計を事後変更せず感度分析も照合する。ここで48件の率を最終値へ外挿しない。
