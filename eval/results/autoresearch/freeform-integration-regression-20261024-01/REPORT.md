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

## 2026-10-25 公開証拠の確認

本書は当時の暫定結果を保持する。公開ツリーでは元runnerと下記`answer_diff_review.csv`を確認できず、両回答・judge理由からの再集計は未完了。baselineという名称だけから従来の多段`production`経路とは断定しない。今回追加した[APIなし監査](../../../reports/EVALUATION_EVIDENCE_AUDIT_20261025.md)は、scorecardの129/130対125/130とpaired内訳の算術整合を検査するもので、当時runnerの復元・原回答の再採点ではない。

後続のfresh holdoutと公開統合は、[改善の総括](../../../reports/ACCURACY_IMPROVEMENT.md)から確認できる。当時の「未deploy」はこのrun時点の状態である。

## Candidateのみ成功した差分

4件は`answer_diff_review.csv`に質問、baseline/candidate回答、judge値、検索要素をまとめた。候補回答の人手確認が必要。

| Case | Dataset |
|---|---|
| VD014 | visual_development_30 |
| VD016 | visual_development_30 |
| VD019 | visual_development_30 |
| VD024 | visual_development_30 |


統合回帰は開発用回帰であり、judge採点は暫定である。fresh sealed holdoutの評価を含まず、本番トラフィック適用可否はまだ確定しない。
