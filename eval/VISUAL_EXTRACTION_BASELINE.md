# Gemini 3.1 visual extraction baseline

## 1. 目的と固定条件

6種類のdevelopment fixtureを同じprompt、Schema、モデルで一度ずつ抽出し、意味抽出と位置抽出を分けて評価した。実行中にpromptを変更せず、自動retryを行っていない。`flowchart_dev_001`は直前の同一prompt実行結果を再利用し、残り5件を一つのbatch commandで実行した。

- model: `gemini-3.1-flash-lite`
- prompt: `visual-extraction-v1`
- manifest: `development_manifest.json` version 1.0
- initial evaluation: 重要値完全一致、要素Recall 0.95以上、平均bbox IoU 0.80以上
- API calls: 5（再利用1件）
- measured latency: 30.626秒（API実行5件の合計）
- tokens: input 7,904、output 9,920、合計17,824

## 2. baseline結果

| fixture | 種類 | 重要値 | Recall | bbox IoU | status |
|---|---|---:|---:|---:|---|
| `flowchart_dev_001` | flowchart | 一致 | 1.000 | 0.662 | gate未達 |
| `flowchart_dev_002` | flowchart | 一致 | 1.000 | 0.629 | gate未達 |
| `timeline_dev_001` | timeline | 一致 | 1.000 | 0.933 | 合格 |
| `table_dev_001` | table | 不一致 | 0.867 | 0.976 | gate未達 |
| `form_dev_001` | form | 一致 | 1.000 | 0.985 | 合格 |
| `table_dev_002` | table | 採点不能 | 採点不能 | 採点不能 | semantic validation失敗 |

raw、normalized候補と機械可読summaryは[`visual_extraction_baseline_gemini_3_1_v1`](results/visual_extraction_baseline_gemini_3_1_v1/)へ保存した。

## 3. 評価revisionの修正

`table_dev_001`の不一致2件は、意味が同じ波ダッシュ`〜`と`～`の文字コード差だった。業務値の誤抽出ではないため、比較時だけ`～`を`〜`へ正規化する`visual-extraction-eval-v2`を作成し、保存済みraw出力を再採点した。評価条件を変えたためbaseline結果を上書きせず、別revisionとして[`visual_extraction_baseline_gemini_3_1_eval_v2`](results/visual_extraction_baseline_gemini_3_1_eval_v2/)へ保存した。

この修正により`table_dev_001`は重要値一致、Recall 1.000、bbox IoU 0.976で合格し、全体の合格は2件から3件になった。

## 4. Revolve改善round 1

`table_dev_002`は5行目のcellを抽出している一方、モデルが`row_count=4`を返したためsemantic validationに失敗した。業務値やcellを変更せず、宣言行列数がcell範囲より小さい場合だけ必要数へ拡張する決定的な正規化を追加した。

- before: validated 5/6、gate合格3/6、invalid 1
- after: validated 6/6、gate合格4/6、invalid 0
- `table_dev_002`: 重要値一致、Recall 1.000、bbox IoU 0.936
- regression: 他5 fixtureの指標低下なし

改善結果は[`visual_extraction_candidate_table_shape_v1`](results/visual_extraction_candidate_table_shape_v1/)へ保存した。

## 5. 残る失敗と判断

2つのflowchartはnode、edge、分岐条件を全件取得し、重要値一致とRecall 1.000を達成した。一方、矢印を端点として返す、細い線として返す、decision nodeの領域が狭いなど誤差の形が異なり、bbox IoUは0.662と0.629だった。

単一のpadding値をdevelopment fixtureへ合わせると未知文書への過適合になる。初期版の表示要件はページ画像全体で、bbox highlightは任意であるため、自動補正の追加roundは行わない。flowchartは`REVIEW_REQUIRED`のまま人が画像と構造を確認し、位置精度未達を既知の限界として公開説明へ残す。

## 6. sandbox失敗からのharness改善

最初のbatchは現在sessionのnetwork sandboxでDNS解決に失敗した。runnerが同じ接続障害を5件繰り返したため、共有transport errorの後は残りを`SKIPPED`にする回帰処理を追加した。失敗runは[`visual_extraction_baseline_gemini_3_1_v1_sandbox_blocked`](results/visual_extraction_baseline_gemini_3_1_v1_sandbox_blocked/)へ残した。
