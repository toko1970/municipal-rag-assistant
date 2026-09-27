# 作業再開checkpoint

- 記録日: 2026-09-27
- 状態: cloud serviceのread-only調査完了。次はGeminiの最小接続spike実行票と承認
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

## 2. 未完了・次回反映すること

- 既存100シナリオ・500問を新しい論理locatorへ移行する処理は、Phase 2以降のingestion実装で具体化する。
- Cloud SQL、GCS、Qdrant Cloud、Geminiのread-only調査は完了した。Geminiから順に承認済みの最小接続spikeを行う。
- 30 scenarioを実行する評価harnessは、Phase 4・5の取込・回答実装と合わせて追加する。
- Phase 0の全要求が揃った段階でcontract conformance loopを再実行する。

## 3. 次回最初に行うこと

1. Codexの5時間枠・週間枠を確認する。
2. `git status`と本checkpointを確認する。
3. [`PHASE0_CONFORMANCE.md`](PHASE0_CONFORMANCE.md)の未実装とweakを確認する。
4. [`CLOUD_SERVICE_SPIKES.md`](CLOUD_SERVICE_SPIKES.md)からGeminiの実行票を作り、1 request、概算`$0.01`未満、停止手順を固定する。
5. 外部APIを呼ぶ前に実行票を提示してユーザー承認を得る。

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
