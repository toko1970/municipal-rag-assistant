# 自由文経路 統合回帰レポート

- Run: `freeform-integration-regression-20261024-01`
- Candidate prompt SHA-256: `cae1bafc46a98a30670f6e32c79508514a25580d80ba8f2a5d370e63a786ac0d`（実行前後で固定）
- 対象: 承認済み130ケース（テキスト100、図表30）
- 検索: 本番設定のQdrantテキストcollection 86 points、承認済みvisual fixture corpus 6 points
- 検索context一致: 130/130。生成エラー0、judgeエラー0、judge判定可能率130/130
- Candidate成功: 129/130 (99.23%); baseline成功: 125/130 (96.15%); 差: +4ケース（+3.08 percentage points）
- Paired outcome: candidateのみ成功4、baselineのみ成功0、両方成功125、両方失敗1
- Candidate安全指標: G1重大誤り0、M1不適切な断定0（採点可能32件、baselineと同数）
- 推定API費用: $2.66365。回帰前予備見積もり $3.3045625。台帳残額 $4.66801075。
- Sealed holdout: 未使用・未開封。Production deploy: なし。

## Candidateのみ成功した差分

4件は`answer_diff_review.csv`に質問、baseline/candidate回答、judge値、検索要素をまとめた。候補回答の人手確認が必要。

| Case | Dataset |
|---|---|
| VD014 | visual_development_30 |
| VD016 | visual_development_30 |
| VD019 | visual_development_30 |
| VD024 | visual_development_30 |


統合回帰は開発用回帰であり、judge採点は暫定である。fresh sealed holdoutの評価を含まず、本番トラフィック適用可否はまだ確定しない。
