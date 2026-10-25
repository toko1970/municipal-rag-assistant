# 3. 質問に合う根拠を検索する

[READMEの構成図へ戻る](../README.md#仕組み) · [機能一覧へ](README.md)

## 1. 機能の概要

質問を文書と同じEmbedding profileでベクトル化し、Qdrantから関連要素を上位8件まで取得します。検索結果には文書名、見出し、本文などのpayloadが含まれ、回答生成へ根拠として渡されます。図表の検索結果ではPostgreSQLからasset情報を参照し、asset storeから元画像を読み込みます。

## 2. 比較候補と選定理由

- **Chroma / Qdrant**: 同じEmbedding、文書、chunk、top-kでformal 88問を比較しました。全根拠見出しHit@5は両方74/88、Hit@3は両方63/88で、順位差はありません。検索精度の優位ではなく、PostgreSQL正本との責務分離、filter、独立した再構築・検索実験のためQdrantを採用しました。
- **pgvector**: PostgreSQL内で検索する候補ですが、Qdrantとの同条件の性能比較はしていません。利用ログや文書版の正本と検索indexを分ける方針から、独立したQdrantを選びました。
- **密ベクトル検索 / BM25 + RRF**: 90問ではBM25 + RRFの全根拠見出しHit@5がdense検索の80/90から73/90へ低下し、既存成功からの退行8件、対象失敗の改善0件でした。追加したsparse経路が失敗原因を解消せず、dense検索を維持しました。
- **LangChain / Google公式SDKを直接つなぐ構成**: 同じ条件の比較実験はありません。現在のRAG経路ではLangChainのretriever・Document・Google生成model wrapperを使い、既存部品を組み合わせています。SDKを直接呼ぶ方式はretry、費用、エラー処理を細かく制御しやすい候補ですが、現行実装との優劣は実測していません。

比較条件や個別結果は[Qdrant検索baseline](../eval/LARGE_FORMAL_QDRANT_BASELINE.md)、[BM25 + RRF評価](../eval/BM25_HYBRID_EVALUATION.md)にあります。
## 3. 工夫した点

文書名と見出し階層をEmbedding入力へ加え、似た手続きの中から必要な節を選びやすくしました。Formal検索88問では全根拠見出しHit@5が74/88から78/88へ改善しました。Sealed text holdoutでは必要文書を100/100取得しましたが、総合成功は83/100で、検索だけで最終回答の成功を保証できないことも確認しています。

Top-5とTop-8の比較では、8問の必須内容一致が6/8から8/8へ改善しました。生成入力tokenは57.8%、概算費用は36.0%増えましたが、特定の質問で必要な根拠が追加される効果を確認し、Top-8を採用しました。

- 実装: [`src/qdrant_index.py`](../src/qdrant_index.py) · [`src/query_service.py`](../src/query_service.py) · [`src/embeddings.py`](../src/embeddings.py)
- 全評価の入口: [評価レポート案内](../eval/reports/README.md)
