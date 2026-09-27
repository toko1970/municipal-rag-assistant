# 作業再開checkpoint

- 記録日: 2026-09-27
- 状態: Work Package Aのローカル基盤、文書取込境界、構造化回答・分類・ログの最小縦断経路を実装済み
- Git: text・visual holdoutは`SEALED`で、両方のsealed本体は`.gitignore`対象

## 1. 完了したこと

- RAGの最終仕様をユーザー承認済みにした。
- 技術設計、データモデル、実装計画、テスト戦略、JSON Schemaを作成した。
- PostgreSQL、Qdrant、Cloud Storageの責務と同期・回復手順を定義した。
- PDF・図表の対象、抽出世代、文書版、評価境界を定義した。
- Generatorは根拠付きclaimsだけを返し、classifier factorsからコードが最終ラベルと表示templateを決める設計にした。
- `corpus_answerability`をオンライン分類・ログから除外し、評価専用の`expected_corpus_answerability`へ移した。
- 学習を目的とした進め方とCodex利用枠の運用ルールをAGENTS.mdへ追加した。
- 独立仕様レビューでP0/P1の重大な曖昧さなし、反対レビューでhigh-impact objectionなしを確認した。
- 仕様baselineを`1e3ad09`としてcommitした。
- text sealed holdoutを50シナリオ・100表現、別文書family、scenario単位集計として計画へ追加した。
- Evidence-first、Quality streak、Phase 0 contract conformanceのadaptationを`LOOPS.md`へ保存した。
- 申請処理フローチャートのPDF、ページ画像、gold annotation、development manifestを作成した。
- JSON Schemaとsemantic validatorを実装し、Schema違反、未知node参照、逆転bbox、hash不一致、family leakageを拒否できるようにした。
- Quality streakの6 scenarioが連続成功し、全test 44件とlintが成功した。
- 支給可否判断フローのPDF、ページ画像、gold annotationを追加し、development manifestを2 fixture構成にした。
- manifest生成を共通化し、どちらのgeneratorを再実行しても他方のentryを失わないようにした。
- flowchart共通検査へstart/end、到達可能性、decisionの分岐条件を追加した。正当な差戻しを扱うため循環自体は禁止していない。
- Quality streakの10 scenarioが連続成功し、全test 48件とlintが成功した。
- 扶養手当の期限タイムラインPDF、ページ画像、gold annotationを追加し、development manifestを3 fixture構成にした。
- timeline共通検査へevent 2件以上とevent ID一意性を追加した。相対期限を誤って日付parseせず、配列順を時系列順として保持する。
- Quality streakの13 scenarioが連続成功し、全test 51件とlintが成功した。
- 支給額・区分表、申請書記入例、改定前後比較のPDF、ページ画像、gold annotationを追加し、development manifestを6 fixture構成にした。
- table共通検査へcell存在、行列範囲、row/column span展開後の重複検査を追加した。
- form共通検査へfield存在とfield ID一意性を追加した。同じlabelの複数欄は実務上あり得るため禁止していない。
- Quality streakの21 scenarioが連続成功し、全test 59件とlintが成功した。
- 5つのgenerator再実行後も、PDF、画像、gold、manifestの19 artifactが同一SHA-256を維持した。
- visual sealed holdoutの20 scenario IDと構成を公開blueprintで固定した。
- holdout PDFとgoldをGit対象外にし、候補実装、予測、開封の順序をpublic manifestで検査するcustody protocolを追加した。
- public manifest検証、全test 65件、lintが成功した。通常検証ではsealed contentを開いていない。
- 6 fixtureへ5件ずつ、合計30件のvisual development scenarioを作成した。
- 期待分類はgrounded 18件、needs_judgment 6件、insufficient_documents 6件とし、gold elementへの論理参照をvalidatorで検査する。
- 30 scenarioのvalidator、全test 72件、lintが成功した。内容レビュー前のため`pending_user_review`としている。
- ユーザー確認を受け、30 scenarioを`user_approved`へ固定した。
- sealed holdoutの内容を実装タスクへ漏らさないため、別タスク用custodian handoffを追加した。
- 別のcustodianタスクでholdout PDF 6件、extraction gold 6件、scenario 20件を作成した。
- visual holdoutは配分一致、SHA-256一致、developmentとのfamily重複0件、72 test、lintを確認して`SEALED`へ遷移した。
- 実装タスクでは公開manifestだけを検証し、`sealed_content_opened=False`を維持した。
- 制限解除後に公開artifactを再検証し、72 test、lint、diff検査が成功した。
- Phase 0 contract conformance ledgerを作成し、proved 8件、weak 1件、unimplemented 6件、not applicable 1件、矛盾0件と判定した。Phase 4対象の抽出精度evaluatorは引継ぎ項目とした。
- text sealed holdoutの50 scenario ID、100表現、分類30/10/10、難度15/15/10/10をblueprintで固定した。
- text holdoutの公開manifest Schema、非公開gold Schema、状態遷移、hash、family分離、公開質問の2表現pairを検査するvalidatorとtestを追加した。
- 既存500問のmanifestへdevelopment split、5文書family、文書・質問・row Schemaのhashを追加し、各CSV行をJSON Schemaでも検査するようにした。
- source Markdownも候補実装固定まで非公開にするcustody方針と、別タスク用handoffを追加した。
- custodian loopで架空Markdown 10文書・5 family、50 scenario・100表現を作成し、text holdoutを`SEALED`へ進めた。
- text holdoutは分類30/10/10、難度15/15/10/10、Quality streak 50件連続成功、修復0回、hash全件一致を確認した。
- 実装タスクでは公開manifestだけを再検証し、`sealed_content_opened=False`、全test 82件、lint、diff検査の成功を確認した。
- Phase 0 ledgerのP0-03とP0-13を`proved`へ更新した。
- native text PDF、ページ画像、期待全文・重要値・page・bboxを持つgold、manifest、専用Schema、validator、testを追加した。
- PyMuPDF 1.28.2でtext layer、全文、重要値、text block位置を検証し、画像の文字化け・切れ・重なりがないことを目視確認した。
- 4 artifactを再生成して全SHA-256が一致し、対象test 5件、全test 87件、lint、diff検査が成功した。
- 全文比較はparserが加える空行と行端空白だけを正規化し、文字列と読み順は完全一致を要求する。
- Phase 0 ledgerのP0-08を`proved`へ更新した。
- [`SCAN_PDF_FIXTURE_PLAN.md`](SCAN_PDF_FIXTURE_PLAN.md)へ、日本語scan PDF fixtureの入力、gold、validator、Phase 4との境界、受入条件を記録した。
- 日本語scan PDF、300 dpi source PNG、再描画画像、期待全文・重要値・region bboxを持つgold、専用manifest、Schema、validator、testを追加した。
- PyMuPDFでtext layerが空、埋め込み画像1件、A4、回転0度を確認し、scanを`review_required=true`へ固定した。
- 正解OCR候補を受理し、重要値の改変とその他の本文差分を拒否する比較規則を実装した。
- 5 artifactを再生成して全SHA-256が一致し、対象test 6件、全test 93件、lint、diff検査が成功した。
- Phase 0 ledgerのP0-09を`proved`へ更新した。
- PDFの`/Rotate`を90/180/270度へ設定した3 fixture、raw表示画像、正規化画像、gold、manifest、専用Schema、validator、testを追加した。
- 0度の正立scanと非0度3種類を揃え、正規化画像がすべて正立referenceと同一SHA-256へ戻ることを確認した。
- 回転角、media box、表示寸法、text layerなし、埋め込み画像、正立regionを検査し、13 artifactの再生成hash一致、対象test 6件、全test 99件、lint、diff検査が成功した。
- Phase 0 ledgerのP0-10を`proved`へ更新した。
- clean sourceを白へ75%合成した低コントラストscan、gold、manifest、専用Schema、validator、testを追加した。
- fixture用dynamic rangeは56、clean referenceは224で、低品質条件の60以下を満たすことを確認した。この値はproductionの自動判定閾値には使用しない。
- 抽出結果`REVIEW_REQUIRED`、文書版`WAITING_REVIEW`、理由`LOW_CONTRAST`、自動`READY`不可を別項目として固定した。
- `READY`への改変、理由欠落、測定値改変、逆転bboxを拒否し、5 artifactの再生成hash一致、対象test 7件、全test 106件、lint、diff検査が成功した。
- Phase 0 ledgerのP0-11を`proved`へ更新した。
- Docker ComposeへPostgreSQL 18.6とQdrant 1.19.1を追加し、Alembic初期migration、health check、管理CLIを実装した。
- PostgreSQLを文書・版・content element・利用ログの正本、Qdrantを安定UUIDで再構築可能な検索indexとするadapterを実装した。
- 同一Markdownの2回取込で文書・要素が増えず、Qdrantのpoint IDがcontent element IDと一致することを実DB統合testで確認した。
- 回答generatorのclaim、根拠ID、不足条件を検証し、classifierの5要因からコードで「根拠十分／判断要／文書不足」を決める純粋ロジックを実装した。
- request、retrieval、generation attempt、classification attempt、generation result、claim、evidence、feedbackを一つのrequest IDから追跡できる保存経路を実装した。
- 分類器がclaim単位の支持判定を返さない現行契約では、`answer_fully_supported=false`のときclaimを推測表示しない安全側の規則をtestへ固定した。
- 外部APIなしの全test 126件、実PostgreSQL・Qdrant統合test 1件、Ruff、diff whitespace検査が成功した。
- プロジェクトの`.codex/config.toml`へ`workspace-write`、network許可、Auto-reviewの中間設定を追加した。新しいchatから適用する。
- Gemini native JSON Schemaを使う構造化providerを実装し、raw responseからmodel・token・request IDを記録するようにした。
- 標準JSON Schemaの`const`がGemini schema方言で空objectになる実失敗を検出し、adapter内で同値の`enum + type`へ変換した。元schemaは変更していない。
- `RAG_BACKEND=chroma|qdrant`の切替を実装し、既存UI操作のまま新経路を選べるようにした。評価用の依存注入経路はChroma baseline互換を維持した。
- 実Markdown 5文書・86要素をPostgreSQLとQdrantへ投入した。最初の実質問はschema方言差により`GENERATION_FAILED`として記録され、修正後の同一質問は`根拠十分`で成功した。
- 成功request `0c9f6daf-b31d-4ae2-b3ce-ae14cf1ede5a`は、検索5件、表示claim 2件、根拠link 2件をSQL一つで結合確認した。
- 実動時の生成はGemini 2.5 Flashで1,725 tokens、分類はGemini 3.1 Flash Liteで1,424 tokensだった。
- 外部APIなしの全test 133件、実PostgreSQL・Qdrant統合test 1件、Ruffが成功した。
- Streamlitの質問入力、回答、参照展開、feedback送信をAppTestで検証した。UI testではLLMをfake化し、画面配線だけを独立確認した。
- PostgreSQLの`INDEXED` IDとQdrant point IDを全件照合する`reconcile` CLIを追加した。
- Qdrant collectionを削除し、5文書・86要素を同じEmbeddingで再構築した。再構築前後とも欠落0件、余分0件だった。
- 同じGemini Embedding、chunk、top-k、実用質問16件でChromaとQdrantを比較し、Hit@1は11/16、Hit@3・Hit@5は16/16で一致した。取得文書・見出しの順位差も0件だった。
- ベクトルDB移行による精度向上は主張せず、Qdrantの採用理由を責務分離、安定ID、filter・検索実験の拡張性として評価記録へ残した。
- 外部APIなしの全test 136件、実PostgreSQL・Qdrant統合test 1件、Ruffが成功した。
- 500問のうち各scenarioのformal表現100件を使い、同一query vectorでChromaとQdrantを比較した。文書不足12件を除く88件で、両backendは全指標・全質問が一致した。
- Qdrantの全必要文書Hit@5は85/88、全根拠見出しHit@5は74/88だった。Top-5失敗14件を分類し、文書不足3件、文書は揃うが根拠節が不足するもの11件と確認した。
- 100問を個別にEmbeddingしてFree tierの1分当たりrequest上限へ達した失敗を受け、query Embeddingを1 batch requestへまとめ、条件付きcacheで再利用する比較runnerへ修正した。
- 検索失敗を再現可能に分類するanalyzer、raw result、集計、代表例、次のEmbedding比較判断を`eval/LARGE_FORMAL_QDRANT_BASELINE.md`へ記録した。
- cache再利用時はEmbedding API呼出0回で同じraw resultをbyte単位で再生成した。外部APIなしの全test 143件、実PostgreSQL・Qdrant統合test 1件、Ruff、diff検査が成功した。
- Embedding profileごとに入力prefix、次元、provider、分離collectionを固定する比較runnerを実装した。本番用Qdrant collectionは変更していない。
- formal 100件で`gemini-embedding-2` 768次元と`ruri-v3-310m`を現行`gemini-embedding-001`へ比較した。根拠見出しHit@5は順に72/88、74/88、74/88、最初の正解根拠MRRは0.847、0.815、0.861だった。
- Gemini 2は根拠Hit@5を3件改善・5件退行、Ruriは4件改善・4件退行した。安定した改善がないため現行Embeddingを維持する判断を`eval/EMBEDDING_MODEL_EVALUATION.md`へ記録した。
- Gemini 2のbatchはAPI call数ではなく入力100件でFree tier毎分上限へ達することを実測した。文書・質問cacheを分け、完了済み86文書を再送せず別枠で100質問を完了した。
- Ruriはoptional依存へ分離し、ローカルApple MPSのwarm実測で86要素4.38秒、100質問1.34秒だった。約1.27GBのmodel取得とcold startはこの時間に含まない。
- Ruriのcache再利用はprovider推論0回でraw resultをbyte単位で再生成した。外部APIなしの全test 147件、実PostgreSQL・Qdrant統合test 1件、Ruff、diff検査が成功した。
- 現行Embedding、Qdrant、formal 100件を固定し、文書名と見出し階層だけを文書Embedding入力へ加えるcontextual headingを評価した。
- 根拠見出しHit@3は63/88から73/88、Hit@5は74/88から78/88、最初の正解根拠MRRは0.861から0.904へ改善した。Top-5のsection missingは11件から7件へ減った。
- 根拠Hit@5は6件改善・2件退行した。Q351は必要文書がTop-5から外れ、Q446は複数根拠のうち提出期限が押し出されたため、回答品質比較前にはactive collectionへ切り替えない。
- 初回の文書86要素Embeddingは1 API call、2.32秒だった。cache再実行はAPI呼出0回でraw resultがbyte単位で一致した。
- 外部APIなしの全test 149件、実PostgreSQL・Qdrant統合test 1件、Ruff、diff検査が成功した。
- 根拠見出しHit@5が変化した8問を、同一query vector・generator・classifier・top-kでbaselineとcontextual headingへ通す回答回帰評価を実施した。
- contextual headingは期待ラベル一致を4/8から7/8、必須内容一致を4/8から6/8、全件確認の完全回答を3/8から6/8へ改善した。Q151は受付を省略して部分回答、Q446は提出期限がTop-5外となり表示失敗した。
- Q381 baselineは別手続の取得文へ忠実でも質問には不適合だった。現行classifierのgrounding判定だけでは質問適合性を保証できないことを失敗例として記録した。
- Q141 baselineとQ446 candidateの生成・分類間の表示不整合を、成功まで再試行せず`分類・表示失敗`として保存した。Q446回帰が残るためactive collectionへの切替は保留した。
- 回帰評価追加後、外部APIなしの全test 153件、実PostgreSQL・Qdrant統合test 1件、Ruff、diff検査が成功した。
- contextual headingのTop-5〜10をformal 100問で比較した。Top-8はQ351とQ446の直接根拠を回復できる最小値で、全根拠見出しHitを78/88から82/88へ改善した。
- Top-8の平均context文字数はTop-5比1.63倍だった。回答評価はQ061・Q141の正解維持まで確認したが、Gemini 2.5 FlashのFree tier日次20 request上限でQ151開始時に停止した。
- Top-8回答runnerは正常結果と品質上の失敗を固定し、429 quota errorだけをreset後に再実行する。途中結果と再開コマンドは`eval/CONTEXTUAL_HEADING_TOP_K_EVALUATION.md`へ保存した。
- Top-k比較と再開制御の追加後、外部APIなしの全test 156件、Ruff、diff検査が成功した。
- Gemini 2.5 Flashの日次20 request制限を受け、条件を混在させずGemini 3.1 Flash-Liteでcontextual heading Top-5・Top-8を各8問再実行した。全16件が生成・分類エラーなしで完了した。
- 3.1のTop-5からTop-8で、期待ラベル一致は7/8を維持し、必須内容一致は6/8から8/8、全件確認の完全回答は6/8から7/8へ改善した。Q446は完全回答へ回復し、Q301は内容が正しいまま`判断要`から`根拠十分`へ分類退行した。
- Top-8のGenerator入力tokenはTop-5比57.8%、paid list price概算は36.0%増えた。8問合計のGenerator概算は$0.00683で、増分とQ446回復を踏まえTop-8をproduction統合候補にした。
- 既定Generatorを`gemini-3.1-flash-lite`へ変更し、Generator・Classifierのモデル名を環境変数で上書き可能にした。raw結果と全件レビューは`eval/GEMINI_3_1_TOP_K_ANSWER_EVALUATION.md`へ記録した。
- contextual headingの共通vector表現を`src/embedding_representation.py`へ移し、評価とproduction ingestionが同じ関数を使用するようにした。原文はPostgreSQLとQdrant payloadへそのまま保存する。
- production取込で`RETRIEVAL_DOCUMENT`を明示し、Embedding profileを`gemini:gemini-embedding-001:contextual-heading-document-v1`へ更新した。検索件数はTop-8へ変更した。
- 旧`municipality_rag_docs_v2`を保持し、新`municipality_rag_docs_v2_contextual_heading_v1`へ5文書・86 pointを構築した。PostgreSQLとのmissing 0・unexpected 0、保存本文へのEmbedding prefix混入0を確認した。
- production composition rootからQ446相当を質問し、request `99fdf2e4-36f9-41af-a7ba-5941f14029de`で根拠十分の完全回答を得た。SQLでretrieval 8、generation 1、classification 1、visible claim 4、evidence link 7を確認した。
- `RAG_BACKEND=qdrant`のStreamlit実UI経路で同じ質問を実行し、request `5c3aeecd-3c69-48e0-8805-07cc36cd6734`で根拠十分、参照8件、UI exception 0を確認した。「採用した」feedback 1件がPostgreSQLへ保存されたこともSQLで確認した。
- production統合後、外部APIなしの全test 157件、実PostgreSQL・Qdrant統合test 1件、Ruff、diff検査が成功した。

## 2. 未完了・次回反映すること

- 既存100シナリオ・500問を新しい論理locatorへ移行する処理は、Phase 2以降のingestion実装で具体化する。
- Cloud SQL、GCS、Qdrant Cloud、Geminiのread-only調査は完了した。Gemini最小接続は成功し、次はGCS、Qdrant Cloud、Cloud SQLの順に進める。
- 30 scenarioを実行する評価harnessは、Phase 4・5の取込・回答実装と合わせて追加する。
- Phase 0の全要求が揃った段階でcontract conformance loopを再実行する。
- 短期集中期間の実行順序は[`PORTFOLIO_DELIVERY_PLAN.md`](PORTFOLIO_DELIVERY_PLAN.md)を正とする。Cloud SQL・Qdrant Cloudの実接続は対応コード完成後へ移し、HA・完全な障害回復・運用自動化はProduction Backlogとして説明する。
- Streamlit画面の質問・引用8件・feedback保存は`RAG_BACKEND=qdrant`の実接続smokeで確認済み。既定backendもQdrantへ変更した。
- Streamlitの実ブラウザから実Gemini・PostgreSQLへ接続する最終smoke testは未実施である。画面配線とcore実動は別々に検証済み。
- 次はCloud Runへ反映する構成差と外部Qdrant・PostgreSQL接続先を確認する。ローカル実装済みとクラウド未接続をREADME・面接説明で区別する。

## 3. 次回最初に行うこと

1. Codexの5時間枠・週間枠を確認する。
2. `git status`と本checkpointを確認する。
3. [`PHASE0_CONFORMANCE.md`](PHASE0_CONFORMANCE.md)の未実装とweakを確認する。
4. [`GCS_CONNECTION_SPIKE_RUNBOOK.md`](GCS_CONNECTION_SPIKE_RUNBOOK.md)に従い、bucket名の不在、runtime service account impersonation、当日価格をread-onlyで確認する。
5. 固定bucket、IAM、1 object round trip、費用上限、cleanupを提示し、resource変更の明示的な承認を得る。
6. [`PORTFOLIO_DELIVERY_PLAN.md`](PORTFOLIO_DELIVERY_PLAN.md)のWork Package AをEvidence-first feature loop、最大3 roundで開始する。
7. 2026-09-27のGCS実行ではruntime identityのupload・metadata取得まで一度成功したが、Token Creatorの一時bindingが2分以内に安定して反映されないrunもあった。全runでbucket不在と一時binding削除を確認し、追加IAM変更を止めてWork Package Aを先行する。

## 4. 完了したvisual fixture学習単位

### 学習目標

- fixtureとgold annotationの違い
- PDFの正規化bbox
- flow node・edgeの構造
- JSON Schema validationとsemantic validationの違い
- development / holdout間のdocument-family leakage

### 作成済み

```text
eval/visual_fixtures/
├── documents/flowchart_dev_001.pdf
├── documents/flowchart_dev_002.pdf
├── documents/timeline_dev_001.pdf
├── documents/table_dev_001.pdf
├── documents/form_dev_001.pdf
├── documents/table_dev_002.pdf
├── images/flowchart_dev_001_page_001.png
├── images/flowchart_dev_002_page_001.png
├── images/timeline_dev_001_page_001.png
├── images/table_dev_001_page_001.png
├── images/form_dev_001_page_001.png
├── images/table_dev_002_page_001.png
├── gold/flowchart_dev_001.json
├── gold/flowchart_dev_002.json
├── gold/timeline_dev_001.json
├── gold/table_dev_001.json
├── gold/form_dev_001.json
├── gold/table_dev_002.json
├── manifests/development_manifest.json
└── README.md

eval/validate_visual_fixture.py
tests/test_visual_fixture_validation.py
```

### 検証結果

- PDFをPNGへ描画し、文字化け、重なり、切れがないことを目視確認済み。
- gold JSONはvisual extraction Schemaを通過。
- node ID、edge参照、bboxをsemantic validatorで検証済み。
- Schema違反、不正edge、逆転bbox、hash不一致、family leakageをtestで拒否。
- PDF、画像、gold、SchemaのSHA-256をmanifestへ記録し、再生成後も同一hashであることを確認。
- `.venv/bin/python -m pytest -q tests`: 44 passed。
- `.venv/bin/python -m ruff check .`: success。
- 2件目追加後、fixture検証10件、全test 48件が成功。
- 2つのgenerator再実行後も、PDF、画像、gold、manifestの7 artifactが同一SHA-256を維持。
- timeline追加後、fixture検証13件、全test 51件が成功。
- 3つのgenerator再実行後も、PDF、画像、gold、manifestの10 artifactが同一SHA-256を維持。
- 必須6種類のdevelopment fixture追加後、fixture検証21件、全test 59件が成功。
- 全generator再実行後も、PDF、画像、gold、manifestの19 artifactが同一SHA-256を維持。

## 5. 評価セットの目標構成

```text
評価基盤
├── テキスト
│   ├── 既存100シナリオ・500表現: development / regression
│   └── 新規・別文書family: sealed holdout 50シナリオ・100表現
└── PDF・図表
    ├── 30シナリオ: development
    └── 20シナリオ: sealed holdout
```

## 6. 確認済み検証

- 3つのJSON SchemaはJSONとしてparse可能。
- design配下のMarkdownリンクに欠落なし。
- Markdown code fenceと行末空白に問題なし。
- `.agent-reviews/redteam.md`は`.gitignore`対象。

## 7. 再開時の確認コマンド

```bash
git status --short
git diff --check
.venv/bin/python -m eval.validate_visual_holdout_protocol eval/visual_holdout/public_manifest.json
.venv/bin/python -m eval.validate_text_holdout_protocol eval/text_holdout/public_manifest.json
.venv/bin/python -m eval.validate_native_text_fixture eval/text_pdf_fixtures/manifests/development_manifest.json
.venv/bin/python -m pytest -q tests
.venv/bin/python -m ruff check .
find design -maxdepth 3 -type f -print | sort
python3 -m json.tool design/schemas/visual-extraction-v1.schema.json >/dev/null
python3 -m json.tool design/schemas/answer-output-v1.schema.json >/dev/null
python3 -m json.tool design/schemas/classification-output-v1.schema.json >/dev/null
python3 -m json.tool design/schemas/text-holdout-public-manifest-v1.schema.json >/dev/null
python3 -m json.tool design/schemas/text-holdout-gold-v1.schema.json >/dev/null
```

## 8. 利用枠checkpoint

残り3 fixtureの連続run開始時点は5時間枠35%使用、週間枠65%使用、完了後は5時間枠41%、週間枠66%使用だった。停止基準80%未満のため有限runを完了した。数値は次回まで維持されるとは限らないため、再開時にUsageを再取得し、`LEARNING_AND_USAGE_PLAN.md`の作業モードを決める。

2026-09-27の中断時点は5時間枠92%使用、週間枠74%使用だった。停止準備基準のため新しい実装とcommitを行わず、公開変更を未commitのまま残した。再開時点は5時間枠1%、週間枠0%で、公開変更の検証を完了した。reset creditは3件あるが、ユーザーの明示的な確認なしに使用しない。

日本語scan PDF fixture開始時点は5時間枠0%使用、週間枠14%使用だった。通常モードでEvidence-first sliceを1回実行し、修正roundなしで成功した。reset creditは使用していない。

回転ページfixture開始時点は5時間枠7%使用、週間枠15%使用だった。90/180/270度のEvidence-first sliceを1回実行し、修正roundなしで成功した。reset creditは使用していない。

低品質scan fixture開始時点は5時間枠16%使用、週間枠17%使用だった。低コントラスト1種類のreview-gate loopを1回実行し、修正roundなしで成功した。reset creditは使用していない。

Cloud serviceのread-only調査開始時点は5時間枠31%使用、週間枠19%使用だった。Research-to-artifact loopを2 pass以内で実行し、[`CLOUD_SERVICE_SPIKES.md`](CLOUD_SERVICE_SPIKES.md)へ4 serviceの現状、認証、最小試験、費用、停止、承認境界を記録した。resource作成、API有効化、権限変更、外部API呼出は行っていない。P0-15は`unimplemented`から`weak`へ変更し、実接続後に再判定する。reset creditは使用していない。

Gemini runner品質確認開始時点は5時間枠53%使用、週間枠22%使用だった。8つの固定scenarioをQuality streakとしてmockで検証し、Secret sanitizeの修正roundを2回行った。対象test 11件、全test 117件、Ruff、dry-runが成功した。dry-runはAPI呼出0回、retry 0回、Secret取得なしで、最大費用見込みは`$0.000692`だった。reset creditは使用していない。

Account preflight時点は5時間枠63%使用、週間枠24%使用だった。AI StudioではFree tierの`Default Gemini Project`だけが表示され、Google Cloudの`municipal-rag-portfolio`にはAPI key metadataが0件だった。Secret version 1との同一性はpayloadを開かずには確認できないため、外部API呼出0回のまま`BLOCKED_KEY_METADATA`とした。AI Studioへのproject import、key・billing設定の変更、reset creditの使用は行っていない。

Gemini実行直前は5時間枠69%使用、週間枠25%使用だった。ユーザー承認後、Secret version 1をprocess memoryへだけ取得してAI Studioのmasked keyと照合し、固定promptを1 request送った。`SUCCESS`、retry 0、1.408788秒、input 54・output 51・合計105 tokens、Free tierの価格表上の推定請求額`$0`、Paid list price換算`$0.00009000`だった。固定Schema・期待値一致、Secret非混入、費用再計算一致を確認した。reset creditは使用していない。

GCS実行票の作成開始時点は5時間枠74%使用、週間枠26%使用だった。固定checklist方式で、既存bucketを流用しない短命bucket、control/data plane identity分離、runtime service accountのbucket限定`roles/storage.objectUser`、131 bytesの架空payload、generation precondition、soft delete無効化、費用上限`$0.01`、cleanupを[`GCS_CONNECTION_SPIKE_RUNBOOK.md`](GCS_CONNECTION_SPIKE_RUNBOOK.md)へ固定した。完了時点は5時間枠80%、週間枠27%のため、read-only preflightとresource操作は開始せずcheckpointで停止した。bucket作成、IAM変更、object操作、reset credit使用は行っていない。

Contextual heading回答回帰評価の開始時点は週間枠4%、完了時点は5%だった。表示されたsecondary 5時間枠はなかった。固定8問・16回答の有限runと全件確認を完了し、reset creditは使用していない。

Cloud Run / local RAG v2差分確認の開始時点は週間枠7%で、表示されたsecondary 5時間枠はなかった。公開serviceはcommit `486a9ff`、revision `municipal-rag-assistant-00004-vv9`で`Ready=True`、healthは`ok`だった。Cloud Runの環境変数はGemini secret参照だけで、PostgreSQLとQdrantの接続設定はなかった。local HEADは41 commit先のQdrant既定構成であるため、imageだけを現行CDで反映すると質問時に接続失敗する可能性が高い。詳細と推奨する公開境界を[`CLOUD_RUN_RAG_V2_GAP_ANALYSIS.md`](CLOUD_RUN_RAG_V2_GAP_ANALYSIS.md)へ記録した。resource、IAM、API、secret、trafficは変更していない。

ユーザー判断により、公開demoもCloud SQL、Qdrant Cloud、Gemini 3.1のRAG v2へ統一する方針へ変更した。週間枠7%から開始し、準備完了時点は8%、secondary 5時間枠は表示されなかった。Qdrant API key対応、Cloud Run Jobの`bootstrap-cloud`、CD設定、Cloud SQL・Secret Manager・IAMのTerraformを実装した。Terraform planは`12 add, 0 change, 0 destroy`で、東京の`db-f1-micro`とHDD 10 GiBは公式価格表から月約`$8.57`と見積もった。160 test、Ruff、workflow YAML、Terraform fmt・validate、Docker build、container内CLIが成功した。resourceはまだapplyしていない。次は費用確認後にTerraform planをapplyし、Qdrant Free clusterとdatabase API keyを作成して、Secret versionとGitHub production variablesを設定する。詳細は[`CLOUD_RAG_V2_DEPLOYMENT_PLAN.md`](CLOUD_RAG_V2_DEPLOYMENT_PLAN.md)を正とする。
