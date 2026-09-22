# 難問セットによる検索評価と比較

2026-09-22に、架空の制度文書5件・Chromaの86チャンクを対象に実検索しました。保存済みチャンクは現在の文書から再生成した86チャンクと本文・文書ID・見出しが一致しました。文書5件のファイル名と内容を連結したSHA-256は `422b43b813aba01b4cac473ab0cd754226011cde6828477122c7696adf6cfb7e` です。両方式の比較前に [evaluation_questions_hard.csv](evaluation_questions_hard.csv) の20件と正解条件を固定し、同じセットで測定しました。

## 評価条件

| 種類 | 件数 | 例 |
| --- | ---: | --- |
| 複数文書 | 5 | 改正後の支給基準と届出期限を別文書から確認する |
| 文書に答えがない | 5 | 会計年度任用職員の給料日を尋ねる |
| 言い換え・誤字 | 5 | 「入金日」「家ちん」などの表現を使う |
| 似ているが答えの異なる質問 | 5 | 届出の受付可否と提出期限を分けて尋ねる |

正解には必要な文書IDと見出しパスを記録しました。複数文書の質問は**すべての必要文書・見出しが取得された場合だけ**Hitとします。文書不足の5件は検索対象の正解文書を持たないため、検索Recallの分母から外します。検索結果は記録しますが、この評価で回答分類や幻覚抑制の成否は判定しません。

両方式ともEmbeddingは `gemini-embedding-001`、出力は上位5チャンクです。比較対象は次のとおりです。

- **vector**：公開アプリと同じChromaのベクトル類似検索。候補上位5件をそのまま返す。
- **hybrid（実験）**：ベクトル候補上位30件について、見出しと本文の文字2・3-gram TF-IDF類似度も計算し、両順位をRRF（定数60）で統合して上位5件を返す。実装は [hybrid_retriever.py](hybrid_retriever.py) にあり、公開アプリでは使用していません。

見出しの一致はチャンクの文書IDと見出しパスで判定します。同じ見出しの内部がさらに分割される場合、この指標だけでは本文の正しさを保証できません。

## 結果

難問セットの検索対象15件について、同じ正解条件で比較しました。分数は成功件数／対象件数です。

| 指標 | vector | hybrid（実験） |
| --- | ---: | ---: |
| 全必要文書Hit@3 | 12/15 | 13/15 |
| 全必要文書Hit@5 | 13/15 | 14/15 |
| 全根拠見出しHit@3 | 8/15 | 10/15 |
| 全根拠見出しHit@5 | 10/15 | 12/15 |

質問別の結果は [改善前CSV](results/hard_baseline.csv) と [実験CSV](results/hard_hybrid.csv) に保存しました。H04は通勤手当の支給停止と住所変更届の期限を上位3件で取得できるようになりました。H12の届出期限、H16の受付可否も改善しました。一方、H02は住居手当の支給条件と改正後の基準を取得しても、住居届の**必要書類**の節が上位5件から外れました。H01・H03など、複数文書の根拠が揃わない質問も残っています。

既存の実務寄り16問も同条件で比較すると、文書Hit@3は **16/16 → 15/16** でした。「通勤ルートを変更した場合の手続き」で、DOC-004が4位へ下がったためです。[改善前CSV](results/practical_baseline.csv) と [実験CSV](results/practical_hybrid.csv) に記録しています。難問の平均値が改善しても既存質問に退行があるため、hybrid方式は評価用の実験として残し、公開アプリの検索方式は変更しません。

## 再実行方法

`GOOGLE_API_KEY` が必要です。各実行は質問のEmbedding APIを呼びます。プロジェクトルートから実行してください。

```bash
python -m eval.evaluate_retrieval --method vector --input eval/evaluation_questions_hard.csv --output eval/results/hard_baseline.csv
python -m eval.evaluate_retrieval --method hybrid --input eval/evaluation_questions_hard.csv --output eval/results/hard_hybrid.csv
python -m eval.compare_retrieval --before eval/results/hard_baseline.csv --after eval/results/hard_hybrid.csv
```

既存16問を再評価する場合は `--input eval/evaluation_questions_practical.csv` を指定し、方式ごとに別の出力ファイル名を使います。比較コマンドは質問文・正解条件が変わると失敗します。回答生成の正確さや「文書不足」の分類は、別の回答品質評価で検証する必要があります。
