# Sudachi BM25 + RRF検索評価

## 目的

評価セットv1.2で残った検索失敗3件（Q156、Q291、Q436）へ、現行dense検索を維持したまま
日本語sparse検索を追加し、必要根拠のcoverageを改善できるか確認した。

旧Chromaでは文字n-gram TF-IDFによるhybrid検索を試し、実務寄り質問を退行させて不採用に
している。今回はその実装を再利用せず、現行のQdrant用content element、contextual heading表現、
固定EmbeddingでBM25を独立比較した。

## 学習上の仮説

- dense検索は言い換えに強いが、届出名、日数、制度名の完全一致が薄まる場合がある。
- BM25は稀な完全一致語を強く評価できる。
- denseとsparseのscore尺度は異なるため、score加算ではなく順位だけを使うRRFで統合する。

Sudachiは長い単位を保持するSplitMode Cを使い、`扶養親族`、`変更届`などの制度語をtoken化した。
[SudachiPy API](https://worksapplications.github.io/sudachi.rs/python/api/sudachipy.html)

## 評価条件

| 条件 | 値 |
|---|---|
| 質問 | gold v1.2 formal 100問 |
| 検索評価対象 | 90問 |
| content element | 86件 |
| dense | `gemini-embedding-001` contextual heading、cache再利用 |
| sparse | SudachiPy 0.7.0 SplitMode C + BM25 |
| BM25 | `k1=1.2`、`b=0.75` |
| 候補数 | dense 20、sparse 20 |
| fusion | RRF、`k=60` |
| 評価cutoff | Top-3、Top-5 |
| 外部API call / 費用 | 0 / US$0 |
| sealed holdout | 未使用 |

dense baselineとhybrid候補は同じ実行内で作成し、同じ質問・gold・cacheを使った。Qdrant Cloudは
使わず、in-memory Qdrantでdense順位を再現した。Sudachi辞書は評価依存へ分離し、本番Docker
imageには追加しない。

## 結果

| 指標 | dense | BM25 + RRF | 差 |
|---|---:|---:|---:|
| 全必要文書Hit@3 | 85/90 | 81/90 | -4 |
| 全必要文書Hit@5 | 87/90 | 85/90 | -2 |
| 全根拠見出しHit@3 | 75/90 | 65/90 | -10 |
| 全根拠見出しHit@5 | 80/90 | 73/90 | -7 |

- 検索失敗3件の改善: 0件
- 全根拠見出しHit@5の既存成功からの退行: 8件
- 全必要文書Hit@5の退行: Q131、Q436、Q446
- 検索p50: dense約1.69ms、hybrid約2.40ms

事前gateの「対象3件中2件以上改善、Top-5退行0」を満たさないため、候補は不採用とした。

## なぜ効かなかったか

BM25は質問と文書に共通する語を拾ったが、「場合」「届出」「通勤」など複数文書に現れる語の
一致も強く評価した。Q156では住所変更の根拠がsparse Top-20へ入らず、通勤や他手当のFAQが
上位を占めた。Q291でも扶養親族変更届の提出期限はsparse Top-20外だった。

RRFはdenseとsparseの両方で一定順位にある要素を強くする。そのためsparse順位が質問の各要求を
分離できない場合、denseの良い順位まで押し下げる。この挙動が正常8件の退行につながった。

## rerankingを次にしない理由

dense候補をTop-30まで診断した結果は次のとおりである。

| ID | 必要根拠のdense順位 |
|---|---|
| Q156 | 通勤手当支給停止=1位、住所変更届=Top-30外 |
| Q291 | 経過措置=1位、改正後=8位、扶養親族変更届期限=9位 |
| Q436 | 通勤手当支給停止=2位、住所変更届期限=27位 |

rerankerは渡された候補の並べ替えであり、候補外のQ156根拠を生成できない。候補を20件とすると
Q436も対象外になる。Q291だけは適合するが、1件のために全質問へrerankerを追加しても最大原因を
解消できない。

次は、質問を「通勤手当の処理」「住所変更届の手続」「扶養手当の支給開始」「届出期限」のように
副質問へ分け、それぞれをdense検索して候補を統合するQuery Decompositionを小規模に比較する。
これは単一queryで別topicの根拠が競合する今回の失敗へ直接対応する。

## 再現方法

```bash
python -m pip install -r requirements-eval.txt
.venv/bin/python -m eval.compare_bm25_hybrid \
  --output-dir eval/results/bm25_hybrid_comparison_v1
```

既存artifactは上書きしないため、再実行時は新しい出力先を指定する。
