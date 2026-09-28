# 図表sealed holdout運用手順

## 目的

このdirectoryは、PDF・図表RAGの最終受入に使う20 scenarioの未見性を守る。holdoutはvalidator単体ではなく、PDF取込、検索、回答生成、回答分類を通したend-to-end評価に使う。

実装担当がholdout PDFやgold annotationを見て調整すると、未知文書への汎化性能を測れない。そのため、ユーザーをgold custodianとし、source PDFとgold本体を`.sealed/`に置く。`.sealed/`はGit管理しない。

実際のholdout作成は、この実装タスクと分離したタスクで[`CUSTODIAN_HANDOFF.md`](CUSTODIAN_HANDOFF.md)を使って行う。

## Git管理するもの

- `scenario_blueprint.json`: 20 scenarioのIDと、全体の種類・難度・期待分類の件数
- `public_manifest.json`: 状態、公開質問、sealed artifactのSHA-256、候補実装、予測結果の固定記録
- この手順とvalidator

scenarioごとの期待分類、正解回答、根拠、bbox、表セル、flow edgeは公開blueprintへ書かない。集計件数だけを先に固定する。

## Git管理しないもの

```text
eval/visual_holdout/.sealed/
├── documents/
│   └── <document_id>.pdf
└── gold/
    ├── extraction_gold.json
    └── scenario_gold.json
```

gold custodian以外は、予測結果の固定が終わるまでこのdirectoryを開かない。

## 状態遷移

1. `PLANNED`: 構成と20個のscenario IDだけを固定する。
2. `SEALED`: custodianが別文書familyのPDF、公開質問、非公開goldを作り、SHA-256だけを`public_manifest.json`へ記録する。
3. `CANDIDATE_FROZEN`: development setだけで候補実装を選び、Git commitと設定manifestのhashを固定する。
4. `PREDICTIONS_FROZEN`: sealed PDFを初めて候補実装へ入力し、run IDと予測結果のhashを固定する。goldはまだ開かない。
5. `OPENED`: custodianがgoldを開き、記録済みhashとの一致を確認する。
6. `CONSUMED`: scoreと失敗例を保存し、結果ファイルのhashを記録する。このholdoutを再びsealed扱いにしない。

各段階はGit commitで履歴を残す。途中の状態を飛ばさず、公開manifestの既存hashを書き換えない。

`CANDIDATE_FROZEN`で固定する設定本体は`candidate_config.json`である。モデル、prompt、Embedding profile、検索件数、画像上限、retry方針、選定に使ったdevelopment artifact、公開Cloud Run revisionを記録し、`public_manifest.json`からSHA-256で参照する。この段階では`.sealed/`を読まない。

予測runnerはgoldのpathを引数に持たない。候補固定後、まず次の`plan`で20問、6 PDF、最大67 logical external call、retry 0、費用上限を確認する。`run`は明示的な開封承認後にだけ実行する。

```bash
.venv/bin/python -m eval.run_visual_holdout_predictions plan
```

## 検証方法

公開情報だけを検証する通常のコマンドは、sealed artifactを読み込まない。

```bash
.venv/bin/python -m eval.validate_visual_holdout_protocol \
  eval/visual_holdout/public_manifest.json
```

`SEALED`以降、gold custodianが手元のartifactと公開hashを照合するときだけ`--sealed-root`を付ける。

```bash
.venv/bin/python -m eval.validate_visual_holdout_protocol \
  eval/visual_holdout/public_manifest.json \
  --sealed-root eval/visual_holdout/.sealed
```

## 学習上の要点

- fixtureは入力文書、goldは期待結果、manifestは「どの版を評価したか」の固定記録で、役割が異なる。
- SHA-256は内容を公開せず、開封したファイルが事前に固定したものか確認するために使う。
- 候補実装と予測をgoldより先に固定することで、正解を見た後の調整を防ぐ。
- 一度開封したholdoutはdevelopment結果として分析できるが、次の最終受入には新しいholdoutが必要になる。
