# Answerability alignment prompt experiment

## 目的

Query Decomposition候補では検索に成功しても、生成器が質問外の不足条件を追加し、分類器が
`文書不足`または`判断要`へ落とすケースが残った。生成と分類のanswerability基準を揃える
限定的なprompt変更が、総合回答成功へつながるか確認した。

## 候補

本番promptは変更せず、候補promptに次の規則だけを追加した。

- 根拠が出来事条件を示す場合、質問の「いつ」「時期」はその条件で回答できる。
- 質問が日付、月、何日以内という粒度を明示した場合だけ、粗い条件を不足と扱う。
- 複数文書の根拠付きclaimが各項目を満たせば、文書間を結ぶ記載がないこと自体を不足としない。
- claimで回答した項目を`missing_conditions`へ重複させない。

対象は現行候補の失敗6件と成功control 3件とし、検索結果、モデル、Top 8、採点条件を固定した。
採用gateは失敗2件以上の改善、control退行0件とした。

## 実行条件

- Generator / Classifier: `gemini-3.1-flash-lite`
- 対象: `G02`, `G03`, `G05`, `G06`, `G07`, `G08`
- control: `G01`, `G04`, `G09`
- 最大logical external calls: 27
- 実使用: 18
- retry: 0
- 費用上限: US$0.05
- 推定費用: US$0.0091185
- sealed holdout: 未使用

## 結果

| 指標 | 現行候補 | prompt候補 |
|---|---:|---:|
| 総合成功 | 3/9 | 2/9 |
| 失敗からの改善 | - | 0件 |
| control退行 | - | 1件 (`G01`) |
| 採用gate | - | **FAIL** |

`G02`と`G05`は根拠十分になったが、住所変更届を回答へ含めず内容条件を満たさなかった。
`G03`と`G06`は質問が求めていない通勤経路変更届の具体的期限を不足扱いした。`G07`も
通勤手当停止のための具体的な届出期限を新たに要求し、文書不足のままだった。

controlの`G01`では、質問が求めていない住所変更届の提出先・具体的手続き方法を不足条件へ追加した。
分類factorは根拠十分だったが、claimsとmissing conditionsを同時に持つため表示契約errorとなった。

## 判断

候補promptは採用しない。一般規則として不足条件を説明しても、LLMが「手続き」「時期」の範囲を
質問より広く解釈する傾向を止められず、過去のrequired facets promptと同じ種類の退行を再現した。

同種の自然言語prompt調整はここで打ち切る。次に改善するなら、質問facetを構造化し、各claimと
missing conditionがどのfacetへ対応するかをschemaとcodeで検証する必要がある。この変更は追加の
設計・実装コストが大きいため、現在の短期ポートフォリオ範囲では優先しない。

検索改善候補も総合回答gateを通過していないため、本番へ反映しない。検索改善、回答生成、分類の
各層を分けて測定し、平均値が改善しても退行gateで棄却した結果をポートフォリオ上の成果とする。

## 再現コマンド

```bash
.venv/bin/python -m eval.compare_query_answerability_prompt \
  --output-dir eval/results/query_answerability_prompt_comparison_v1 \
  --max-logical-external-calls 27 \
  --max-cost-usd 0.05 \
  --min-scenario-interval-seconds 15
```
