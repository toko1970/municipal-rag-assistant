# Query Decomposition評価

## 1. 目的

Dense検索で必要根拠が候補外になった`Q156`、`Q291`、`Q436`に対し、質問を業務上の論点ごとに
分けて候補集合を広げる。正解文書IDや正解見出しは分解入力に使わず、質問本文の業務語、日付、
要求facetだけを使用した。

Gemini Embeddingsは複数入力のbatch embeddingに対応する。

- API: https://ai.google.dev/api/embeddings
- 価格確認: https://ai.google.dev/gemini-api/docs/pricing

## 2. 比較条件

- 評価セット: `evaluation_questions_500.csv`のformal 100問
- 検索対象: 90問（文書に答えがない10問を除外）
- 文書表現: contextual heading
- Embedding: `gemini-embedding-001`
- 出力: Top 5
- 分解対象: 質問本文だけから複数論点を検出した6問
- 統合: 各subqueryへ同数の候補枠を予約し、重複排除後に元質問の検索結果で補完
- sealed holdout: 未使用

分解後の11個の一意なsubqueryは1 batchで埋め込み、retryは0とした。保守的な上限見積りは
227 tokens、US$0.0000454で、事前上限US$0.001未満だった。

## 3. 検索結果

| 指標 | Dense baseline | Query Decomposition | 差 |
|---|---:|---:|---:|
| Document Hit@3 | 85/90 | 83/90 | -2 |
| Document Hit@5 | 87/90 | 89/90 | +2 |
| Evidence Hit@3 | 75/90 | 74/90 | -1 |
| Evidence Hit@5 | 80/90 | 82/90 | +2 |

Evidence Hit@5は`Q291`と`Q436`で改善し、退行は0件だった。事前gateの「対象3件中2件以上を
改善し、Evidence Hit@5とDocument Hit@5の退行0件」を満たした。`Q156`は必要文書まで取得
できたが、正解節の「住所変更届 > 提出が必要な場合」はTop 5へ入らず未改善だった。

Top 3は低下している。複数intentへ候補枠を配るため、単一intentの上位集中度と引き換えに
Top 5の網羅性が上がった。現在の回答処理がTop 8を使うことも含め、この候補を採用するには
回答回帰が必要である。

## 4. 回答回帰の部分結果

検索gate通過後、`Q291`と`Q436`をbaseline/candidateへ通す4シナリオの回答回帰を実行した。
上限は12 logical calls、US$0.02、retry 0とした。

| 質問 | baseline | candidate | 判定 |
|---|---|---|---|
| Q291 | 文書不足 | 根拠十分だが旧ルールを回答 | 検索は改善、内容は失敗 |
| Q436 | Gemini 503 | 根拠十分かつ内容正解 | paired比較不成立 |

`Q291`のcandidateは「扶養親族変更届は15日以内」を正しく答えた一方、「改正後は認定月から」
ではなく、旧FAQの「認定事由発生日の翌月から」を選んだ。Query Decompositionで新旧両方の
根拠が入った後、Generatorが旧情報を選び、Classifierもversion conflictを検出しなかった。
本番のVersion ResolverはClassifierがversion conflictを立てた後に動くため、このケースでは
`NOT_REQUIRED`となった。

`Q436`のbaseline生成時にGeminiが`503 UNAVAILABLE`を返した。評価器のfail-fast判定が
`ServiceUnavailable`表記だけを想定し、実際の文字列を認識できずcandidateを1件実行した。
そのため、このrunは採用gateに使用しない。追加retryや再実行は行っていない。生データは保持し、
`run_audit.json`で実行上の欠陥と実際の8 logical callsを記録した。

## 5. 判断

Query Decompositionは検索候補として有望だが、現時点では本番へ反映しない。検索のEvidence
Hit@5は2件改善したものの、総合回答成功のpaired評価が完了せず、Q291では版選択による回答生成
失敗が残ったためである。

次の最小実験は、Q291のような日付付き質問に対し、Generatorへ渡す前に適用時期と新旧根拠を
整理する処理を比較することである。後段Classifierのversion conflict検出だけに依存せず、
生成時点で有効な規程を選べるかを評価する。

## 6. 再現手順

検索比較（同名出力を上書きしないため、新しい出力先を使う）:

```bash
.venv/bin/python -m eval.compare_query_decomposition \
  --output-dir eval/results/query_decomposition_comparison_v2
```

回答回帰は今回の503をretryしない方針のため、自動再実行していない。新しい独立runを行う場合は、
修正済みfail-fastの確認後、新しい出力先と費用上限を指定する。
