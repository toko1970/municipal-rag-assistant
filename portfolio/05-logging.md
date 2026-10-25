# 5. 実行内容とfeedbackを記録する

[READMEの構成図へ戻る](../README.md#仕組み) · [機能一覧へ](README.md)

## 1. 機能の概要

公開デモはPostgreSQLに質問受付、検索結果の順位とscore、生成attempt、最終回答、feedbackをrequest IDで関連付けて記録します。独立分類・claimと根拠の対応を含む詳細な記録は、ローカル既定の従来経路で行います。同じrequestをたどり、何を検索し、何を根拠に、どう回答したかを評価や失敗分析に使えます。経路ごとの記録粒度は異なり、公開中の一回生成経路は生成attemptと最終回答を保存しますが、独立したclassification attemptやclaim-evidence紐付けは作りません。

## 2. 比較候補と選定理由

**JSONL / SQLite**は準備が軽い選択肢ですが、同一条件の性能試験はしていません。質問と回答に加えて、検索結果、生成・分類の試行、回答claim、根拠、feedbackを互いに関連づけて保存するため、外部キーやtransactionを使え、SQLで追跡・集計できるPostgreSQLを採用しました。
## 3. 工夫した点

質問受付時にrequest IDを作り、検索結果、生成・分類の試行、最終回答、根拠、feedbackをそのIDへ関連付けます。検索indexのQdrantとは保存責務を分けているため、indexを再構築しても利用ログを保持できます。設計は架空データを使うポートフォリオ規模のデモを対象にしています。

- 経路の違い: [現行構成の正本](04-answer-generation.md)
- 実装: [`src/persistence/event_logger.py`](../src/persistence/event_logger.py)
- 保存モデル: [`design/DATA_MODEL.md`](../design/DATA_MODEL.md)
- 評価資料: [評価レポート案内](../eval/reports/README.md)
