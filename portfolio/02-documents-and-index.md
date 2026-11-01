# 文書を登録し、検索indexを作る

[機能一覧へ](README.md) · [トップの構成図へ](../README.md#アーキテクチャ)

規程や手順書の本文を検索しやすい単位に分け、見出しなどの文脈を付けて索引化します。文書と版の正本はPostgreSQLに、ベクトル検索用indexはQdrantに保存します。Qdrantのindexは正本から再構築できます。

図表は抽出内容を人がレビューしてから登録します。画像そのものはasset storeに保存し、参照時に回答の根拠と一緒に表示します。任意PDFのアップロードや抽出レビューを行うWeb画面はありません。

- 実装: [`src/ingestion.py`](../src/ingestion.py) · [`scripts/manage_rag_v2.py`](../scripts/manage_rag_v2.py)
- 図表機能の範囲: [図表RAGの実装状況](../eval/reports/VISUAL_RAG_STATUS.md)
- データ構造: [データモデル](../design/DATA_MODEL.md)
