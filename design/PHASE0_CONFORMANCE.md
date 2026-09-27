# Phase 0 contract conformance ledger

- 監査日: 2026-09-27
- 対象commit: `fce09df`
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
| P0-08 | native text PDF fixtureを用意する | `unimplemented` | [`TEST_STRATEGY.md`](TEST_STRATEGY.md) §2.3 | 現在の6 development PDFは図表fixtureで、native text抽出専用の期待値とtestがない |
| P0-09 | 日本語scan PDF fixtureを用意する | `unimplemented` | [`TEST_STRATEGY.md`](TEST_STRATEGY.md) §2.3 | OCR入力、期待全文、OCR誤りの検証fixtureがない |
| P0-10 | 回転ページfixtureを用意する | `unimplemented` | [`TEST_STRATEGY.md`](TEST_STRATEGY.md) §2.3、[`TECHNICAL_DESIGN.md`](TECHNICAL_DESIGN.md) §3 | 0/90/180/270度を対象にしているが、回転補正を検証するfixtureとtestがない |
| P0-11 | 曖昧矢印または低品質scanを`REVIEW_REQUIRED`にする | `unimplemented` | [`TEST_STRATEGY.md`](TEST_STRATEGY.md) §2.3、[`TECHNICAL_DESIGN.md`](TECHNICAL_DESIGN.md) §3 | 正常なfixtureの`review_required=true`はあるが、曖昧入力を誤って自動合格させない失敗系fixtureがない |
| P0-12 | 重要値完全一致、要素recall、bbox IoUを測る | `not_applicable` | `eval/validate_visual_fixture.py`、`tests/test_visual_fixture_validation.py`、[`IMPLEMENTATION_PLAN.md`](IMPLEMENTATION_PLAN.md) Phase 4 | Phase 0は比較可能なgoldと評価契約を用意する段階。抽出器出力とgoldを比較するrecall・IoU evaluatorはPhase 4の受入条件として実装する |
| P0-13 | manifestにsplit、文書、質問、schemaのhashを持つ | `proved` | visualの2 manifest、text developmentの[`evaluation_set_manifest.json`](../eval/evaluation_set_manifest.json)、text holdoutの[`public_manifest.json`](../eval/text_holdout/public_manifest.json) | text developmentとtext・visual holdoutで、split、文書、質問、Schema、blueprint、goldの必要なhashを追跡できる |
| P0-14 | holdoutを実装調整に使わず、候補・予測・開封順を検査する | `proved` | text・visual holdoutのREADME、public manifest、protocol validator、test | 両holdoutが`SEALED`で、candidate、predictions、opening、resultsは未設定。通常validatorはsealed内容を読まない |
| P0-15 | Cloud SQL、GCS、Qdrant Cloud、Geminiの最小接続・費用・停止手順を確認する | `unimplemented` | [`IMPLEMENTATION_PLAN.md`](IMPLEMENTATION_PLAN.md) §2 Phase 0、[`LEARNING_AND_USAGE_PLAN.md`](LEARNING_AND_USAGE_PLAN.md) §6 | 目標構成と予算条件は仕様化したが、接続spikeのrun record、実測費用、停止手順がない。課金resource作成は事前承認が必要 |
| P0-16 | 秘密情報と本番個人情報をrepositoryへ保存しない | `proved` | `.gitignore`、架空fixture、公開manifest | `.env`とsealed本体を除外し、公開artifactにはhashと架空識別子だけを置いている |

## 3. 2026-09-27再確認結果

| 状態 | 件数 |
|---|---:|
| proved | 10 |
| weak | 0 |
| contradicted | 0 |
| unimplemented | 5 |
| not applicable | 1 |
| blocked | 0 |

silent gapはない。P0-03とP0-13を証拠付きで解消し、未完了5件をPhase 0完了前の作業として追跡する。Phase 4で実装する1件はPhase 0の完了判定から除外し、Phase 4の受入時に再監査する。

## 4. 修正判断

text sealed holdoutの契約実装とcustodian loopにより、P0-03とP0-13を解消した。

- P0-08〜P0-11はPDF生成、OCR、回転、失敗系判定を含む別のfixture familyであり、一つずつevidence-first sliceを実行する。
- P0-12の抽出精度evaluatorは抽出器出力ができるPhase 4で初めて意味のある比較ができる。Phase 0ではgoldと評価契約を準備済みとし、Phase 4のledgerへ引き継ぐ。
- P0-15はserviceごとに接続、認証、費用、停止を確認する。課金resourceを作成する前にユーザー承認を得る。

大きな未実装を文書だけで合格扱いにする修正や、Phase 4の実装をPhase 0へ前倒しする修正は行わない。

## 5. 次の順序

1. **Extraction edge fixtures**: native text、scan、回転、曖昧/低品質を一種類ずつ追加する。
2. **Cloud connection spikes**: Gemini、Cloud SQL、GCS、Qdrant Cloudを個別に調査し、無料でできる確認と課金が必要な操作を分ける。
3. **再監査**: P0-08〜P0-11、P0-15の証拠を更新してPhase 0完了を判定する。

## 6. 未達項目の解消先

| 対象 | 解消する工程 | 完了証拠 |
|---|---|---|
| P0-08 native text PDF | extraction edge fixture 1 | text layer、期待全文、page/bboxを持つfixtureとtest |
| P0-09 日本語scan PDF | extraction edge fixture 2 | OCR用scan、期待全文、重要値を持つfixtureとtest |
| P0-10 回転ページ | extraction edge fixture 3 | 回転角を固定したPDFと補正後の期待位置を検査するtest |
| P0-11 曖昧/低品質 | extraction edge fixture 4 | 誤ってREADYにせずREVIEW_REQUIREDとなる失敗系test |
| P0-15 cloud接続・費用 | Phase 0最後のservice別spike | 接続先、認証方式、見積・実測費用、停止手順。課金resource作成前はユーザー承認 |
| P0-12 抽出精度evaluator | Phase 4 | 実抽出結果とgoldの重要値一致率、要素recall、bbox IoUのreportとtest |

最初の次工程は、native text PDFを使う**extraction edge fixture 1**とする。
