# Visual extraction format-normalized evaluation

## 目的

図表抽出の内容評価で、読点や空白の表記差と、金額・日付・条件語の意味差を分けて記録する。厳密一致の証拠は残し、format-normalized指標を追加する。

## 指標

従来の次の値は維持する。

- `matched_elements`
- `element_recall`
- `important_values_exact`
- `mean_bbox_iou`

同じ要素について、次の値を追加した。

- `format_normalized_matched_elements`
- `format_normalized_element_recall`
- `format_normalized_important_values_exact`
- `format_normalized_mean_bbox_iou`

Gateはformat-normalized完全一致、recall 0.95以上、mean bbox IoU 0.80以上で判定する。厳密値も結果へ残るため、表記差が何件あったか後から確認できる。

## 正規化範囲

- Unicode NFKCで全角・半角の表記をそろえる。
- 空白と`、`、`。`、`,`、`・`を除く。
- `-`、`+`、`:`、`/`、通貨記号、数字、単位、比較語は残す。

すべての記号を削除すると`-500円`と`500円`、`17:00`と`1700`を同一視する危険があるため、除外文字を限定した。

## 回帰ケース

| 差分 | 厳密一致 | format-normalized一致 | Gate |
|---|---|---|---|
| `記載内容・添付書類` / `記載内容、添付書類` | 不一致 | 一致 | 通過 |
| `確認` / `破棄` | 不一致 | 不一致 | 不通過 |
| `-500円` / `500円` | 不一致 | 不一致 | 不通過 |
| `17:00` / `1700` | 不一致 | 不一致 | 不通過 |

## Development評価

保存済みdevelopment raw 6件をAPI call 0で再評価した。

| 指標 | 結果 |
|---|---:|
| Schema valid | 6 / 6 |
| strict important values exact | 6 / 6 |
| format-normalized important values exact | 6 / 6 |
| Gate pass | 4 / 6 |
| API call | 0 |

既存developmentには表記差がなかったため、結果は4/6のまま変わらない。flowchart 2件の不合格理由はmean bbox IoUが0.80未満であり、文字正規化で隠していない。

評価revisionは`visual-extraction-eval-v3`、集計結果は`eval/results/visual_extraction_candidate_format_normalization_v1/summary.json`に保存した。再評価入力には既存baseline rawを使用し、同一内容のraw・normalizedコピーは重複保存しない。消費済みholdoutは再採点せず、次の新規holdoutからこの評価定義を適用する。
