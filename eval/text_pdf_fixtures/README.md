# Text PDF development fixtures

## 目的

`native_text_dev_001`は、画像OCRを使わずPDFのtext layerから日本語本文、ページ、座標を取得できることを検証する架空fixtureである。Phase 0では入力、gold、hash、validatorを固定し、一般の抽出pipelineと精度比較はPhase 2・4で実装する。

## Artifact

1. `documents/native_text_dev_001.pdf`: text layerを持つ入力PDF
2. `images/native_text_dev_001_page_001.png`: 目視確認用のページ画像
3. `gold/native_text_dev_001.json`: 期待全文、重要値、page、text block bbox
4. `manifests/development_manifest.json`: Schemaと各artifactのSHA-256

すべて架空で、実在する自治体、制度、個人情報を含まない。

## 設計判断

- 図表用`visual-extraction-v1`へ`native_text`を追加せず、専用Schemaを使う。図表のnode・cellと通常本文のblockでは必要な意味検査が異なるためである。
- goldは生成時に既知の文章と描画座標から作り、抽出結果から作らない。抽出誤りを正解として固定することを防ぐ。
- PyMuPDFでtext layer、全文、検索位置を検査する。pypdfだけでも全文抽出はできるが、production設計で採用したAPIと座標規則をPhase 0から揃える。
- native textだけは自動承認可能な仕様なので、`review_required=false`とする。scan、図表、帳票には適用しない。

## 生成と検証

```bash
.venv/bin/python -m eval.text_pdf_fixtures.generate_native_text_fixture
.venv/bin/python -m eval.validate_native_text_fixture \
  eval/text_pdf_fixtures/manifests/development_manifest.json
.venv/bin/python -m pytest -q tests/test_native_text_fixture.py
```

validatorは次を確認する。

- PDF、PNG、gold、SchemaのSHA-256
- text layerが空でないこと
- parserが加える空行と行頭・行末空白だけを正規化した上で、ページ単位とPDF全体の文字列・順序がgoldと一致すること
- 施行日、提出期限、処理期限の重要値が完全一致すること
- text blockが一意に検索でき、gold bbox内にあること
- page番号、page寸法、source image参照が一致すること

PDFの見た目はtext extractionでは検証できないため、PNGを目視して文字化け、切れ、重なりを別に確認する。

## 日本語scan PDF

`scan_text_dev_001`は、text layerを持たない日本語PDFをOCR経路へ送る入力契約を検証する。高コントラスト、A4縦、300 dpi相当、回転0度のclean scanだけを対象とし、回転・低品質は別fixtureで検証する。

### Artifact

1. `documents/scan_text_dev_001.pdf`: source PNGだけを埋め込んだ入力PDF
2. `images/scan_text_dev_001_source.png`: 300 dpiのOCR入力画像
3. `images/scan_text_dev_001_page_001.png`: PDF再描画の目視確認用画像
4. `gold/scan_text_dev_001.json`: 期待全文、重要値、page、text region bbox
5. `manifests/scan_development_manifest.json`: Schemaと各artifactのSHA-256

goldはOCR出力から作らず、画像へ描画する既知の文章と座標から作る。Phase 0では外部OCRを呼ばず、将来のOCR候補が全文と重要値を保持したか判定する契約までを固定する。Gemini structured OCRの実行、recall、bbox IoU、費用の測定はPhase 4で行う。

### 生成と検証

```bash
.venv/bin/python -m eval.text_pdf_fixtures.generate_scan_text_fixture
.venv/bin/python -m eval.validate_scan_text_fixture \
  eval/text_pdf_fixtures/manifests/scan_development_manifest.json
.venv/bin/python -m pytest -q tests/test_scan_text_fixture.py
```

validatorは、text layerが空であること、埋め込み画像、A4寸法、回転角、source PNGの寸法・dpi、Schema、bbox、hash、`review_required=true`を検査する。testでは正解全文を合格させ、重要値の改変とその他の文字差分を拒否する。
