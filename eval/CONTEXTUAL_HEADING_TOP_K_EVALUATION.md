# Contextual heading検索深度評価

## 目的

contextual headingで複数根拠質問の必要節がTop-5から押し出される問題に対し、検索件数だけを増やす最小変更を評価する。Embedding、query vector、Qdrant collection、formal 100問は固定した。

## 検索結果

検索評価対象は、文書不足12問を除く88問である。

| k | 全必要文書Hit | 全根拠見出しHit | 100問の平均context文字数 | Top-5比 |
|---:|---:|---:|---:|---:|
| 5 | 85/88 | 78/88 | 372 | 1.00倍 |
| 6 | 86/88 | 78/88 | 447 | 1.20倍 |
| 7 | 87/88 | 79/88 | 526 | 1.41倍 |
| 8 | 87/88 | **82/88** | 606 | 1.63倍 |
| 9 | 87/88 | 83/88 | 686 | 1.84倍 |
| 10 | 87/88 | 84/88 | 764 | 2.05倍 |

Q446の不足していた`5. 住居届 > 5.2 提出期限`は8位、Q351の直接根拠`2. 住所変更届 > 2.1 提出が必要な場合`も8位だった。Top-8は両方を回復できる最小値で、全根拠見出しHitを78件から82件へ増やした。

Top-9とTop-10はそれぞれ1問ずつ追加で回復するが、平均context量がTop-5の1.84倍、2.05倍になる。まず最小のTop-8を回答回帰候補に固定した。

## 回答評価checkpoint

同じ8問のTop-8回答評価を開始したが、Gemini 2.5 FlashのFree tier日次20 request上限に達したため2問完了時点で停止した。これはCodex利用枠とは別のGemini API quotaである。

| 質問 | Top-5 | Top-8 | Top-5入力token | Top-8入力token |
|---|---|---|---:|---:|
| Q061 | 完全回答 | 完全回答 | 1,183 | 1,915 |
| Q141 | 完全回答 | 完全回答 | 1,166 | 1,840 |

完了した2問では正解を維持したが、generator入力tokenはそれぞれ約62%、58%増えた。2問だけでは回答品質を確定しない。Q151以降はquota reset後に同じCSVへ再開する。

runnerは正常結果と品質上の失敗を再利用し、`429`または`RESOURCE_EXHAUSTED`の行だけを再実行する。品質上の失敗を成功するまで再試行する挙動にはしない。

## 再開コマンド

```bash
.venv/bin/python -m eval.evaluate_contextual_answer_candidate \
  --input eval/evaluation_questions_500.csv \
  --baseline-retrieval eval/results/large_formal_qdrant.csv \
  --candidate-retrieval eval/results/large_formal_contextual_heading.csv \
  --query-cache .eval_cache/large_formal_query_vectors.json \
  --criteria eval/contextual_answer_review_criteria.json \
  --output eval/results/contextual_heading_top_8_answer_regression.csv \
  --top-k 8 \
  --contextual-only \
  --delay-seconds 1
```

再開後の採用条件は、Q446が完全回答へ回復し、Top-5で正しかった質問を悪化させず、増加tokenを許容できることである。

## 後続評価

Gemini 2.5 Flashの日次制限を待って続きを混在させず、GeneratorをGemini 3.1 Flash-Liteへ固定してTop-5とTop-8を両方再実行した。完了結果と採用判断は[`GEMINI_3_1_TOP_K_ANSWER_EVALUATION.md`](GEMINI_3_1_TOP_K_ANSWER_EVALUATION.md)を参照する。

## Artifact

- 検索runner: `compare_contextual_top_k.py`
- 検索raw結果: `results/contextual_heading_top_k.json`
- 回答途中結果: `results/contextual_heading_top_8_answer_regression.csv`
