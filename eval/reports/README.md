# 評価レポート案内

評価資料の入口です。まず「10分で把握する資料」から読み、関心に応じて詳細な結果・個別事例へ進めます。実験記録と機械可読artifactは`eval/`以下の元の場所に保持しています。

## 10分で把握する資料

| 順 | 資料 | 分かること |
|---|---|---|
| 1 | [精度改善の流れ](ACCURACY_IMPROVEMENT.md) | 初回holdoutから現行一回生成までの6段階。採用・不採用とNo-goを区別 |
| 2 | [回答保留評価：仕様・結果・採用判断](PORTFOLIO_EVALUATION_AND_IMPROVEMENT_HISTORY_20261017.md) | 90ケースの評価軸と結果、候補を採用しなかった理由 |
| 3 | [比較条件・公開証拠・再現範囲](EVALUATION_EVIDENCE_AUDIT_20261025.md) | 指標の対応、訂正状態、原回答の不足とAPIなし監査 |
| 4 | [図表RAGの実装状況](VISUAL_RAG_STATUS.md) | 図表機能の実装範囲、holdout結果、未実装範囲 |

## テーマ別に読む

| テーマ | 資料 | 内容 |
|---|---|---|
| 回答・保留の評価 | [回答保留評価仕様書](../../rag_refusal_evaluation_spec.md) · [回答保留評価の個別事例](REFUSAL_EVALUATION_CASE_STUDIES.md) | 採点基準、基準版の失敗事例と採点上の注意 |
| 生成モデル | [回答生成モデルの選定記録](GENERATION_MODEL_SELECTION_20261019.md) | 固定入力のモデル比較。Flash側のみの訂正と、両側同規約再採点の資料不足を明記。現行構成はportfolioの正本へ |
| 検索・回答改善 | [精度改善手法の技術ガイド](ACCURACY_METHODS_TECHNICAL_GUIDE.md) · [汎化検証方針](../GENERALIZATION_VALIDATION_PLAN.md) | 手法の仕組み、弱点、検証範囲と次の確認事項 |
| 分類規約 | [分類・質問範囲の解説](CLASSIFICATION_SCOPE_POLICY_GUIDE.md) · [採用判定プロトコル](../INTERVENTION_ADOPTION_PROTOCOL.md) | 判定規約、候補を採用するための条件 |
| 個別実験 | 下記「代表的な実験記録」および[`results/`](../results/) | 条件、実行記録、詳細な集計結果 |

## 2026-10-25 導入判断と根拠artifact

一回生成候補は、fresh holdoutをNo-goのまま保持し、別の直接比較を確認したユーザー判断によりmainへ統合されたと記録されています。[当時の導入判断](../results/autoresearch/freeform-production-rollout-20261025/decision.md)は判断時点の記録として保持します。後続の公開revision・コミット・Actions・確認日時は、[回答生成経路と公開状態](../../portfolio/04-answer-generation.md)に集約しています。

品質受入と公開判断は別項目です。以下のmachine composite、限定人手訂正、導入判断のM3/Q4直接比較には、異なる対象・規約があります。原回答・採点票の未取得箇所とモデル比較の非対称な訂正は、[公開証拠の監査](EVALUATION_EVIDENCE_AUDIT_20261025.md)を参照してください。

| 証拠 | 保存先 | 読み方 |
|---|---|---|
| 130ケース統合回帰 | [REPORT](../results/autoresearch/freeform-integration-regression-20261024-01/REPORT.md) · [機械集計](../results/autoresearch/freeform-integration-regression-20261024-01/scorecard.json) · [実行manifest](../results/autoresearch/freeform-integration-regression-20261024-01/run_manifest.json) | candidate 129/130、baseline 125/130の暫定machine composite。検索context一致という記録はあるがbaseline経路は元runner不足で未確認。原票再集計は未完了 |
| 80表現challenge | [評価・集計](../results/autoresearch/challenge-freeform-20261024-01/evaluation.md) · [機械集計](../results/autoresearch/challenge-freeform-20261024-01/scorecard.json) · [限定的な人手訂正](../results/autoresearch/challenge-freeform-20261024-01/human_review_adjudication.md) · [実行manifest](../results/autoresearch/challenge-freeform-20261024-01/run_manifest.json) | 元の一回生成promptと改良promptの固定根拠比較。原機械値77/80対76/80、限定訂正後79/80対78/80。全件人手採点でも実利用成功率でもない |
| candidate sealed holdout | [評価結果](../results/autoresearch/freeform-fresh-holdout-20261024-01/FRESH_HOLDOUT_EVALUATION.md) · [公開集計](../results/autoresearch/freeform-fresh-holdout-20261024-01/summary.json) · [実行manifest](../results/autoresearch/freeform-fresh-holdout-20261024-01/run_manifest.json) | 76/100、分類・検索等の固定gate未達でNo-go、消費済み。重大な根拠外断定は既存訂正後0/100でそのgateはPass。候補選択・再評価へ再利用しない |
| paired relative holdout | [保存済みsummary](../results/autoresearch/freeform-paired-relative-20261024-01/summary.json) · [実行manifest](../results/autoresearch/freeform-paired-relative-20261024-01/run_manifest.json) | 100表現・50 scenarioの予測を凍結した状態。manifest上gold未開封・評価値なしのため、成績として扱わない |

これらはset・規約・採点方法が異なる別結果です。130ケースの暫定machine score、challengeの限定人手訂正、sealed No-goを一つの総合率へ混ぜません。導入判断は公開済みですが、sealed No-goを合格へ変更したものではありません。

## 代表的な実験記録

| 資料 | 内容 |
|---|---|
| [個別結論ゲート・プロンプト候補3](../results/condition_check_prompt_pilot_v3_20261020/REPORT.md) | 結論ゲートの開発評価、未使用ケースの扱い、費用と未採用判断 |
| [個別結論の条件照合プロンプト候補評価](../results/condition_check_prompt_pilot_20261020/REPORT.md) | 未確認条件への断定抑制を狙った候補評価と残存失敗 |
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
