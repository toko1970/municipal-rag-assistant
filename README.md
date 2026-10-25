# 自治体向け制度問い合わせ支援RAG

[公開デモ](https://municipal-rag-assistant-280649014820.asia-northeast1.run.app/) · [精度改善の意思決定](eval/reports/ACCURACY_IMPROVEMENT.md) · [機能説明](portfolio/README.md)

自治体の給与事務担当者が、規程・通知・FAQ・業務マニュアルから根拠を探す作業を支援するRAGです。架空の人事・給与文書を検索し、回答、回答区分、根拠本文、図表の元画像を一画面で確認できます。

制度の問い合わせには、文書だけで答えられるもの、個別事実の確認が必要なもの、文書に規則がないものがあります。この違いを`根拠十分`・`判断要`・`文書不足`として示し、断定できない場合には不足情報と確認先を伝えることを目指しています。実在する自治体文書、職員情報、問い合わせ履歴は使用していません。

## 実画面とデモ

**通常回答:** 給与支給日の回答と、開いた根拠本文を同時に確認します。

![通常の給与支給日への根拠十分の回答と、給与制度規程の根拠本文を表示した実UI](portfolio/assets/ui_answer_saved_replay_20261025.png)

**保留回答:** 休職時の支給停止割合を文書から確定できないため、不足する規則と人事給与課への確認を示します。

![休職時の給与停止割合について文書不足と回答し、不足情報・確認先・根拠本文を表示した実UI](portfolio/assets/ui_hold_saved_replay_20261025.png)

撮影日: 2026-10-25。UIはcommit `912f095`の`app.py`を使用し、2026-09-23のFlash-Lite評価で保存したQ011/Q076の実際の応答を再生しました。**現在の公開Flashモデルによる新規生成の確認ではありません。** 元の回答・検索contextは保持し、版情報の未記録項目は補完していません。[再生方法・撮影記録](portfolio/01-ui.md)

[公開デモ](https://municipal-rag-assistant-280649014820.asia-northeast1.run.app/)では新しく質問できます。Cloud Runのscale-to-zeroにより初回表示に時間がかかる場合があります。回答内容は実行時のモデル出力です。

## 改善の過程で判断したこと

最初のText holdoutでは、根拠の検索が100/100でも、生成・分類・表示まで含む成功は83/100でした。そこで、検索後に何が失敗するかを分けて検証しました。

| 判断 | 得られた知見・採否 |
|---|---|
| 期限計算を限定してコード化 | 起算規則がないのに期限日を補う誤答を公開smokeで検出し、rollbackと根拠照合を実施。限定計算は従来経路に保持 |
| 分類規約・claim/facetガードを比較 | 過剰保留や正常回答を止める退行があり、不採用。安全停止の増加を精度向上とは扱わない |
| 一回生成のモデル・promptを比較 | 開発回帰とchallengeで差を確認。両モデルの採点訂正の統一や原票の回収が残る |
| 開発結果と独立した品質受入を分離 | 一回生成候補のfresh holdoutは76/100でNo-goを維持。公開統合の判断を品質合格へ読み替えない |

[改善総括](eval/reports/ACCURACY_IMPROVEMENT.md)に、各段階の課題、仮説、比較条件、採否、現行構成との関係、原記録へのリンクをまとめています。

## 現行構成と評価

公開設定は`ANSWER_GENERATION_FLOW=autoresearch_candidate`、Gemini 3.8 Flashによる一回生成です。回答本文と分類を同時に出し、検索された根拠を表示します。ローカル既定の`production`は従来の生成・独立分類経路であり、両者は別の構成です。公開経路にはclaim単位の根拠対応、独立分類、決定的期限計算、従来Version Resolverはありません。[構成比較・公開履歴・判断の正本](portfolio/04-answer-generation.md)

| 評価 | 結果 | 読み方 |
|---|---|---|
| 130ケース統合回帰 | candidate 129/130、baseline 125/130。改善4・退行0 | 暫定machine composite。改善4件は図表開発ケース。元runner等がなくbaselineの処理経路は未確認 |
| 80表現challenge | 限定訂正後79/80対78/80 | 一回生成prompt同士の比較。40シナリオ単位では改善1・退行1。全件人手再採点ではない |
| candidate fresh holdout | 76/100、総合の事前閾値95%に未達 | No-go。重大な根拠外断定は訂正後0/100で当該gateのみPass |

評価の集合・構成・採点方法が違うため、初回83/100と129/130をつないで汎化精度の改善率にはしません。図表sealed holdoutも分類の事前閾値未達で総合不合格です。実利用者の時間短縮や実務正答率の改善は測定していません。[評価の入口](eval/reports/README.md) · [比較条件と原資料の不足](eval/reports/EVALUATION_EVIDENCE_AUDIT_20261025.md)

## 仕組み

```mermaid
flowchart TD
    DOC["制度文書・レビュー済み図表"] --> INGEST["文書取込CLI"]
    INGEST --> PG["PostgreSQL：文書・版・実行記録"]
    INGEST --> QD["Qdrant：検索index"]
    INGEST --> GCS["GCS：図表ページ画像"]
    UI["Streamlit：質問・回答・根拠表示"] --> SEARCH["Embeddingと根拠検索"]
    SEARCH --> QD
    SEARCH --> GEN["Gemini：回答・分類を一回生成"]
    GCS --> GEN
    GEN --> UI
    SEARCH --> PG
    GEN --> PG
    UI -->|feedback| PG
```

| 機能 | 詳細 |
|---|---|
| 質問・回答・根拠表示 | [UIと実画面](portfolio/01-ui.md) |
| 文書・図表の取込と保存 | [PostgreSQL・Qdrant・画像保存](portfolio/02-documents-and-index.md) |
| 検索 | [質問ベクトル化と根拠の取得](portfolio/03-retrieval.md) |
| 回答・分類 | [現行経路と評価・公開判断](portfolio/04-answer-generation.md) |
| 実行記録とfeedback | [経路ごとの記録粒度](portfolio/05-logging.md) |

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

PostgreSQL/Qdrant統合テストには、DB名・資格情報・volume・ホスト側ポートを分けた専用の[`compose.integration.yaml`](compose.integration.yaml)を使います。通常の`compose.yaml`は5432/6333/6334を固定公開するため、project名を変えるだけではポートを分離できません。

```bash
# このテストで作るproject名を一意にする。使用済みポートなら各RAG_TEST_*_PORTも変更する。
export RAG_TEST_PROJECT=rag-check-20261025
export RAG_TEST_POSTGRES_PORT=15432
export RAG_TEST_QDRANT_PORT=16333
export RAG_TEST_QDRANT_GRPC_PORT=16334
docker compose --env-file /dev/null -f compose.integration.yaml \
  -p "$RAG_TEST_PROJECT" up -d
# 両サービスがhealthyになることを確認してから次へ進む。
docker compose --env-file /dev/null -f compose.integration.yaml \
  -p "$RAG_TEST_PROJECT" ps

# サブシェル内だけで接続先を上書きし、既存.envの共有・cloud接続値を使わない。
(
  export DATABASE_URL="postgresql+psycopg://rag_test:rag_test_only@127.0.0.1:${RAG_TEST_POSTGRES_PORT}/rag_handoff_test"
  export QDRANT_URL="http://127.0.0.1:${RAG_TEST_QDRANT_PORT}"
  export QDRANT_COLLECTION_NAME="${RAG_TEST_PROJECT}_only"
  export QDRANT_API_KEY= GOOGLE_API_KEY= OPENAI_API_KEY= MISTRAL_API_KEY=
  export VISUAL_ASSET_BACKEND=local
  python -m scripts.manage_rag_v2 migrate &&
  python -m pytest -q -m integration tests/integration
)

# 上で作ったテストprojectだけを削除する。
docker compose --env-file /dev/null -f compose.integration.yaml \
  -p "$RAG_TEST_PROJECT" down -v
```

統合テストは固定ベクトルとfakeを使い、Embedding/LLM APIを呼びません。各テストは独立したcollectionを作成して削除します。CIでは専用PostgreSQL/QdrantとTerraform検査の成功を、候補準備の前提にします。

### 保存済み評価の確認と公開smoke

```bash
# 公開aggregateの算術整合のみ。原回答の再採点ではない。
python -m eval.audit_public_evaluation
```

smoke専用コマンドは、schema・indexを変更せず5種類の代表質問を実行し、不完全出力や必要根拠の欠落で非ゼロ終了します。**こちらは外部LLM/Embeddingと監査ログ書込みを伴います。** 回数・費用を確認してから実行してください。

```bash
python -m scripts.manage_rag_v2 smoke \
  --max-cases 5 --max-attempts 5 --max-503-retries 0
```

成功は構造検査の通過であり、意味品質や公開受入の完了ではありません。通常CIはtraffic未切替の候補準備まで、公開は検査したrevisionに結び付けた意味確認・実UI確認と既存Environment承認の後に行います。[公開リリース手順](design/PUBLIC_RELEASE_RUNBOOK.md)

## 制作・評価への関与と詳細資料

制作者による確認として公開記録から追えるのは、分類改善方針の選択と分類境界・期待ラベルの確認、安全性を重視したモデル選定方針、モデル比較の3ケースとchallengeの限定訂正、直接比較を確認した候補統合の判断です。分類失敗の分析では、本人が期待ラベルを承認し、Codexが失敗原因を初回分類した分担も記録されています。各ファイルの執筆分担や基準90件の採点者の本人確認は残っており、確認できた個別作業を全制作工程の担当実績へ広げていません。[確認できた担当範囲と出典](portfolio/01-ui.md#制作者の関与とai支援)

- [精度改善の総括](eval/reports/ACCURACY_IMPROVEMENT.md): 課題から採用・不採用まで。
- [評価比較の条件と再現範囲](eval/reports/EVALUATION_EVIDENCE_AUDIT_20261025.md): 規約・分母・訂正・原資料・不足資料。
- [技術選定](design/TECH_STACK_DECISIONS.md): 実測による比較と設計上の選択を区別。
- [技術設計](design/TECHNICAL_DESIGN.md): 現行実装とProduction Referenceの境界。
- [公開リリース手順](design/PUBLIC_RELEASE_RUNBOOK.md): 候補の検査、意味確認、公開・復旧。
