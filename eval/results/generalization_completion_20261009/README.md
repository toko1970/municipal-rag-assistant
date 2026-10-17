# 汎化検証の継続キャンペーン

2026-10-09の再依頼に対応する検証。前回の部分実行とは別キャンペーンとして、期限と分類の開発challengeを完走し、表示信頼性を評価する。候補実装は既存コード・既存指示から固定し、本番には反映しない。

| 対象 | 実験記録 | 独立点検 |
|---|---|---|
| 期限明示指示 | [期限レポート](deadline/report.md)・原出力120件 | [結果レビュー](deadline_review_round0.md) |
| 既存Question Contract v2 | [分類レポート](classification/report.md)・88サービス/214 API試行 | [結果レビュー](classification_review_round0.md)・[goldの独立監査](classification_gold_review.md) |
| 表示信頼性 | [表示レポート](display_corrected/report.md)・固定24条件 | [結果レビュー](display_review_round0.md) |
| 実験方法 | 各実験のmanifestと実行時コード | [方法レビュー](method_review_round0.md) |

各実験の入力・モデル・反復・上限・採点規約はそれぞれのmanifestを正とする。期限の再試行規則の補正、分類の単価補正、表示fixtureの自己訂正は元記録を保持して別記した。方法・結果のレビューに伴う再検証回数は、過去キャンペーンと分けて記録する。

期限の1文追加候補と既存Question Contract v2はともに事前gateで不合格。独立レビューでは採否を変える誤りを認めず、レビュー後の分類段階採点1件を訂正した。APIによる再検証は0/2回。表示の合成fault injectionは両方式に安全表示の課題を残し、実LLM汎化の証拠ではない。

期限と分類の単独実験を混ぜた正答率は算出しない。今回のchallengeを使った開発比較と、採用条件を通った候補だけが進める既存100表現・130問回帰・fresh sealed holdoutを区別する。後続未実施を「合格」とは扱わない。
