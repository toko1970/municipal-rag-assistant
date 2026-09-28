# Query Decomposition・生成前版注記の統合評価

## 1. 目的

局所実験で有望だったQuery Decompositionと生成前版注記を、公開環境と同じローカルquery flowへ
接続し、gold v1.2の130問に対する総合回答成功への効果を確認する。

総合成功は、検索、回答内容、根拠支持、最終分類がすべて成功した場合だけとする。外部providerの
API errorは内容品質へ混ぜず、別の運用上の失敗として保存する。

## 2. production候補への接続

- `DecomposedVectorIndex`をQdrant adapterの前に置く。
- 単一intentでは、既存のquery vectorと1回の検索をそのまま使う。
- 対応する複合質問だけsubqueryを追加Embeddingし、Top 8の候補枠をintent間で配分する。
- 検索後、質問日・制度domain・改正通知のeffective dateから版注記を決定的に作る。
- 通常質問では既存generation promptを変更しない。
- 既存Classifierと条件付きVersion Resolverは維持する。

## 3. 影響範囲回帰

130問すべてを再生成すると、変更が発火しない質問にもLLMの揺らぎが入り、費用も増える。そのため、
最終コードでQuery Decompositionまたは版注記が発火する10問だけを新規または保存済み同一条件の
候補recordで評価し、残る120問はgold v1.2のbaselineを再利用した。

manifestでdataset、query/subquery/document cache、model、Top-k、候補コードのhashを固定した。
sealed holdoutは使用していない。

## 4. 適用規則の縮小

初期候補には5種類のQuery Decomposition規則があった。影響評価の結果、総合成功へつながった
次の2系統だけを残した。

- 出生＋支給開始＋届出期限: `Q291`を改善
- 転居＋通勤実態消失: `Q436`を改善、`Q156`は未改善

次の3規則はproduction候補から外した。

- 通勤経路変更: `Q131`の検索は成功したが「実際に通勤」の回答facetを落とし、生成失敗を改善しない
- 過払給与＋口座変更: `Q441`はbaselineから成功しており、追加検索の便益がない
- 住宅の要件・書類・期限: `Q446`を`判断要`へ退行させた

`Q446`はDense検索へ戻し、質問中の`家賃`と`入居／住宅／賃貸`から住居手当domainを決める版注記
だけを適用した結果、内容・根拠支持・分類がすべて成功した。

## 5. 結果

| 指標 | gold v1.2 baseline | 最終候補 | 差 |
|---|---:|---:|---:|
| 総合成功 | 117/130 (90.0%) | 120/130 (92.3%) | +3 |
| 回答生成失敗 | 6 | 6 | 0 |
| 回答分類失敗 | 4 | 3 | -1 |
| 検索失敗 | 3 | 1 | -2 |

改善は`Q286`、`Q291`、`Q436`の3件で、退行は0件だった。`Q156`は住所変更届の正解節が候補へ
入らず、検索失敗として残った。

- 影響範囲gate: PASS
- 採用判定に使用したcandidate recordの推定費用: US$0.012088
- 統合段階の失敗試行を含む費用: US$0.01114625、17 logical calls
- temporal pilotからの全試行: US$0.0229015、40 logical calls
- retry: 各run 0
- sealed holdout: 未使用
- production deploy: 未実施

途中のResolver失敗、Generator 503、Classifier 503は削除せず、品質評価から分けてartifactへ残した。

## 6. 判断

最終候補は、適用条件を実測効果のある質問構造へ狭めた状態で、総合回答成功を3件改善し、退行0件
だったためローカル採用gateを通過した。改善率だけでなく、効かなかったQ131、未改善のQ156、
一度退行したQ446を残している。

次はbranch全体のreviewと実PostgreSQL・Qdrant integration testを行う。公開Cloud Runへのdeployは
別の承認境界であり、review結果とローカルsmokeを確認してから実施する。

実装後の検証は、非integration 289件、実PostgreSQL・Qdrant integration 3件、Ruff、diff検査が
すべて成功した。branch差分の自己reviewでは、通常質問の検索経路維持、追加Embeddingの発火条件、
版注記の非対象prompt維持を対象testで確認した。

機械可読な統合結果は
[`integrated_query_candidate_consolidated_v5`](results/integrated_query_candidate_consolidated_v5/)
を参照する。
