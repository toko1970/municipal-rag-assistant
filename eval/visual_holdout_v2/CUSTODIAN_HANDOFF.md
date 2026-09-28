# Visual sealed holdout v2 custodian handoff

## 別タスクへ渡す依頼

```text
このリポジトリのvisual sealed holdout v2 custodianとして作業してください。

AGENTS.md、design/TEST_STRATEGY.md、eval/visual_holdout_v2/README.md、scenario_blueprint.json、public_manifest.jsonを読んでください。development fixtureおよびv1 holdoutと重複しない、完全に架空の4つのdocument familyから1 page PDFを4件作成し、10問の公開質問と非公開goldを作成してください。

必須条件:
- PDFとgold本体はeval/visual_holdout_v2/.sealed/だけに保存する
- 実在する自治体名、個人情報、実データを使わない
- scenario IDはVH2-001〜VH2-010とし、blueprintの種類・分類・難度件数に一致させる
- process flow、decision flow、table、formのPDFを各1件作る
- flow 2件は開始、分岐、合流または終了を含み、v1文書の単なる言い換えにしない
- 公開質問に期待分類、正解、難度、根拠、欠落条件を書かない
- scenario別gold、bbox、node、edge、cell、fieldは応答やGit管理ファイルへ出さない
- public_manifest.jsonをPLANNEDからSEALEDへ進め、candidate以降はnullのままにする
- .sealedのgoldをschemaとsemantic validatorで検証する
- scenario goldはdesign/schemas/visual-holdout-scenario-gold-v2.schema.jsonへ適合させる
- expected_answer_key_termsは回答に必要な最小語句を配列で固定し、表記揺れを許す場合はgold作成時に正規化した共通部分を選ぶ
- --sealed-root付きprotocol validation、test、lintを実行する

完了報告は、作成件数、種類別件数、分類・難度の集計、hash検証、test結果だけにしてください。内容やscenario別正解は報告しないでください。
```

## 公開artifact

- `questions.json`: holdout ID、10件のscenario IDと質問文だけ
- `public_manifest.json`: 文書ID、family、kind、PDF hash、質問hash、gold hash

## 非公開artifact

```text
eval/visual_holdout_v2/.sealed/
├── documents/<document_id>.pdf
└── gold/
    ├── extraction_gold.json
    └── scenario_gold.json
```

Custodianは`git status --ignored`で`.sealed/`がignore対象であることも確認する。
