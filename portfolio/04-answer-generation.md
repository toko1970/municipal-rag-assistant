# 4. 根拠に沿って回答し、回答可否を分類する

[READMEの構成図へ戻る](../README.md#仕組み) · [機能一覧へ](README.md)

## 1. 機能の概要

Geminiへ質問と検索根拠を渡し、根拠に沿った回答を生成します。回答可否は`根拠十分`・`判断要`・`文書不足`に分類します。図表の根拠がある場合は、構造化した内容に加えて元画像も確認します。期限計算は、根拠が揃う限定パターンを決定的に処理します。

## 2. 比較候補と選定理由

- **回答生成モデル**: `gemini-3.1-flash-lite`と旧`gemini-2.5-flash`のTop-5比較では、前者が8問を完走し、後者は1件で表示失敗しました。3.1 Flash-Liteは既存formal 100問も完走したため、既定モデルに選ばれました。後続のTop-5/Top-8比較では必須内容一致が6/8から8/8へ改善し、生成費用は36%増えたためTop-8を採用しました。
- **回答分類器**: 開発用36件ではGemini 3.1 Flash-Liteが31/36、BGE-M3 zero-shotが6/36でした。mDeBERTaは全根拠が512 token上限を超えて推論前に停止。Jevは比較環境を用意できず未実施です。品質差からGeminiを維持しましたが、結果はsealed holdoutではありません。
- **一回生成 / 回答生成と独立分類**: 一回生成のモデル比較は回答と分類ラベルを同じ呼び出しで出す簡易経路でした。現行経路では回答生成と分類処理を分けます。前者はモデル候補を選ぶため、後者は分類結果を独立して検証するためで、実験結果を現在の分類器の性能とはみなしません。

実験の詳細は[Gemini 3.1とTop-kの評価](../eval/GEMINI_3_1_TOP_K_ANSWER_EVALUATION.md)、[回答分類モデル比較](../eval/CLASSIFIER_MODEL_COMPARISON.md)にあります。
## 3. 工夫した点

回答には根拠IDを付け、取得した根拠と結び付けます。根拠が足りない場合は推測せず、回答可能性を分類して表示します。日付・期限も生成モデル任せにせず、根拠と対象条件が揃うケースだけ決定的な計算へ渡します。

Sealed visual holdoutではEnd-to-End成功率70%、分類精度70%でした。分類の事前閾値80%に届かず、総合受入は不合格です。Text holdout後の日付改善について、2回目のText sealed holdoutは未実施です。

- 実装: [`src/query_service.py`](../src/query_service.py) · [`src/answering.py`](../src/answering.py) · [`src/deadline_calculator.py`](../src/deadline_calculator.py)
- 回答・保留評価: [仕様、結果、採用判断](../eval/reports/PORTFOLIO_EVALUATION_AND_IMPROVEMENT_HISTORY_20261017.md)
