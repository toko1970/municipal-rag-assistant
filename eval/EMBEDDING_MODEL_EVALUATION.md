# Embeddingモデル比較評価

- 実行日: 2026-09-27
- 目的: Qdrant、文書、chunk、Top-k、評価setを固定し、Embedding profileだけを変更して節選択失敗が減るか確認する
- 評価元: `evaluation_questions_500.csv`の`variant_type=formal` 100件
- 検索評価対象: 88件。文書不足12件は検索失敗として数えない
- 評価元SHA-256: `1208bdb86358fd5f61c8cf4e86ace3cd03ea5e958cbdc2c838c25e4065d98601`

## 固定条件と変更条件

固定したもの:

- Qdrant 1.19.1、Cosine距離
- 架空Markdown 5文書、86 content element
- chunk 800文字、overlap 100文字
- Top-k 5
- formal 100シナリオ
- 回答生成・回答分類は実行しない

変更したもの:

| profile | 次元 | query入力規則 | document入力規則 | 実行場所 |
| --- | ---: | --- | --- | --- |
| `gemini-embedding-001` | 3072 | `RETRIEVAL_QUERY` | `RETRIEVAL_DOCUMENT` | Gemini API |
| `gemini-embedding-2-768` | 768 | `task: question answering \| query:` | `title: none \| text:` | Gemini API |
| `ruri-v3-310m` | 768 | `検索クエリ:` | `検索文書:` | ローカルApple MPS |

モデルごとに別のQdrant collectionを作った。既存の本番用collectionや他モデルのvectorを上書きしていない。

Gemini 2の768次元は、公式推奨次元の一つであり、自動正規化される。Ruriはモデル固有の768次元である。この比較はモデル、次元、モデル指定の入力規則をまとめたEmbedding profileの比較であり、モデル名だけを単独で変えた比較ではない。

## 結果

| 指標 | Gemini 001 baseline | Gemini 2 768 | Ruri v3 310M |
| --- | ---: | ---: | ---: |
| 全必要文書Hit@3 | **82/88** | **83/88** | 82/88 |
| 全必要文書Hit@5 | **85/88** | **85/88** | 84/88 |
| 全根拠見出しHit@3 | 63/88 | **64/88** | 62/88 |
| 全根拠見出しHit@5 | **74/88** | 72/88 | **74/88** |
| 最初の正解根拠MRR | **0.861** | 0.847 | 0.815 |
| Top-5 document missing | **3** | **3** | 4 |
| Top-5 section missing | 11 | 13 | **10** |

主要指標は全根拠見出しHit@5である。Gemini 2は2件悪化し、Ruriはbaselineと同数だった。MRRはbaselineが最も高い。

## 質問単位の変化

### Gemini 2 768

- 根拠Hit@5改善: Q151、Q381、Q411の3件
- 根拠Hit@5退行: Q186、Q201、Q281、Q391、Q446の5件
- 正味: 2件悪化

提出後の処理手順や適用開始日を改善した一方、改定、境界、判断、複数文書の質問を退行させた。文書Hit@3と根拠Hit@3だけを見ると改善しているため、複数指標と個別退行の確認が必要な例になった。

### Ruri v3 310M

- 根拠Hit@5改善: Q061、Q151、Q301、Q381の4件
- 根拠Hit@5退行: Q046、Q186、Q201、Q446の4件
- 正味: 変化なし

section missingは11件から10件へ1件減ったが、document missingが3件から4件へ増えた。最大原因への部分的な効果はあるものの、別の失敗へ移動しており総合改善とは判定しない。

## 実行特性と失敗から得たこと

Ruriは初回に約1.27GBのモデル取得が必要だった。取得後のローカルApple MPS実測は、86文書要素のEmbeddingが4.38秒、100質問が1.34秒だった。これはモデルdownloadと初期loadを含まないwarm実行時間である。API費用とrate limitはないが、Cloud Runで採用する場合はimage容量、memory、cold start、CPU時間を別に検証する必要がある。

Gemini 2はFree tierの毎分100 Embedding入力上限に達した。1 API callへまとめても、quotaはbatch内の入力数で数えられた。文書86件をcacheした後、別の時間枠で質問100件を処理した。失敗後も完了済みstageを再送しないため、文書vectorと質問vectorのcacheを分けている。初回Embedding時間は失敗runをまたいだため、比較可能な値として記録していない。

## 判断

現行の`gemini-embedding-001`を維持する。理由は主要指標で最高値と同率で、MRRが最も高く、変更による退行リスクと運用変更に見合う精度改善がないためである。

`gemini-embedding-2`のマルチモーダル対応は、今回のtext検索精度とは別の利点である。初期visual RAGは図表を構造化テキストへ変換して検索する設計なので、画像Embeddingを必須としない。画像そのものによるcross-modal検索を後から比較する場合に、別profileとして再検討する。

次の検索改善はEmbeddingを固定し、同じ文書内の類似した提出期限・処理手順を区別する施策を一つだけ試す。候補は、見出しをEmbedding対象本文へ明示的に加えるcontextual headingである。既存の簡易検証結果を再利用せず、今回のformal 100件と同じ指標で比較する。

## 再現用artifact

- runner: `compare_embedding_models.py`
- profileとadapter: `embedding_profiles.py`
- optional依存: `../requirements-ruri.txt`
- Gemini 2 raw result: `results/large_formal_gemini_embedding_2_768.csv`
- Gemini 2 manifest: `results/large_formal_gemini_embedding_2_768.json`
- Ruri raw result: `results/large_formal_ruri_v3_310m.csv`
- Ruri manifest: `results/large_formal_ruri_v3_310m.json`
- baseline: `results/large_formal_qdrant.csv`

参照した一次資料:

- Gemini Embeddings: https://ai.google.dev/gemini-api/docs/embeddings
- Ruri v3 310M model card: https://huggingface.co/cl-nagoya/ruri-v3-310m
