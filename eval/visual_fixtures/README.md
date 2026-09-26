# Visual evaluation fixtures

## 目的

fixtureは抽出処理へ渡す架空の入力文書で、gold annotationは正しい抽出結果として期待する構造化データである。抽出器の出力をgoldとして保存せず、作成時に分かっている図形、文字、接続、座標からgoldを作る。

最初の学習単位では、申請処理フローチャート1件を次の4層で管理する。

1. `documents/flowchart_dev_001.pdf`: 利用者が読む原本fixture
2. `images/flowchart_dev_001_page_001.png`: 抽出器またはマルチモーダルモデルへ渡すページ画像
3. `gold/flowchart_dev_001.json`: 期待するnode、edge、分岐条件、bbox
4. `manifests/development_manifest.json`: split、document family、Schemaと各artifactのSHA-256

すべて架空の内容であり、実在する自治体、制度、個人情報を含まない。

## Development fixtures

| Fixture | 確認する構造 |
|---|---|
| `flowchart_dev_001` | 1つのdecision、差戻しによる循環、単一の終了node |
| `flowchart_dev_002` | 3つのdecision、複数edgeの合流、3種類の終了node |
| `timeline_dev_001` | 基準日、相対期限、処理内容を持つ5つのevent |
| `table_dev_001` | row spanを含む支給額・区分表 |
| `form_dev_001` | label、記入例、bboxを持つ申請書field |
| `table_dev_002` | row spanとcolumn spanを含む改定前後比較 |

同じ`flowchart` Schemaでも異なる接続構造を用意し、抽出処理やvalidatorが一つの図だけを暗黙に仮定していないことを確認する。

## bbox契約

bboxは`x0, y0, x1, y1`で表し、ページ左上を原点としてページ幅・高さを1に正規化する。小数第4位へ丸め、`x0 < x1`かつ`y0 < y1`を必須とする。PDFのpoint座標をそのまま保存しないため、解像度の異なるページ画像でも同じ領域を参照できる。

## Schema validationとsemantic validation

- JSON Schemaは必須field、型、列挙値、0〜1の数値範囲を検査する。
- semantic validatorはSchemaだけでは表せないbboxの大小関係、node IDの一意性、edge参照、PDF page、source image、SHA-256を検査する。
- flowchartでは、startとendの存在、startへのincoming edge禁止、endからのoutgoing edge禁止、decisionの分岐条件、startから全nodeへの到達可能性も検査する。業務上正しい差戻しを扱うため、循環自体は禁止しない。
- timelineではeventが2件以上あることとIDの一意性を検査する。`翌日から10日以内`のような相対期限を機械的な日付へ誤変換せず、配列順を時系列順として保持する。
- tableではcellが行列範囲内に収まり、row spanとcolumn spanを展開したgrid上で重複しないことを検査する。
- formではfieldが1件以上あり、field IDが一意であることを検査する。同じlabelを持つ複数欄は将来あり得るため、labelの重複は禁止しない。

形式上は文字列として正しいedge参照でも、そのIDのnodeが存在しなければ意味的には不正である。この違いを分けて検証する。

## 生成と検証

fixtureを再生成するにはReportLab、日本語font、Popplerの`pdftoppm`が必要である。通常のCIは生成済みartifactを再生成せず、validatorで整合性を確認する。

```bash
python -m eval.visual_fixtures.generate_flowchart_fixture
python -m eval.visual_fixtures.generate_eligibility_flowchart_fixture
python -m eval.visual_fixtures.generate_timeline_fixture
python -m eval.visual_fixtures.generate_table_fixtures
python -m eval.visual_fixtures.generate_form_fixture
python eval/validate_visual_fixture.py eval/visual_fixtures/manifests/development_manifest.json
pytest -q tests/test_visual_fixture_validation.py
```

development manifestは各generatorから直接追記せず、`build_development_manifest.py`が完成済みartifactを列挙して再構築する。generatorをどの順番で再実行しても、他のfixture entryを消さないためである。

## 実装から学べる処理の流れ

```text
架空の業務資料を設計
  ↓
generatorでPDFを作成
  ↓
pdftoppmでページ画像を作成
  ↓
作成時の図形・cell・field情報からgold JSONを作成
  ↓
manifest builderがPDF・画像・gold・SchemaのSHA-256を記録
  ↓
validatorがSchemaと意味規則を検査
  ↓
正常系・異常系testを固定し、変更のたびに全fixtureを再検証
```

goldは抽出器の出力から作らない。抽出結果からgoldを作ると、抽出器の誤りを正解として保存する循環が生じるためである。今回のgeneratorは、PDFを描画した時点で既知のnode、edge、event、cell、field、bboxをgoldへ保存する。

### 共通検査と種類別検査

| 層 | 主な検査 |
|---|---|
| JSON Schema | 必須field、型、列挙値、0〜1のbbox範囲 |
| 共通semantic | `x0 < x1`、`y0 < y1`、PDF page、画像hash、fixture ID |
| flowchart | node参照、start/end、分岐条件、到達可能性 |
| timeline | event数、event ID、配列順の維持 |
| table | 行列範囲、row/column span、cell重複 |
| form | field数、field ID |

Schemaはデータの形を保証し、semantic validatorはデータ同士の関係を保証する。例えば`edge.to`が文字列であることはSchemaで検査できるが、その文字列と同じIDのnodeが存在するかはsemantic validatorで検査する。

### 評価での使い方

development fixtureは抽出処理やpromptを修正するために繰り返し使用する。sealed holdoutは別のdocument familyから作り、予測結果を固定するまでgoldを実装側へ見せない。これにより、既知の6文書だけに合わせた改善と、未見文書へ一般化する改善を区別する。

図表、scan、帳票は自動承認しない方針のため、goldの`confidence.review_required`は`true`とする。目視レビューを完了しても、後続の取込処理ではレビュー履歴を残してから`APPROVED`へ遷移させる。

## developmentとsealed holdout

`document_family`はレイアウトや内容を共有する派生文書のまとまりを表す。developmentとsealed holdoutで同じfamilyを使わない。holdoutのgold本体は予測結果を固定するまでrepositoryへcommitせず、hashだけをmanifestへ保存する。
