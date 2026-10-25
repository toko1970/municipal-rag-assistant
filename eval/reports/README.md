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
| 生成モデル | [回答生成モデルの選定記録](GENERATION_MODEL_SELECTION_20261019.md) | 固定入力での比較結果。ローカル既定値は未変更だが、別のユーザー判断による候補統合後、Cloud RunではGemini 3.8 Flashを使用 |
| 検索・回答改善 | [精度改善手法の技術ガイド](ACCURACY_METHODS_TECHNICAL_GUIDE.md) · [汎化検証方針](../GENERALIZATION_VALIDATION_PLAN.md) | 手法の仕組み、弱点、検証範囲と次の確認事項 |
| 分類規約 | [分類・質問範囲の解説](CLASSIFICATION_SCOPE_POLICY_GUIDE.md) · [採用判定プロトコル](../INTERVENTION_ADOPTION_PROTOCOL.md) | 判定規約、候補を採用するための条件 |
| 個別実験 | 下記「代表的な実験記録」および[`results/`](../results/) | 条件、実行記録、詳細な集計結果 |

## 2026-10-25 導入判断と根拠artifact

一回生成候補は、sealed評価をNo-goのまま保持したうえで、別の回帰・challenge比較を確認したユーザー判断によりmainへ統合されました。mainのGitHub Actions run #172は2026-10-25 14:04 JSTに成功し、revision `municipal-rag-assistant-00011-kwv`へ100% trafficを切替えています。[run #172](https://github.com/toko1970/municipal-rag-assistant/actions/runs/40161778266) · [導入判断の記録](../results/autoresearch/freeform-production-rollout-20261025/decision.md)

導入判断文書は判断時点の記録であり、文書内の「未merge・未deploy」はその時点を示します。後続のdeploy完了状態は上記Actions runで確認してください。

| 証拠 | 保存先 | 読み方 |
|---|---|---|
| 130ケース統合回帰 | [REPORT](../results/autoresearch/freeform-integration-regression-20261024-01/REPORT.md) · [機械集計](../results/autoresearch/freeform-integration-regression-20261024-01/scorecard.json) · [実行manifest](../results/autoresearch/freeform-integration-regression-20261024-01/run_manifest.json) | 同一検索条件のcandidate 129/130、baseline 125/130。Gemini judgeによる暫定集計として読み、ユーザーの導入判断とは区別する |
| 80表現challenge | [評価・集計](../results/autoresearch/challenge-freeform-20261024-01/evaluation.md) · [機械集計](../results/autoresearch/challenge-freeform-20261024-01/scorecard.json) · [限定的な人手訂正](../results/autoresearch/challenge-freeform-20261024-01/human_review_adjudication.md) · [実行manifest](../results/autoresearch/challenge-freeform-20261024-01/run_manifest.json) | 限定訂正後の参考値はcandidate 79/80、baseline 78/80。全件人手採点でも、実利用分布の成功率でもない |
| candidate sealed holdout | [評価結果](../results/autoresearch/freeform-fresh-holdout-20261024-01/FRESH_HOLDOUT_EVALUATION.md) · [公開集計](../results/autoresearch/freeform-fresh-holdout-20261024-01/summary.json) · [実行manifest](../results/autoresearch/freeform-fresh-holdout-20261024-01/run_manifest.json) | 76/100、固定gate未達のNo-go、消費済み。custodian採点原票は公開せず、候補選択・再評価へ再利用しない |
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
