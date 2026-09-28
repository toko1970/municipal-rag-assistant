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

## Gold開封後の採点

事前登録されたgold SHA-256との一致を確認してから採点した。

| 指標 | 結果 |
|---|---:|
| sealed document | 6 |
| extraction attempt | 2 |
| Schema valid / invalid | 1 / 1 |
| unattempted document | 4 |
| extraction gate pass | 0 / 1 |
| completed answer | 0 / 20 |
| extraction errorでblocked | 20 / 20 |
| classification evaluated | 0 |
| end-to-end success | 0 / 20 |

分類器を実行していないため、分類精度は未算出である。20件を分類誤りとして数えず、上流の抽出失敗でblockedになった件数として記録した。

Schema-validだった`vh_doc_a7`も、gold 9要素中5要素一致、element recall 0.556、mean bbox IoU 0.806、重要値完全一致なしでgate不合格だった。主な差は句読点を含む文言の完全一致であり、現行の完全一致指標が表記差にも敏感なことが分かった。

`vh_doc_m2`では、goldの先頭ノードは`start`、末端ノードは`end`である。一方、候補は先頭と末端を`process`とした。内容文字列と接続関係を抽出できても、graph上の役割分類がSchema契約を満たさないことが主要因である。

次のdevelopment改善候補は、incoming edgeがない唯一のnodeを`start`、outgoing edgeがないnodeを`end`として検査・正規化するgraph topology処理である。句読点差については、金額・日付・条件を維持した正規化比較と厳密比較を分ける。このholdoutには再適用せず、新しいdevelopment fixtureと将来の別holdoutで検証する。

採点artifactは`eval/results/visual_holdout_predictions_v1/score.json`に保存した。SHA-256は`61322650d94df8748c43a334e87aef84f4b49b23dddde230b2dba07ed083de2e`である。
