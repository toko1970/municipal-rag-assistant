# 日本語scan PDF fixture実装計画

- 記録日: 2026-09-27
- 対象: Phase 0 / P0-09
- 状態: 設計済み、未実装
- 外部API: 使用しない

## 1. この学習単位の目的

### 何を学ぶか

- PDFのtext layerと、文字が画像に焼き付いたscan PDFの違い
- OCRへ渡す入力、正解を表すgold、OCRの候補出力を分離する理由
- OCRモデルを動かす前に、再現可能な評価fixtureを作る方法
- 正常scan、回転、低品質を別fixtureにして原因を一つずつ検証する考え方

### 今回の設計判断

- 最初のscanは、回転なし・高コントラスト・300 dpiの日本語1ページとする。
- ページ画像だけをPDFへ埋め込み、text layerが空であることをvalidatorで確認する。
- goldはOCR結果から作らず、画像生成前の既知の文章と配置から作る。
- Gemini OCRはPhase 4で接続する。Phase 0では外部API、費用、モデル差による揺れをfixture検証へ持ち込まない。
- scan専用Schemaとmanifestを追加し、完成済みのnative text fixtureの契約は変更しない。

### 完了時に説明できること

- なぜnative text抽出とOCRを別経路にするのか
- なぜgoldをOCR出力から作ると循環評価になるのか
- OCRを呼ばずに、OCR誤りの検出規則をどうtestできるのか
- なぜこの正常scanだけではOCR精度を証明したことにならないのか

## 2. native text fixtureから引き継ぐ流れ

完成済みのnative text fixtureは、次の責務を分けている。

1. generatorの既知の文章と座標を正解の起点にする。
2. ReportLabでtext layerを持つPDFを作る。
3. 抽出結果をコピーせず、既知の文章と座標からgoldを作る。
4. manifestへPDF、ページ画像、gold、SchemaのSHA-256を記録する。
5. JSON Schemaで型と必須項目を、semantic validatorで参照関係、順序、bbox、hashを検査する。
6. PyMuPDFで実際のtext layer、全文、重要値、座標を検査する。
7. 正常系と意図的に壊したgoldをtestする。
8. ページ画像を目視し、文字化け、切れ、重なりを確認する。

scan fixtureでもこの流れを使う。ただし、PDFから直接文字を取得できることではなく、text layerが空で画像が存在することを入力契約にする。

## 3. fixtureの範囲

### 含めるもの

- 日本語の業務通知を模した架空文書1ページ
- A4縦、300 dpi相当、回転0度
- 見出し、本文、箇条書き、日付、金額、期限を含むレイアウト
- PDFへ埋め込むsource PNG
- PDFを再描画した確認用PNG
- 期待全文、重要値、領域bboxを持つgold
- Schema、manifest、validator、unit test

### 後続fixtureへ分けるもの

- 90/180/270度の回転: P0-10
- ぼけ、低コントラスト、欠け、曖昧な文字: P0-11
- 複数ページ、表、図: Phase 4以降の実装・評価
- Geminiによる実OCRと精度集計: Phase 4

正常scanへ複数の難しさを同時に入れない。失敗したときに、画像品質、回転補正、OCRのどれが原因か判別できなくなるためである。

## 4. 作成するartifact

```text
design/schemas/scan-text-extraction-v1.schema.json
eval/text_pdf_fixtures/
├── documents/scan_text_dev_001.pdf
├── images/scan_text_dev_001_source.png
├── images/scan_text_dev_001_page_001.png
├── gold/scan_text_dev_001.json
├── manifests/scan_development_manifest.json
└── generate_scan_text_fixture.py
eval/validate_scan_text_fixture.py
tests/test_scan_text_fixture.py
```

scan用manifestを分ける理由は、既存のnative manifestがtop-levelでSchemaを一つだけ参照しているためである。Phase 0では完成済み契約を改変せず、共通化の必要性が実装で確認できた段階でmanifest形式を見直す。

## 5. goldの契約

goldには少なくとも次を持たせる。

| 項目 | 意味 |
|---|---|
| `schema_version` | 契約の版 |
| `kind` | `scanned_text`固定 |
| `title` | 架空文書名 |
| `page_count` | 期待ページ数 |
| `expected_full_text` | 読み順を含む正解全文 |
| `critical_values` | 日付、金額、期限など完全一致させる値 |
| `input_characteristics` | text layerなし、300 dpi、回転0度、cleanを明示 |
| `review` | confidence未取得と人手確認要否を明示 |
| `pages[].regions` | 領域ID、正解文字列、正規化bbox |

confidenceはOCRモデルが返す観測値であり、fixture生成時には存在しない。このfixtureでは`source: unavailable`、`value: null`、`review_required: true`とし、未観測値を推測で埋めない。

## 6. generatorと正解の独立性

generatorは次の順でartifactを作る。

1. 正解文章と描画座標をコード上のsource of truthとして定義する。
2. 日本語フォントを使って300 dpiのPNGへ描画する。
3. PNGだけをA4 PDFの1ページへ埋め込む。
4. PDFをPNGへ再描画し、入力と表示を確認できるようにする。
5. 手順1の文章と座標からgoldを作る。
6. 各artifactとSchemaのSHA-256をmanifestへ記録する。

OCR出力は手順に含めない。OCRが誤読した文字をgoldへコピーすると、その誤りを正解として評価してしまうためである。

## 7. Phase 0のvalidator

validatorは次を検査する。

- goldがscan専用JSON Schemaを満たす。
- manifestの参照先とSHA-256が一致する。
- PDFが1ページ、A4、回転0度である。
- PyMuPDFの`page.get_text()`が空で、native text経路へ誤って入らない。
- ページに埋め込み画像が存在する。
- source PNGが300 dpi相当の規定pixel寸法を持つ。
- region IDが一意で、bboxが`0 <= x0 < x1 <= 1`、`0 <= y0 < y1 <= 1`を満たす。
- regionの順序から組み立てた全文が`expected_full_text`と一致する。
- すべての`critical_values`が期待全文に存在する。
- scanは`review_required: true`である。

さらに、候補OCR文字列とgoldを比較する副作用のない関数を用意する。重要値を一文字変えた候補をtestへ渡し、誤りを拒否できることを示す。これはOCR精度の測定ではなく、後続のOCR結果を判定する契約の検証である。

## 8. Phase 4との境界

Phase 0で証明するのは、再現可能なscan入力、独立した正解、誤りを検出する規則が存在することである。

Phase 4では次を追加する。

- Gemini structured OCRの実行とmodel・prompt・実行条件の記録
- OCR全文と重要値の比較
- 必須要素recallとbbox IoUの集計
- confidence閾値と`REVIEW_REQUIRED`への遷移
- 実行費用、待ち時間、失敗時の再試行記録

Tesseractは必須条件にしない。production候補はGemini structured OCRであり、日本語tessdataの有無によってCI結果が変わるためである。必要ならPhase 4で、ローカルの比較baselineまたは任意のsmoke testとして評価する。

## 9. 実装後の受入条件

1. PDFのtext layerが空で、ページ画像が存在する。
2. A4縦、300 dpi相当、回転0度のclean scanである。
3. goldがSchemaとsemantic validatorを通過する。
4. 正しい候補OCR文字列は合格し、重要値を壊した候補は不合格になる。
5. generator再実行後もPDF、画像、gold、manifestのhashが一致する。
6. 再描画画像に文字化け、切れ、重なりがない。
7. 対象test、全test、Ruff、`git diff --check`が成功する。
8. 外部API呼び出しとクラウド費用が発生しない。

## 10. 再開後の最小手順

1. Codexの5時間枠・週間枠を確認する。
2. generatorとscan専用Schemaを作る。
3. 1 fixtureを生成し、目視確認する。
4. validatorと正常系・破壊系testを追加する。
5. 再生成hash、対象test、全test、lintを確認する。
6. P0-09の証拠をledgerへ記録する。

