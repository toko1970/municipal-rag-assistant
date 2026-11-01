# 質問に合う根拠を検索する

[機能一覧へ](README.md) · [トップの構成図へ](../README.md#アーキテクチャ)

質問を文書と同じEmbedding profileでベクトル化し、Qdrantから関連する文書要素を上位8件まで取得します。文書名や見出しの文脈も検索に使い、回答生成には取得した根拠を渡します。

検索候補の比較では、単語一致を加える方式が既存の検索成功を退行させたため採用せず、見出し文脈と検索件数を改善しました。検索評価では必要な根拠を取れても、回答や分類が誤れば総合回答は成功にならないことも確認しています。

- 実装: [`src/qdrant_index.py`](../src/qdrant_index.py) · [`src/query_service.py`](../src/query_service.py) · [`src/embeddings.py`](../src/embeddings.py)
- 検索評価と数値: [精度改善の流れ](../eval/reports/ACCURACY_IMPROVEMENT.md) · [評価資料の案内](../eval/reports/README.md)
