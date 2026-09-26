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

同じ`flowchart` Schemaでも異なる接続構造を用意し、抽出処理やvalidatorが一つの図だけを暗黙に仮定していないことを確認する。

## bbox契約

bboxは`x0, y0, x1, y1`で表し、ページ左上を原点としてページ幅・高さを1に正規化する。小数第4位へ丸め、`x0 < x1`かつ`y0 < y1`を必須とする。PDFのpoint座標をそのまま保存しないため、解像度の異なるページ画像でも同じ領域を参照できる。

## Schema validationとsemantic validation

- JSON Schemaは必須field、型、列挙値、0〜1の数値範囲を検査する。
- semantic validatorはSchemaだけでは表せないbboxの大小関係、node IDの一意性、edge参照、PDF page、source image、SHA-256を検査する。
- flowchartでは、startとendの存在、startへのincoming edge禁止、endからのoutgoing edge禁止、decisionの分岐条件、startから全nodeへの到達可能性も検査する。業務上正しい差戻しを扱うため、循環自体は禁止しない。

形式上は文字列として正しいedge参照でも、そのIDのnodeが存在しなければ意味的には不正である。この違いを分けて検証する。

## 生成と検証

fixtureを再生成するにはReportLab、日本語font、Popplerの`pdftoppm`が必要である。通常のCIは生成済みartifactを再生成せず、validatorで整合性を確認する。

```bash
python -m eval.visual_fixtures.generate_flowchart_fixture
python -m eval.visual_fixtures.generate_eligibility_flowchart_fixture
python eval/validate_visual_fixture.py eval/visual_fixtures/manifests/development_manifest.json
pytest -q tests/test_visual_fixture_validation.py
```

development manifestは各generatorから直接追記せず、`build_development_manifest.py`が完成済みartifactを列挙して再構築する。generatorをどの順番で再実行しても、他のfixture entryを消さないためである。

図表、scan、帳票は自動承認しない方針のため、goldの`confidence.review_required`は`true`とする。目視レビューを完了しても、後続の取込処理ではレビュー履歴を残してから`APPROVED`へ遷移させる。

## developmentとsealed holdout

`document_family`はレイアウトや内容を共有する派生文書のまとまりを表す。developmentとsealed holdoutで同じfamilyを使わない。holdoutのgold本体は予測結果を固定するまでrepositoryへcommitせず、hashだけをmanifestへ保存する。
