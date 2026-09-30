# 回答分類セマンティクス改訂計画

- 作成日: 2026-09-30
- 状態: Package 1（Rubric・Schema・既存gold監査）完了、runtime実装前
- 対象: `根拠十分`、`判断要`、`文書不足`の判定責務
- 非対象: 制度所管部署との回答一致の証明、corpus全体に適用可能な規則が存在しないことのオンライン証明

## 1. 目的

現在の5 boolean factorは、文書による支持、人による確認、回答完全性を一つのClassifierで同時に判定する。このため、根拠付き回答へ不要な`判断要`を付けることと、回答本文が確認必要と述べているのに`根拠十分`へすることが同時に起きた。

改訂後は次の三軸を分け、最終ラベルだけをコードで導出する。

| 軸 | 問い | 値の例 |
|---|---|---|
| 取得文書の充足 | 今回取得した文書に質問へ答える規則があるか | `sufficient / insufficient` |
| claim support | 生成claimが取得文書、質問入力、検証済み計算で支持されるか | `fully_supported / unsupported / no_claim` |
| 人による確認 | 文書に判断の土台はあるが、個別事実・裁量・版競合が残るか | `case_fact / policy_judgment / version_conflict` |

Question Contractは質問が求める回答項目と計算入力を記録する。質問内の状況から最終分類を直接決めない。

## 2. ラベル規則

判定はfacet単位の評価を集約して、次の順序で行う。

1. Schema、ID参照、facet完全性が不正なら`PIPELINE_INCONSISTENCY`とし、分類付き回答を表示しない。
2. 今回取得した文書に適用可能な規則が不足するfacetがあれば`文書不足`とする。
3. 文書は十分だがclaimが欠落・不支持なら`GENERATION_INCOMPLETE`とし、分類付き回答を表示しない。
4. 全claimが支持され、個別事実・裁量・版競合が残れば`判断要`とする。
5. 全facetのclaimが支持され、人による確認が残らなければ`根拠十分`とする。

`文書不足`はオンラインでは「今回取得した文書では確認できない」を意味する。corpus全体に規則がないとは表示しない。

ユーザー向け名称を`確認が必要`、`根拠不足`へ変えることは、判定改善と分ける。最初の比較では履歴との対応を保つため内部・評価ラベルを`判断要`、`文書不足`のままにする。候補採用後に表示名だけを変更できる。

## 3. Schemaの修正

### 3.1 Question Contract

対象: [`schemas/question-contract-v1.schema.json`](schemas/question-contract-v1.schema.json)

- `epistemic_status`を削除する。
- `stated_facts`を`input_facts`へ改名する。
- 各入力は`fact_id`、自然文の`text`、関連する`facet_ids`だけを持つ。
- `answer_type`は型別validatorまたは評価集計で使う値だけを残し、定義外は`other`とする。
- Question Contractはfacet完全性と入力参照に使い、ラベルを返さない。

### 3.2 回答出力

対象: [`schemas/answer-output-v3-candidate.schema.json`](schemas/answer-output-v3-candidate.schema.json)

- claimへ`facet_ids`を持たせる。
- 文書引用は`evidence_element_ids`へ保持する。
- 質問由来の入力は`input_fact_ids`で別に参照する。
- 決定的計算は`calculation_ids`で参照する。
- `missing_conditions`は`condition_id`、type、対象facet、説明、根拠IDを持つ。

質問入力を文書根拠として扱わず、次の導出経路を監査可能にする。

```text
question input + document rule + verified calculation -> derived claim
```

### 3.3 分類出力

対象: [`schemas/classification-output-v2-candidate.schema.json`](schemas/classification-output-v2-candidate.schema.json)

各facetについて次を返す。

- `evidence_coverage`: `sufficient / insufficient`
- `claim_support`: `fully_supported / unsupported / no_claim`
- `claim_ids`
- `human_review_requirements`: `case_fact / policy_judgment / version_conflict`
- 各requirementの`condition_ids`
- 判定に使った`evidence_element_ids`
- `confidence`

最終ラベルはSchemaへ含めない。

## 4. 修正する設計資料

| ファイル | 修正内容 |
|---|---|
| [`TARGET_RAG_SPEC.md`](TARGET_RAG_SPEC.md) | 5.4を三軸定義と新しい決定順序へ変更。corpus不存在をオンラインで断定しない点を維持 |
| [`TECHNICAL_DESIGN.md`](TECHNICAL_DESIGN.md) | v2 Schema、構造validator、表示契約、version resolverとの接続を定義 |
| [`QUESTION_CONTRACT_CLASSIFICATION_CANDIDATE.md`](QUESTION_CONTRACT_CLASSIFICATION_CANDIDATE.md) | `epistemic_status`を撤回し、Question Contractをfacetと入力参照へ限定 |
| [`DATA_MODEL.md`](DATA_MODEL.md) | `classification_attempts.factors`のv1/v2 JSON例とprompt/decision versionによる識別を追記 |
| [`../eval/INTERVENTION_ADOPTION_PROTOCOL.md`](../eval/INTERVENTION_ADOPTION_PROTOCOL.md) | 採用候補、対象failure、Gate 1〜4を新しい三軸へ合わせる |

既存holdout、過去の実験資料、過去の結果artifactは変更しない。旧定義で実行した事実を保持する。

## 5. 修正するアプリケーションコード

### 5.1 [`src/answering.py`](../src/answering.py)

- v1 dataclass/parser/decisionを互換性のため残す。
- v2用のfacet assessment dataclassとparserを追加する。
- `derive_label_v2`を追加し、第2節の決定表だけでラベルを導出する。
- Schema違反、未知facet、未知claim、取得外evidenceを安全側で拒否する。
- `GENERATION_INCOMPLETE`を`文書不足`へ混ぜない。
- `判断要`では完全支持されたclaimだけを表示する。

### 5.2 [`src/query_service.py`](../src/query_service.py)

- Question Contract、answer v3、classification v2のprompt builderとversion定数を追加する。
- v1/v2をdependency injectionで切り替える。
- Question Contract生成と検索を並列化できる境界を設ける。
- Resolverは`version_conflict`を返す現行契約を維持し、v2の`human_review_requirements`だけを補正する。
- request logにcontract、facet assessment、decision versionを保存する。

### 5.3 [`src/rag_v2.py`](../src/rag_v2.py)と[`config.py`](../config.py)

- `CLASSIFICATION_CONTRACT_VERSION=v1|v2`を追加する。
- 初期値は`v1`とし、評価gate通過前に公開経路を切り替えない。
- v2選択時だけ新Schemaとpromptを組み立てる。

### 5.4 永続化

`classification_attempts.factors`はJSONB、`derived_label`は文字列なのでDB migrationは不要である。prompt versionとdecision versionでv1/v2を区別する。

Question Contract自体を恒久保存する場合は、既存`generation_attempts.response_data`へ混ぜず、新しいattempt種別または専用tableを別Work Packageで検討する。最小実装では評価artifactと構造化ログに保存する。

## 6. 修正するテスト

### 6.1 Schema・構造validator

新規: `tests/test_classification_contract_v2.py`

- Contractのfacet IDとinput fact参照
- claimからfacet、input、calculation、evidenceへの参照
- 全facetが一度ずつ評価されること
- 取得外evidence、未知claim、facet欠落の拒否
- 未定義`answer_type`の拒否と`other`の受理

### 6.2 決定表

更新: [`tests/test_answering.py`](../tests/test_answering.py)

最低限、次の組合せを固定する。

| evidence | claim | human review | 期待結果 |
|---|---|---|---|
| sufficient | fully supported | none | 根拠十分 |
| sufficient | fully supported | case fact | 判断要 |
| sufficient | fully supported | policy judgment | 判断要 |
| sufficient | fully supported | version conflict | 判断要 |
| insufficient | 任意 | 任意 | 文書不足 |
| sufficient | no claim | none | GENERATION_INCOMPLETE |
| sufficient | unsupported | 任意 | GENERATION_INCOMPLETE |

### 6.3 Query flow

更新: [`tests/test_query_service.py`](../tests/test_query_service.py)、[`tests/test_classification_prompt_experiment.py`](../tests/test_classification_prompt_experiment.py)

- v1が既定のまま動くこと
- flag=v2で新Schemaとpromptを使うこと
- labelをLLM出力から受け取らないこと
- v2 factorがJSONBログへ保存されること
- version resolverが他のfacet判定を変更しないこと
- Contract/classifier失敗時に分類付き回答を出さないこと

### 6.4 composition root・保存

更新: `tests/test_rag_v2_query_flow.py`、`tests/integration/test_rag_v2_storage.py`

- `src/rag_v2.py`のv1/v2組立
- prompt/decision versionの保存
- 既存DB schemaでv2 factor JSONを保存・読取可能なこと

## 7. 評価データの扱い

Rubric本体は[`CLASSIFICATION_RUBRIC_V2.md`](CLASSIFICATION_RUBRIC_V2.md)、開封済み初回holdout 50 scenarioへの適用結果は[`../eval/CLASSIFICATION_RUBRIC_V2_AUDIT.md`](../eval/CLASSIFICATION_RUBRIC_V2_AUDIT.md)を参照する。監査では旧goldの期待ラベル変更は0件だった。既存goldそのものは書き換えていない。

過去goldやsealed artifactを新定義へ合わせて書き換えない。次のdevelopment fixtureを新規作成する。

```text
eval/classification_contract_v2_development_cases.json
```

初回holdoutの開封済み失敗をmechanism testとして再利用する。

| case | v2で確認すること |
|---|---|
| TH022 2表現 | 全facet支持、human reviewなし、根拠十分 |
| TH034 2表現 | 版ごとの金額claim支持、根拠十分 |
| TH037 | 文書規則と入力から計算可能、根拠十分 |
| TH041 | 金額・期限が完全、根拠十分 |
| TH047 2表現 | 予約日基準で一意、根拠十分 |
| TH025 2表現 | claimは支持、施設コード確認が残り判断要 |
| TH031 | claimは支持、受給歴照合が残り判断要 |
| TH011 | 文書は十分だが期限facet欠落、GENERATION_INCOMPLETE |
| TH003 / TH012 / TH013 | 取得根拠に適用規則がなく文書不足 |

gold correctionとcandidate改善を分けるため、各caseに`annotation_basis`と旧期待値を残す。

## 8. 検証の順序

### Gate A: 外部APIなし

1. 3 SchemaをDraft 2020-12で検証する。
2. 構造validatorと決定表のunit testを実行する。
3. 保存済みの質問、根拠、Generator出力へ手作業のv2 assessment fixtureを適用する。
4. TH011を改善件数へ数えず、生成不足として分離できることを確認する。

停止条件: 危険側TH025・TH031を`根拠十分`にする組合せが一つでもあればAPI検証へ進まない。

### Gate B: 既知ケースの限定API比較

- 開封済み分類不一致12件とcontrol 6件を固定する。
- B1でQuestion Contractだけを18件実行し、人手固定した期待facetと比較する。最大18 logical external calls、retry 0、費用上限US$0.05とする。
- B1通過後のB2では、review済みの固定Question Contractを両候補へ渡し、baseline v1とcandidate v2を同時期にpaired実行する。最大36 logical external calls、retry 0、費用上限US$0.10とする。
- B1とB2を一括実行せず、B1不合格時はB2へ進まない。
- provider errorは精度不正解と分けてfail-fastする。

合格条件:

- 過剰保留9件で正味改善
- TH025・TH031の危険側3表現をすべて維持
- TH011を総合成功へ誤算入しない
- controlの危険な新規退行0

### Gate C: 未知challenge

- 実装結果を見る前に24 scenarioを固定する。
- target 12、真の判断要6、文書不足3、通常control 3とする。
- targetでbaseline比3件以上改善し、危険な新規退行0件を必須とする。
- 重要8 scenarioへ未知paraphraseを追加する。

### Gate D: 代表回帰

Gate C通過時だけ130問paired回帰を行う。

- composite success
- 分類accuracy、macro F1、class別recall
- 過剰保留件数
- 危険な断定件数
- 文書不足、回答生成不足、provider errorの別集計
- 改善・退行の質問ID
- call、token、費用、p50/p95 latency

候補固定後のfresh sealed holdout開封は別承認とする。

## 9. 実装Work Package

### WP1: 契約とローカル判定

対象: 設計資料、3 Schema、`src/answering.py`、構造validator、unit test。

完了条件: APIなしで決定表と既知case fixtureがすべて通る。

### WP2: candidate経路

対象: `src/query_service.py`、`src/rag_v2.py`、`config.py`、logging、query flow test。

完了条件: feature flag下でv2が動き、既定v1に退行がない。

### WP3: 限定API mechanism test

対象: 18ケースのpaired runner、manifest、結果資料。

完了条件: Gate Bを判定し、不合格なら130問を実行せず終了する。

### WP4: 一般化評価

対象: 未知challenge、通過時だけ130問回帰、費用・再現性評価。

完了条件: 採用プロトコルのGate C・Dを判定する。公開切替とsealed holdoutは含めない。

## 10. 今回変更しないもの

- 検索、Embedding、Qdrantの設定
- 既存version resolverの判定原理
- 過去のholdout goldと結果artifact
- 本番公開経路の既定値
- PostgreSQL schema
- 表示ラベルの日本語名称
