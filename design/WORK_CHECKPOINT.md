# 作業再開checkpoint

- 記録日: 2026-09-26
- 状態: Phase 0の最初の学習単位が完了
- Git: 仕様baselineは`1e3ad09`でcommit済み。評価境界と最初のfixture実装はcommit前

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

## 2. 未完了・次回反映すること

- 既存100シナリオ・500問をtext development / regression setとして新しい論理locatorへ移行する計画を具体化する。
- text sealed holdoutの架空文書family、質問、commit対象外goldを作る。
- 残り5種類のdevelopment用図表fixtureを同じmanifest・validatorへ追加する。
- sealed holdout用の別文書familyを作り、gold custodian手順を実際のartifactで確認する。
- Phase 0の全要求が揃った段階でcontract conformance loopを実行する。

## 3. 次回最初に行うこと

1. Codexの5時間枠・週間枠を確認する。
2. `git status`と本checkpointを確認する。
3. 最初のfixtureの生成物、gold、manifest、validatorを読み、処理を説明できることを確認する。
4. 次の一種類をEvidence-first loopで追加する。次候補は支給可否判断フローとする。
5. 種類ごとの正常・異常caseをQuality streakへ追加する。

## 4. 最初の学習単位

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
├── images/flowchart_dev_001_page_001.png
├── gold/flowchart_dev_001.json
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

2026-09-26の再開時点では5時間枠0%使用、週間枠60%使用だったため、節約モードで一つの学習単位に限定した。数値は次回まで維持されるとは限らないため、再開時にUsageを再取得し、`LEARNING_AND_USAGE_PLAN.md`の作業モードを決める。

reset creditや追加creditはユーザーの明示的な確認なしに使用しない。
