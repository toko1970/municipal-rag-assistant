# Contextual headingのformal 100件評価

- 実行日: 2026-09-27
- 目的: 最大の検索失敗原因だった節選択失敗へ、文書名・見出し階層の追加だけで対処できるか確認する
- 評価元: `evaluation_questions_500.csv`の`variant_type=formal` 100件
- 検索評価対象: 88件。文書不足12件は検索失敗として数えない
- 評価元SHA-256: `1208bdb86358fd5f61c8cf4e86ace3cd03ea5e958cbdc2c838c25e4065d98601`

## 仮説と変更点

手続文書には「提出期限」「処理手順」のような同じ子見出しが複数ある。本文だけのEmbeddingでは、通勤経路変更届、扶養親族変更届、給与口座変更届などの親文脈を区別しにくい。

文書Embeddingの入力だけを次の形へ変更した。

```text
文書: 届出・手続きマニュアル
見出し: 4. 通勤経路変更届 > 4.2 提出期限

変更日から10日以内に提出すること。
```

質問Embedding、Embeddingモデル、chunk、Top-k、Qdrant、評価setはbaselineと同じである。回答生成・分類は実行していない。

## 固定条件

| 条件 | 値 |
| --- | --- |
| Embedding | `gemini-embedding-001`、3072次元 |
| 質問vector | baselineの`RETRIEVAL_QUERY` vectorを再利用 |
| 文書 | 架空Markdown 5件、86要素 |
| chunk | 800文字、overlap 100文字 |
| Top-k | 5 |
| vector store | Qdrant 1.19.1、Cosine距離 |
| 実験collection | `municipal_docs_eval_gemini_001_contextual_heading_v1` |

実験collectionは本番用collectionと分離した。Qdrant payloadへ保存する本文は原文のままとし、文書名・見出しを加えた文字列はvector生成だけに使用した。回答生成へ同じ情報を二重表示しない。

## 結果

| 指標 | baseline | contextual heading | 差 |
| --- | ---: | ---: | ---: |
| 全必要文書Hit@3 | 82/88 | **83/88** | +1 |
| 全必要文書Hit@5 | **85/88** | **85/88** | 0 |
| 全根拠見出しHit@3 | 63/88 | **73/88** | +10 |
| 全根拠見出しHit@5 | 74/88 | **78/88** | +4 |
| 最初の正解根拠MRR | 0.861 | **0.904** | +0.043 |
| Top-5 document missing | 3 | 3 | 0 |
| Top-5 section missing | 11 | **7** | -4 |

主要指標の全根拠見出しHit@5は84.1%から88.6%へ4.5ポイント改善した。最大原因だったsection missingは11件から7件へ減った。Hit@3は11.4ポイント改善し、正解根拠がより上位へ移った。

初回の文書86要素Embeddingは1 API call、2.32秒だった。質問vectorはcacheを再利用した。二回目はEmbedding API呼び出し0回でraw resultがbyte単位で一致した。

## 質問単位の改善と退行

根拠Hit@5の改善6件:

- Q061: 給与口座変更の提出期限
- Q141: 通勤経路変更届の提出期限
- Q151: 通勤経路変更届の処理手順
- Q266: 扶養親族変更届の提出期限
- Q301: 別居している父母の扶養認定
- Q381: 給与口座変更届の処理手順

このうちQ061、Q141、Q151、Q266、Q381は、同じ手続文書に類似見出しが複数あるという仮説へ直接対応する改善である。

根拠Hit@5の退行2件:

- Q351「転居した職員は住所変更届を出す必要がありますか？」: baselineでは正解節が5位だったが、contextual headingではDOC-004自体がTop-5から外れた。
- Q446「2025年10月に本人名義で契約し、家賃15,500円を負担する住宅へ入居した場合の要件・書類・期限は？」: 必要3文書は取得したが、`5.2 提出期限`が`改正後`と`経過措置`に押し出された。

根拠Hit@3は10件改善し、退行0件だった。Top-5では複数条件を要求する質問で候補枠が不足する退行が残る。

## 判断

contextual headingを次の候補実装として固定する。Embeddingモデル変更では得られなかった、最大失敗原因への明確な改善があり、変更内容も文書Embedding入力の前処理に限定できるためである。

この時点では公開アプリのactive collectionへ切り替えない。Q351とQ446の退行が回答品質へ及ぼす影響を含め、development質問の回答生成・分類をbaselineと比較する。検索改善が最終回答の改善につながり、根拠なし断定を増やさないことを確認してから、production ingestionへ同じ前処理を適用する。

sealed holdoutはcandidate実装と評価条件を固定した後に一度だけ実行する。退行を見てからholdoutの質問や正解条件を変更しない。

## artifact

- runner: `compare_contextual_heading.py`
- raw result: `results/large_formal_contextual_heading.csv`
- 条件・集計・質問単位差分: `results/large_formal_contextual_heading.json`
- baseline: `results/large_formal_qdrant.csv`
- 旧20問・Chroma実験: `CONTEXTUAL_HEADING_EVALUATION.md`
