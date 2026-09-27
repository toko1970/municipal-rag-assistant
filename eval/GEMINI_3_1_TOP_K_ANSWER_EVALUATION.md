# Gemini 3.1 Flash-LiteによるTop-k回答比較

## 目的

回答生成モデルをGemini 3.1 Flash-Liteへ固定し、contextual heading検索のTop-5とTop-8を同じ8問で比較する。Top-5をGemini 2.5 Flash、Top-8を3.1 Flash-Liteにするような条件混在は行わない。

対象8問は、formal 100問でcontextual headingによって根拠見出しHit@5が変化した質問である。変化例を意図的に選んだ回帰試験であり、全質問の正解率ではない。

## 固定条件

| 項目 | 条件 |
|---|---|
| Generator | `gemini-3.1-flash-lite` |
| Classifier | `gemini-3.1-flash-lite` |
| Embedding | `gemini-embedding-001` |
| Vector DB | Qdrant |
| 文書vector | contextual heading |
| query vector | baseline cacheを共用 |
| 比較対象 | Top-5 / Top-8 |
| 実行日 | 2026-09-27 |

## 結果

| 指標（8問中） | Top-5 | Top-8 | 差 |
|---|---:|---:|---:|
| 実行完了 | 8 | 8 | 0 |
| 期待ラベル一致 | 7 | 7 | 0 |
| 必須内容・順序一致 | 6 | **8** | +2 |
| 全件確認で完全回答 | 6 | **7** | +1 |
| 全件確認で部分回答 | 1 | 1 | 0 |
| エラー | 0 | 0 | 0 |
| Generator入力token | 9,655 | 15,237 | +57.8% |
| Generator出力token | 1,737 | 2,011 | +15.8% |
| Generator概算費用 | $0.00502 | $0.00683 | +36.0% |

概算費用はStandard paid list priceの入力`$0.25 / 1M tokens`、出力`$1.50 / 1M tokens`で計算した。現行ログ契約ではClassifier tokenを保存していないため、表のtokenと費用はGeneratorだけである。

## 質問単位の差

### Top-8で改善

- Q351: 住所変更届の直接根拠が8位で入り、転居時に提出が必要であることを明示した。
- Q446: 提出期限が8位で入り、改正後要件、必要書類、入居日から30日以内を一つの回答にまとめた。

### Top-8で分類が退行

Q301は回答本文で「扶養実態や生計維持関係を総合確認し、人事給与課へ確認する」と正しく説明したが、Top-8では`requires_case_facts=false`となり、期待する`判断要`ではなく`根拠十分`になった。追加根拠に制度所管部署確認の節が含まれていても、Classifierが個別事情の必要性を安定して判定できるとは限らない。

### 維持

Q061、Q141、Q151、Q266、Q381は両条件で完全回答だった。Top-8で追加された根拠による内容上の幻覚は全件確認では見つからなかった。

## Gemini 2.5 Flashからの変更判断

同じ8問の旧Top-5 runでは、Gemini 2.5 Flashが1件の表示失敗を起こし、Generator出力tokenは7,614だった。Gemini 3.1 Flash-LiteのTop-5は8/8件を完了し、出力tokenは1,737だった。必須内容一致はどちらも6/8だが、3.1は日次20件で停止した2.5より評価を継続でき、構造化出力も安定した。

この結果と既存formal 100問の100/100件完了実績を合わせ、既定Generatorを`gemini-3.1-flash-lite`へ変更する。環境変数`LLM_MODEL_NAME`で明示的に差し替え可能にする。

## Top-8の判断

Top-8はQ446を完全回答へ回復し、必須内容一致を8/8にした。Generator概算費用は8問合計で約0.00181ドル増えた。Q301の分類退行は検索根拠不足ではなくClassifierの要因判定であり、Top-5へ戻してQ446を回答不能にするより、Top-8を検索候補として採用し分類評価を別の改善単位にする。

active collectionへの反映時は、contextual headingの文書Embedding前処理とTop-8を同時にproduction ingestionへ適用し、collectionを再構築する。旧baseline collectionは比較証拠として保持する。

## Artifact

- raw result: `results/contextual_heading_gemini_3_1_top_k_answer.csv`
- manual review: `contextual_heading_gemini_3_1_top_k_manual_review.csv`
- 内容判定基準: `contextual_answer_review_criteria.json`
- 検索Top-k比較: `CONTEXTUAL_HEADING_TOP_K_EVALUATION.md`
