# 評価レポート案内

評価資料の入口です。まず「10分で把握する資料」から読み、関心に応じて詳細な結果・個別事例へ進めます。実験記録と機械可読artifactは`eval/`以下の元の場所に保持しています。

## 10分で把握する資料

| 順 | 資料 | 分かること |
|---|---|---|
| 1 | [精度改善の流れ](ACCURACY_IMPROVEMENT.md) | 課題の発見、比較、採用・不採用の経緯 |
| 2 | [回答保留評価：仕様・結果・採用判断](PORTFOLIO_EVALUATION_AND_IMPROVEMENT_HISTORY_20261017.md) | 90ケースの評価軸と結果、候補を採用しなかった理由 |
| 3 | [図表RAGの実装状況](VISUAL_RAG_STATUS.md) | 図表機能の実装範囲、holdout結果、未実装範囲 |

## テーマ別に読む

| テーマ | 資料 | 内容 |
|---|---|---|
| 回答・保留の評価 | [回答保留評価仕様書](../../rag_refusal_evaluation_spec.md) · [回答保留評価の個別事例](REFUSAL_EVALUATION_CASE_STUDIES.md) | 採点基準、基準版の失敗事例と採点上の注意 |
| 生成モデル・検索件数 | [Gemini 3.1とTop-kの評価](../GEMINI_3_1_TOP_K_ANSWER_EVALUATION.md) | 生成モデル既定値とTop-5/Top-8の比較、費用との判断 |
| 検索・回答改善 | [精度改善手法の技術ガイド](ACCURACY_METHODS_TECHNICAL_GUIDE.md) · [汎化検証方針](../GENERALIZATION_VALIDATION_PLAN.md) | 手法の仕組み、弱点、検証範囲と次の確認事項 |
| 分類規約 | [分類・質問範囲の解説](CLASSIFICATION_SCOPE_POLICY_GUIDE.md) · [採用判定プロトコル](../INTERVENTION_ADOPTION_PROTOCOL.md) | 判定規約、候補を採用するための条件 |
| 個別実験 | 下記「代表的な実験記録」および[`results/`](../results/) | 条件、実行記録、詳細な集計結果 |

## 代表的な実験記録

| 資料 | 内容 |
|---|---|
| [改善手法の一般化監査](../GENERALIZATION_REVIEW.md) | 現行規則の監査と次の比較案 |
| [期限指示の開発challenge検証](../results/generalization_validation_20261009/report.md) | 未知日付での部分比較、誤期限による不採用判断 |
| [汎化検証の継続キャンペーン](../results/generalization_completion_20261009/README.md) | 期限・分類・表示の検証と独立レビュー |
| [汎化検証結果の再確認](../results/generalization_recheck_20261009/report.md) | 保存結果の再集計と関連テストによる再確認 |
| [分類設計とLLM入力の仮説検証](../results/classification_design_input_audit_20261009/report.md) | 分類規約・prompt・判定規則の差と保存入力の監査 |
| [質問範囲・分類規約の明示候補](../results/classification_scope_policy_v1_20261009/report.md) | 固定入力による候補比較とGate 1結果 |
| [修正版v2.2の比較評価完了](../results/scope_release_v22_gate1_final_20261012/report.md) | 全応答取得後の比較と不合格判断 |
| [修正版v2.2の比較評価](../results/scope_release_v22_gate1_20261009/report.md) | API上限で途中停止した比較と未実施範囲 |
| [版解決後の回答再検証](../results/scope_revalidation_v22_20261009/report.md) | 版解決後の表示再検証と残課題 |
| [分類改善の本番受入準備](../results/scope_release_gate1_20261009/report.md) | 実装準備、独立レビュー、未完了のAPI比較 |

## 指標の読み方

### Recall@K

正解として定めた文書または根拠節が検索上位`K`件に含まれた質問の割合です。複数根拠が必要な質問では、必要な根拠をすべて取得した場合だけ成功とします。文書に答えがない質問は検索Recallの分母から外し、回答分類で評価します。

### 総合回答成功率

必要な根拠の取得、回答内容、根拠による支持、回答分類、表示まで、定めた必須条件を満たした質問の割合です。検索Recallが高くても、回答生成や分類が誤れば総合成功にはなりません。

### 数値を比較するときの注意

評価セット、質問数、正解条件、Top-k、モデルが異なる数値は直接比較できません。各レポートで測定条件と母数を確認してください。改善しなかった候補、退行、未完了の実験も記録に残しています。
