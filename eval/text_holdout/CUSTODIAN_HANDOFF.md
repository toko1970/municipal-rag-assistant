# Text sealed holdout custodian handoff

## この文書を使う場面

この文書は、RAG実装・調整を行うタスクとは別のCodexタスクへ渡す。実装担当がholdoutのsource Markdownとgoldを見た状態で検索、chunk、promptを調整することを防ぐためである。

作成後に実装タスクへ伝えるのは、完了状態、公開質問、artifactのSHA-256、集計件数、検証結果だけとする。source本文、gold回答、scenarioごとの難度・期待分類・根拠は応答へ貼らない。

## Custodianタスクへ渡す依頼文

```text
このリポジトリのtext sealed holdout custodianとして作業してください。

最初にAGENTS.md、design/TEST_STRATEGY.md、eval/text_holdout/README.md、eval/text_holdout/scenario_blueprint.json、eval/text_holdout/public_manifest.jsonを読んでください。既存text development setとdocument family、制度名、文書ID、見出し、文面が重ならない、完全に架空のsource Markdown、公開質問、非公開goldを作成してください。

Evidence-first feature loopでscenarioを一つずつ作り、各scenarioにformalとparaphrase_or_noisyを1件ずつ用意してください。全50 scenarioを作成後、Quality streak loopでTH001からTH050まで固定順に検査してください。

必須条件:
- source Markdownとgold本体はeval/text_holdout/.sealed/だけに保存する
- 各MarkdownのYAML front matterにpublic manifestと一致するdocument_idとdocument_familyを設定する
- 実在する自治体名、個人情報、実データを使わない
- scenarioはTH001〜TH050の50件、質問は合計100表現
- 分類、難度、表現の集計はscenario_blueprint.jsonと完全に一致させる
- 最低5つのdocument familyを使い、developmentとのfamily重複を0件にする
- scenarioごとの難度、期待分類、正解、根拠、参照文書、missing conditionを公開ファイルや応答へ書かない
- 公開するのは質問文、document ID、document family、format、SHA-256だけ
- public_manifest.jsonをPLANNEDからSEALEDへ進める
- candidate、predictions、opening、resultsはnullのままにする
- eval.validate_text_holdout_protocolを--sealed-root付きで実行する
- testとlintを実行し、失敗を残したまま完了扱いにしない

Quality streakの品質基準:
- 1 scenarioにformalとparaphrase_or_noisyが1件ずつある
- 2表現が同じgold条件を共有する
- goldのclassification契約、document参照、配分がvalidatorを通る
- failureを発見したら原因を記録し、必要な回帰testまたはvalidator修正を追加してstreakを0へ戻す
- 50 scenario連続成功で完了する
- 最大2 repair round、同じ失敗が改善しない、仕様変更が必要、またはCodex利用率80%以上でcheckpointを残して停止する

完了報告には、文書数、family数、scenario数、表現数、分類・難度の集計、hash検証、streak、test、lintの結果だけを書いてください。source本文、gold内容、scenario別の期待分類や正解は書かないでください。
```

## Local artifact layout

```text
eval/text_holdout/.sealed/
├── documents/
│   └── <document_id>.md
└── gold/
    └── scenario_gold.json
```

`.sealed/`は`.gitignore`対象である。custodianは`git status --ignored`で確認する。

## 公開artifact

Custodianは次だけをGit管理対象にする。

1. `eval/text_holdout/questions.json`
   - `holdout_id`
   - 50 scenario / 100表現の件数
   - `scenarios[].scenario_id`
   - `expressions[].variant_type`
   - `expressions[].question`
2. `eval/text_holdout/public_manifest.json`
   - stateを`SEALED`へ変更
   - questionsのpath、SHA-256、件数
   - documentsのID、family、format、SHA-256
   - scenario goldのSHA-256と件数

公開質問にdifficulty、expected classification、expected answer、expected evidence、expected document、missing conditionを含めない。

## Goldの検査責任

実装タスクは開封前にgold本体を読めないため、custodian側で次を検査する。

- goldが`text-holdout-gold-v1.schema.json`を通る
- scenario IDがTH001〜TH050で一意かつ順序固定
- grounded 30件、needs judgment 10件、insufficient documents 10件
- single document direct 15件、multi document 15件、boundary/effective date 10件、similar/absent 10件
- groundedは`expected_corpus_answerability=true`で根拠あり
- needs judgmentは`expected_corpus_answerability=true`で根拠とmissing conditionあり
- insufficient documentsは`expected_corpus_answerability=false`で参照文書・根拠・missing conditionなし
- 全gold参照がmanifestに固定したdocument IDを参照する

検査結果は集計だけを報告し、scenario別の内訳は報告しない。

## Seal完了後の戻り方

実装タスクでは公開manifestに対して通常validatorだけを実行する。

```bash
.venv/bin/python -m eval.validate_text_holdout_protocol \
  eval/text_holdout/public_manifest.json
```

この検証は`.sealed/`を読まない。`--sealed-root`による実体照合はcustodianタスクだけが実行する。次に実装タスクはdevelopment setだけで候補実装を調整し、`CANDIDATE_FROZEN`へ進める。
