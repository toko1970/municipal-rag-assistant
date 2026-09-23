# 500問評価に向けた回答生成モデル候補

2026-09-23時点の各社公式料金を基に比較した。モデルの一般ベンチマーク値を本RAGの精度として扱わず、同じ質問・検索結果・プロンプト・採点基準で実測して選定する。

## 比較用の費用仮定

500問を各1回実行し、1問あたり入力5,000トークン、出力400トークンと仮定する。

- 入力合計: 2.5Mトークン
- 出力合計: 0.2Mトークン
- 検索Embedding、再試行、キャッシュ、為替、税は含めない
- 実際の選定ではAPIレスポンスの使用トークンを保存して再計算する

## 候補

| 候補 | 入力 / 1M | 出力 / 1M | 500問の概算 | 位置付け |
| --- | ---: | ---: | ---: | --- |
| Gemini 2.5 Flash Standard | $0.30 | $2.50 | $1.25 | 現行モデル。Paid Tierならモデル変更なしで上限問題を解消しやすい |
| Gemini 2.5 Flash Batch | $0.15 | $1.25 | $0.63 | 即時応答が不要な一括評価の第一候補 |
| Gemini 3.1 Flash-Lite Standard | $0.25 | $1.50 | $0.93 | 同じGoogle SDKで利用できる低コスト候補。精度は要実測 |
| Gemini 3.5 Flash-Lite Standard | $0.30 | $2.50 | $1.25 | 2.5世代からの移行候補。3.1より新しいが費用は高い |
| GPT-5 mini | $0.25 | $2.00 | $1.03 | Structured Outputs対応。分類形式を安定させる候補 |
| Mistral Small 4 | $0.15 | $0.60 | $0.50 | 低コスト候補。日本語の制度文書と判断要分類を要実測 |
| Claude Haiku 4.5 | $1.00 | $5.00 | $3.50 | 高速モデル。候補中では費用が高いため100問で効果を確認してから拡大 |

公式情報:

- Gemini: <https://ai.google.dev/gemini-api/docs/pricing>
- OpenAI: <https://developers.openai.com/api/docs/models/gpt-5-mini>
- Mistral: <https://docs.mistral.ai/inference/pricing>
- Anthropic: <https://platform.claude.com/docs/en/models/overview>

## 推奨順序

### 1. Gemini 2.5 FlashのPaid TierまたはBatch

検索改善の比較では、回答生成モデルを変えると「検索変更の効果」と「モデル変更の効果」を分離できない。まず現行モデルを有料枠またはBatchで実行し、従来条件の基準値を確定する。

500問を同期APIで繰り返す必要がなければ、単価が半分のBatchを優先する。公開アプリの対話処理はStandard、オフライン評価はBatchという分離も可能である。

### 2. 100シナリオでモデル比較

次の4候補を`formal`の100問で比較する。

1. Gemini 2.5 Flash
2. Gemini 3.1 Flash-Lite
3. GPT-5 mini
4. Mistral Small 4

Claude Haiku 4.5は、上記候補の精度が不足する場合の追加候補とする。

### 3. 上位2モデルだけ500問で比較

100問で次の指標を測り、上位2モデルへ絞る。

- 回答分類一致率
- 回答要点の充足率
- 幻覚抑制率
- JSONまたは指定形式の遵守率
- 平均・中央値・95パーセンタイル応答時間
- 入力、出力、思考トークン
- 1問あたり費用と500問あたり費用

最終的なモデル選定は、全体平均だけでなく「文書不足」と「判断要」の失敗を重く見る。給与制度の問い合わせでは、根拠がない回答を断定する失敗の影響が大きいためである。

## 実装上の方針

モデル名を`config.py`で直接切り替えるだけでは、プロバイダーごとの処理が混在する。回答生成を共通インターフェースへ分離し、各プロバイダーの実装で次を統一して記録する。

- モデル名と固定バージョン
- temperature・reasoning設定
- 入出力トークン数
- 応答時間
- APIエラー種別と再試行回数
- 推定費用
- 生の回答と正規化した回答分類

評価実行と公開アプリのモデル切替は分け、比較完了前に公開設定を変更しない。

## 比較基盤

`src/llm_provider.py`でGemini、OpenAI、Mistralの応答を共通形式へ変換し、`eval/evaluate_models.py`で同じ質問と検索結果を使って比較する。公開アプリは引き続きGemini 2.5 Flashを使用する。

モデルごとに再検索すると検索順位の変動が回答比較へ混ざるため、最初に100問の検索結果をJSONLへ保存し、各モデルで共有する。

```bash
python -m eval.evaluate_models \
  --provider gemini \
  --prepare-retrieval-only
```

最初は5問でAPIキーと記録項目を確認する。

```bash
python -m eval.evaluate_models --provider gemini --limit 5
python -m eval.evaluate_models --provider gemini --model gemini-3.1-flash-lite --limit 5
python -m eval.evaluate_models --provider openai --limit 5
python -m eval.evaluate_models --provider mistral --limit 5
```

問題がなければ`--limit`を外してformal 100問を実行する。結果は質問ごとに保存され、同じコマンドを再実行すると完了済みの質問を飛ばして再開する。失敗行だけ再試行する場合は`--retry-errors`を付ける。

実行結果には、期待・予測分類、回答、検索文書、実モデル名、入出力トークン、応答時間、リクエストID、APIエラー、概算費用を保存する。回答要点の充足と幻覚有無は、モデル実行後に別途評価する。

必要な環境変数は次のとおりである。

- 検索とGemini回答: `GOOGLE_API_KEY`
- OpenAI回答: `OPENAI_API_KEY`
- Mistral回答: `MISTRAL_API_KEY`

OpenAIはResponses APIへ`store=false`で送信し、MistralはChat Completions APIを使用する。

2026-09-23のスモーク実行では`gemini-2.5-flash-lite`が新規利用者向けに提供されず、APIから`gemini-3.5-flash-lite`への移行案内が返った。そのため、2.5 Flash-Liteは比較候補から外し、現行の安価な候補として3.1 Flash-Liteを採用した。

## 5問スモーク結果

固定した同一検索結果を使い、formal質問の先頭5シナリオで実行経路と記録項目を確認した。

| モデル | 分類一致 | 入力トークン | 出力トークン | 概算費用 | 合計応答時間 |
| --- | ---: | ---: | ---: | ---: | ---: |
| Gemini 2.5 Flash | 4/5 | 2,935 | 2,560 | $0.00728050 | 19.166秒 |
| Gemini 3.1 Flash-Lite | 4/5 | 2,935 | 266 | $0.00113275 | 16.962秒 |

両モデルとも、会計年度任用職員の支給日は対象文書だけでは確定できないと本文では正しく回答したが、回答分類を`文書不足`ではなく`根拠十分`とした。これは回答内容の誤りではなく分類の誤りであり、分類一致率と内容妥当性を分けて評価する必要がある。

3.1 Flash-Liteはこの5問で概算費用が約84%低かった。ただし、5問は接続確認用であり、精度や費用の最終比較には使わない。次はformal 100問で同じ指標を測る。OpenAIとMistralはAPIキー未設定のため、まだ実測していない。

その後、3.1 Flash-Liteはformal 100問を完了し、回答分類一致84/100、回答生成エラー0、概算費用$0.02473575となった。詳細は[Gemini 3.1 Flash-Lite formal 100問評価](GEMINI_3_1_FORMAL_EVALUATION.md)に記録している。2.5 Flashは無料枠の日次20件制限により22問成功・1問保留で中断しているため、100問同士のモデル比較は未完了である。次回は`--retry-errors`を付けてQ111から再開する。
