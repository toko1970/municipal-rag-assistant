# Phase 0 contract conformance ledger

- 監査日: 2026-09-27
- 対象基準: `e286581`からの低品質scan fixture差分を含む
- 対象範囲: 仕様、fixture、evaluation set、manifest、validator、test
- sealed境界: text・visualの`.sealed/`は開かず、公開manifestとcustodianの集計結果だけを証拠にした
- 判定: **Phase 0は未完了**

## 1. 判定方法

| 状態 | 意味 |
|---|---|
| `proved` | repository内のartifactと検証結果で要求を確認できる |
| `weak` | 一部の証拠はあるが、要求全体を確認できない |
| `contradicted` | 現在のartifactが要求と矛盾する |
| `unimplemented` | 要求に対応するartifactまたは検証がない |
| `not_applicable` | 現在のPhaseには適用しない |
| `blocked` | 外部承認や外部状態がなければ進められない |

## 2. Evidence ledger

| ID | 要求 | 状態 | 証拠 | 判定理由・残課題 |
|---|---|---|---|---|
| P0-01 | RAGの対象、非目標、回答・分類・保存・評価境界を仕様化する | `proved` | [`TARGET_RAG_SPEC.md`](TARGET_RAG_SPEC.md)、[`TECHNICAL_DESIGN.md`](TECHNICAL_DESIGN.md)、[`DATA_MODEL.md`](DATA_MODEL.md)、[`SPEC_CHANGE_SUMMARY.md`](SPEC_CHANGE_SUMMARY.md) | Generator、classifier、`expected_corpus_answerability`、PostgreSQL/Qdrant/GCSの責務を追跡できる |
| P0-02 | 既存100 scenario / 500表現をtext development v1.0として固定する | `proved` | [`evaluation_set_manifest.json`](../eval/evaluation_set_manifest.json)、[`evaluation_questions_500.csv`](../eval/evaluation_questions_500.csv)、`tests/test_large_evaluation_set.py` | 100 scenario、500表現、承認日、SHA-256が固定されている |
| P0-03 | 別文書familyのtext sealed holdout 50 scenario / 100表現を作る | `proved` | [`scenario_blueprint.json`](../eval/text_holdout/scenario_blueprint.json)、[`questions.json`](../eval/text_holdout/questions.json)、[`public_manifest.json`](../eval/text_holdout/public_manifest.json)、`tests/test_text_holdout_protocol.py` | 10文書、5 family、50 scenario、100表現を固定し、分類30/10/10・難度15/15/10/10・50件連続成功をcustodianが検証した。通常validatorではsealed内容を開いていない |
| P0-04 | 必須6図表のdevelopment fixtureとgoldを機械可読にする | `proved` | [`development_manifest.json`](../eval/visual_fixtures/manifests/development_manifest.json)、[`visual-extraction-v1.schema.json`](schemas/visual-extraction-v1.schema.json)、`tests/test_visual_fixture_validation.py` | flow 2種、timeline、table、form、改定比較のPDF・画像・gold・hashがある |
| P0-05 | 必須6図表のholdoutを別document familyで封印する | `proved` | [`public_manifest.json`](../eval/visual_holdout/public_manifest.json)、[`scenario_blueprint.json`](../eval/visual_holdout/scenario_blueprint.json)、[`CUSTODIAN_HANDOFF.md`](../eval/visual_holdout/CUSTODIAN_HANDOFF.md) | 6 family、PDF/gold hash、20質問を公開し、sealed本体をGit対象外にした。実装タスクでは内容を開いていない |
| P0-06 | 図表development 30 scenarioを改善用に固定する | `proved` | [`development_evaluation_set.json`](../eval/visual_fixtures/development_evaluation_set.json)、[`development_evaluation_manifest.json`](../eval/visual_fixtures/manifests/development_evaluation_manifest.json)、`tests/test_visual_evaluation_set.py` | 6 fixtureへ5件ずつ、分類18/6/6、gold element参照、`user_approved`を検証する |
| P0-07 | 図表sealed holdout 20 scenarioの未見評価境界を固定する | `proved` | [`questions.json`](../eval/visual_holdout/questions.json)、[`public_manifest.json`](../eval/visual_holdout/public_manifest.json)、`tests/test_visual_holdout_protocol.py` | 状態は`SEALED`。候補、予測、開封、結果は未設定で、通常validatorはsealed内容を読まない |
| P0-08 | native text PDF fixtureを用意する | `proved` | [`development_manifest.json`](../eval/text_pdf_fixtures/manifests/development_manifest.json)、[`native_text_dev_001.json`](../eval/text_pdf_fixtures/gold/native_text_dev_001.json)、[`native-text-extraction-v1.schema.json`](schemas/native-text-extraction-v1.schema.json)、`tests/test_native_text_fixture.py` | text layer、期待全文、重要値、page、bbox、画像、hashを固定した。PyMuPDFによる全文・座標検査、目視確認、再生成hash一致、87 testを確認した |
| P0-09 | 日本語scan PDF fixtureを用意する | `proved` | [`scan_development_manifest.json`](../eval/text_pdf_fixtures/manifests/scan_development_manifest.json)、[`scan_text_dev_001.json`](../eval/text_pdf_fixtures/gold/scan_text_dev_001.json)、[`scan-text-extraction-v1.schema.json`](schemas/scan-text-extraction-v1.schema.json)、`tests/test_scan_text_fixture.py` | 画像のみの日本語PDF、300 dpi source、期待全文、重要値、region bbox、hashを固定した。text layerなし、埋め込み画像、OCR候補の重要値・全文差分検査、目視確認、再生成hash一致、93 testを確認した |
| P0-10 | 回転ページfixtureを用意する | `proved` | [`rotation_development_manifest.json`](../eval/text_pdf_fixtures/manifests/rotation_development_manifest.json)、[`rotated-scan-extraction-v1.schema.json`](schemas/rotated-scan-extraction-v1.schema.json)、`tests/test_rotated_scan_fixture.py` | 正立0度に加えてPDFの`/Rotate`が90/180/270度の3 fixtureを固定した。raw表示、正立化、座標空間、hashを検査し、正規化画像3件が正立referenceと一致、再生成13 artifact一致、99 testを確認した |
| P0-11 | 曖昧矢印または低品質scanを`REVIEW_REQUIRED`にする | `proved` | [`low_quality_development_manifest.json`](../eval/text_pdf_fixtures/manifests/low_quality_development_manifest.json)、[`low_quality_scan_dev_001.json`](../eval/text_pdf_fixtures/gold/low_quality_scan_dev_001.json)、[`low-quality-scan-v1.schema.json`](schemas/low-quality-scan-v1.schema.json)、`tests/test_low_quality_scan_fixture.py` | clean画像へ低コントラストだけを加えた失敗系fixtureを固定した。`REVIEW_REQUIRED`、`WAITING_REVIEW`、`LOW_CONTRAST`、自動`READY`不可を検査し、改変拒否、再生成5 artifact一致、106 testを確認した |
| P0-12 | 重要値完全一致、要素recall、bbox IoUを測る | `not_applicable` | `eval/validate_visual_fixture.py`、`tests/test_visual_fixture_validation.py`、[`IMPLEMENTATION_PLAN.md`](IMPLEMENTATION_PLAN.md) Phase 4 | Phase 0は比較可能なgoldと評価契約を用意する段階。抽出器出力とgoldを比較するrecall・IoU evaluatorはPhase 4の受入条件として実装する |
| P0-13 | manifestにsplit、文書、質問、schemaのhashを持つ | `proved` | visualの2 manifest、text developmentの[`evaluation_set_manifest.json`](../eval/evaluation_set_manifest.json)、text holdoutの[`public_manifest.json`](../eval/text_holdout/public_manifest.json) | text developmentとtext・visual holdoutで、split、文書、質問、Schema、blueprint、goldの必要なhashを追跡できる |
| P0-14 | holdoutを実装調整に使わず、候補・予測・開封順を検査する | `proved` | text・visual holdoutのREADME、public manifest、protocol validator、test | 両holdoutが`SEALED`で、candidate、predictions、opening、resultsは未設定。通常validatorはsealed内容を読まない |
| P0-15 | Cloud SQL、GCS、Qdrant Cloud、Geminiの最小接続・費用・停止手順を確認する | `unimplemented` | [`IMPLEMENTATION_PLAN.md`](IMPLEMENTATION_PLAN.md) §2 Phase 0、[`LEARNING_AND_USAGE_PLAN.md`](LEARNING_AND_USAGE_PLAN.md) §6 | 目標構成と予算条件は仕様化したが、接続spikeのrun record、実測費用、停止手順がない。課金resource作成は事前承認が必要 |
| P0-16 | 秘密情報と本番個人情報をrepositoryへ保存しない | `proved` | `.gitignore`、架空fixture、公開manifest | `.env`とsealed本体を除外し、公開artifactにはhashと架空識別子だけを置いている |

## 3. 2026-09-27再確認結果

| 状態 | 件数 |
|---|---:|
| proved | 14 |
| weak | 0 |
| contradicted | 0 |
| unimplemented | 1 |
| not applicable | 1 |
| blocked | 0 |

silent gapはない。P0-03、P0-08〜P0-11、P0-13を証拠付きで解消し、未完了1件をPhase 0完了前の作業として追跡する。Phase 4で実装する1件はPhase 0の完了判定から除外し、Phase 4の受入時に再監査する。

## 4. 修正判断

text sealed holdout、native text PDF、日本語scan PDF、回転・低品質fixtureにより、P0-03、P0-08〜P0-11、P0-13を解消した。

- P0-12の抽出精度evaluatorは抽出器出力ができるPhase 4で初めて意味のある比較ができる。Phase 0ではgoldと評価契約を準備済みとし、Phase 4のledgerへ引き継ぐ。
- P0-15はserviceごとに接続、認証、費用、停止を確認する。課金resourceを作成する前にユーザー承認を得る。

大きな未実装を文書だけで合格扱いにする修正や、Phase 4の実装をPhase 0へ前倒しする修正は行わない。

## 5. 次の順序

1. **Cloud connection spikes**: Gemini、Cloud SQL、GCS、Qdrant Cloudを個別に調査し、無料でできる確認と課金が必要な操作を分ける。
2. **再監査**: P0-15の証拠を更新してPhase 0完了を判定する。

## 6. 未達項目の解消先

| 対象 | 解消する工程 | 完了証拠 |
|---|---|---|
| P0-15 cloud接続・費用 | Phase 0最後のservice別spike | 接続先、認証方式、見積・実測費用、停止手順。課金resource作成前はユーザー承認 |
| P0-12 抽出精度evaluator | Phase 4 | 実抽出結果とgoldの重要値一致率、要素recall、bbox IoUのreportとtest |

最初の次工程は、**service別cloud接続・費用spike**とする。
