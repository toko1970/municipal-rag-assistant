# 回転ページfixture実装計画

- 記録日: 2026-09-27
- 対象: Phase 0 / P0-10
- 状態: 実装・検証済み
- Loop: `Phase 0 evidence-first slice`

## 1. 学習目標

- PDFのページ回転情報と、画像内の画素を回転する処理の違いを説明できる。
- 回転前、表示時、正立化後の座標空間を区別できる。
- 同じ入力内容で回転角だけを変える一因子実験を作れる。

## 2. 設計判断

初期仕様が0/90/180/270度を対象にしているため、正立0度は完成済みの`scan_text_dev_001`、非0度は90/180/270度の3 fixtureで固定する。

今回はPDFの`/Rotate`情報を使う。画像の画素自体を回転したscanは別の入力形態であり、同時に扱うと回転情報の検出と画像方向推定の失敗を区別できないため対象外とする。

goldのregion bboxは正立したsource画像の左上原点・0〜1座標で保持する。入力PDFを回転0度へ正規化したページ画像が、完成済みの正立reference画像と同一SHA-256になることを受入条件にする。

## 3. Artifact

```text
design/schemas/rotated-scan-extraction-v1.schema.json
eval/text_pdf_fixtures/
├── documents/rotated_scan_dev_090.pdf
├── documents/rotated_scan_dev_180.pdf
├── documents/rotated_scan_dev_270.pdf
├── images/rotated_scan_dev_ANGLE_page_001.png
├── images/rotated_scan_dev_ANGLE_normalized_page_001.png
├── gold/rotated_scan_dev_ANGLE.json
├── manifests/rotation_development_manifest.json
└── generate_rotated_scan_fixtures.py
eval/validate_rotated_scan_fixture.py
tests/test_rotated_scan_fixture.py
```

3 fixtureは`scan_text_dev_001_source.png`とそのgoldを共通の正解起点として使う。OCR出力からgoldは作らない。

## 4. 検証境界

- PDFのrotationがmanifest・goldの90/180/270度と一致する。
- text layerが空で、元の300 dpi画像が埋め込まれている。
- 90/270度では表示幅・高さが入れ替わり、180度では維持される。
- 正規化後の画像hashが正立reference画像と一致する。
- 正立座標のregion bbox、期待全文、重要値を保持する。
- scanなので`review_required=true`を維持する。

Phase 0では回転補正できるfixture契約までを証明する。未知の画像方向を推定する処理、Gemini OCR、bbox IoUの測定はPhase 4で実装する。

## 5. 停止条件

- 3角度のfixtureと検証がすべて成功する。
- 最大2修正roundへ到達する。
- 同じ失敗が改善しない、仕様変更が必要、または利用率が80%以上になる。

## 6. 実装結果

- PDFの`/Rotate`を90/180/270度へ設定した3 fixtureを作成した。
- raw表示画像は各角度を反映し、正規化後の3画像は正立referenceと同一SHA-256になった。
- text layerなし、埋め込み画像、media box、表示寸法、回転角、正立regionをvalidatorで検査した。
- 0度への改変、PDFとgoldの角度不一致、逆転bbox、自動承認への改変をtestで拒否した。
- 13 artifactはgenerator再実行後も同一SHA-256を維持した。
- 目視確認、対象test 6件、全test 99件、Ruff、diff検査が成功した。
- 修正roundは発生せず、外部APIとクラウド費用は使用していない。
