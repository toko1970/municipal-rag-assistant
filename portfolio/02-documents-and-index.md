# 2. 文書を登録し、正本と検索indexを作る

[READMEの構成図へ戻る](../README.md#仕組み) · [機能一覧へ](README.md)

## 1. 機能の概要

制度文書の本文を解析し、見出しなどの文脈を付けた検索単位へ分割します。PostgreSQLは文書、版、抽出要素の正本、Qdrantはベクトルと検索用payloadを持つ再構築可能なindexです。図表ページ画像はasset storeに保存し、PostgreSQLに対応情報を記録します。

## 2. 比較候補と選定理由

- **JSONL / SQLiteとPostgreSQL**: 性能ベンチマークはありません。文書、版、抽出要素を関係・制約付きで管理し、変更と状態をSQLで追えるようにするためPostgreSQLを正本に選びました。
- **ローカルfilesystem / DB内binaryとGCS**: 容量・費用・速度の比較試験はありません。公開環境でコンテナの入れ替え後も画像を保持し、画像binaryをDB行から分けるためGCSを使います。ローカル開発では同じAssetStore境界のローカル実装を使います。
- **Embedding profile**: Qdrant、文書、chunk、top-k、88問を固定し、`gemini-embedding-001`、Gemini Embedding 2、Ruri v3 310Mを比較しました。全根拠見出しHit@5は74/88、72/88、74/88、MRRは`gemini-embedding-001`が0.861で最高でした。主要指標と順位品質を保てたため、既存の`gemini-embedding-001`を維持しました。

比較条件と個別結果は[Embeddingモデル比較評価](../eval/EMBEDDING_MODEL_EVALUATION.md)にあります。
## 3. 工夫した点

本文をPostgreSQLへ登録した後にEmbeddingを作り、Qdrantへ登録します。Qdrantには検索結果として返す本文・見出し等のpayloadも持たせます。indexを削除してもPostgreSQLの正本から再構築できます。図表は抽出候補のレビュー後に登録し、登録失敗時は状態を記録して管理CLIから再実行できます。

任意PDFのアップロード・レビュー画面は未実装です。

- 実装: [`src/ingestion.py`](../src/ingestion.py) · [`scripts/manage_rag_v2.py`](../scripts/manage_rag_v2.py)
- 図表機能の範囲: [図表RAGの実装状況](../eval/reports/VISUAL_RAG_STATUS.md)
