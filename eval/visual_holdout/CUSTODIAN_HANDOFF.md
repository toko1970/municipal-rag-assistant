# Visual sealed holdout custodian handoff

## この文書を使う場面

この文書は、RAG実装・調整を行うタスクとは別のCodexタスクへ渡す。別タスクを使う理由は、実装担当がholdout PDFとgoldを見た状態で検索・抽出・promptを調整することを防ぐためである。

作成後、この実装タスクへ伝えるのは、完了状態、公開質問、artifactのSHA-256、検証件数だけとする。PDF本文、gold回答、scenarioごとの期待分類、根拠要素は回答へ貼らない。

## Custodianタスクへ渡す依頼文

以下を新しいタスクへそのまま渡せる。

```text
このリポジトリのvisual sealed holdout custodianとして作業してください。

最初にAGENTS.md、design/TEST_STRATEGY.md、eval/visual_holdout/README.md、eval/visual_holdout/scenario_blueprint.json、eval/visual_holdout/public_manifest.jsonを読んでください。development fixtureのdocument_familyと重複しない、完全に架空のholdout PDFとgoldを作成してください。

必須条件:
- source PDFとgold本体はeval/visual_holdout/.sealed/だけに保存する
- 実在する自治体名、個人情報、実データを使わない
- scenarioはVH001〜VH020の20件
- 図表構成、期待分類、難度の集計はscenario_blueprint.jsonと完全に一致させる
- scenarioごとの期待分類、正解、根拠、bbox、表セル、flow edgeを公開ファイルや応答へ書かない
- 公開するのは質問文、document ID、document family、kind、SHA-256だけ
- developmentとのdocument family重複を0件にする
- public_manifest.jsonをPLANNEDからSEALEDへ進める
- candidate、predictions、opening、resultsはnullのままにする
- eval.validate_visual_holdout_protocolを--sealed-root付きで実行する
- testとlintを実行し、失敗を残したまま完了扱いにしない

完了報告には、作成件数、種類別件数、hash検証結果、test結果だけを書いてください。PDF内容、gold内容、scenario別の期待分類や正解は書かないでください。
```

## Local artifact layout

```text
eval/visual_holdout/.sealed/
├── documents/
│   └── <document_id>.pdf
└── gold/
    ├── extraction_gold.json
    └── scenario_gold.json
```

`.sealed/`は`.gitignore`対象である。custodianタスクは、`git status --ignored`で対象になっていることを確認する。

## 公開artifact

Custodianは次だけをGit管理対象にする。

1. `eval/visual_holdout/questions.json`
   - `holdout_id`
   - `scenario_count`
   - `scenarios[].scenario_id`
   - `scenarios[].question`
2. `eval/visual_holdout/public_manifest.json`
   - stateを`SEALED`へ変更
   - questionsのpath、SHA-256、count
   - documentsのID、family、kind、PDFのSHA-256
   - extraction goldとscenario goldのSHA-256

公開質問にexpected answer、expected classification、difficulty、evidence、missing conditionを含めない。

## Goldの検査責任

実装タスクは開封前にgold本体を読めないため、次はcustodian側で検査する。

- extraction goldが`visual-extraction-v1.schema.json`とsemantic validatorを通る
- scenario IDがVH001〜VH020で一意
- `grounded` 12件、`needs_judgment` 4件、`insufficient_documents` 4件
- direct 6件、multi element 6件、boundary/revision 4件、paraphrase/typo 4件
- 処理flow 4件、判断flow 4件、表4件、帳票3件、timeline 2件、改定比較3件
- groundedは根拠あり、needs judgmentは根拠と不足条件あり、insufficient documentsはcorpus answerability false
- 全gold参照が対応するdocumentのnode、edge、cell、field、eventに存在する

この検査結果は件数だけを報告し、scenario別の内訳は報告しない。

## Seal完了後の戻り方

実装タスクでは公開manifestに対して次だけを実行する。

```bash
.venv/bin/python -m eval.validate_visual_holdout_protocol \
  eval/visual_holdout/public_manifest.json
```

この通常検証は`.sealed/`を読まない。`--sealed-root`による実体照合はcustodianタスクだけが実行する。次に実装タスクはdevelopment setだけで候補実装を調整し、`CANDIDATE_FROZEN`へ進める。
