# Visual sealed holdout prediction result

## 実行条件

- candidate Git commit: `6a2d7e628ba91eb939f13edbe37eaab2a23f026a`
- run ID: `visual_holdout_predictions_v1`
- sealed PDF: 6件
- public question: 20件
- logical external call上限: 67
- Gemini費用上限: US$0.35
- retry: 0
- gold access: なし

候補、設定、developmentでの選定根拠を先に`CANDIDATE_FROZEN`としてcommitし、その後にだけsealed PDFを入力した。

## 結果

2件目のPDF `vh_doc_m2`で図表抽出結果がSchema検証に失敗し、fail-fastした。

```text
ValueError: flowchartにはstart nodeが1件必要です
```

抽出結果は先頭ノード「当月の夜間対応を集計」を`process`と判定した。現行Schemaはflowchartにstart nodeを1件要求するため、検索indexの構築前に停止した。

| 項目 | 件数 |
|---|---:|
| 図表抽出API attempt | 2 |
| Schema valid extraction | 1 |
| Schema invalid extraction | 1 |
| 質問API attempt | 0 |
| 固定したscenario outcome | 20 |
| retry | 0 |

20問はすべて`BLOCKED_BY_EXTRACTION_ERROR`として保存した。回答精度の失敗として数えず、図表抽出の失敗として扱う。fail-fast後にtoken usageを復元できないため、実費を推測値で補完していない。

## 固定artifact

- prediction bundle: `eval/results/visual_holdout_predictions_v1/predictions.json`
- SHA-256: `4572a4475ab550fa272dc062ef6dcf927e28b339d9c01e99e85b98d30ff07e71`
- normalized extractionとraw extractionもbundleからSHA-256で参照する

候補を変更して同じholdoutを再実行すると未見評価ではなくなるため、再実行しない。gold開封後は、抽出goldと比較して`start`判定以外の差も分類する。
