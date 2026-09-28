# 専用Version Resolver評価

## 目的

5要因を一度に返す分類promptでは、`version_conflict`の規則追加が`requires_case_facts`へ影響し、対象5件の改善とcontrol 2件の退行が同時に起きた。版競合だけを別の構造化出力へ分離し、他の4要因を変更せず補正できるか確認する。

最初に候補を切り出して評価し、合格後にローカルのproduction query flow候補へ組み込んだ。公開環境にはまだdeployしていない。

## 固定条件

- model: `gemini-3.1-flash-lite`
- 対象: version誤検出7件
- true conflict control: `Q176`
- retrieval failure diagnostic: `Q291`
- 最大logical external call: 各round 9
- retry: 0
- 費用上限: 各round US$0.03
- sealed holdout access: false
- Generator、Embedding、Top-8、既存分類4要因: 保存済み結果を固定

専用出力は[`version-resolution-v1.schema.json`](../design/schemas/version-resolution-v1.schema.json)に従い、`version_conflict`、解決根拠種別、根拠element ID、confidenceだけを返す。既存分類器が`version_conflict=true`とした場合だけresolverを呼ぶ構成を想定する。

## Round 1

9件すべてのbooleanと合成ラベルは正しかった。推定費用はUS$0.00774725、API error 0件だった。

ただし`Q231`は、質問に関係する処理手順が一つだけであるにもかかわらず`resolution_basis=precedence_rule`を返した。引用根拠にも優先規則はなく、ラベル正解だけでは説明可能性のgateを満たさないと判断した。

## Round 2

`single_applicable_source`をSchemaとpromptへ追加し、同じ9件を再評価した。

| 対象 | 正解 | 結果 |
|---|---:|---|
| version誤検出 | 7/7 | すべて`version_conflict=false` |
| 真の版競合 | 1/1 | `Q176`を`unresolved`、判断要で維持 |
| 診断 | 1/1 | `Q291`のversionだけ解消、検索不足による文書不足は維持 |

- logical external call: 9
- retry: 0
- API error: 0
- input / output token: 21,602 / 1,770
- 推定費用: US$0.0080555
- confidence: 全件0.9以上

`Q231`は`single_applicable_source`となり、届出・手続きマニュアルの処理手順だけを引用した。日付境界の5件は`effective_period`、明示的な旧通知優先関係は`precedence_rule`、真の競合は`unresolved`となり、根拠種別と引用内容が一致した。

2 roundの実測費用合計はUS$0.01580275である。

## 17件比較へのfactor合成結果

条件付き構成では、既存分類器が`version_conflict=false`としたcaseにresolverを呼ばない。そのため、前回候補で退行した`Q206`と`Q211`を含む非version controlは既存結果を維持する。

- 対象7件: resolverで7/7へ改善
- true conflict control `Q176`: resolverで正解維持
- resolver非対象control 9件: 既存正解を維持
- 合成: **17/17**

これはversion factorとラベルだけを合成した結果であり、Generatorの`missing_conditions`を含む表示契約までは検証していなかった。

## ローカル統合と130問固定回帰

専用resolver候補は切り出し評価gateを通過したため、次を実装した。

1. 既存分類器が`version_conflict=true`の場合だけresolverを呼ぶ。
2. resolver成功時は`version_conflict`だけを置換し、他の4要因を保持する。
3. resolver失敗、低confidence、取得外根拠ID、または補正後の表示契約違反では既存分類結果を維持する。
4. provider、model、prompt、解決根拠、confidence、fallbackをログへ保存する。
5. 保存済み130問で分類失敗、重大ラベルの退行、条件付きcall数を比較する。

固定したGenerator、基準分類器、Resolverの保存済み出力へ、実装と同じconfidence・表示契約を適用した結果は次のとおりだった。

| 指標 | 基準 | Resolver候補 |
|---|---:|---:|
| 成功 | 106 | **112** |
| 分類失敗 | 15 | **9** |
| 回答生成失敗 | 6 | 6 |
| 検索失敗 | 3 | 3 |
| 分類正解 | 110 | **116** |
| 既存正解からの退行 | - | **0** |

- Resolver対象: 9/130件（6.9%）
- 適用: 8件。version factorの実変更は7件
- 表示契約fallback: 1件（`Q196`）
- 改善: `Q121`、`Q201`、`Q231`、`Q281`、`Q286`、`Q416`
- 真の版競合`Q176`: `判断要`を維持
- 検索失敗診断`Q291`: 版競合だけを解消したが、根拠不足による`文書不足`を維持
- 新規API call: 0。Resolver出力はRound 2の9件を再利用し、その実測費用はUS$0.0080555
- sealed holdout: 未使用

`Q196`は版を一意に決められても、Generatorが`住居届の提出状況`を未確認条件として返していた。ここで`根拠十分`へ変えると表示契約に違反するため、実装は基準の`判断要`へ戻した。したがって、factorだけの17/17と、実際の表示契約を含む改善6件は区別して説明する。

回帰gateは合格し、専用Resolverをローカル採用候補とした。結果は[`analysis.json`](results/version_resolver_regression_v1/analysis.json)に保存した。公開環境への反映と新規end-to-end API runは別gateとする。
