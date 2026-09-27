# Contextual heading production activation

## 目的

評価で採用したcontextual heading、Top-8、Gemini 3.1 Flash-LiteをローカルRAG v2の実行経路へ反映する。公開Cloud Runへのデプロイ完了を示す文書ではない。

## 実装

- Embedding入力: `文書名 + 見出し1〜3 + 原文`
- PostgreSQL保存本文: 原文
- Qdrant payload本文: 原文
- Embedding task type: `RETRIEVAL_DOCUMENT`
- Embedding profile: `gemini:gemini-embedding-001:contextual-heading-document-v1`
- 検索件数: 8
- Generator / Classifier: `gemini-3.1-flash-lite`
- active local collection: `municipality_rag_docs_v2_contextual_heading_v1`

旧`municipality_rag_docs_v2`は削除せず、比較・rollback用に保持した。新collectionの構築に失敗しても旧vectorを失わない。

## 実行結果

2026-09-27に新collectionを再構築した。

| 確認 | 結果 |
|---|---|
| 取込文書 | 5 |
| Qdrant point | 86 |
| PostgreSQL INDEXED element | 86 |
| Qdrant不足ID | 0 |
| Qdrant余分ID | 0 |
| 新Embedding profile以外のpoint | 0 |
| 保存本文へのEmbedding prefix混入 | 0 |

## Production composition root smoke

質問:

> 2025年10月に本人名義で契約し、家賃15,500円を負担する住宅へ入居した場合の要件・書類・期限は？

結果は`根拠十分`で、改正後の15,000円超、本人名義、住居届・契約書写し・支払確認書類、入居日から30日以内を回答した。

- request ID: `99fdf2e4-36f9-41af-a7ba-5941f14029de`
- retrieval: 8
- generation attempt: 1
- classification attempt: 1
- visible claim: 4
- claim-evidence link: 7
- Generator: 1,837 input / 608 output tokens
- Classifier: 2,336 input / 100 output tokens

## Streamlit UI smoke

`RAG_BACKEND=qdrant`でStreamlit AppTestを実Qdrant・Gemini・PostgreSQLへ接続し、同じ複数根拠質問を画面経路で実行した。

- request ID: `5c3aeecd-3c69-48e0-8805-07cc36cd6734`
- 最終分類: `根拠十分`
- 参照expander: 8件
- feedback: `採用した`を1件保存
- UI exception: 0

このsmokeはローカルRAG v2のUI配線を検証したもので、公開Cloud Runのデプロイ状態は示さない。

## 再現コマンド

```bash
docker compose up -d postgres qdrant
.venv/bin/python -m scripts.manage_rag_v2 rebuild-qdrant
.venv/bin/python -m scripts.manage_rag_v2 reconcile
.venv/bin/python -m scripts.manage_rag_v2 index-info
```

`rebuild-qdrant`は現在設定されたcollectionだけを削除して再構築する。collection名を確認せず実行しない。

## Rollback

`QDRANT_COLLECTION_NAME=municipality_rag_docs_v2`、`TOP_K=5`相当の旧設定へ戻せば旧baseline collectionを参照できる。ただし、旧collectionは本文だけのvector表現である。環境変数によるTop-k切替は未実装のため、rollback時は検証済みcommitへ戻す。
