# RAGデータモデル

## 1. 目的

PostgreSQLを正本、Qdrantを再構築可能な検索インデックス、Cloud Storageを原本・画像の保存先として扱うための論理データモデルを定義する。

## 2. データ所有権

| データ | 正本 | 備考 |
|---|---|---|
| 文書原本、ページ画像、図表画像 | Cloud Storage | オブジェクトのSHA-256をPostgreSQLへ記録する |
| 文書、版、チャンク、図表の構造 | PostgreSQL | Qdrantから復元しない |
| 質問、検索、回答、分類、フィードバック | PostgreSQL | 分析と監査の基礎データ |
| dense・sparse・画像ベクトル | Qdrant | PostgreSQLとCloud Storageから再生成可能 |
| 運用ログ | Cloud Logging | 個人情報、APIキー、プロンプト全文を含めない |

Qdrantのpoint IDとPostgreSQLの`content_elements.id`には同じUUIDを使用する。

## 3. 文書管理

### `documents`

文書の論理的な同一性を表す。

| 列 | 内容 |
|---|---|
| `id` | UUID主キー |
| `document_code` | 人が確認できる一意コード |
| `title` | 文書名 |
| `document_type` | 規程、通知、FAQ、マニュアル、様式など |
| `owning_department` | 所管部署。架空データのみ |
| `created_at` / `updated_at` | 監査用時刻 |

### `document_versions`

施行期間と原本を管理する。

| 列 | 内容 |
|---|---|
| `id` | UUID主キー |
| `document_id` | `documents.id`への外部キー |
| `version_label` | 版表示 |
| `effective_from` / `effective_to` | 有効期間。`effective_to`は終了時点を含まない |
| `ingestion_status` | `RECEIVED`、`PROCESSING`、`WAITING_REVIEW`、`INDEXED`、`READY`、`FAILED` |
| `availability_status` | `PUBLISHED`、`WITHDRAWN`。施行期間とは別に管理する |
| `source_format` | Markdown、PDFなど |
| `object_uri` | Cloud Storage上の原本URI |
| `source_sha256` | 原本の同一性確認 |
| `parser_version` | 解析処理の版 |
| `supersedes_version_id` | 同一文書の直接の置換元。存在する場合のみ自己外部キー |
| `active_ingestion_run_id` | 現在公開する抽出世代。検証完了後にだけ切り替える |
| `created_at` / `activated_at` | 登録・有効化時刻 |

同じ文書について有効期間が重ならないことをDB制約で保証する。検索対象は`ingestion_status=READY`かつ`availability_status=PUBLISHED`だけとする。過去版は`effective_to`が過ぎても`PUBLISHED`のまま保持し、基準日filterで検索できる。誤登録、法的理由等で検索対象から除外する場合だけ`WITHDRAWN`にする。質問に基準日がない場合は日本時間の質問受付日を使う。版が重複・欠落する場合は自動選択せず、`VERSION_CONFLICT`として「判断要」にする。

### `content_elements`

検索と引用の最小単位を表す。

| 列 | 内容 |
|---|---|
| `id` | UUID主キー。後述の規則で安定生成する |
| `document_version_id` | `document_versions.id`への外部キー |
| `ingestion_run_id` | 要素を生成した抽出世代 |
| `parent_element_id` | 親要素。図全体と分岐経路などを関連付ける |
| `element_type` | `TEXT`、`FAQ`、`TABLE`、`FLOWCHART`、`FORM`、`TIMELINE`など |
| `heading_path` | 見出し階層のJSON |
| `page_start` / `page_end` | 参照ページ |
| `source_locator` | ページ・要素順・領域を表す安定した位置識別子 |
| `bounding_box` | ページ内座標。存在する場合のみ |
| `content_text` | 正本となる抽出・整形済みテキスト |
| `structured_content` | 表セル、フローのノード・エッジなどのJSON |
| `ocr_confidence` | OCR利用時の信頼度 |
| `content_sha256` | 内容の同一性確認 |
| `ordinal` | 文書内表示順 |
| `extractor_version` / `schema_version` | 再現に必要な抽出器・構造定義の版 |
| `review_status` | `AUTO_ACCEPTED`、`REVIEW_REQUIRED`、`APPROVED`、`CORRECTED`、`REJECTED` |

IDはUUIDv5を使用し、`document_version_id + ingestion_run_id + element_type + normalized_source_locator`から生成する。同じidempotency keyの再試行は既存runを再開するためIDが変わらない。parser、model、schemaを変えて再抽出する場合は新しいrunを作り、旧要素との曖昧なmatchingを行わず、検証後に`active_ingestion_run_id`を一括切替する。旧runの要素・asset・pointは切替完了後にtombstone eventで検索対象から外す。

`normalized_source_locator`は`page/{1-based page}/region/{kind}/{ordinal}`とする。ordinalは左上から下、同じ行は左から右の決定的順序で付ける。bboxはページ左上を原点とする0〜1の正規化座標を小数第4位で丸める。検出順、bbox、要素数が変わる再抽出は新runとなるため、世代間でIDを一致させない。

### `document_relations`

異なる文書を含む改定・補足・解釈関係を明示する。

| 列 | 内容 |
|---|---|
| `id` | UUID主キー |
| `source_version_id` / `target_version_id` | 関係元・先の版ID |
| `relation_type` | `SUPERSEDES`、`AMENDS`、`SUPPLEMENTS`、`INTERPRETS` |
| `effective_from` | 関係が有効になる日 |
| `priority` | 同種の関係が複数ある場合の明示順 |
| `reason` | 管理者が確認できる根拠 |

`SUPERSEDES`はtargetを置換し、`AMENDS`はsourceの変更箇所を優先する。`SUPPLEMENTS`は両方を必要根拠とし、`INTERPRETS`は原規程を置換せず解釈根拠として加える。同じ日・同じpriorityに競合関係がある場合は`VERSION_CONFLICT`とする。

### `visual_assets`

| 列 | 内容 |
|---|---|
| `id` | UUID主キー |
| `content_element_id` | 対応する要素 |
| `asset_type` | ページ画像、図表切り出し、帳票領域など |
| `storage_uri` | Localでは`file://`、Cloud Storageでは`gs://`のURI |
| `mime_type` | MIMEタイプ |
| `sha256` | 画像の同一性確認 |
| `width` / `height` | 画像寸法 |

### `extraction_reviews`

| 列 | 内容 |
|---|---|
| `id` | UUID主キー |
| `content_element_id` | 対象要素 |
| `reviewer` | レビュー主体。個人情報ではなく管理用識別子 |
| `decision` | `APPROVED`、`CORRECTED`、`REJECTED` |
| `before_value` / `after_value` | 修正前後の構造JSON。訂正時だけafterを必須にする |
| `reason` / `reviewed_at` | 判断理由と時刻 |

版を`READY`にできるのは、全必須要素が`AUTO_ACCEPTED`、`APPROVED`、`CORRECTED`のいずれかで、`REJECTED`と`REVIEW_REQUIRED`が0件の場合だけである。

## 4. 取込と検索インデックス

### `ingestion_runs`

| 列 | 内容 |
|---|---|
| `id` | UUID主キー |
| `document_version_id` | 対象版 |
| `status` | `STARTED`、`PARSED`、`WAITING_REVIEW`、`INDEXED`、`VERIFIED`、`FAILED` |
| `source_sha256` | 対象原本 |
| `parser_version` | 解析版 |
| `embedding_profile_id` | 使用したEmbedding設定 |
| `idempotency_key` | 呼出側が指定する一意キー。同一原本・版の二重実行を防ぐ |
| `stage_manifest` | 各段階の入力hash、出力件数、モデル・prompt・schema版 |
| `started_at` / `finished_at` | 処理時間 |
| `error_code` | 失敗分類。秘密や原文を含めない |

### `embedding_profiles`

Embedding比較の条件を固定する。

| 列 | 内容 |
|---|---|
| `id` | UUID主キー |
| `provider` / `model_name` | 提供元とモデル |
| `modality` | text、imageなど |
| `dimensions` | 出力次元 |
| `normalization` | 正規化方式 |
| `query_prefix` / `document_prefix` | 検索用途の入力規則 |
| `prompt_version` | 説明文生成等の版 |

### `embedding_records`

| 列 | 内容 |
|---|---|
| `content_element_id` | PostgreSQLとQdrantの対応ID |
| `embedding_profile_id` | 使用した設定 |
| `collection_name` | Qdrantコレクション |
| `vector_name` | `text_dense`、`image_dense`、`text_sparse`など |
| `indexed_content_sha256` | ベクトル化した入力のハッシュ |
| `status` | `PENDING`、`INDEXED`、`FAILED`、`DELETED` |
| `indexed_at` | 登録時刻 |

ベクトル値そのものはPostgreSQLへ重複保存しない。

### `outbox_events`

PostgreSQL更新とQdrant更新の不整合を回復する。

| 列 | 内容 |
|---|---|
| `id` | UUID主キー |
| `event_type` | `UPSERT_ELEMENT`、`ACTIVATE_GENERATION`、`TOMBSTONE_GENERATION`など |
| `aggregate_id` | 対象ID |
| `payload` | インデックス更新に必要な最小JSON |
| `status` | `PENDING`、`PROCESSING`、`DONE`、`FAILED` |
| `attempt_count` | 試行回数 |
| `available_at` / `processed_at` | 再試行と完了の管理 |

文書データとoutboxイベントを同じPostgreSQLトランザクションで保存し、ワーカーがQdrantへ冪等に反映する。Qdrant更新後に失敗しても、同じpoint IDへのupsertで再実行できる。

次の制約を必須とする。

- `documents.document_code`は一意。
- `document_versions(document_id, version_label)`と`document_versions(source_sha256, version_label)`は一意。
- `content_elements(document_version_id, ingestion_run_id, element_type, source_locator)`は一意。`parent_element_id`は同じ`ingestion_run_id`の要素だけを参照できる。
- `ingestion_runs.idempotency_key`は一意。
- `embedding_records(content_element_id, embedding_profile_id, vector_name)`は一意。
- outboxは`event_type + aggregate_id + payload hash`を冪等キーとして重複処理できる。

## 5. Qdrant

### 5.1 コレクション

Embedding比較ではモデルごとに別コレクションを作る。採用コレクションはaliasで切り替える。

```text
municipal_docs_gemini_embedding_2_v1
municipal_docs_ruri_v3_310m_v1
municipal_docs_active -> 採用コレクション
```

コレクションを直接上書きせず、新規作成、検証、alias切替、旧版保持または削除の順で移行する。

### 5.2 vector

| 名前 | 必須 | 内容 |
|---|---|---|
| `text_dense` | 必須 | 本文、FAQ、図表説明、構造化内容の検索 |
| `text_sparse` | 評価後 | 制度名、条番号、様式名などの字面検索 |
| `image_dense` | 評価後 | 図表画像の検索。改善効果が確認できた場合のみ採用 |

### 5.3 payload

Qdrantには検索とPostgreSQL参照に必要な最小情報だけを持たせる。

```json
{
  "content_element_id": "uuid",
  "document_id": "uuid",
  "document_version_id": "uuid",
  "document_type": "manual",
  "element_type": "flowchart",
  "effective_from": "2026-04-01",
  "effective_to": null,
  "page_start": 4,
  "page_end": 4,
  "content_sha256": "...",
  "publication_state": "QUERYABLE",
  "ingestion_run_id": "uuid"
}
```

本文、回答、質問、フィードバックはQdrantのpayloadへ保存しない。

## 6. 質問・回答・フィードバック

### `rag_requests`

質問処理の追跡単位。

| 列 | 内容 |
|---|---|
| `id` | UUID主キー。correlation IDとして使用 |
| `question_text` | 架空データの質問。実運用では保存・マスキング方針を別途適用 |
| `question_hmac` | 日次鍵付きHMACによる短期重複分析用。親requestと同時削除 |
| `session_hmac` | 質問を発行した匿名sessionの短期識別子 |
| `as_of_date` | 質問で指定された基準日 |
| `requested_at` | 受付時刻 |
| `status` | 成功、検索失敗、生成失敗、分類失敗など |

### `retrieval_results`

1質問につき検索候補ごとに1行を保存する。

| 列 | 内容 |
|---|---|
| `request_id` | 質問ID |
| `content_element_id` | 取得要素 |
| `rank` | 最終順位 |
| `dense_score` / `sparse_score` / `fused_score` / `rerank_score` | 使用した段階だけ保存 |
| `filters` | 適用した検索条件 |
| `collection_name` / `embedding_profile_id` | 再現条件 |
| `selected_for_generation` | LLMコンテキストへ採用したか |

### `generation_results`

| 列 | 内容 |
|---|---|
| `id` | UUID主キー |
| `request_id` | 質問ID |
| `answer_text` | 検証済みclaimsと固定templateからコードで組み立てた表示本文 |
| `answer_type` | 根拠十分、判断要、文書不足 |
| `generation_model` | 回答生成モデル |
| `classifier_model` | 分類モデル |
| `classification_factors` | 検索十分性、個別判断、矛盾、根拠整合性などオンライン分類器の構造化結果 |
| `classifier_fallback_used` | フォールバック有無 |
| `input_tokens` / `output_tokens` | 使用量 |
| `latency_ms` / `estimated_cost` | 性能・費用 |
| `prompt_version` | 再現条件 |

`request_id`は一意とし、1 requestにつき採用されたgeneration resultを1件とする。再試行の個別attemptは別のattempt logへ記録し、採用結果を上書きしない。

### `generation_attempts` / `classification_attempts`

各外部API呼出のretryとfallbackを保存する。両テーブルは`id`、`request_id`、`attempt_no`、`provider`、`model`、`started_at`、`latency_ms`、`input_tokens`、`output_tokens`、`estimated_cost`、`status`、`error_code`、`fallback_from_attempt_id`を持つ。`(request_id, attempt_no)`を各テーブル内で一意とし、全attemptの費用・遅延・error率を集計できるようにする。

回答本文とは別に、回答中の各重要主張と`content_element_id`の対応を保存する。金額、日付、期限、要件、可否に根拠IDがない場合は`根拠十分`として返さない。

### `answer_claims` / `claim_evidence`

`answer_claims`は`id`、`generation_result_id`、`ordinal`、`claim_text`、`evidence_kind`、`validation_status`を持つ。`claim_evidence`は`claim_id`、`content_element_id`、表セル・edge・field等の任意`source_locator`を持つ。`feedback.generation_result_id`とこれらの外部キーは、評価再現性を保つため通常削除せず、親requestの保持期限到達時にまとめて削除する。

### `feedback`

| 列 | 内容 |
|---|---|
| `id` | UUID主キー |
| `request_id` | 対象質問 |
| `generation_result_id` | 対象回答 |
| `rating` | 採用、修正採用、不採用 |
| `comment` | 任意コメント |
| `corrected_answer` | 修正採用時の任意データ |
| `created_at` | 登録時刻 |

`feedback.generation_result_id`を一意とし、1回答につきfeedbackは1件だけupsertする。登録・更新時に、現在のsession HMACと`rag_requests.session_hmac`が一致することを確認する。session HMACを24時間後に削除した後は更新不可とし、feedback本体は親requestの30日保持期限まで残す。履歴を無制限に追加しない。

### `quota_buckets`

公開demoの費用上限を外部API呼出前に予約する。

| 列 | 内容 |
|---|---|
| `bucket_date` / `bucket_type` / `bucket_key` | 日本時間の日付、`QUESTION_GLOBAL`、`QUESTION_SESSION`、`FEEDBACK_GLOBAL`、`FEEDBACK_SESSION`と識別keyの複合主キー |
| `reserved_count` | transaction内で加算する予約数 |
| `limit_count` | 質問はglobal 50・session 5、feedbackはglobal 200・session 10 |
| `disabled` | kill switch。GLOBALだけ使用 |
| `updated_at` | 更新時刻 |

sessionの`bucket_key`には署名cookieの生値を保存せずHMACを使い、24時間後に削除する。予約は`SELECT FOR UPDATE`を使い、上限確認と加算を一つのtransactionで行う。

## 7. 評価

### `evaluation_runs`

評価セット版、文書スナップショット、Qdrantコレクション、Embedding、検索設定、生成・分類モデル、プロンプト版を固定する。

### `evaluation_results`

シナリオID、質問ID、`expected_corpus_answerability`、期待根拠、実取得根拠、期待分類、実分類、内容評価、失敗分類、費用、応答時間を保存する。`expected_corpus_answerability`はgold annotation由来の評価専用値で、`rag_requests`と`generation_results`には保存しない。

同一シナリオの言い換えを学習用と最終確認用へまたがって分割しない。

## 8. 削除・再構築・回復

- 文書版は施行期間終了後も`PUBLISHED`で保持する。誤登録等で検索不能にする場合だけ`WITHDRAWN`へ変更する。
- 検索対象から外す操作はoutboxを通じてQdrantへ反映する。
- Qdrantの全pointはPostgreSQLとCloud Storageから再構築できる。
- 再構築後は、対象件数、ID集合、内容ハッシュ、代表検索を照合する。
- 日次のreconciliationでPostgreSQLにだけ存在する要素、Qdrantの孤立point、hash不一致を検出する。初回取込またはactive抽出世代の不整合は、修復まで版の`ingestion_status`を`READY`にしない。非activeのstaged runだけに不整合がある場合はそのrunを`FAILED`として有効化せず、版と旧active runは`READY`のまま維持する。
- 原本の物理削除は別の保管期限・承認ルールを必要とし、本ポートフォリオの通常処理には含めない。
