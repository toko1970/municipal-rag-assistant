# Text sealed holdout運用手順

## 目的

このdirectoryは、text RAGの最終受入に使う50 scenario / 100表現の未見性を守る。各scenarioは同じ正解条件を共有する`formal`と`paraphrase_or_noisy`を1件ずつ持つ。合否は50 scenarioを同じ重みで集計し、2表現がともに成功した割合をscenario stabilityとして別に示す。

実装担当がholdout文書やgoldを見て検索、chunk、promptを調整すると、未知文書familyへの汎化性能を測れない。そのため、ユーザーをgold custodianとし、source Markdownとgold本体を`.sealed/`へ置く。`.sealed/`はGit管理しない。公開する質問文も正解を推測する手掛かりにはなるため、実装担当は質問を読んで個別調整せず、固定候補へ一括入力する用途だけに使う。

実際のholdout作成は、この契約実装と分離したタスクで[`CUSTODIAN_HANDOFF.md`](CUSTODIAN_HANDOFF.md)を使って行う。

## 設計判断

- 公開質問はCSVの100行ではなく、1 scenarioの2表現を同じobjectへまとめる。splitや正解条件の単位がscenarioであることを構造で保つためである。
- source Markdownもgoldと同じく候補固定まで非公開にする。goldだけを隠す方式では、未知の文書構造・見出し・言い回しに対する取込性能を測れないためである。
- holdoutは最低5 document familyを使う。1つの長い文書だけで50 scenarioを作るより制度・文書構造の偏りを抑えられ、作成負荷も有限に保てる。
- JSON Schemaはfield、型、列挙値を検査する。validatorは件数配分、状態遷移、hash、document family分離、分類ごとのgold意味条件を検査する。

## Git管理するもの

- `scenario_blueprint.json`: 50 scenarioのIDと分類・難度・表現の集計件数
- `public_manifest.json`: 状態、公開質問、sealed artifactのSHA-256、候補実装、予測、開封の固定記録
- `design/schemas/text-holdout-gold-v1.schema.json`: 非公開goldが従う公開契約
- この手順、custodian handoff、validator、test

scenarioごとの難度、期待分類、正解、根拠、参照文書、判断に不足する条件は公開ファイルへ書かない。

## Git管理しないもの

```text
eval/text_holdout/.sealed/
├── documents/
│   └── <document_id>.md
└── gold/
    └── scenario_gold.json
```

gold custodian以外は、候補実装と予測結果の固定が終わるまでこのdirectoryを開かない。

各source MarkdownのYAML front matterには、公開manifestと一致する`document_id`と`document_family`を必ず持たせる。validatorはhashに加えてこの対応と空でない本文を検査する。

## 公開質問の形

`SEALED`で追加する`questions.json`は、正解fieldを持たない。

```json
{
  "schema_version": "1.0",
  "holdout_id": "text-sealed-holdout-v1",
  "scenario_count": 50,
  "expression_count": 100,
  "scenarios": [
    {
      "scenario_id": "TH001",
      "expressions": [
        {"variant_type": "formal", "question": "公開質問文"},
        {"variant_type": "paraphrase_or_noisy", "question": "公開質問文"}
      ]
    }
  ]
}
```

## 状態遷移

1. `PLANNED`: 構成、50個のscenario ID、Schema、development境界を固定する。
2. `SEALED`: custodianが別familyのMarkdown、公開質問、非公開goldを作り、SHA-256だけをmanifestへ記録する。
3. `CANDIDATE_FROZEN`: development setだけで候補実装を選び、Git commitと設定manifestのhashを固定する。
4. `PREDICTIONS_FROZEN`: sealed Markdownを候補実装へ初めて入力し、100表現の予測結果とrun IDを固定する。goldは開かない。
5. `OPENED`: custodianがgoldを開き、事前に記録したhashとの一致を確認する。
6. `CONSUMED`: score、scenario stability、Wilson 95% interval、失敗例を保存する。このholdoutを再びsealed扱いにしない。

各段階はGit commitで履歴を残す。状態を飛ばさず、公開manifestの既存hashを書き換えない。

## 検証方法

公開情報だけを検証する通常コマンドは、sealed artifactを読み込まない。

```bash
.venv/bin/python -m eval.validate_text_holdout_protocol \
  eval/text_holdout/public_manifest.json
```

`SEALED`以降、custodianがローカルartifactと公開hash、goldの意味条件を照合するときだけ`--sealed-root`を付ける。

```bash
.venv/bin/python -m eval.validate_text_holdout_protocol \
  eval/text_holdout/public_manifest.json \
  --sealed-root eval/text_holdout/.sealed
```

## 学習上の要点

- Schemaはデータの形、semantic validatorはデータ間の意味関係を受け持つ。
- SHA-256は内容を公開せず、後で開いたartifactが先に固定した版と同一か確認する。
- developmentとholdoutのdocument familyを分けると、既知の制度文面への暗記ではなく未知文書への汎化を測れる。
- 一度開封したholdoutは失敗分析へ使えるが、次の最終受入には新しいholdout版が必要になる。

## 候補固定後の予測

外部APIを呼ぶ前に、公開情報だけから実行上限を確認する。この`plan`はsealed Markdownもgoldも読まない。

```bash
.venv/bin/python -m eval.run_text_holdout_predictions plan
```

明示承認後、sealed Markdownだけを初めて候補へ入力する。出力先は新規directoryに限定し、goldはrunnerへ渡さない。
Gemini Embeddingはbatch内の各contentを100 RPM quotaへ計上するため、30 documentのEmbedding後に
60秒の計画的cooldownを置いて100 queryを送る。SDK attemptは1回に固定し、429後の自動retryは
行わない。回答系の無料枠15 RPMにはGenerator、Classifier、Version Resolverで一つのpacerを
共有し、理論上の最短4秒に運用余裕を加えて各callを5.1秒以上離す。provider errorで停止した場合、成功済みpredictionだけを
hash付きで次runへ引き継ぎ、失敗表現から再開できる。

```bash
.venv/bin/python -m eval.run_text_holdout_predictions run \
  --sealed-documents-dir eval/text_holdout/.sealed/documents \
  --output-dir eval/results/text_holdout_v1_predictions
```

100表現が完走した場合だけ予測を固定する。途中停止artifactは原因調査に使えるが、`PREDICTIONS_FROZEN`には進めない。

```bash
.venv/bin/python -m eval.run_text_holdout_predictions freeze \
  --predictions eval/results/text_holdout_v1_predictions/predictions.jsonl \
  --summary eval/results/text_holdout_v1_predictions/summary.json
```
