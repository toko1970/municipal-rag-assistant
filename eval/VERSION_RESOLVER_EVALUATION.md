# 専用Version Resolver評価

## 目的

5要因を一度に返す分類promptでは、`version_conflict`の規則追加が`requires_case_facts`へ影響し、対象5件の改善とcontrol 2件の退行が同時に起きた。版競合だけを別の構造化出力へ分離し、他の4要因を変更せず補正できるか確認する。

この評価は候補の切り出し試験であり、production query flowにはまだ組み込んでいない。

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

## 17件比較への合成結果

条件付き構成では、既存分類器が`version_conflict=false`としたcaseにresolverを呼ばない。そのため、前回候補で退行した`Q206`と`Q211`を含む非version controlは既存結果を維持する。

- 対象7件: resolverで7/7へ改善
- true conflict control `Q176`: resolverで正解維持
- resolver非対象control 9件: 既存正解を維持
- 合成: **17/17**

これは保存済み結果を使った条件付き合成であり、production統合後のend-to-end実測ではない。

## 判断と次のgate

専用resolver候補は切り出し評価gateを通過した。次はproductionへ直接採用せず、次を実装して同じ130問で回帰する。

1. 既存分類器が`version_conflict=true`の場合だけresolverを呼ぶ。
2. resolver成功時は`version_conflict`だけを置換し、他の4要因を保持する。
3. resolver失敗または低confidence時は既存分類結果を維持する。
4. provider、model、prompt、解決根拠、confidence、fallbackをログへ保存する。
5. 保存済み130問で分類失敗、重大ラベルの退行、追加call数・費用を比較する。

130問で改善があり、`判断要`と`文書不足`の退行が0件の場合だけproduction採用候補とする。
