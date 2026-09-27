# 100シナリオによるQdrant検索baseline

- 実行日: 2026-09-27
- 目的: Qdrant移行後の検索性能を難しい質問を含むdevelopment setで測り、次の改善対象を決める
- 評価元: `evaluation_questions_500.csv`の`variant_type=formal` 100件
- 評価元SHA-256: `1208bdb86358fd5f61c8cf4e86ace3cd03ea5e958cbdc2c838c25e4065d98601`

## 評価条件

| 条件 | 値 |
| --- | --- |
| Embedding | `gemini-embedding-001` |
| 文書 | 架空Markdown 5件 |
| content element | 86件 |
| chunk | 800文字、overlap 100文字 |
| top-k | 5 |
| 回答生成・分類 | 実行しない |

100件のうち、文書に答えがない12件は検索失敗として数えない。検索対象は88件である。ChromaとQdrantには質問ごとに同じquery vectorを渡し、vector store以外の条件を固定した。

当初は100問を1問ずつEmbedding APIへ送り、Free tierの1分当たり100 request上限で最後に失敗した。再実行では100問を1 batch requestでEmbeddingし、条件付きcacheへ保存した。これにより同一条件の再分析はAPI呼び出しなしで行える。

## ChromaとQdrantの比較

| 指標 | Chroma | Qdrant | 差 |
| --- | ---: | ---: | ---: |
| 全必要文書Hit@3 | 82/88 (93.2%) | 82/88 (93.2%) | 0 |
| 全必要文書Hit@5 | 85/88 (96.6%) | 85/88 (96.6%) | 0 |
| 全根拠見出しHit@3 | 63/88 (71.6%) | 63/88 (71.6%) | 0 |
| 全根拠見出しHit@5 | 74/88 (84.1%) | 74/88 (84.1%) | 0 |

質問単位の変化も0件だった。Qdrantへの変更は検索精度を改善も悪化もさせていない。Qdrantの採用理由は、PostgreSQLの正本データとの責務分離、安定ID、filterや検索実験の拡張性であり、精度向上ではない。

## 失敗分類

- `document_missing`: 必要文書が上位k件にすべて揃わない。複数文書質問で一部だけ取得した場合を含む。
- `section_missing`: 必要文書はすべて揃うが、必要な根拠見出しが一つ以上欠ける。
- `success`: 必要な根拠見出しがすべて揃う。

| cutoff | success | document missing | section missing | 失敗合計 |
| --- | ---: | ---: | ---: | ---: |
| Top-1 | 45 | 28 | 15 | 43 |
| Top-3 | 63 | 6 | 19 | 25 |
| Top-5 | 74 | 3 | 11 | 14 |

Top-5の失敗14件中、section missingは11件（78.6%）、document missingは3件（21.4%）だった。最大の弱点は「文書は見つかるが、必要な節が上位5件にすべて入らない」である。

Top-5失敗は、必要根拠が1件の質問で5件、2件で7件、3件で2件だった。単純に複数根拠だけの問題ではない。類似する届出の提出期限・処理手順、改正内容と適用開始日の組み合わせ、複数文書をまたぐ条件整理で失敗している。

代表例:

- Q141「通勤経路変更届は変更日から何日以内ですか？」: 文書は取得したが、同じ手続文書内の`4.2 提出期限`がTop-5に入らない。
- Q151「通勤経路変更届を受け付けた後の処理順序は？」: 文書は取得したが、`4.4 処理手順`が入らない。
- Q111「2025年10月以降の通勤距離基準は何km以上ですか？」: 改正後の基準は取得したが、正解条件に含む`適用開始日`が欠ける。
- Q131「2025年10月に通勤経路が変わり、1.8kmを車通勤する職員の要件と届出期限」: 3文書中、手続期限を持つDOC-004が欠ける。

## 次の判断

次はvector storeを再変更せず、同じ88件・同じchunk・同じTop-5でEmbeddingモデルだけを比較する。主要指標は全根拠見出しHit@5とし、補助指標としてHit@3、failure category、質問単位の改善・悪化を残す。

Embedding変更でsection missingが減るかを先に測る。改善しない場合は、質問分解、見出しを使った検索、parent-child retrieval、rerankerを一つずつ比較する。一度に複数の施策を入れないため、どの変更が効いたかを説明できる。

## 証拠

- backend比較条件・集計: `results/large_formal_backend_comparison.json`
- Chroma raw result: `results/large_formal_chroma.csv`
- Qdrant raw result: `results/large_formal_qdrant.csv`
- 失敗集計: `results/large_formal_qdrant_failure_analysis.json`
- Top-5失敗14件: `results/large_formal_qdrant_failures_at_5.csv`
- 再実行コード: `compare_vector_backends.py`、`analyze_retrieval_failures.py`
