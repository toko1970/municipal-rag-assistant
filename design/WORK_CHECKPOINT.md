# 作業再開checkpoint

## 2026-09-29 最新checkpoint: 再リリース後に発見した運用修正

PR #11（merge commit `3ed3f4996d80e485aae28f85d9170d0bd3f7e610`）をGitHub Actions run
`36573652613`で再リリースし、revision `municipal-rag-assistant-00008-9kt`を作成した。通常質問とhealthは
成功した。Cloud Runのtrafficがrollback先へ固定されたままだったため、新revisionへ手動で100%切り替えた。

具体期限smokeではGemini provider errorとなったが、現行UIはすべての
`ChatGoogleGenerativeAIError`を「利用上限」と表示するため、429と503を識別できなかった。追加API呼び出しは
停止し、図表smokeも未実施である。公開受入は未完了で、trafficはReadyかつhealthが成功している
`00008-9kt`へ維持している。

現在のbranchは`codex/release-retry-and-traffic`。503限定のbounded exponential backoffを共通moduleへ
移し、UIの429・503・その他error表示を分離し、CDに`--to-latest`を追加した。外部APIを使わない回帰
378件、実PostgreSQL・Qdrant integration 3件、Ruff、Python構文、diff検査は成功した。次の最小手順は
commit・push・PR reviewへ進むこと。mergeとproduction deployは明示承認境界である。詳細は
[`PUBLIC_RELEASE_RESULT_2026-09-29.md`](PUBLIC_RELEASE_RESULT_2026-09-29.md)を参照する。

## 2026-09-29 公開release smokeとrollback

PR #10をsquash mergeし、GitHub Actions run `36569983269`でrevision
`municipal-rag-assistant-00007-wt2`を作成した。CI、bootstrap Job、health、通常質問、図表質問は成功し、
bootstrapの503 retryは0件だった。具体期限smokeでは、根拠に起算規則がないにもかかわらず当日を
1日目と補って期限日を断定したため、公開受入を不合格とした。trafficは直前revision
`municipal-rag-assistant-00006-m8d`へ100%戻し、Readyとhealth `ok`を確認した。詳細は
[`PUBLIC_RELEASE_RESULT_2026-09-29.md`](PUBLIC_RELEASE_RESULT_2026-09-29.md)を参照する。

この問題はPR #11で修正済みである。引用根拠に起算規則が明記されていない`date_calculations`をコードで
破棄し、安全表示へ落とす。再公開後の経過は上の最新checkpointを参照する。

## 2026-09-29 最新checkpoint: sealed text holdout後の対策調査

- Text sealed holdoutの受入採点は完了し、総合回答成功83/100、分類86/100、内容94/100、
  実行98/100、検索100/100だった。
- Loop Libraryのclaim-ledger research loopを3 roundへ縮小し、分類校正、具体期限計算、
  表示契約不整合の対策を一次資料と現行コードに照らして調査した。
- 調査結果と実験gateは
  [`SEALED_HOLDOUT_REMEDIATION_RESEARCH.md`](../eval/SEALED_HOLDOUT_REMEDIATION_RESEARCH.md)
  に記録した。
- 次のcoherent sliceは、外部APIを使わず、typed missing condition、semantic invariant validator、
  `PIPELINE_INCONSISTENCY`の安全表示と監査ログを最小実装すること。
- その後、別sliceで決定的な期限計算を実装し、新規development fixtureで評価する。
- 分類校正は総合成功を単体で最大11件改善し得る一方、退行リスクが高い。上記2層を整えた後、
  新規development setでGemini baselineと構造変更を比較する。
- 今回開封済みのtext holdoutは、候補選択には再利用せず観測済み回帰setとして扱う。
- `eval/results/text_holdout_v1_predictions_v3`から`v9`の部分予測7ファイルはuntrackedのまま保持する。
  意図的に削除していない。

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
- Qdrant Cloud Free cluster `municipal-rag-portfolio`をGCP Sydneyで作成し、`HEALTHY`を確認した。最終database API keyをSecret Manager `qdrant-api-key` version 5へ保存し、`/collections`へのHTTP 200、JWT subjectとQdrant key IDの一致を確認した。
- Qdrant Cloudの旧database API keyはすべて削除し、Secret Manager version 1〜4を無効化した。CDのbootstrap JobとCloud Run serviceはversion 5を明示参照する。
- GitHub Actionsの通常CIから`integration` markerを分離した。GitHub RunnerにPostgreSQL・Qdrantを起動していない状態で統合テストだけが接続失敗したためで、外部service非依存159件と、ローカル実DB統合1件を別々に実行して成功を確認した。
- 初回production CDはCloud Run Job作成前の`gcloud run jobs deploy`で停止し、Cloud Run serviceは更新されなかった。`--args`先頭の`-m`がgcloudのoptionとして解釈されたため、ハイフン引数を必要としない`cloud_bootstrap.py` entrypointへ変更した。
- 修正後の2回目のproduction CDはimage buildと設定検証を通過したが、Cloud Run Job作成前に停止した。Cloud Run service用の`--add-cloudsql-instances`をJobにも使用していたため、Jobで受け付ける`--set-cloudsql-instances`へ変更した。サービス更新はskipされ、公開revisionは変更されていない。
- 3回目のproduction CDは全工程に成功した。bootstrap execution `municipal-rag-bootstrap-jtkms`はmigration head、5文書・86要素、Qdrant 86 point、missing 0、unexpected 0、代表質問`根拠十分`・参照8件を記録した。
- revision `municipal-rag-assistant-00005-rwd`へcommit `4a621fcb938b37d718cb294c51870733531387e7`を反映し、traffic 100%、`Ready=True`、health `ok`、トップページHTTP 200を確認した。
- 公開実ブラウザで「給与支給日はいつですか？」を実行し、毎月21日、休日は直前営業日という回答、`根拠十分`、参照8件を確認した。「採用した」とsmoke用コメントを送信し、保存成功表示を確認した。
- Cloud SQL Auth Proxyを一時起動し、公開request `25be953a-bf46-4adf-97f6-5554740107b3`をread-only SQLで監査した。検索8件、生成1件、分類1件、claim 2件、evidence 3件、feedback「採用した」とコメントを結合でき、公開text RAG v2のgo-live条件をすべて確認した。

## 2. 未完了・次回反映すること

- 既存100シナリオ・500問を新しい論理locatorへ移行する処理は、Phase 2以降のingestion実装で具体化する。
- Cloud SQL、Qdrant Cloud、Gemini 3.1を使うtext RAG v2は、公開反映、ブラウザsmoke、Cloud SQLの直接read-only監査まで完了した。
- PDF・図表runtimeは、レビュー済み抽出JSONを入力にした最小vertical sliceまで実装した。ページ画像の描画・hash照合、Schemaと意味検証、`LocalAssetStore`保存、PostgreSQLのvisual metadata、検索用説明のEmbedding、Qdrant登録を一つのCLI経路で実行できる。Gemini画像抽出、画像付き回答、6 fixture評価は次のroundで実装する。
- Gemini画像抽出adapterと`extract-visual` CLIを追加した。`flowchart_dev_001`の実モデル試験ではnode 6件・edge 6件・分岐条件を抽出した一方、矢印bboxを端点として返し、意味検証が拒否した。prompt修正でも再現したため、端点の大小整列とゼロ幅線への最小幅付与を決定的な正規化として追加した。保存済み実応答のオフライン再検証はbbox 13件を正規化後、validation error 0件となった。候補は常に`REVIEW_REQUIRED`で、review前にはDBへ登録しない。
- visual extraction evaluatorを追加し、kindごとの論理要素をIDではなく内容で対応付け、重要値完全一致、要素recall、bbox IoUを同時に測れるようにした。上記のGemini実候補は重要値完全一致、要素recall `12/12 = 1.0`、平均bbox IoU `0.6623`で、固定gate `0.80`未達のため不合格だった。意味抽出と位置抽出の成否を分離して記録できる状態になった。
- 6 visual fixtureの固定baselineを完了した。残り5件を単一batch、retryなしでGemini 3.1へ送り、input 7,904・output 9,920 tokens、実行5件合計30.626秒を記録した。初期評価は合格2/6、validated 5/6だった。波ダッシュの同値比較を評価revision v2として分離し3/6へ修正し、cell範囲から不足したtable行数だけを補正するRevolve roundで4/6、validated 6/6へ改善した。残るflowchart 2件は重要値・要素Recall 1.0、bbox IoU 0.662/0.629で、人手review対象として自動調整を停止した。詳細は[`VISUAL_EXTRACTION_BASELINE.md`](../eval/VISUAL_EXTRACTION_BASELINE.md)に記録した。
- reviewed ingestion Quality streakは6 fixture連続成功した。各fixtureを2回登録しても、PostgreSQLの文書・content element・visual asset、Qdrant point、LocalAssetStoreのPNGは各6件のままで、重複0件だった。実PostgreSQL・Qdrant integration testは3件すべて成功した。
- 画像付き回答のローカルvertical sliceを接続した。Qdrantの図表hit順にPostgreSQLからvisual assetを取得し、保存画像のSHA-256を検証して、構造JSON・element ID・添付順と最大3枚の元画像をGeminiへ渡す。返却referenceにはページ・bbox・画像pathを付け、Streamlitの根拠欄で元画像を表示する。画像欠損・hash不一致は`GENERATION_FAILED`として記録する。Cloud公開時は`LocalAssetStore`をGCS adapterへ差し替える必要がある。
- 図表回答30 scenario用のbounded evaluatorを追加した。development以外を拒否し、インメモリQdrant、最大scenario・費用、scenarioごとの費用予約、retry 0、error fail-fast、逐次JSONL、条件一致resumeを固定した。VD001 pilot v2は分類・必須fixture検索・回答内容が成功し、input 17,871、output 247 tokens、標準料金換算US$0.00483825、15.38秒だった。v1のartifact保存失敗も上書きせず保存した。詳細は[`VISUAL_ANSWER_BASELINE.md`](../eval/VISUAL_ANSWER_BASELINE.md)に記録した。
- 図表回答baseline 30/30を完了した。必須fixture検索30/30、分類28/30、API error 0、input 573,290・output 9,468 tokens、標準料金換算US$0.1575245、平均10.08秒だった。分類失敗は`needs_judgment`の2件だけで、どちらも検索成功後の生成・分類境界だった。Codex初回内容reviewはpass 27、partial 1、fail 2で、ユーザー確認前の値として分離保存した。
- `VD004`の根拠外読み替えをpromptだけで防ぐRevolveを2候補試した。v2はVD004単体を改善したが、全体runのVD003で誤記「モレ」を「不備」へ対応できず表示契約違反となった。誤字を許可したv3も同じ退行を再現したため、両候補を不採用にして`answer-claims-v1`へ戻した。次の改善はclaim locatorまたは生成・分類の決定的不整合処理とする。
- visual asset境界をLocal/GCSで差替可能にした。DB列を`local_path`から`storage_uri`へ非破壊migrationし、Localは`file://`、GCSは`gs://`を保存する。GCSはcreate-only precondition、content hash key、重複時hash照合を使い、readerはdownload後にSHA-256を再検証する。回答時の同じbytesをGeminiとStreamlitへ渡すため、Cloud Runの一時filesystemに依存しない。cloud bucketとIAMはまだ作成・変更していない。
- 30 scenarioを実行する評価harnessは、Phase 4・5の取込・回答実装と合わせて追加する。
- Phase 0の全要求が揃った段階でcontract conformance loopを再実行する。
- 短期集中期間の実行順序は[`PORTFOLIO_DELIVERY_PLAN.md`](PORTFOLIO_DELIVERY_PLAN.md)を正とする。Cloud SQL・Qdrant Cloudの実接続は対応コード完成後へ移し、HA・完全な障害回復・運用自動化はProduction Backlogとして説明する。
- Streamlit画面の質問・引用8件・feedback保存は`RAG_BACKEND=qdrant`の実接続smokeで確認済み。既定backendもQdrantへ変更した。
- 公開text RAG v2は実ブラウザで質問、分類、回答、参照8件、feedback保存まで確認済みである。次の主要実装はPDF・図表runtime取込と画像付き回答のvertical sliceである。

## 3. 次回最初に行うこと

1. Codexの5時間枠・週間枠を確認する。
2. `git status`と本checkpointを確認する。
3. `VD004`の根拠外読み替えと`VD024`の判断要/文書不足境界に限定した候補を、同じ30 scenarioで比較する。
4. Terraformへprivate application bucketとruntime object権限を追加し、具体的な費用・rollbackを提示してapply承認を得る。
5. reviewed 6 fixtureをGCS・Cloud SQL・Qdrant Cloudへ登録し、Cloud Runで画像付き質問をsmokeする。
6. development候補と内容reviewを固定した後にだけ、visual sealed holdoutの実行可否をユーザーへ確認する。

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

2026-09-28のPDF・図表runtime開始時点は週間枠13%使用で、secondary 5時間枠は表示されなかった。`flowchart_dev_001`を対象に最大3 roundのEvidence-first sliceを開始し、1 roundで停止条件を満たした。レビュー前の登録拒否、Schema・意味・画像hash検証、決定的な検索表現、LocalAssetStore、PostgreSQL・Qdrantへの冪等登録を実装した。対象test 38件、外部依存を除く全test 164件、実PostgreSQL・Qdrant integration 2件、Ruff、diff検査が成功した。Gemini API呼出とreset creditは使用していない。

同日のGemini画像抽出roundは最大3回で実施した。1回目はAPI送信前のLangChain入力型エラー、2回目と3回目はそれぞれinput/output `1253/1531` tokens、`1318/1594` tokensで応答した。両方とも図の論理構造は取得したがedge bboxが意味検証に失敗し、promptだけでは改善しなかったため追加API再試行を停止した。既存応答で座標正規化を検証し、Schema・意味検証を通過した。API候補は`/tmp`だけに保存し、DB・Qdrantには未登録、reset creditは使用していない。

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

同日、週間枠8%・secondary表示なしの状態でクラウド適用を再開した。対象project限定の月額2,000円予算を先行適用し、50%、80%、100%の実費通知を確認した。請求先全体には既存の月額1,000円予算も存在する。続いてRAG v2基盤を`12 added, 0 changed, 0 destroyed`で適用した。Cloud SQL PostgreSQL 16は`RUNNABLE`、database・user・接続URL secret version 1、Qdrant key用secret container、runtime IAMが作成済みで、適用後planは`No changes`だった。次はQdrant Free clusterを作成し、database API keyをSecret Managerへ登録してGitHub production variablesを設定する。reset creditは使用していない。

## 9. Visual sealed holdoutと改善checkpoint

2026-09-28に公開Cloud Run commit `6a2d7e6`をvisual candidateとして固定し、6 PDF・20 scenarioのsealed holdoutをretry 0、最大67 logical external call、費用上限US$0.35で実行した。2件目`vh_doc_m2`の抽出で先頭nodeを`process`と返し、start nodeが0件となってSchema検証でfail-fastした。質問APIは0件で、20 scenarioを`BLOCKED_BY_EXTRACTION_ERROR`として固定した。gold hash照合後の採点では、1件目`vh_doc_a7`も9要素中5要素一致、element recall 0.556、mean bbox IoU 0.806でgate不合格だった。holdoutは`CONSUMED`で、再実行しない。詳細は[`VISUAL_HOLDOUT_PREDICTION_RESULT.md`](../eval/VISUAL_HOLDOUT_PREDICTION_RESULT.md)を参照する。

消費後のdevelopment改善として、連結された一意なflowchartに限り、incoming edgeがない`process`を`start`、outgoing edgeがない`process`を`end`へ補正するtopology normalizationを追加した。既存development 6件はSchema-valid 6/6、gate 4/6を維持し、合成回帰入力では2 nodeの補正後にSchemaを通過した。詳細は[`VISUAL_TOPOLOGY_NORMALIZATION.md`](../eval/VISUAL_TOPOLOGY_NORMALIZATION.md)を参照する。

続いてvisual extraction評価をv4へ更新し、厳密一致に加えてformat-normalized一致を記録するようにした。NFKC、空白、限定した句読点だけを正規化し、負号、時刻区切り、数字、単位、条件語は残す。PR reviewでは、正規化後に異なる要素が同じ比較keyへ潰れる場合を検出してgate不合格にするよう修正した。また、成功したsealed prediction bundleにもgold未参照を明示し、validatorとの契約をそろえた。既存development 6件は厳密・正規化とも完全一致、collision 0件、gate 4/6を維持した。全test 217件とRuffが成功した。詳細は[`VISUAL_FORMAT_NORMALIZATION_EVALUATION.md`](../eval/VISUAL_FORMAT_NORMALIZATION_EVALUATION.md)を参照する。

現在の改善branchは`codex/visual-topology-normalization`である。次はreview後にこのbranchをmergeし、消費済みholdoutを使わず別の小規模sealed holdoutで最終受入を行う。合格後に公開demoへ反映する。mergeと本番deployは明示承認が必要である。

## 10. Retrieved-evidence回帰checkpoint

2026-09-28、週間枠26%・secondary 5時間枠表示なしの状態で、候補`classification-decision-v2`をdevelopment 130問（text 100、visual 30）へ適用した。sealed holdoutは使用していない。採用runはretry 0、API error 0、実測US$0.2424035だった。初版runnerの中止試行US$0.00155475を含む実験全体はUS$0.24395825である。

候補v2は既存v1比で改善0件、退行2件だったため不採用とし、本番規則をv1へ戻した。v1基準では成功106件、回答分類15件、回答生成6件、検索3件で、最大原因は回答分類（24失敗中15件、62.5%）である。詳細は[`RETRIEVED_EVIDENCE_REGRESSION.md`](../eval/RETRIEVED_EVIDENCE_REGRESSION.md)と機械可読な[`analysis.json`](../eval/results/retrieved_regression_e24d7d4_v1/analysis.json)を参照する。

現在のbranchは`codex/visual-holdout-v2`である。次の最小学習単位は、production v1で残る分類失敗15件を要因パターンへ分解し、最大の一類型へ対策を一つだけ試すことである。内容レビューはCodexによる初回判定なので、ポートフォリオの確定値に使う前にユーザー確認を行う。mergeと本番deployには明示承認が必要である。

分類失敗15件の要因分析を[`CLASSIFICATION_FAILURE_PATTERN_ANALYSIS.md`](../eval/CLASSIFICATION_FAILURE_PATTERN_ANALYSIS.md)へ追加した。内訳は、解決済み条件の誤検出8件（version 7、case facts 1）、個別・所管判断の見逃し4件、GeneratorとClassifierの不足判定不整合2件、Visual類似事例の適用境界1件である。実装前の推奨は、最大かつ変更範囲を限定できる`version_conflict`誤検出7件に対する分類prompt比較である。対策対象はユーザーと合意してから固定する。

ユーザー合意後、`version_conflict`だけを変更する候補promptと17件の比較runnerを実装した。開始時のCodex週間枠は28%でsecondary表示なしだった。17件すべてのTop-8を保存済みrunと同一順序で再現後、最大34 call、retry 0、US$0.10上限で開始したが、最初のGemini callがFree Tier日次500 request上限の429となりfail-fastした。成功call 0、token 0、推定費用US$0で、改善度は未評価である。詳細と再開コマンドは[`VERSION_CONFLICT_PROMPT_EXPERIMENT.md`](../eval/VERSION_CONFLICT_PROMPT_EXPERIMENT.md)を参照する。

日本時間16:05の自動再開で同じ比較を完了した。候補は対象7件中5件を改善したが、controlの`Q206`と`Q211`を2件退行させ、採用gateは不合格だった。34 call、retry 0、API error 0、79,215 input tokens、3,427 output tokens、推定US$0.02494425である。候補は本番へ反映せず、130問回帰にも進めていない。失敗原因は、version規則の追加が同じLLM出力内の`requires_case_facts`にも影響したことにある。

責務を分けた専用Version Resolverを9件で評価した。Round 1はboolean 9/9だったが`Q231`の解決根拠種別が不正確だったため、`single_applicable_source`を追加してRound 2を実施した。Round 2はversion誤検出7/7、真の競合1/1、診断1/1、根拠種別・引用も一致し、API error 0、推定US$0.0080555だった。2 round合計はUS$0.01580275である。条件付き合成は17/17だがproduction未統合であり、次はresolver失敗時fallbackとログを実装して130問回帰を行う。詳細は[`VERSION_RESOLVER_EVALUATION.md`](../eval/VERSION_RESOLVER_EVALUATION.md)を参照する。

専用Version Resolverをローカルquery flowへ統合した。既存分類がversion conflictのときだけ呼び、confidence 0.80以上かつ表示契約を満たす場合にversion要因だけを置換する。失敗・低confidence・取得外根拠・表示契約違反では基準分類へfallbackし、resolver attemptと最終分類を別々に記録する。保存済みの同一130問による固定回帰では、対象9件、適用8件、表示契約fallback 1件、改善6件、退行0件だった。主原因は成功106→112、分類失敗15→9、回答生成失敗6、検索失敗3となりgateを通過した。新規API callは0、sealed holdoutは未使用である。Ruff、非integration 243件、ローカルPostgreSQL・Qdrant統合3件が成功した。公開環境へのdeployは未実施。次の最大分類類型は個別・所管判断の見逃し4件である。

総合回答成功率を対象に、RAG側と回答分類器側の改善手法を[`RAG_AND_CLASSIFIER_IMPROVEMENT_RESEARCH.md`](../eval/RAG_AND_CLASSIFIER_IMPROVEMENT_RESEARCH.md)へ統合した。分類失敗9件は、分類器だけで総合成功へ変えられる高確度4件、検索完全性またはgold境界に論点がある2件、Generator・表示契約とのcross-layer問題3件に分けた。分類器候補には現行Gemini、Jevのfactor別5 Noul、多言語NLIがあるが、Jevは公開直後で日本語制度文書の独立評価が不足しているため置換を前提にしない。RAG側はQdrant Hybrid Search、Generator required facets、条件付きQuery Decompositionを候補とし、分類器実験と分離して評価する。sealed holdout、外部API、production設定は使用・変更していない。

優先順位を失敗件数ではなく限界効果で再確認した。分類器だけで総合成功へ変わる高確度対象は、取得根拠と回答本文が正しい`Q046`、`Q086`、`Q301`、`Q316`の4件である。`Q126`は検索完全性、`VD024`はgold境界、残る3件はcross-layerの論点がある。

ユーザーとの再確認により、分類器モデルの技術選定を説明できることもポートフォリオ上の便益へ含め、モデル比較を先に行う。現状の130件には最終3ラベルのgoldはあるが5 factorのgoldはないため、既存分類development case、観測済み失敗、hard negative controlから分類専用benchmarkを作り、factor goldをmodel実行前に固定する。現行Gemini、Jev 5 Noul、多言語NLIをこの小benchmarkで比較し、gate通過候補だけを保存済み130件へ適用する。全候補を130件実行しない。モデル選定後、Version Resolverの基盤を再利用した個別・所管判断専用resolverへ進む。比較指標はfactor・最終ラベルmacro F1、重大誤り、総合回答成功、費用、遅延、API errorとする。Jev外部APIはread-only preflight後に上限付きrunを別途行い、sealed holdoutは使わない。

分類専用benchmarkのdraftを[`CLASSIFIER_MODEL_BENCHMARK.md`](../eval/CLASSIFIER_MODEL_BENCHMARK.md)と[`classifier_model_benchmark_v1.json`](../eval/classifier_model_benchmark_v1.json)へ作成した。既存control 14件、factor補完control 4件、保存済み回帰16件の計34件で、ラベル配分は根拠十分14・判断要14・文書不足6、Text 26・Visual 8である。5 factorの正例・負例、入力元hash、annotation根拠を記録した。`CPD-T05`、`REG-Q046`、`REG-Q086`、`REG-Q316`は回答範囲またはcase facts / policy judgment境界の確認が必要なため、benchmark全体を`draft`にしてmodel runを禁止する。再生成builderはAPIを使わず保存済みTop-8の一致を検証する。Schema、semantic validator、対象test 3件が成功した。開始時のCodex週間枠は31%、secondary表示なしで、reset creditは使用していない。

ユーザー確認により分類を「質問が直接求める命題」で行う規約へ統一し、S010/Q046、S018/Q086、S064/Q316を`判断要`から`根拠十分`へ訂正した。各5表現の計15問を含む500問評価セットはv1.1として再固定した。保存済みVersion Resolver出力へ訂正後goldを適用した現在値は、総合成功115/130、分類正解119/130、分類失敗6、生成失敗6、検索失敗3である。3件の差はモデル改善として数えない。benchmarkは根拠十分17・判断要11・文書不足6となり、4件のadjudication結果を反映した。詳細は[`CLASSIFIER_GOLD_CORRECTION.md`](../eval/CLASSIFIER_GOLD_CORRECTION.md)を参照する。外部API、sealed holdout、reset creditは使用していない。

分類専用benchmarkの残り30件を一括レビューし、26件を提案どおり承認した。質問範囲規約との不整合をQ006、Q076、Q176、Q301で発見し、4シナリオ20表現を追加訂正して500問評価セットをv1.2へ更新した。保存済み130件の現在値は総合成功117/130、分類正解121/130、主原因が分類4、生成6、検索3であり、数値差はモデル改善として数えない。少数クラスを維持する明確な文書不足control 2件を追加し、benchmarkは36件（根拠十分21・判断要9・文書不足6、Text 27・Visual 9）、全annotation承認済みとなった。週間利用率32%、外部API call 0、sealed holdout未使用、reset credit未使用である。詳細は[`CLASSIFIER_BENCHMARK_REVIEW.md`](../eval/CLASSIFIER_BENCHMARK_REVIEW.md)を参照する。

分類モデルのread-only preflightを実施した。公式Jevはearly access・label fit型で一般公開APIと価格を確認できず、公開OpenJev 0.8B longも約1.73GB、現TransformersでQwen 3.5未対応、8GB M1でCPUのみのため最初の比較から除外した。日本語を含む27言語のNLI学習を明記したmDeBERTa-v3-baseをlocal pilot第一候補、Gemini 3.1 Flash-Liteをbaselineとした。次は約580MBを1回だけdownloadし、36件のtoken auditで512超過があれば採点前に停止する。外部API call、model download、sealed holdoutは未実施。詳細は[`CLASSIFIER_MODEL_PREFLIGHT.md`](../eval/CLASSIFIER_MODEL_PREFLIGHT.md)を参照する。

2026-09-29にmDeBERTa revision `b5113eb38ab63efdd7f280f8c144ea8b13f978ce`を
1回downloadし、承認済み36件×5 factorのtoken auditを実施した。180 pair中80 pair、
36ケース中16ケースが512 tokenを超え、最大802 tokenだった。超過はすべて保存済みTop-8
回帰ケースである。計画どおりlocal inference前に`BLOCKED_BY_CONTEXT_LIMIT`で停止し、
外部API call 0、費用US$0、sealed holdout未使用だった。次は、claim-evidence単位のNLI集約か
4k以上のlocal modelかを入力契約・日本語適性・8GB M1の実行可能性で比較し、設計を一つに
固定する。Gemini baselineはlocal候補と公平に比較できる状態まで実行しない。結果は
[`token_audit.json`](../eval/results/classifier_model_mdeberta_pilot_v1/token_audit.json)を参照する。

同じ検証で、text sealed holdoutの公開manifestが参照するdevelopment manifestのhashが、
評価セットv1.2へのgold訂正後もv1.0の値だったため全test 1件が失敗することを発見した。
sealed内容を開かず、公開manifestの参照hashだけを現行v1.2へ更新した。公開validatorで
文書family分離を再確認し、sealed holdoutのquestions、gold、状態、採点結果は変更していない。

長文local候補として商用利用向け`bge-m3-zeroshot-v2.0-c`を追加し、同じ36件・180 NLI
pairを閾値調整なしで実行した。最長886 token、推論94.13秒、平均0.523秒/pair、peak RSS
約1.85 GiBで完走したが、最終ラベル6/36、macro F1 0.153だった。続いて現行Gemini 3.1
Flash-Liteを最大36 call、retry 0、US$0.05上限で実行し、31/36、macro F1 0.862、API error
0、実測US$0.0110875だった。両候補とも重大な`根拠十分`誤判定は0件だが、BGE-M3は
`根拠十分`を一度も予測しない過度に保守的な結果だった。現行Geminiを維持し、local候補の
130問Stage Bは行わない。外部APIは合意済み上限内、sealed holdout・production設定・reset
creditは未使用。詳細は[`CLASSIFIER_MODEL_COMPARISON.md`](../eval/CLASSIFIER_MODEL_COMPARISON.md)
を参照する。

モデル比較後にgold v1.2の残存失敗を再確認した。主原因は回答生成6、分類4、検索3である。
分類4件はQ126だけが分類器単独の高確度対象で、Q176・Q196はGeneratorの不足条件、VD024は
Visual類似事例の適用境界を含むため、一つのresolverで安全に一括改善できない。最大かつ共通性
のある次の一手を、Generatorの`required facets`確認へ変更した。テキスト失敗4件とcontrolを使う小pilot
を先に行い、2件以上改善・control退行0・根拠外断定増加0を通過した場合だけ130問へ進む。
この再優先付けではAPIを呼んでいない。詳細は
[`CURRENT_FAILURE_PRIORITY_V1_2.md`](../eval/CURRENT_FAILURE_PRIORITY_V1_2.md)を参照する。

実装前の重複確認で、VisualのVD004には同種のprompt候補v2/v3を既に試し、VD003を退行させて
不採用としていたことを確認した。今回のrequired facets pilotはテキスト失敗4件とcontrol 6件
だけに限定する。Visual 2件はprompt再試行から外し、locator付きSchemaまたは表示契約の構造変更
として別工程にする。

required facets pilotを実行した。20 logical calls、retry 0、US$0.01053975、sealed holdout未使用で、
厳密gateの改善0/4、control退行4/6となり不採用とした。Q391は意味上改善したが、採用条件の2件へ
届かず、退行も解消しない。本番promptとSchemaは維持し、130問回帰は行わない。次は同質性のある
検索失敗3件のHybrid Search / reranking比較を優先する。詳細は
[`GENERATION_FACETS_PROMPT_EXPERIMENT.md`](../eval/GENERATION_FACETS_PROMPT_EXPERIMENT.md)を参照する。

現行gold v1.2のformal 100問で、Sudachi BM25 + RRFをcontextual denseと比較した。外部API call、
費用、sealed holdout使用はいずれも0。検索失敗3件の改善0、全根拠見出しHit@5は80/90から
73/90、既存成功8件退行のため不採用とした。Q156の不足根拠はdense Top-30外、Q436は27位で、
rerankerでは2件を回復できない。次はQuery Decompositionの有限比較を候補とする。詳細は
[`BM25_HYBRID_EVALUATION.md`](../eval/BM25_HYBRID_EVALUATION.md)を参照する。

Query Decompositionをformal 100問で比較し、Evidence Hit@5は80/90から82/90へ改善した。
Q291とQ436を回復し、Hit@5退行0件で検索gateを通過した。11 subqueriesのEmbeddingは1 batch、
retry 0、保守的費用上限見積りUS$0.0000454で、sealed holdoutは使用していない。

回答回帰ではQ291 candidateが旧ルールを選び内容失敗となった。Q436 candidateは正解したが、
baselineがGemini 503となりpaired比較は不成立だった。fail-fast文字列判定の不足で503後に1
scenario進んだため、このrunは採用判定不可として監査記録を保存した。追加retryと追加runは
行っておらず、production検索も変更していない。

次の最小手順は、生成前に適用時期と新旧根拠を整理する処理をQ291で比較し、検索改善を総合回答
成功へ接続できるか確認することである。詳細は
[`QUERY_DECOMPOSITION_EVALUATION.md`](../eval/QUERY_DECOMPOSITION_EVALUATION.md)を参照する。

生成前版注記のpilotをQ291と改正前後比較control 3件で実行した。質問日、対象制度、改正通知の
effective dateと見出しから優先根拠と旧記載候補をコードで決め、現行generation promptへ注記した。
Q291はQuery Decomposition、版注記、既存Version Resolverの組み合わせで「認定月から支給・
15日以内」を正答し、control 3件も正解した。4/4 composite success、9 logical calls、retry 0、
推定US$0.00501575、API error 0、sealed holdout未使用でgateを通過した。

formal 100問のdry runで同処理の対象は7問と判明した。未評価のQ186、Q191、Q286だけを追加実行し、
7件の影響範囲回帰を完了することが次の最小手順である。production統合、130問回帰、deployは
未実施。詳細は
[`TEMPORAL_GENERATION_EVALUATION.md`](../eval/TEMPORAL_GENERATION_EVALUATION.md)を参照する。

残るQ186、Q191、Q286を最大9 logical calls、retry 0、US$0.015上限で実行した。Q186とQ286は
総合成功し、Q191も回答内容は正しかったがVersion Resolverが`RESOLUTION_FAILED`となり、
影響範囲は6/7で採用gate不合格だった。新規8 logical calls、input 9,033・output 972 tokens、
推定US$0.00371625で、sealed holdoutは未使用である。

このrunで、内部Resolver失敗が戻り値に理由を残さず、評価器のtop-level errorにも反映されない
観測欠陥を発見した。Resolverの`error_summary`を戻り値へ追加し、`RESOLUTION_FAILED`をscenario
errorとして扱う修正と対象testを追加した。実行済みartifactは上書きせず`run_audit.json`で
有効完了6件へ訂正し、追加retryは行っていない。次の最小手順は、修正済み観測処理でQ191だけを
独立runし、失敗理由と再現性を確認することである。production統合、130問回帰、merge、deployは
未実施。詳細は
[`TEMPORAL_GENERATION_EVALUATION.md`](../eval/TEMPORAL_GENERATION_EVALUATION.md)を参照する。

Q191単一診断を、最大3 logical calls、retry 0、US$0.005上限で開始した。最初のGenerator callが
Gemini 3.1 Flash-Liteの`503 UNAVAILABLE`となったためfail-fastし、Resolverへは到達しなかった。
成功call 0、token 0、推定費用US$0、sealed holdout未使用である。前回Resolver失敗の原因が
provider障害だった可能性とは整合するが、前回の失敗詳細がないため同一原因とは断定しない。
追加retryは行っていない。再開時は新しい出力先でQ191を1回だけ実行し、成功時だけ版選択品質を
採点する。

ユーザー指示でQ191を新しい独立runとして再実行した。Generatorはinput 2,245・output 321
tokensで成功したが、ClassifierがGemini 3.1 Flash-Liteの`503 UNAVAILABLE`となりfail-fastした。
logical calls 2、推定US$0.00104275、retry 0、Resolver未到達、sealed holdout未使用である。
前回診断のGenerator 503から失敗箇所が移動したため、共有endpointの一時的な可用性が測定を
妨げていると判断し、品質gateは6/7のまま維持した。

次回の正確な測定に備え、Classifier失敗時にも部分成功を監査できるよう、評価recordへGeneratorの
status・構造化response・errorとClassifierのstatus・errorを保存するようにした。実行済みartifactは
上書きしていない。endpoint安定後に、新しい出力先でQ191を1回だけ実行する。

時間を置いたQ191の3回目の独立runは、Generator・Classifier・Version Resolverの3 logical callsを
完了した。15,000円ちょうどは対象外と正答し、Resolverは`effective_period`、confidence 1.0で
版競合を解消して、分類・内容・根拠支持がすべて成功した。input 4,652・output 545 tokens、
推定US$0.0019805、retry 0、API error 0、sealed holdout未使用である。

既存6件と条件hashを照合して統合し、影響範囲は7/7 composite successで内容品質gateを通過した。
失敗したResolver 1件、Generator 503、Classifier 503は削除せず運用上の証拠として残した。
選択品質recordの推定費用US$0.00966975、失敗試行を含む実験全体は23 logical calls、推定
US$0.01175525である。次の最小手順は候補をローカルquery flowへ統合し、同じ130問で総合回答
成功と退行を評価すること。production deployは未実施で、実行前に明示承認が必要である。

Query Decompositionと生成前版注記をローカルproduction query flowへ接続した。単一intentは従来の
query vectorを再利用し、対応複合質問だけ追加Embeddingする。通常質問ではpromptを変更しない。
production composition rootの接続testを含む非integration 282件が、この統合時点で成功した。

影響範囲評価では、通勤経路変更Q131は生成失敗を改善せず、過払給与Q441は追加検索の便益がなく、
住宅Q446は一度分類退行した。そのためQuery Decompositionを、改善を確認した出生複合質問と
転居・通勤実態消失の2規則へ縮小した。Q446はDenseへ戻し、家賃と入居／住宅／賃貸の組合せを
住居手当domainへ対応付ける版注記だけで成功を維持した。

最終候補をgold v1.2の130問へ影響範囲方式で統合し、総合成功は117/130（90.0%）から
120/130（92.3%）へ改善した。改善Q286・Q291・Q436、退行0。失敗内訳は回答生成6、回答分類3、
検索1で、Q156の検索失敗が残る。採用record推定US$0.012088、temporal pilot以降の全試行は
40 logical calls、推定US$0.0229015、sealed holdout未使用、production deploy未実施である。
詳細は[`INTEGRATED_QUERY_CANDIDATE_EVALUATION.md`](../eval/INTEGRATED_QUERY_CANDIDATE_EVALUATION.md)
を参照する。次はbranch全体reviewと実PostgreSQL・Qdrant integration testを行う。

採用候補の最終検証として、非integration 289件、実PostgreSQL・Qdrant integration 3件、Ruff、
diff検査が成功した。branch差分の自己reviewでも、通常質問の既存検索経路、対象質問だけの追加
Embedding、非対象質問のprompt維持に新しい問題は見つからなかった。次は成果をreview可能な形へ
整理し、production deploy前の判断を行う。

未知言い換えへ広げたtrigger候補は、検索比較では改善したがend-to-end 9件で退行1件となり、
追加answerability promptも改善0・退行1だったためproduction不採用とした。runtimeの
`query_decomposition.py`と`temporal_evidence.py`を、130問で120/130・退行0を確認した
`e923b54`の狭い候補へ戻した。一般化候補は再現用のeval moduleへ隔離し、40件のtrigger評価が
再び100%で完走することを確認した。

公開前回帰は、非integration 294件、実PostgreSQL・Qdrant integration 3件、Ruff、diff検査が
すべて成功した。READMEの旧Chroma・ファイルログという古い記述も、現在のCloud SQL・Qdrant
Cloud公開構成と、まだ未deployの92.3%候補を区別する内容へ更新した。次の最小手順は、この差分を
commit・pushしてPRを確認し、review後にsealed holdout、merge、production deployの承認境界へ
進むことである。

PR #10をdraftで作成し、GitHub Actions 4 checksの成功とconflictなしを確認した。採用候補を
commit `5d1ecc50985db681cfa71bddc6cbfcfa99480e40`としてtext sealed holdoutへ固定し、manifestを
`CANDIDATE_FROZEN`へ進めた。予測runnerはgold pathを受け取らず、10 sealed Markdown・50
scenario / 100表現を、最大302 logical calls、retry 0、費用上限US$0.15、provider error
fail-fastで実行する。完走した100予測だけを別操作で固定できる。

gold開封後の採点器も先に用意した。期待分類、期待document、期待evidenceを自動比較し、回答要点は
文字列一致で決めず100件の内容reviewを確定してから、総合回答成功率、scenario stability、
Wilson 95%区間、失敗内訳を算出する。非integration 302件とRuff、公開manifest validator、
plan検査が成功した。sealed Markdownとgoldは未開封で、次の最小手順は上記有限runの明示承認後に
predictionを実行・固定すること。gold開封と本番deployは、それぞれ別の承認境界である。

承認済みtext holdout predictionの初回runは、30 document chunksのEmbedding後、100 queryの
EmbeddingでGemini無料枠の`embed_content_free_tier_requests` 100 RPMに達し、429で停止した。
prediction 0件、Generator・Classifier call 0、gold未開封で、追加runは行っていない。さらに
`google-genai` SDKが既定で初回を含む最大5 attemptを使うことが判明したため、当初のretry 0契約と
実装が一致していなかった。失敗artifactは
`eval/results/text_holdout_v1_predictions/failure_summary.json`へ保存した。

品質設定を変えず、Embedding SDKを1 attemptへ固定し、30 documentと100 queryのphase間に
60秒の計画的cooldownを入れた。これは429後のretryではなく、事前にquota windowを分離する
実行制御である。候補configのhashだけを更新し、source candidate commit、モデル、chunk、検索、
prompt、Top-Kは維持した。次の最小手順は、新しい出力先を使う再run条件について明示承認を得る
こと。初回失敗出力は上書きせず、goldも引き続き開かない。

修正後runはEmbedding quotaを通過し、保存時のUUID変換漏れを発見して停止した。保存処理を修正し、
前試行の最大5 calls・US$0.002をcarryoverとして累計上限から控除した。次のrunは8表現成功後、
TH005 formalのGeneratorで`generate_content_free_tier_requests` 15 RPMに達して429 fail-fastした。
累計24 logical calls、推定US$0.01415925、gold未開封で、100予測は未固定である。

追加調査結果に合わせ、Generator・Classifier・Version Resolverで共有する4.1秒間隔pacerを追加した。
成功済み8 predictionだけを次の新規runへ引き継ぎ、provider失敗recordは再実行対象とする。次回は
carryover 24 calls・US$0.01415925から開始するため、最悪でも累計302 calls・US$0.15を超えない。
また、100件すべてがSUCCESSでない限り`PREDICTIONS_FROZEN`へ進めない検査を追加した。品質設定と
goldは変更・参照していない。次の最小手順は、このpacing・resume条件での追加run承認を得ること。

4.1秒pacerで成功済み8件から再開したrunは、新規7件成功後、TH008 paraphraseのGeneratorで
15 RPM quotaへ再到達した。成功済みを合わせ15表現、失敗1、累計41 logical calls、推定
US$0.02538575、gold未開封でfail-fastした。理論上15 calls / 60秒を満たす4.1秒間隔には、rolling
windowと同projectの利用に対する余裕が不足していた。品質設定は変えず、間隔を5.1秒へ広げて
約12 RPMとし、成功済み15件を次runへ引き継ぐ。次回carryoverは41 calls・US$0.02538575で、
残り85件を全て3 calls使う場合でも累計298 callsとなり、302上限内に収まる。

5.1秒pacerで成功済み15件から再開したrunは、TH008 paraphraseを成功へ変えた後、TH009 formalの
GeneratorでGemini 503 `high demand`となりfail-fastした。成功済みは16表現、失敗1、累計47
logical calls、推定US$0.03286925、gold未開封である。RPM制限ではなくproviderの一時的な可用性
障害で、pacing変更の追加根拠にはしない。成功16件はhash付きpartial artifactに保持し、次回は
carryover 47 calls・US$0.03286925で残り84件から再開できる。追加runは未実行。

予定したheartbeatが14:11を過ぎても実行artifactを作成しなかったため、同じ承認済み条件で手動再開
した。v5の成功16件を引き継いだv6は、合計41 prediction（成功39、失敗2）まで進み、TH021 formalの
GeneratorでGemini 503 `high demand`を検出してfail-fastした。今回51 logical calls、推定
US$0.02383025、carryover込み98 calls・US$0.0616995、gold未開封である。

もう1件の失敗はTH014 formalで、provider障害ではなく、分類結果が根拠十分を示した一方で表示条件を
満たさず`ValueError`となったアプリケーション上の失敗である。このrecordを単純に再実行して成功だけを
引き継ぐとholdout評価を有利に選別するおそれがあるため、次runは直ちに行わない。次の最小手順は、
provider失敗だけを再実行対象とし、TH014のような候補pipelineの失敗を評価対象として固定できるよう、
resume・freeze規則をgoldを開かずに監査することである。

resume・freeze規則を修正し、成功recordと非providerの候補失敗を固定して引き継ぎ、503等のprovider
失敗だけを再実行対象にした。候補失敗を含む100件は実行失敗として採点可能にし、provider失敗が
残るbundleはfreezeできない検査を追加した。v7はTH014を候補失敗として保持し、TH021の503だけを
再実行して成功した。その後、TH026 paraphraseで同じ表示条件`ValueError`が発生したため2件目の
候補失敗として保持し、TH027 paraphraseのGeneratorがGemini 503 `high demand`となって
fail-fastした。v7は54 prediction（成功51、候補失敗2、provider失敗1）、carryover込み128
logical calls、推定US$0.080328、gold未開封である。次runは成功51件と候補失敗2件だけを引き継ぎ、
TH027のprovider失敗だけを再実行する。

v8はv7の成功51件と候補失敗2件を引き継ぎ、TH027の503を再実行して成功した。次のTH028
paraphraseで再びGemini 503 `high demand`となりfail-fastした。v8は56 prediction（成功53、
候補失敗2、provider失敗1）、carryover込み136 logical calls、推定US$0.08829025、gold未開封で
ある。成功と候補失敗の固定は維持されており、次runの再実行対象はTH028のprovider失敗だけである。
同時刻の連続実行は避け、provider負荷が落ち着いてから再開する。

時間を置いたv9はTH028の503を成功へ変え、追加で12件進んだ後、TH034 paraphraseのGeneratorで
Gemini 503 `high demand`となりfail-fastした。v9は68 prediction（成功65、候補失敗2、provider
失敗1）、carryover込み163 logical calls、推定US$0.10529775、gold未開封である。provider
高負荷中の短時間runを重ねると各runのEmbedding費用を消費するため、次は時間を十分に空け、成功65件
と候補失敗2件を引き継いでTH034のprovider失敗だけを再実行する。残り32表現を各最大3 callsで処理
しても累計261 callsで302上限内だが、費用は最悪見積りでUS$0.15に近いため追加runは1回を基本とする。

Gemini公式の503対応に合わせ、retry 0契約を明示的なbounded retryへ改定した。SDK内部retryは無効の
まま、503 `UNAVAILABLE/high demand`だけを初回後に最大2回、5.1秒・10.2秒の指数待機と最大1秒の
jitterで再試行する。429、入力不備、候補pipeline失敗は再試行しない。全attemptを302 calls上限へ
数え、上限到達時は未完了表現を候補失敗として記録せず停止する。候補の検索・prompt・モデル・出力は
変更していない。非integration 308件、Ruff、plan、公開manifest validatorが成功し、goldは未開封。
参考: https://ai.google.dev/gemini-api/docs/troubleshooting および
https://cloud.google.com/vertex-ai/generative-ai/docs/model-reference/api-errors

指数バックオフを適用したv10は、v9の成功65件と候補失敗2件を固定してTH034の503から再開し、
100 predictionを完走した。途中の503は1回のretryで回復し、最大2 retryは消費しなかった。最終結果は
成功98、候補pipeline失敗2（TH014 formal、TH026 paraphrase）、provider失敗0、累計232/302
logical calls、推定US$0.144191/US$0.15である。100件の一意性とprediction hashを確認し、public
manifestを`PREDICTIONS_FROZEN`へ進めた。goldは未開封で、公開validatorとRuffが成功した。
次の工程は、ユーザーの明示承認後にgoldを開封し、固定済みpredictionを受入採点することである。

ユーザー承認後、固定済みprediction hashを再確認してgoldを開封し、100表現を受入採点した。総合回答
成功83/100（83.0%、Wilson 95% 74.5%–89.1%）、scenario stability 39/50（78.0%、
64.8%–87.2%）。document retrievalとevidence retrievalは各100/100、回答分類86/100、回答内容
94/100、実行98/100だった。総合失敗17件の最大要因は分類14件で、内訳は`根拠十分→判断要`9件、
`判断要→根拠十分`3件、実行失敗による分類不能2件。内容失敗は、具体期限を起算規則までしか返さない
TH011・TH039の各2表現と、候補pipeline実行失敗2件である。詳細は
[`TEXT_HOLDOUT_ACCEPTANCE_RESULTS.md`](../eval/TEXT_HOLDOUT_ACCEPTANCE_RESULTS.md)へ保存した。

public manifestは`CONSUMED`へ進み、同じsealed holdoutを追加改善の選択に再利用しない。次の最小手順は、
holdoutで判明した分類の過剰慎重と具体期限計算不足を、開発評価側へ一般化したfixtureとして追加し、
改善候補を開発セットで選ぶことである。

回答契約v2、typed missing condition、決定的な暦日計算を合成12件でpilotした後、formal 100問へ
段階評価した。初期v2は17問で既存成功5件を退行させたため早期停止し、質問範囲gateを追加した
v2.2は小pilotを通過した。しかし100問回帰では分類一致88/100、semantic success 93/100、
不一致15件となり、広いtyped condition変更は不採用とした。100問runは204 logical calls、
US$0.1070345、provider error 0で完走し、採用gate不合格時点で図表30問を実行しなかった。

改善を分離し、通常質問は既存v1生成・classifier v1を維持し、具体的な起算日と期限日を質問する場合
だけ`answer-output-v1.1`、決定的date calculator、日付専用classifier補足へrouteする構成へ縮小した。
日付6件とcontrol 2件の再評価は8/8総合成功、16 logical calls、US$0.0040205、provider error 0。
safe fallbackは監査用status付きで維持し、typed v2は実験artifactだけ残した。詳細は
[`ANSWER_CONTRACT_V2_SCOPE_REFINEMENT.md`](../eval/ANSWER_CONTRACT_V2_SCOPE_REFINEMENT.md)を参照する。
次の最小手順は全ローカル回帰とintegration smokeを確定し、日付route用の小さい未知表現holdoutを
設計すること。production deploy、sealed holdout開封は実施していない。

日付route判定を、保存済みQuality streakとversioned experimentを組み合わせたbounded loopで
再評価した。開始時のCodex利用率は50%、対象は`should_use_deadline_calculation()`、最大2修正round、
外部API 0回と固定した。baselineは20件中11件、適合率54.5%、再現率60.0%で、ISO日付等の
false negative 4件と、営業日・一般ルール等のfalse positive 5件が見つかった。

第1 roundで、対応日付形式、起算日の明示、具体期限の意図、未対応calendarの除外を一般条件として
実装した。開発20/20、凍結acceptance 12/12となり、追加修正せず停止した。Gemini・Embedding・
cloud呼び出しは0、推定API費用US$0。acceptanceはsealed holdoutではなく、実行後に回帰testへ
昇格した。詳細は[`DEADLINE_ROUTE_LOOP.md`](../eval/DEADLINE_ROUTE_LOOP.md)を参照する。

日付routeの公開前影響監査として、固定500問を旧判定と新判定で比較した。全500問、formal 100問
ともroute発火・判定変更は0件だった。130問回帰の残る30問はvisual別経路であるため、日付変更による
再生成対象は0件と確定した。保存済み120/130は維持値として再利用し、改善値とは扱わない。

新規route表現4件だけを生成・決定的計算・分類・表示まで通し、4/4総合成功だった。8 logical calls、
input 1,822・output 1,247 tokens、推定US$0.002326、provider error 0、sealed holdout未使用である。
第1 roundでgateを通過したため第2 roundは行わなかった。統合release gateは合格。次の最小手順は
非integration・integration・Ruffを確定し、PR差分をreviewしてmerge・production deployの承認境界へ
進むこと。詳細は[`POST_HOLDOUT_TARGETED_RELEASE_GATE.md`](../eval/POST_HOLDOUT_TARGETED_RELEASE_GATE.md)
を参照する。

release候補の固定checklistとして、非integration 368件、実PostgreSQL・Qdrant integration 3件、
Ruff、diff検査がすべて成功した。評価結果とREADMEは、既存130問の維持値120/130と、新規日付表現
4/4を分けて記載している。次はcommit・push後のPR reviewで、mergeとproduction deployは明示承認が
必要である。
