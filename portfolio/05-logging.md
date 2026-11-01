# 実行内容とfeedbackを記録する

[機能一覧へ](README.md) · [トップの構成図へ](../README.md#アーキテクチャ)

質問受付時に作るrequest IDを使い、検索結果、生成結果、回答、根拠、feedbackを関連付けます。これにより、一つの質問について「何を検索し、何を根拠に、どう回答したか」を後から追えます。

利用ログはPostgreSQL、検索indexはQdrantに分けています。indexを作り直しても実行記録は独立して保持できます。記録の細かさは回答経路によって異なるため、運用中の経路と保存項目は[回答経路の説明](04-answer-generation.md)を参照してください。

- 実装: [`src/persistence/event_logger.py`](../src/persistence/event_logger.py)
- 保存モデル: [データモデル](../design/DATA_MODEL.md)
