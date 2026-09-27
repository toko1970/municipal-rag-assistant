# Phase 0 contract conformance ledger

- 監査日: 2026-09-27
- 対象commit: `6dc1048`
- 対象範囲: 仕様、fixture、evaluation set、manifest、validator、test
- sealed境界: `eval/visual_holdout/.sealed/`は開かず、公開manifestとcustodianの集計結果だけを証拠にした
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
| P0-03 | 別文書familyのtext sealed holdout 50 scenario / 100表現を作る | `unimplemented` | [`scenario_blueprint.json`](../eval/text_holdout/scenario_blueprint.json)、[`public_manifest.json`](../eval/text_holdout/public_manifest.json)、[`CUSTODIAN_HANDOFF.md`](../eval/text_holdout/CUSTODIAN_HANDOFF.md) | custody contract、Schema、validatorは実装済み。実文書、公開質問、gold hashはcustodian工程前で、manifestは`PLANNED` |
| P0-04 | 必須6図表のdevelopment fixtureとgoldを機械可読にする | `proved` | [`development_manifest.json`](../eval/visual_fixtures/manifests/development_manifest.json)、[`visual-extraction-v1.schema.json`](schemas/visual-extraction-v1.schema.json)、`tests/test_visual_fixture_validation.py` | flow 2種、timeline、table、form、改定比較のPDF・画像・gold・hashがある |
| P0-05 | 必須6図表のholdoutを別document familyで封印する | `proved` | [`public_manifest.json`](../eval/visual_holdout/public_manifest.json)、[`scenario_blueprint.json`](../eval/visual_holdout/scenario_blueprint.json)、[`CUSTODIAN_HANDOFF.md`](../eval/visual_holdout/CUSTODIAN_HANDOFF.md) | 6 family、PDF/gold hash、20質問を公開し、sealed本体をGit対象外にした。実装タスクでは内容を開いていない |
| P0-06 | 図表development 30 scenarioを改善用に固定する | `proved` | [`development_evaluation_set.json`](../eval/visual_fixtures/development_evaluation_set.json)、[`development_evaluation_manifest.json`](../eval/visual_fixtures/manifests/development_evaluation_manifest.json)、`tests/test_visual_evaluation_set.py` | 6 fixtureへ5件ずつ、分類18/6/6、gold element参照、`user_approved`を検証する |
| P0-07 | 図表sealed holdout 20 scenarioの未見評価境界を固定する | `proved` | [`questions.json`](../eval/visual_holdout/questions.json)、[`public_manifest.json`](../eval/visual_holdout/public_manifest.json)、`tests/test_visual_holdout_protocol.py` | 状態は`SEALED`。候補、予測、開封、結果は未設定で、通常validatorはsealed内容を読まない |
| P0-08 | native text PDF fixtureを用意する | `unimplemented` | [`TEST_STRATEGY.md`](TEST_STRATEGY.md) §2.3 | 現在の6 development PDFは図表fixtureで、native text抽出専用の期待値とtestがない |
| P0-09 | 日本語scan PDF fixtureを用意する | `unimplemented` | [`TEST_STRATEGY.md`](TEST_STRATEGY.md) §2.3 | OCR入力、期待全文、OCR誤りの検証fixtureがない |
| P0-10 | 回転ページfixtureを用意する | `unimplemented` | [`TEST_STRATEGY.md`](TEST_STRATEGY.md) §2.3、[`TECHNICAL_DESIGN.md`](TECHNICAL_DESIGN.md) §3 | 0/90/180/270度を対象にしているが、回転補正を検証するfixtureとtestがない |
| P0-11 | 曖昧矢印または低品質scanを`REVIEW_REQUIRED`にする | `unimplemented` | [`TEST_STRATEGY.md`](TEST_STRATEGY.md) §2.3、[`TECHNICAL_DESIGN.md`](TECHNICAL_DESIGN.md) §3 | 正常なfixtureの`review_required=true`はあるが、曖昧入力を誤って自動合格させない失敗系fixtureがない |
| P0-12 | 重要値完全一致、要素recall、bbox IoUを測る | `not_applicable` | `eval/validate_visual_fixture.py`、`tests/test_visual_fixture_validation.py`、[`IMPLEMENTATION_PLAN.md`](IMPLEMENTATION_PLAN.md) Phase 4 | Phase 0は比較可能なgoldと評価契約を用意する段階。抽出器出力とgoldを比較するrecall・IoU evaluatorはPhase 4の受入条件として実装する |
| P0-13 | manifestにsplit、文書、質問、schemaのhashを持つ | `weak` | visualの2 manifest、text developmentの[`evaluation_set_manifest.json`](../eval/evaluation_set_manifest.json)、text holdoutの[`public_manifest.json`](../eval/text_holdout/public_manifest.json) | text developmentはsplit、5文書、質問、row Schemaのhashを追跡可能。text holdoutはSchema・blueprint・development境界を固定したが、`SEALED`前のため文書・質問hashが未設定 |
| P0-14 | holdoutを実装調整に使わず、候補・予測・開封順を検査する | `proved` | [`visual_holdout/README.md`](../eval/visual_holdout/README.md)、`eval/validate_visual_holdout_protocol.py`、`tests/test_visual_holdout_protocol.py` | visualは状態遷移とhashを検査できる。textへの適用はP0-03で別途必要 |
| P0-15 | Cloud SQL、GCS、Qdrant Cloud、Geminiの最小接続・費用・停止手順を確認する | `unimplemented` | [`IMPLEMENTATION_PLAN.md`](IMPLEMENTATION_PLAN.md) §2 Phase 0、[`LEARNING_AND_USAGE_PLAN.md`](LEARNING_AND_USAGE_PLAN.md) §6 | 目標構成と予算条件は仕様化したが、接続spikeのrun record、実測費用、停止手順がない。課金resource作成は事前承認が必要 |
| P0-16 | 秘密情報と本番個人情報をrepositoryへ保存しない | `proved` | `.gitignore`、架空fixture、公開manifest | `.env`とsealed本体を除外し、公開artifactにはhashと架空識別子だけを置いている |

## 3. 初回監査結果

| 状態 | 件数 |
|---|---:|
| proved | 8 |
| weak | 1 |
| contradicted | 0 |
| unimplemented | 6 |
| not applicable | 1 |
| blocked | 0 |

silent gapはない。未完了6件とweak 1件をPhase 0完了前の作業として明示できた。Phase 4で実装する1件はPhase 0の完了判定から除外し、Phase 4の受入時に再監査する。

## 4. 修正判断

今回のloopでは実装修正を行わない。

- P0-03は50 scenario、100表現、別文書family、custodyをまとめて設計する独立した学習単位になる。
- P0-08〜P0-11はPDF生成、OCR、回転、失敗系判定を含む別のfixture familyであり、一つずつevidence-first sliceを実行する。
- P0-12の抽出精度evaluatorは抽出器出力ができるPhase 4で初めて意味のある比較ができる。Phase 0ではgoldと評価契約を準備済みとし、Phase 4のledgerへ引き継ぐ。
- P0-15はserviceごとに接続、認証、費用、停止を確認する。課金resourceを作成する前にユーザー承認を得る。

大きな未実装を文書だけで合格扱いにする修正や、Phase 4の実装をPhase 0へ前倒しする修正は行わない。

## 5. 次の順序

1. **Text sealed holdout custody**: 50 scenario / 100表現の別文書family、公開質問、非公開gold、manifestを作る。
2. **Extraction edge fixtures**: native text、scan、回転、曖昧/低品質を一種類ずつ追加する。
3. **Cloud connection spikes**: Gemini、Cloud SQL、GCS、Qdrant Cloudを個別に調査し、無料でできる確認と課金が必要な操作を分ける。
4. **再監査**: P0-03、P0-08〜P0-11、P0-13、P0-15の証拠を更新してPhase 0完了を判定する。

## 6. 未達項目の解消先

| 対象 | 解消する工程 | 完了証拠 |
|---|---|---|
| P0-03 text sealed holdout | 次の工程 | 50 scenario / 100表現、別文書family、公開質問、非公開gold hash、SEALED manifest |
| P0-13 manifest hashの不足 | text sealed holdoutと同時 | text development / holdoutのsplit、文書、質問、schema hashを追跡できるmanifest |
| P0-08 native text PDF | extraction edge fixture 1 | text layer、期待全文、page/bboxを持つfixtureとtest |
| P0-09 日本語scan PDF | extraction edge fixture 2 | OCR用scan、期待全文、重要値を持つfixtureとtest |
| P0-10 回転ページ | extraction edge fixture 3 | 回転角を固定したPDFと補正後の期待位置を検査するtest |
| P0-11 曖昧/低品質 | extraction edge fixture 4 | 誤ってREADYにせずREVIEW_REQUIREDとなる失敗系test |
| P0-15 cloud接続・費用 | Phase 0最後のservice別spike | 接続先、認証方式、見積・実測費用、停止手順。課金resource作成前はユーザー承認 |
| P0-12 抽出精度evaluator | Phase 4 | 実抽出結果とgoldの重要値一致率、要素recall、bbox IoUのreportとtest |

最初の次工程は、既存text development setと分離した**text sealed holdout custodyの設計**とする。visual holdoutで確立した状態遷移とgold custodian方式を再利用できるが、同一scenarioのformal / noisy 2表現を同じsplit・同じ重みで扱う検査を追加する。
