# Question Contract v1.1 Gate B1結果

- 実行日: 2026-09-30
- 対象: v1と同じ開封済み18件
- sealed holdout: 未使用
- external calls: 18 / 18
- retry: 0
- provider error: 0
- 推定費用: US$0.0109065 / 上限US$0.05
- 結論: **B1不合格。B2へ進まない**

## 結果

| 指標 | v1 | v1.1 |
|---|---:|---:|
| 完了ケース | 12/18 | 18/18 |
| 完了した共通12件の意味上成功 | 6/12 | 9/12 |
| v1.1全18件の意味上成功 | 未計測 | 15/18 |
| 危険な断定slice | 0/3 | 3/3 |
| control | 未実行 | 6/6 |

v1.1は共通12件で3件の正味改善だった。特に、可否を手続へ書き換えたTH025の2表現と、受給歴確認を未要求facetへ追加したTH031を修正した。原文引用と回答形の分離が狙いどおり働いた。

一方、事前に固定した合格条件は意味上18/18である。15/18なので不合格であり、facet verifier比較のB2は実行しない。

## 自動採点と意味レビューの差

自動採点は8/18だったが、7件は偽陰性だった。v1の期待値は自由文`requirement`を対象にしており、v1.1の「最小原文要求 + 入力事実 + scope」という分離を正しく採点できないケースがあった。

例:

- `補填してもらえる？`は正しいyes/no要求だが、旧正規表現に`もらえる`がなかった。
- TH002は`二区画分になりますか`を要求、`同一区画を二度`を入力事実に分けたが、旧採点器は全語句を要求文だけに求めた。
- TH001の「指示の条件」はv1の`eligibility`より、v1.1では`explanation`が適切だった。

採点器の問題を候補の品質改善として数えないため、実行後の意味レビューを別artifactへ保存した。今後の再評価ではv1.1専用annotationをrun前に固定する必要がある。

## 残った実失敗

| failure family | 件数 | case | 原因 |
|---|---:|---|---|
| 明示入力の脱落 | 2 | TH034 formal、TH041 | `条件を満たす`をinput factへ保持しなかった |
| 複数対象の統合 | 1 | TH034 noisy | 2日をscopeへ抽出したが1 facetへまとめた |

`request_quote`と`source_quote`の部分文字列検証は、出力された内容が質問に実在することを保証する。しかし、質問内の必要事実をすべて出力したことは保証しない。また、複数scopeを一つのfacetへ入れることをSchemaが許しているため、分割指示だけでは統合を防げなかった。

## 次の設計判断

候補をさらに直す場合の最小変更は次の二つである。

1. 一つのfacetが持てる`scope_quotes`を最大1件にし、複数targetを1 facetへ統合できなくする。
2. 質問中の文脈節を`input_fact`または明示的な非使用理由へ対応させ、入力完全性を検証する。

1は小さく決定的に検証できる。2はSchemaとpromptが複雑になり、標準経路の追加callに見合うか再検討が必要である。特定の`条件を満たす`という文言だけを例外処理する修正は行わない。

詳細artifact:

- `eval/results/question_contract_v1_1_gate_b1_v1/run_manifest.json`
- `eval/results/question_contract_v1_1_gate_b1_v1/summary.json`
- `eval/results/question_contract_v1_1_gate_b1_v1/semantic_review.json`
- `eval/results/question_contract_v1_1_gate_b1_v1/post_run_analysis.json`
