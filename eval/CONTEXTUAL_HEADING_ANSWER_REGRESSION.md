# Contextual heading回答回帰評価

## 目的

見出し文脈を文書Embeddingへ加えた候補が、検索指標だけでなく最終回答にも効果を持つかを確認する。active collectionは変更せず、同じ質問、query vector、生成モデル、分類モデル、`top_k=5`で検索collectionだけを切り替えた。

この評価はformal 100問のうち、根拠見出しHit@5が変化した8問を意図的に選んだ回帰試験である。母集団から無作為抽出した精度ではないため、結果を全質問の正解率として扱わない。

## 固定条件

| 項目 | 条件 |
|---|---|
| 質問 | Q061、Q141、Q151、Q266、Q301、Q351、Q381、Q446 |
| 比較 | baseline Qdrant / contextual heading Qdrant |
| query vector | `gemini-embedding-001`のbaseline cacheを共用 |
| generator | `gemini-2.5-flash` |
| classifier | `gemini-3.1-flash-lite` |
| 検索件数 | 5 |
| 内容判定 | API実行前に固定した必須語・順序 |
| 実行日 | 2026-09-27 |

判定基準は[`contextual_answer_review_criteria.json`](contextual_answer_review_criteria.json)、raw結果は[`results/contextual_heading_answer_regression.csv`](results/contextual_heading_answer_regression.csv)、全件確認は[`contextual_heading_answer_manual_review.csv`](contextual_heading_answer_manual_review.csv)に残す。「受付」と「受け付け」は同じ語の表記差なので、実測後に正規表現の偽陰性だけを修正した。回答や正解内容は変更していない。

## 結果

| 指標（8問中） | baseline | contextual heading | 差 |
|---|---:|---:|---:|
| 正常に表示まで完了 | 7 | 7 | 0 |
| 期待ラベル一致 | 4 | 7 | +3 |
| 必須内容・順序一致 | 4 | 6 | +2 |
| 全件確認で完全回答 | 3 | 6 | +3 |
| 全件確認で部分回答 | 1 | 1 | 0 |
| エラー | 1 | 1 | 0 |

検索改善6問のうち、Q141・Q266・Q381は完全回答へ改善した。Q151は「経路確認、支給額確認、システム登録」まで改善したが、goldの先頭手順「受付」を省略した。Q061とQ301は両方式で正解した。

検索退行2問のうち、Q351は直接の住所変更手続節がTop-5外になっても届出義務の根拠から正解を維持した。Q446は提出期限の根拠がTop-5外となり、候補方式だけ表示に失敗した。

## 発見した失敗境界

### 検索改善が回答改善へつながった例

- Q141: 提出期限の節が入り、「変更日から10日以内」を回答できた。
- Q266: 提出期限の節が入り、「事由発生日から15日以内」を回答できた。
- Q381: 給与口座変更の処理手順が入り、別手続の処理順から正しい処理順へ変わった。

### 検索が良くても完全回答にならない例

Q151は正解節を取得してラベルも正しくなったが、4段階のうち「受付」を出力しなかった。これは検索失敗ではなく回答生成の網羅性不足として分けて扱う。

### groundingと質問への適合は別の検査

Q381のbaselineは、取得した別手続の文章には沿った回答だったため`answer_fully_supported=true`になった。しかし給与口座変更の質問には答えていない。現行classifierのsupport判定だけでは、質問への適合性を保証できない。

### 表示不整合を隠さない

Q141 baselineとQ446 candidateは、classifierが「根拠十分」を返した一方、generator側にclaim欠落または不足条件があり、コードの表示条件で停止した。成功するまで再実行せず、`分類・表示失敗`として残した。この不整合はclassifierと構造化回答の契約を改善する対象である。

## 判断

contextual headingは対象8問で完全回答を3件から6件へ増やし、検索改善が最終回答にも届くことを確認できた。一方、複数文書から要件・書類・期限を集めるQ446を悪化させたため、この時点ではactive collectionへ反映しない。

次の変更は一つに絞り、contextual headingのまま複数根拠質問で必要節を落とさない取得方法を比較する。候補は`top_k`拡大または多様性を考慮した取得である。Q446の期限回復、Q151の網羅性、追加ノイズとtoken増加を同じ8問で測り、採用後にformal 100問を再評価する。

## コスト計測上の制約

generatorのtokenはraw結果へ保存できたが、現行のclassification logging contractはclassifierのtoken数を保存しない。このrunではclassifier tokenを0として記録しているため、合計token費用の比較には使わない。応答時間もAPI混雑を含む8問だけの値なので性能判断には使わない。

## 再現コマンド

```bash
.venv/bin/python -m eval.evaluate_contextual_answer_candidate \
  --input eval/evaluation_questions_500.csv \
  --baseline-retrieval eval/results/large_formal_qdrant.csv \
  --candidate-retrieval eval/results/large_formal_contextual_heading.csv \
  --query-cache .eval_cache/large_formal_query_vectors.json \
  --criteria eval/contextual_answer_review_criteria.json \
  --output eval/results/contextual_heading_answer_regression.csv \
  --delay-seconds 1
```

既存結果は再利用し、未実行の組だけを追加する。既存の失敗も実測結果として再利用し、成功するまでの自動再試行は行わない。
