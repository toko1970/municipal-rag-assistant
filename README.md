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
        SEARCH -->|検索ログ・図表asset情報| PG
        GEN -->|生成試行・回答結果を記録| PG
        UI -->|feedbackを保存| PG
        SEARCH -. 元画像を取得 .-> GCS
    end

    classDef user fill:#e8f3ff,stroke:#3572a5,color:#16324f
    classDef process fill:#f2edff,stroke:#7656a5,color:#30224a
    classDef store fill:#e9f6ef,stroke:#3b8058,color:#183b27
    class U user
    class UI,INGEST,DOC_EMB,SEARCH,QUERY_EMB,GEN process
    class PG,QD,GCS store
```

図中の番号から、各機能の役割・設計上の工夫・評価結果へ進めます。

| 図の役割 | 説明 |
|---|---|
| 1. UI | [質問・回答・根拠の表示](portfolio/01-ui.md) |
| 2. 文書登録・正本管理・ベクトル化 | [取込、レビュー、PostgreSQLとQdrant](portfolio/02-documents-and-index.md) |
| 3. 根拠検索 | [質問ベクトル化と根拠の取得](portfolio/03-retrieval.md) |
| 4. 回答生成・分類 | [現行経路・評価・公開状態](portfolio/04-answer-generation.md) |
| 5. 実行ログ・feedback管理 | [検索・生成・根拠・feedbackの記録](portfolio/05-logging.md) |

[評価結果と詳しいレポート](eval/reports/README.md) · [技術設計](design/TECHNICAL_DESIGN.md)

## デモで確認できること

[公開デモを開く](https://municipal-rag-assistant-280649014820.asia-northeast1.run.app/)と、質問、回答区分、参照チャンク、根拠本文を確認できます。図表が根拠に含まれる質問では、参照欄に元ページ画像も表示します。Cloud Runはscale-to-zeroのため、初回表示に時間がかかる場合があります。

検索対象はすべて架空の制度文書です。試す質問の例:

| 質問 | 確認するポイント |
|---|---|
| 給与支給日はいつですか？ | 規程本文と該当する根拠箇所 |
| 給与口座変更届が前月15日に間に合わない場合、いつ反映されますか？ | 個別条件に関する回答区分と確認事項 |
| 通勤手当の申請書を受領した後、最初に何を確認しますか？ | フローチャートの回答と元ページ画像 |

質問に対する回答内容は公開中のモデル出力であり、ここでは固定の回答例として保証しません。現行UI・回答経路の説明は[機能ページ](portfolio/README.md)、評価条件と制約は[評価資料の案内](eval/reports/README.md)を参照してください。

## 現行版と評価上の制約

2026-10-25時点の公開Cloud Runは、Qdrantを検索indexとして使う一回生成候補です。回答と分類を一度の生成で出力します。独立分類attempt、claim単位の根拠リンク、決定的な期限計算を備えるローカル既定の`production`経路とは異なります。[公開revisionと導入判断](portfolio/04-answer-generation.md)

導入判断では130ケースの暫定machine scoreと80表現challengeの限定訂正結果を別々に確認しています。一方、candidate sealed holdoutは76/100で事前gate未達のNo-goです。評価セットの違う数値を合算せず、架空データの結果を実務導入効果へ一般化しません。図表sealed holdoutも分類精度の事前閾値未達で不合格です。

## 技術事例: 根拠にない期限日を公開smokeで検出

2026-09-29の公開確認で、文書には「14日以内」とだけある質問に対して、旧回答経路が起算規則を補い、具体的な期限日を断定しました。公開を不合格としてtrafficをrollbackし、promptだけでなく、起算規則が根拠本文に明記されているかをコードで検証する修正を行いました。[公開smoke・rollback・修正記録](design/PUBLIC_RELEASE_RESULT_2026-09-29.md)

この修正は当時の経路に対するものです。現在のCloud Run一回生成候補は決定的期限計算を使わないため、この事例の修正が現在の公開経路にもそのまま適用されるとは主張しません。

## ローカルで起動する

必要なものはPython 3.11、Docker Compose、Gemini APIキーです。通常の起動手順は次のとおりです。

```bash
git clone https://github.com/toko1970/municipal-rag-assistant.git
cd municipal-rag-assistant
python3.11 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements-dev.txt
cp .env.example .env
```

`.env`の`GOOGLE_API_KEY`に自分のAPIキーを設定します。秘密情報を含む`.env`はコミットしないでください。ローカル既定は`ANSWER_GENERATION_FLOW=production`と`LLM_MODEL_NAME=gemini-3.1-flash-lite`です。現在のCloud Runと同じ一回生成候補を試す場合は、`.env`で`ANSWER_GENERATION_FLOW=autoresearch_candidate`を指定します。候補の生成モデルは実装で固定されており、`LLM_MODEL_NAME`では切り替わりません。設定値は起動時に読み込まれるため、変更後はアプリを再起動してください。

PostgreSQLとQdrantを起動し、schema適用と架空文書の初回取込を行ってからUIを起動します。

```bash
docker compose up -d postgres qdrant
python -m scripts.manage_rag_v2 migrate
python -m scripts.manage_rag_v2 ingest
streamlit run app.py
```

ブラウザでStreamlitが表示するURLを開き、たとえば「給与支給日はいつですか？」と質問します。初回取込はEmbedding APIを、質問は外部LLMを呼び出すため、APIキーとprovider利用枠が必要です。図表を追加する場合は、抽出結果を人が確認したレビュー済みJSONを用意し、次のCLIで登録します。

```bash
python -m scripts.manage_rag_v2 ingest-visual \
  --pdf /path/to/fictional-document.pdf \
  --extraction /path/to/reviewed-extraction.json \
  --document-key unique-document-id \
  --document-name '図表の文書名' \
  --reviewed
```

このCLIは登録時に外部Embedding APIを使います。任意PDFのアップロードや抽出結果の承認を行うWeb管理画面はありません。図表機能の範囲は[図表RAGの実装状況](eval/reports/VISUAL_RAG_STATUS.md)に記載しています。

再開時はPostgreSQLとQdrantを起動してから`streamlit run app.py`を実行します。停止は`docker compose down`です。ローカルDBとindexも削除して最初から作り直す場合に限り、`docker compose down -v`を使ってください。この操作はCompose管理下のローカルvolumeを削除します。

### テストとCI

通常のテストとlintは外部API不要です。

```bash
python -m ruff check app.py config.py src scripts tests
python -m pytest -q -m "not integration" tests
```

PostgreSQL/Qdrant統合テストは、使い捨てのCompose projectで実行できます。既存の共有DBやindexへ接続しないでください。

```bash
docker compose -p rag-portfolio-integration up -d postgres qdrant
DATABASE_URL=postgresql+psycopg://rag_app:rag_local_only@localhost:5432/rag_portfolio \
QDRANT_URL=http://localhost:6333 \
python -m scripts.manage_rag_v2 migrate
DATABASE_URL=postgresql+psycopg://rag_app:rag_local_only@localhost:5432/rag_portfolio \
QDRANT_URL=http://localhost:6333 \
python -m pytest -q -m integration tests/integration
docker compose -p rag-portfolio-integration down -v
```

統合テストは固定ベクトルとfakeを使い、Embedding/LLM APIを呼びません。CIでは専用PostgreSQLとQdrant service上でschema migrationと統合テストを実行し、その成功をdeployの依存条件にしています。CIのproduction deployには既存のGitHub Environment承認と`ENABLE_CD`設定も必要です。

## 開発と検証

このリポジトリでは、質問受付・根拠表示、文書取込、PostgreSQLとQdrantの保存、回答・分類、ログ、CI/CDを実装・記録しています。変更は通常テスト、サービス境界の統合テスト、または条件を固定した評価runで確認します。品質評価にはモデル出力の揺らぎや評価規約の限界があるため、採否、実測値、未検証範囲を[評価資料](eval/reports/README.md)に分けて記録しています。評価対象は架空文書であり、実利用者による時短・正答率の比較は実施済みの成果として主張していません。
