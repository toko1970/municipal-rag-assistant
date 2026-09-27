# ChromaからQdrantへの検索移行評価

- 実行日: 2026-09-27
- 目的: ベクトルDBの変更と検索精度改善を分離し、DB移行だけで退行しないことを確認する
- 評価質問: `evaluation_questions_practical.csv` 16件
- 質問set SHA-256: `312637d937942a8a430b667ae5ab3384703f98a31719248f98422e933458c8e8`

## 固定した条件

| 条件 | 値 |
| --- | --- |
| Embedding | `gemini-embedding-001` |
| 文書 | `docs/*.md` 5件 |
| content element | 86件 |
| chunk | `CHUNK_SIZE=800`、`CHUNK_OVERLAP=100`、同じ`split_documents()` |
| top-k | 5 |
| 変更した要因 | ChromaからQdrantへのvector store変更だけ |

文書不足質問はこのsetに含まれない。回答生成・分類は実行せず、検索だけを評価した。

## 結果

| 指標 | Chroma | Qdrant | 差 |
| --- | ---: | ---: | ---: |
| Hit@1 | 11/16 (68.75%) | 11/16 (68.75%) | 0 |
| Hit@3 | 16/16 (100%) | 16/16 (100%) | 0 |
| Hit@5 | 16/16 (100%) | 16/16 (100%) | 0 |

- 取得文書IDの順位差: 0/16
- 取得見出しの順位差: 0/16
- PostgreSQLの`INDEXED`要素: 86件
- Qdrant point: 86件
- 欠落ID: 0件
- 余分なID: 0件

raw result:

- Chroma: `eval/results/practical_baseline.csv`
- Qdrant: `eval/results/practical_qdrant.csv`

## 判断

Qdrantへの移行を採用する。この評価から、Qdrant自体による精度向上は主張しない。同じEmbeddingとchunkでは検索順位が一致し、主要な検索指標にも変化がなかった。

採用理由は、PostgreSQLの文書・ログ正本と検索indexの責務を分離できること、安定UUIDとmetadata filterを使えること、今後のEmbedding・filter・hybrid検索を独立experimentとして比較しやすいことである。

Hit@1は11/16に留まるため、精度改善はDB変更とは別にEmbedding比較と失敗分類で行う。
