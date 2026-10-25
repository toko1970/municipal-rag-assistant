# 4. 根拠に沿って回答し、回答可否を分類する

[READMEの構成図へ戻る](../README.md#仕組み) · [機能一覧へ](README.md)

## 1. 機能の概要

Geminiへ質問と検索根拠を渡し、根拠に沿った回答を生成します。回答可否は`根拠十分`・`判断要`・`文書不足`に分類します。図表の根拠がある場合は、構造化した内容に加えて元画像も確認します。期限計算は、根拠が揃う限定パターンを決定的に処理します。

## 2. 実行経路と評価状態（2026-10-25 14:04 JST確認）

| 対象 | 設定・状態 |
|---|---|
| ローカル既定（`.env`等による上書きなし） | `ANSWER_GENERATION_FLOW=production`、`LLM_MODEL_NAME=gemini-3.1-flash-lite`、`CLASSIFICATION_CONTRACT_VERSION=v1`。独立分類・版解決・限定的な期限計算を含む既存経路 |
| 公開中Cloud Run | revision `municipal-rag-assistant-00011-kwv`、image tag/commit `2fa8ef463dd1747165081cb845a80cfa30dc6fd9`。CI run #172がdeploy・traffic切替・health checkまで成功し、100% LATEST trafficを確認 |
| 公開経路の設定 | `ANSWER_GENERATION_FLOW=autoresearch_candidate`、`gemini-3.8-flash`、Qdrant collection `municipality_rag_docs_v2_contextual_heading_v1`。一回生成で回答分類も出力する。独立分類attempt・claim単位の根拠リンク・決定的期限計算はない |
| 一回生成候補 | 凍結prompt SHA-256 `cae1bafc46a98a30670f6e32c79508514a25580d80ba8f2a5d370e63a786ac0d`。公開設定のモデルはenv表示だけで決めず、候補コードの固定値も参照 |
| sealed評価 | 総合76/100など事前基準未達のNo-go。sealed setは消費済みで、今回の採用根拠には再利用していない |
| 導入判断 | ユーザーが130問の統合回帰と80表現challengeの直接比較を確認し、候補統合を指示。その後mainへ統合し、上記revisionを公開。これはsealed評価を合格へ変更する判断ではない |

公開確認: [GitHub Actions production deploy run #172](https://github.com/toko1970/municipal-rag-assistant/actions/runs/40161778266)。評価条件と採否の根拠は[候補導入判断](../eval/results/autoresearch/freeform-production-rollout-20261025/decision.md)および[評価artifact案内](../eval/reports/README.md)を参照してください。ローカル既定と公開設定は別の状態です。

## 3. 比較候補と選定理由

- **回答生成モデル**: 質問と根拠を固定し、`gemini-3.1-flash-lite`、`gemini-3.8-flash`、`gemini-3.1-pro-preview`を比較しました。予約テスト44件では総合成功がFlash-Lite 37/44、Flash 35/44。Flash-Liteは費用と速度で優位でしたが、Flashは保留対象への不適切な回答が1件少なく、ユーザーが安全性を重視して`gemini-3.8-flash`を選びました。この比較の後、別の直接比較に基づき一回生成候補がCloud Runへ統合され、現在の公開モデルは`gemini-3.8-flash`です。リポジトリのローカル既定値は`gemini-3.1-flash-lite`のままです。
- **回答分類器**: 開発用36件ではGemini 3.1 Flash-Liteが31/36、BGE-M3 zero-shotが6/36でした。mDeBERTaは全根拠が512 token上限を超えて推論前に停止。Jevは比較環境を用意できず未実施です。品質差からGeminiを維持しましたが、結果はsealed holdoutではありません。
- **一回生成 / 回答生成と独立分類**: ローカル既定の`production`経路は回答生成と分類処理を分けます。公開中のCloud Runは凍結promptの一回生成候補で、回答と分類ラベルを同じ呼び出しで出します。モデル比較結果を現在の独立分類器の性能とはみなしません。

実験の詳細は[回答生成モデルの選定記録](../eval/reports/GENERATION_MODEL_SELECTION_20261019.md)、[回答分類モデル比較](../eval/CLASSIFIER_MODEL_COMPARISON.md)にあります。
## 4. 工夫した点

ローカル既定の`production`経路は回答claimを根拠IDと結び付け、期限も条件が揃うケースだけ決定的に計算します。公開中の一回生成経路は回答と分類を一度に出し、検索された参照チャンクを表示しますが、独立分類attempt・claim単位の根拠リンク・期限計算は行いません。

Sealed visual holdoutではEnd-to-End成功率70%、分類精度70%でした。分類の事前閾値80%に届かず、総合受入は不合格です。Text holdout後の日付改善について、2回目のText sealed holdoutは未実施です。

- 実装: [`src/query_service.py`](../src/query_service.py) · [`src/answering.py`](../src/answering.py) · [`src/deadline_calculator.py`](../src/deadline_calculator.py)
- 回答・保留評価: [仕様、結果、採用判断](../eval/reports/PORTFOLIO_EVALUATION_AND_IMPROVEMENT_HISTORY_20261017.md)
