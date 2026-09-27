# 低品質scan review gate fixture実装計画

- 記録日: 2026-09-27
- 対象: Phase 0 / P0-11
- 状態: 実装・検証済み
- Loop: `Low-quality scan review-gate loop`

## 1. 学習目標

- 抽出結果の`REVIEW_REQUIRED`と文書版の`WAITING_REVIEW`を区別する。
- 低品質入力を再現可能に作り、誤って`READY`へ進めない契約をtestする。
- fixture用の劣化測定値と、productionの自動判定閾値を区別する。

## 2. 設計判断

完成済みclean scanと同じ画像を白へ75%合成し、低コントラストだけを加える。ぼけ、ノイズ、欠け、回転を同時に加えず、失敗原因を一つに保つ。

劣化が実際に生成されたことは、グレースケールの最大値と最小値の差で確認する。このfixtureではdynamic rangeが60以下であることを生成条件として固定する。この値は制御されたfixtureを検査するための値であり、未知のproduction文書を自動判定する閾値には使わない。

goldには次を分けて記録する。

- 抽出結果: `REVIEW_REQUIRED`
- 文書版の状態: `WAITING_REVIEW`
- review理由: `LOW_CONTRAST`
- 自動`READY`: 不可

すべてのscanは人手確認対象だが、このfixtureでは低コントラストという具体的なreview理由が欠落しないことも検査する。

## 3. Artifact

```text
design/schemas/low-quality-scan-v1.schema.json
eval/text_pdf_fixtures/
├── documents/low_quality_scan_dev_001.pdf
├── images/low_quality_scan_dev_001_source.png
├── images/low_quality_scan_dev_001_page_001.png
├── gold/low_quality_scan_dev_001.json
├── manifests/low_quality_development_manifest.json
└── generate_low_quality_scan_fixture.py
eval/validate_low_quality_scan_fixture.py
tests/test_low_quality_scan_fixture.py
```

## 4. 検証境界

- clean sourceよりdynamic rangeが小さく、fixture gateの60以下である。
- PDFはA4、回転0度、text layerなし、埋め込み画像ありである。
- 期待全文、重要値、正立regionはclean fixtureのgoldと一致する。
- `REVIEW_REQUIRED`、`WAITING_REVIEW`、`LOW_CONTRAST`、自動`READY`不可を固定する。
- `READY`への改変、review理由の欠落、測定値の不一致を拒否する。
- artifactのhashと再生成性を検査する。

Phase 0では失敗入力と期待gateを固定する。未知画像の品質判定、OCR confidence、実際の状態遷移処理はPhase 4で実装する。

## 5. 停止条件

- fixture、gold、manifest、validator、testが成功する。
- 最大2修正roundへ到達する。
- 同じ失敗が改善しない、仕様変更が必要、または利用率が80%以上になる。

## 6. 実装結果

- clean sourceを白へ75%合成し、dynamic range 56の低コントラストscanを作成した。
- clean referenceのdynamic range 224より小さく、fixture gate 60以下であることを検査した。
- 抽出結果`REVIEW_REQUIRED`、文書版`WAITING_REVIEW`、理由`LOW_CONTRAST`、自動`READY`不可をSchemaで固定した。
- `READY`への改変、理由欠落、測定値改変、逆転bboxをtestで拒否した。
- 5 artifactはgenerator再実行後も同一SHA-256を維持した。
- 目視確認、対象test 7件、全test 106件、Ruff、diff検査が成功した。
- 修正roundは発生せず、外部APIとクラウド費用は使用していない。
