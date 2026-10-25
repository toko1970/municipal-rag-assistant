# 自治体向け制度問い合わせ支援RAG

[公開デモ](https://municipal-rag-assistant-280649014820.asia-northeast1.run.app/) · [機能説明](portfolio/README.md)

自治体の給与事務担当者が、規程・通知・FAQ・業務マニュアルから根拠を探す作業を支援するRAGです。架空の制度文書を対象に、回答と根拠、回答できるかどうかを示します。

実在する自治体文書、職員情報、問い合わせ履歴は使用していません。公開デモはCloud Runのscale-to-zero設定により、初回表示に時間がかかる場合があります。

## 仕組み

```mermaid
flowchart LR
    subgraph ING[文書登録・索引作成]
        DOC[制度文書・レビュー済みPDF] --> INGEST[2. 取込・レビュー]
        INGEST --> PG[(PostgreSQL<br/>文書・版の正本)]
        INGEST --> DOC_EMB[文書Embedding]
        DOC_EMB --> QD[(Qdrant<br/>検索index)]
        INGEST --> GCS[(GCS<br/>図表ページ画像)]
    end

    subgraph QA[質問への回答]
        U[利用者] --> UI[1. UI]
        UI --> SEARCH[3. 質問をベクトル検索]
        SEARCH --> QUERY_EMB[質問Embedding]
        QUERY_EMB --> QD
        QD --> SEARCH
        SEARCH --> GEN[4. 回答生成・分類]
        GEN --> UI
        SEARCH -->|図表asset情報を参照| PG
        SEARCH -->|検索記録| LOG
        GEN -->|回答・分類記録| LOG
        UI -->|feedback| LOG
        LOG[5. 実行ログ・feedback] --> PG
        SEARCH -. 元画像を取得 .-> GCS
    end

    classDef user fill:#e8f3ff,stroke:#3572a5,color:#16324f
    classDef process fill:#f2edff,stroke:#7656a5,color:#30224a
    classDef store fill:#e9f6ef,stroke:#3b8058,color:#183b27
    class U user
    class UI,INGEST,DOC_EMB,SEARCH,QUERY_EMB,GEN,LOG process
    class PG,QD,GCS store
```

図中の番号から、各機能の役割・設計上の工夫・評価結果へ進めます。

| 図の役割 | 説明 |
|---|---|
| 1. UI | [質問・回答・根拠の表示](portfolio/01-ui.md) |
| 2. 文書登録・正本管理・ベクトル化 | [取込、レビュー、PostgreSQLとQdrant](portfolio/02-documents-and-index.md) |
| 3. 根拠検索 | [質問ベクトル化と根拠の取得](portfolio/03-retrieval.md) |
| 4. 回答生成・分類 | [根拠付き回答と回答可否の判定](portfolio/04-answer-generation.md) |
| 5. 実行ログ・feedback管理 | [検索・生成・根拠・feedbackの記録](portfolio/05-logging.md) |

[評価結果と詳しいレポート](eval/reports/README.md) · [技術設計](design/TECHNICAL_DESIGN.md)
