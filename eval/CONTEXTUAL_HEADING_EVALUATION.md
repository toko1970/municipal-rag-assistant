# 親見出しをEmbeddingへ加える検索実験

2026-09-23に、検索失敗の最大原因だった「必要な節が上位5件に揃わない」問題へ対策を1つだけ適用した。公開アプリの検索方式は変更せず、評価用のChroma DBで同じ質問セットを比較した。

## 仮説

手続きマニュアルには「提出期限」という似た子見出しが複数ある。従来のチャンク本文には現在の子見出しが含まれる一方、「通勤経路変更届」「扶養親族変更届」などの親見出しはメタデータにしか保持されない場合があった。このため、Embeddingが各届出の期限を区別しにくいと考えた。

対策として、各チャンク本文の前に親を含む見出し階層を1行だけ加えてからEmbeddingした。

```text
見出し階層: 4. 通勤経路変更届 > 4.2 提出期限

## 4.2 提出期限
変更日から10日以内に提出すること。
```

Embeddingモデル、質問、正解条件、上位取得件数は変更していない。以前試したhybrid検索やクエリ分割も併用していない。

## 評価条件

- Embedding: `gemini-embedding-001`
- 上位取得件数: 5
- 文書: 架空の制度文書5件、86チャンク
- 難問: 20件（検索評価対象15件、文書不足5件）
- 実務寄り質問: 16件
- 比較対象: 公開アプリと同じvector検索
- 実験方式: 親見出し階層を本文へ加えたcontextual検索

評価用DBは`.eval_cache/contextual_chroma_db`へ保存し、文書・見出し・Embeddingモデルから作ったfingerprintが一致する間だけ再利用する。キャッシュはGitの管理対象外である。

## 結果

### 難問15件

| 指標 | vector | contextual | 差 |
| --- | ---: | ---: | ---: |
| 全必要文書Hit@1 | 7/15 | 9/15 | +2 |
| 全必要文書Hit@3 | 12/15 | 10/15 | -2 |
| 全必要文書Hit@5 | 13/15 | 14/15 | +1 |
| 全根拠見出しHit@1 | 4/15 | 7/15 | +3 |
| 全根拠見出しHit@3 | 8/15 | 8/15 | 0 |
| 全根拠見出しHit@5 | 10/15 | 12/15 | +2 |

- H03は全根拠見出しHit@5が失敗から成功へ変わった。
- H12とH17は、狙っていた提出期限の根拠が上位3件以内へ入った。
- H01は全必要文書Hit@5が成功へ変わったが、必要な見出しはすべて揃わなかった。
- H02は全必要文書・全根拠見出しともHit@5が成功から失敗へ変わった。
- H05はHit@5を維持したが、Hit@3では成功から失敗へ変わった。

### 実務寄り16件

| 指標 | vector | contextual | 差 |
| --- | ---: | ---: | ---: |
| 全必要文書Hit@1 | 11/16 | 12/16 | +1 |
| 全必要文書Hit@3 | 16/16 | 16/16 | 0 |
| 全必要文書Hit@5 | 16/16 | 16/16 | 0 |

実務寄り質問では、事前に定めた「Hit@3を16/16で維持する」という条件を満たした。

## コストと制約

- 評価用DBの初回作成で86チャンクをEmbeddingした。
- 完了した比較には、難問20件と実務寄り16件の質問Embeddingが必要だった。
- 初回実行はDB作成直後に1分100件の無料枠へ到達し、H16で停止した。キャッシュを再利用して20件を再実行したため、H01からH15までの質問Embeddingが重複した。
- 無料枠を利用しており、API料金とトークン数は取得していない。
- 回答生成の無料枠20件を使い切っていたため、H20の再実行とcontextual方式の回答品質評価は完了していない。

## 判断

親見出しの追加は、難問の全根拠見出しHit@5を`10/15`から`12/15`へ改善し、実務寄り質問のHit@3を`16/16`で維持したため、検索評価の事前条件を満たした。

一方で、難問の全必要文書Hit@3は`12/15`から`10/15`へ低下し、H02にはHit@5の退行がある。検索指標だけでは回答品質への最終的な効果を判断できないため、現時点では公開アプリへ採用しない。API上限解除後、同じ20件で回答分類・内容妥当性・幻覚抑制を比較して採否を決める。

## 再実行方法

```bash
python -m eval.evaluate_retrieval \
  --method contextual \
  --input eval/evaluation_questions_hard.csv \
  --output eval/results/hard_contextual.csv

python -m eval.evaluate_retrieval \
  --method contextual \
  --input eval/evaluation_questions_practical.csv \
  --output eval/results/practical_contextual.csv

python -m eval.compare_retrieval \
  --before eval/results/hard_baseline.csv \
  --after eval/results/hard_contextual.csv

python -m eval.evaluate_answer_quality \
  --method contextual \
  --input eval/evaluation_questions_hard.csv \
  --output eval/results/hard_answer_contextual.csv
```
