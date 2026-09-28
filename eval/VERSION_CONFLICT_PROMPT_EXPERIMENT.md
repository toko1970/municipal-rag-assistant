# Version conflict分類prompt比較

## 目的

Retrieved-evidence回帰で確認した`version_conflict`誤検出7件へ、分類promptだけの対策を適用する。Generator、Embedding、検索結果、最終決定規則は変更しない。

## 固定した比較条件

- 対象: 誤検出7件
- control: 真の版競合`Q176`、その他の正しい判断要7件、文書不足2件
- 合計: 17件
- 比較: 既存`answer-classification-v1`と候補`answer-classification-version-conflict-v1`
- model: `gemini-3.1-flash-lite`
- 最大logical external call: 34
- retry: 0
- 費用上限: US$0.10
- sealed holdout access: false

候補は`version_conflict`だけを変更する。複数版が取得された事実ではなく、質問の基準日、施行日、適用期間、優先規則を使っても適用版を一意に決められない場合だけ`true`とする。

ローカルpreflightでは、17件すべてで保存済みTop-8のelement IDと順序を再現した。Embedding APIとGenerator APIは呼び出していない。

## 2026-09-28の実行結果

`version_conflict_prompt_comparison_v1`を開始したが、最初のbaseline callがGemini Free Tierの日次500 request上限で`429 RESOURCE_EXHAUSTED`となった。runnerはfail-fastし、成功call 0件、token 0、推定費用US$0だった。

これはprompt品質を測った結果ではない。比較精度、改善件数、退行件数は未評価であり、候補を採用または不採用にしない。失敗runは削除せず、上限による中断の証拠として保存する。

## 再開条件

GeminiのFree Tier request上限が解除された後、新しい出力先`version_conflict_prompt_comparison_v2`で同じ34 callを1回実行する。既存v1 artifactは上書きしない。

```bash
.venv/bin/python -m eval.compare_version_conflict_prompt \
  --output-dir eval/results/version_conflict_prompt_comparison_v2 \
  --max-logical-external-calls 34 \
  --max-cost-usd 0.10
```

採用gateは、対象7件の改善が1件以上、controlの退行が0件、API errorが0件である。gate通過後だけ保存済み130問の分類器回帰へ進む。
