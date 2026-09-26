# Visual evaluation fixtures

## 目的

fixtureは抽出処理へ渡す架空の入力文書で、gold annotationは正しい抽出結果として期待する構造化データである。抽出器の出力をgoldとして保存せず、作成時に分かっている図形、文字、接続、座標からgoldを作る。

最初の学習単位では、申請処理フローチャート1件を次の4層で管理する。

1. `documents/flowchart_dev_001.pdf`: 利用者が読む原本fixture
2. `images/flowchart_dev_001_page_001.png`: 抽出器またはマルチモーダルモデルへ渡すページ画像
3. `gold/flowchart_dev_001.json`: 期待するnode、edge、分岐条件、bbox
4. `manifests/development_manifest.json`: split、document family、Schemaと各artifactのSHA-256

すべて架空の内容であり、実在する自治体、制度、個人情報を含まない。

## bbox契約

bboxは`x0, y0, x1, y1`で表し、ページ左上を原点としてページ幅・高さを1に正規化する。小数第4位へ丸め、`x0 < x1`かつ`y0 < y1`を必須とする。PDFのpoint座標をそのまま保存しないため、解像度の異なるページ画像でも同じ領域を参照できる。

## Schema validationとsemantic validation

- JSON Schemaは必須field、型、列挙値、0〜1の数値範囲を検査する。
- semantic validatorはSchemaだけでは表せないbboxの大小関係、node IDの一意性、edge参照、PDF page、source image、SHA-256を検査する。

形式上は文字列として正しいedge参照でも、そのIDのnodeが存在しなければ意味的には不正である。この違いを分けて検証する。

## 生成と検証

fixtureを再生成するにはReportLab、日本語font、Popplerの`pdftoppm`が必要である。通常のCIは生成済みartifactを再生成せず、validatorで整合性を確認する。

```bash
python eval/visual_fixtures/generate_flowchart_fixture.py
python eval/validate_visual_fixture.py eval/visual_fixtures/manifests/development_manifest.json
pytest -q tests/test_visual_fixture_validation.py
```

図表、scan、帳票は自動承認しない方針のため、goldの`confidence.review_required`は`true`とする。目視レビューを完了しても、後続の取込処理ではレビュー履歴を残してから`APPROVED`へ遷移させる。

## developmentとsealed holdout

`document_family`はレイアウトや内容を共有する派生文書のまとまりを表す。developmentとsealed holdoutで同じfamilyを使わない。holdoutのgold本体は予測結果を固定するまでrepositoryへcommitせず、hashだけをmanifestへ保存する。
