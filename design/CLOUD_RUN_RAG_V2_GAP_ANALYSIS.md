# Cloud Run / local RAG v2 gap analysis

- 確認日: 2026-09-27
- 対象Cloud Run service: `municipal-rag-assistant` (`asia-northeast1`)
- 公開revision: `municipal-rag-assistant-00004-vv9`
- 公開image commit: `486a9ff4b3a00963ee805d1977e4154d4c86f9d5`
- 比較対象local commit: `efe47b81fe963686b62818d61380de61ad229d37`
- 調査範囲: read-only。resource、IAM、API、secret、trafficは変更していない

## 1. 結論

公開Cloud Runはhealth checkへ`ok`を返し、100%のtrafficを受けている。一方、公開imageはlocal HEADより41 commit前であり、Chromaをcontainer内で構築する旧RAGである。

local RAG v2はQdrant、PostgreSQL、contextual heading、Top-8、構造化回答、回答分類、Gemini 3.1 Flash-Liteまで検証済みである。ただしCloud Runには`DATABASE_URL`、`QDRANT_URL`、`QDRANT_COLLECTION_NAME`がなく、Cloud SQL Admin APIも無効だった。Qdrant Cloud endpointとAPI keyも設定されていない。

この状態でlocal HEADのimageだけを現行CDから反映すると、既定値の`localhost`にあるPostgreSQLとQdrantへ接続しようとする。Cloud Runのhealth checkはStreamlit processの起動だけを見るため成功し得るが、質問時のRAG v2経路は接続に失敗する可能性が高い。現行HEADをそのまま公開しない。

## 2. 3層の観測結果

### 2.1 Code

| 項目 | 公開image `486a9ff` | local HEAD `efe47b8` |
|---|---|---|
| Vector store | Chroma | Qdrantを既定値として選択可能 |
| Metadata / event store | なし | PostgreSQL + Alembic |
| Embedding入力 | chunk本文 | 文書名 + 見出し1〜3 + 原文 |
| 検索件数 | Top-5 | Top-8 |
| 回答model | `gemini-2.5-flash` | `gemini-3.1-flash-lite` |
| 回答形式 | 自由文を1回生成 | claim JSON生成、分類JSON生成、codeで表示文を構築 |
| ログ / feedback | container内JSONL | RAG v2はPostgreSQL。legacy経路はJSONL fallback |
| 評価証拠 | 難問評価まで | 500表現、Qdrant、Embedding、contextual heading、Top-k、回答回帰評価まで追加 |
| PDF・図表 | 未対応 | fixture、gold、validator、development / holdout protocolまで。runtime取込は未実装 |

公開commitからlocal HEADまでの差分は41 commit、234 filesである。件数には評価結果、fixture、設計文書を含むため、その全てがruntime変更という意味ではない。

### 2.2 Deployment configuration

2026-09-27に`gcloud run services describe`で次を確認した。

| 項目 | 実状態 |
|---|---|
| 状態 | `Ready=True` |
| traffic | latest revisionへ100% |
| ingress | all |
| runtime service account | `municipal-rag-runtime@municipal-rag-portfolio.iam.gserviceaccount.com` |
| CPU / memory | 1 CPU / 1 GiB |
| container concurrency | 10 |
| container env | `GOOGLE_API_KEY`がSecret Manager `gemini-api-key:1`を参照する1件のみ |
| PostgreSQL設定 | なし |
| Qdrant設定 | なし |
| GCS設定 | なし |

Secret本文は取得していない。公開URLの`/_stcore/health`は`ok`を返した。質問回答のend-to-end smokeはAPI費用とログ書込を伴うため、このread-only調査では行っていない。

### 2.3 Cloud services / data

| 必要要素 | localでの証拠 | Cloud Run側の証拠 | 判定 |
|---|---|---|---|
| PostgreSQL schema | migration、repository、実DB integration test | `DATABASE_URL`なし。Cloud SQL Admin API無効 | 未接続 |
| Qdrant collection | 86 point、PostgreSQLとの差分0 | endpoint、key、collection設定なし | 未接続 |
| Embedding | 新profileで86 point再構築 | 公開imageは旧本文Embedding | 未反映 |
| Gemini 3.1 | 8問比較とlocal UI smoke | 公開imageは2.5固定 | 未反映 |
| 永続ログ / feedback | PostgreSQLへ保存を確認 | container内JSONL | 非永続 |
| PDF・図表 | fixture評価基盤 | GCS保存・runtime extraction・indexingなし | runtime未実装 |

Cloud SQL Admin APIが無効なため、今回のコマンドだけでinstanceが存在しないと断定はしない。ただし、Cloud Runに接続設定がなく、現在のアプリ経路からは利用できない。

## 3. CDが埋めない差分

GitHub Actionsのdeploy jobは次を行う。

1. commitのcontainer imageをbuildする。
2. Artifact Registryへpushする。
3. 既存Cloud Run serviceのimageを差し替える。
4. Streamlit health endpointを確認する。

このjobは次を行わない。

- Cloud SQL、Qdrant Cloud、GCSの作成
- PostgreSQL migration
- 文書取込とQdrant collection構築
- DB / Qdrant接続secretと環境変数の設定
- runtime service accountへの追加IAM付与
- 質問から回答、ログ、feedbackまでのend-to-end smoke

従って、CI成功とCloud Run health成功だけではRAG v2が利用可能だとは判断できない。

## 4. 公開方法の選択肢

### A. 公開demoはChromaを維持する

Cloud Runへ`RAG_BACKEND=chroma`を明示し、local RAG v2のQdrant・PostgreSQL実装と評価証拠はrepositoryで示す。外部DBの継続費と運用を増やさず、現在の公開demoを維持できる。

弱点は、公開画面でQdrant検索とPostgreSQL永続化を実演できないことである。面接では「localで検証済み」「公開環境では費用と運用範囲を理由にbaselineを選択」と分けて説明する。

### B. RAG v2をCloud Runへ公開する

Cloud SQLまたは別のhosted PostgreSQL、Qdrant Cloud、必要なsecret/IAM/network、migration、文書取込、end-to-end smokeを追加する。公開画面で実装を実演できるが、費用、接続管理、データ初期化、障害時の運用が増える。

### 決定

ユーザーが公開画面でRAG v2を評価できることを優先し、Bを採用した。Cloud SQL、Qdrant Cloud、Secret Managerを接続し、migration、取込、代表質問が成功した後にCloud Runへ同じimageを反映する。具体的なresource、費用、CD順序、go-live条件は[`CLOUD_RAG_V2_DEPLOYMENT_PLAN.md`](CLOUD_RAG_V2_DEPLOYMENT_PLAN.md)を正とする。

## 5. 次の最小学習単位

- 学ぶこと: deploy時の設定を暗黙のcode defaultへ依存させない理由
- 変更: Cloud Runの公開backendをQdrantへ固定し、Cloud SQLとSecret Managerを接続する
- 検証: bootstrap Jobによるmigration、取込、整合性、代表質問と、公開UI・feedbackのsmoke
- 完了時に説明できること: 「同じimageでも環境ごとの依存サービスが違うため、CDに設定検証とRAG smokeが必要」

公開代表質問はGemini呼出とログ生成を伴う。実行時は1問に固定し、結果とmodel、commit、時刻を記録する。
