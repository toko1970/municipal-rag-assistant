# 作業再開checkpoint

- 記録日: 2026-09-26
- 状態: 仕様確定。Phase 0は未着手
- Git: 仕様・設計資料、AGENTS.md、.gitignoreは未コミット

## 1. 完了したこと

- RAGの最終仕様をユーザー承認済みにした。
- 技術設計、データモデル、実装計画、テスト戦略、JSON Schemaを作成した。
- PostgreSQL、Qdrant、Cloud Storageの責務と同期・回復手順を定義した。
- PDF・図表の対象、抽出世代、文書版、評価境界を定義した。
- Generatorは根拠付きclaimsだけを返し、classifier factorsからコードが最終ラベルと表示templateを決める設計にした。
- `corpus_answerability`をオンライン分類・ログから除外し、評価専用の`expected_corpus_answerability`へ移した。
- 学習を目的とした進め方とCodex利用枠の運用ルールをAGENTS.mdへ追加した。
- 独立仕様レビューでP0/P1の重大な曖昧さなし、反対レビューでhigh-impact objectionなしを確認した。

## 2. 未完了・次回反映すること

- 現在の仕様一式をbaselineとしてcommitする。
- Phase 0の計画にテキスト用sealed holdoutを明示的に追加する。
- 既存100シナリオ・500問をtext development / regression setとして新しい論理locatorへ移行する計画を具体化する。
- developmentと異なる架空文書familyを使ったtext sealed holdoutの件数・構成を決める。
- 画像fixture、gold annotation、validatorの実装はまだ開始していない。

## 3. 次回最初に行うこと

1. Codexの5時間枠・週間枠を確認する。
2. `git status`と本checkpointを確認する。
3. 仕様資料の差分を最終確認し、仕様baselineをcommitする。
4. `IMPLEMENTATION_PLAN.md`と`TEST_STRATEGY.md`へtext sealed holdoutを追加する。
5. 最初の学習単位「申請処理フローチャート1件のfixtureとgold annotation」を開始する。

## 4. 最初の学習単位

### 学習目標

- fixtureとgold annotationの違い
- PDFの正規化bbox
- flow node・edgeの構造
- JSON Schema validationとsemantic validationの違い
- development / holdout間のdocument-family leakage

### 作成予定

```text
eval/visual_fixtures/
├── documents/flowchart_dev_001.pdf
├── gold/flowchart_dev_001.json
├── manifests/development_manifest.json
└── README.md

eval/validate_visual_fixture.py
tests/test_visual_fixture_validation.py
```

### 完了条件

- PDFを目視確認できる。
- gold JSONがvisual extraction Schemaを通る。
- node ID、edge参照、bboxをsemantic validatorで検証できる。
- 不正なedge参照とbboxをtestで拒否できる。
- PDFとgold JSONのSHA-256をmanifestへ記録できる。
- 実装内容と実務上の意味をユーザー向けに振り返る。

## 5. 評価セットの目標構成

```text
評価基盤
├── テキスト
│   ├── 既存100シナリオ・500表現: development / regression
│   └── 新規・別文書family: sealed holdout（件数は次回確定）
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
git diff --check -- AGENTS.md .gitignore
find design -maxdepth 3 -type f -print | sort
python3 -m json.tool design/schemas/visual-extraction-v1.schema.json >/dev/null
python3 -m json.tool design/schemas/answer-output-v1.schema.json >/dev/null
python3 -m json.tool design/schemas/classification-output-v1.schema.json >/dev/null
```

## 8. 利用枠checkpoint

直近確認時点では5時間枠93%使用、週間枠59%使用だった。数値は次回まで維持されるとは限らないため、再開時にUsageを再取得し、`LEARNING_AND_USAGE_PLAN.md`の作業モードを決める。

reset creditや追加creditはユーザーの明示的な確認なしに使用しない。
