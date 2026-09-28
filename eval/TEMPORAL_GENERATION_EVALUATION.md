# 生成前版選択pilot

## 1. 背景

Query Decompositionで`Q291`の必要根拠を取得できたが、Generatorは2025年10月の質問に対して
旧FAQの「認定事由発生日の翌月から」を選んだ。既存Version ResolverはClassifierが
`version_conflict=true`とした場合だけ動くため、GeneratorとClassifierがともに旧情報を採用した
ケースを回復できなかった。

## 2. 候補

外部LLMを追加せず、次の情報を取得チャンクから決定的に作り、現行generation promptの前へ
追加した。

- 質問中の基準日
- 質問が対象とする制度
- 質問日時点で適用済みの改正後・経過措置element
- 同じ制度についてeffective dateが古い記載候補
- 改正前後比較では両方を保持する例外

制度scopeは質問中の`通勤手当`、`住居手当`、`扶養手当`と、業務イベント`出生 → 扶養手当`
から決める。取得結果だけから制度を集めると、Top 8内の無関係な改正チャンクを誤って対象に
含めたため、API実行前のdry runで質問scopeへ修正した。

検索結果自体は削除せず、旧記載が優先根拠と矛盾する場合だけ採用しないようGeneratorへ伝える。
届出期限のような別の補完根拠は維持する。既存Version Resolverも後段で維持した。

## 3. 評価条件

- target: `Q291`
- regression controls: `Q421`、`Q426`、`Q431`
- Q291検索: Query Decomposition Top 8
- controls検索: 現行Dense Top 8
- Generator / Classifier / Version Resolver: `gemini-3.1-flash-lite`
- 最大12 logical calls、retry 0、費用上限US$0.02
- 採用gate: 4件すべてで分類、内容キー、根拠支持が成功
- sealed holdout: 未使用
- production integration: 未実施

## 4. 結果

| ID | 役割 | 結果 | Version Resolver |
|---|---|---|---|
| Q291 | target | 認定月から支給、届出15日以内を正答 | 発火し、effective periodで解決 |
| Q421 | control | 2km以上から1.5km以上を正答 | 不要 |
| Q426 | control | 16,000円超から15,000円超を正答 | 不要 |
| Q431 | control | 翌月から認定月への変更を正答 | 不要 |

- composite success: 4/4
- logical external calls: 9
- API error: 0
- input tokens: 10,919
- output tokens: 1,524
- 推定費用: US$0.00501575
- gate: PASS

Q291はQuery Decomposition、生成前版注記、既存Version Resolverの組み合わせで成功した。
版注記によりGeneratorが正しいclaimを作り、その後Classifierが検出した版競合をResolverが
適用期間で解消した。controlでは「両方を保持」の注記により比較内容を維持し、Resolverを追加で
呼ばなかった。

## 5. 判断と限界

候補はpilotを通過したが、まだproductionへ統合しない。formal 100問へ同じ決定ロジックをdry
runした結果、適用対象は7問だった。今回の4問以外に`Q186`、`Q191`、`Q286`があるため、既存4件
を再利用し、残る3件だけを実行する影響範囲回帰を次のgateとする。

現時点のイベントaliasは`出生 → 扶養手当`だけである。未知の言い換えや新しい制度を自動的に
理解する汎用分類器ではない。実務では文書取込時に制度topic、valid from/to、supersedesを明示的な
メタデータとして管理し、この決定ロジックへ渡す設計が望ましい。

## 6. 影響範囲回帰

pilot 4件のdataset・cache・model・Top-k・内容基準のhashと条件を照合して再利用し、dry runで
判明した残り3件だけを新規実行した。

- 新規対象: `Q186`、`Q191`、`Q286`
- 最大9 logical calls、retry 0、費用上限US$0.015
- 実測8 logical calls、input 9,033、output 972 tokens
- 新規実測費用: US$0.00371625
- pilotの履歴費用との合計: US$0.008732
- sealed holdout: 未使用

| ID | 内容 | 分類・pipeline | 総合判定 |
|---|---|---|---|
| Q186 | 15,000円超を正答 | 根拠十分 | 成功 |
| Q191 | 15,000円ちょうどは対象外と正答 | Resolver失敗後に判断要へfallback | 失敗 |
| Q286 | 認定月から支給を正答 | Resolverがeffective periodで解決 | 成功 |

影響範囲全体は6/7成功で、7/7を要求する採用gateは不合格だった。`Q191`は検索・版選択・回答生成
には成功しており、残った失敗はClassifierが版競合を検出した後のVersion Resolverである。
評価時点の戻り値にはResolverの失敗理由が含まれず、APIエラーか構造化出力エラーかは確定できない。

実行時の評価器は、内部の`RESOLUTION_FAILED`をtop-level errorとして数えず、raw summaryの
`completed_count`を7としていた。生artifactは改変せず、[`run_audit.json`](results/temporal_generation_scope_v2/run_audit.json)
で有効完了を6件へ訂正した。以後はResolverの`error_summary`を戻り値へ残し、同statusをscenario
errorとして扱う。今回のretryは行っていない。

## 7. 現時点の判断

生成前版注記は、追加3件すべてで正しい内容を生成したため、版選択対策として有望である。
一方、公開flowへ統合するには採用gateを満たしていない。次の最小検証は、修正済み観測処理で
`Q191`だけを独立runし、Resolver失敗の理由と再現性を確認することである。成功した場合でも、
production統合前に対象7件の証拠と130問回帰の範囲を固定する。

## 8. Q191単一診断

修正済み観測処理でQ191だけを独立runした。条件は同じdataset・cache・検索・Generator・
Classifier・Version Resolverとし、最大3 logical calls、retry 0、費用上限US$0.005に固定した。

最初のGenerator呼び出しでGemini 3.1 Flash-Liteが`503 UNAVAILABLE`を返したため、fail-fastした。
成功call 0、token 0、推定費用US$0、sealed holdout未使用である。Resolverへは到達していない。

この結果はQ191の版判定ロジックの正否を追加評価するものではない。同じmodel endpointの一時的な
高負荷が実際に発生しているため、前回のResolver失敗もprovider障害だった可能性は高まったが、
前回の失敗詳細が保存されていない以上、同一原因とは断定しない。成功するまで再試行せず、
[`temporal_generation_q191_diagnostic_v1`](results/temporal_generation_q191_diagnostic_v1/)を
provider availability failureとして固定した。

次に再開する場合は、新しい出力先でQ191を1回だけ実行する。成功時は内容・分類・Resolver statusを
採点し、失敗時は今回追加した`error_summary`で生成・分類・Resolverのどこで失敗したかを区別する。

## 9. Q191再診断

ユーザーの指示により、新しい独立runとしてQ191をもう1回実行した。上限は同じく最大3 logical
calls、retry 0、US$0.005である。

今回はGeneratorがinput 2,245・output 321 tokensで完了した後、ClassifierがGemini 3.1
Flash-Liteの`503 UNAVAILABLE`となりfail-fastした。logical calls 2、推定費用
US$0.00104275で、Resolverへは到達していない。

2回の独立診断で503の発生箇所がGenerator、Classifierと移動した。この事実は、Q191固有の
版判定ロジックより、共有model endpointの一時的な可用性が現在の測定を妨げていることを示す。
ただし、最初の影響範囲回帰におけるResolver失敗の詳細は残っていないため、3件すべてが同じ原因
だったとは断定しない。

Classifier失敗時にも部分成功したGeneratorを監査できるよう、以後のrecordへgenerationのstatus、
構造化response、errorとclassificationのstatus、errorを保存するよう評価器を更新した。今回のv2
artifactは実行時点のraw結果として変更しない。次の外部runはendpointが安定してから行い、直後の
連続retryはしない。

## 10. Q191有効測定と統合判定

時間を置いた3回目の独立runは、Generator、Classifier、Version Resolverの3 logical callsを
すべて完了した。Q191は「15,000円を超えていないため支給対象外」と回答し、内容、根拠支持、
最終分類`根拠十分`がすべて成功した。

Classifierが検出した版競合に対し、Version Resolverは`effective_period`を根拠に
`version_conflict=false`、confidence 1.0を返した。fallbackは使用していない。

- input 4,652・output 545 tokens
- 推定費用US$0.0019805
- retry 0、API error 0
- sealed holdout未使用

既存6件とdataset、query/subquery/document cache、Generator、Classifier、Top-k、候補promptが
一致することをhashとmanifestで確認した。有効に完了した同一条件のrecordを統合すると、影響範囲
7件は7/7 composite successとなり、内容品質の採用gateを通過した。統合artifactは
[`temporal_generation_scope_consolidated_v3`](results/temporal_generation_scope_consolidated_v3/)
に保存した。

失敗した3試行は削除していない。Resolver失敗1件、Generator 503、Classifier 503を運用上の証拠
として残し、内容品質の分母からだけ除外した。選択した品質recordの推定費用はUS$0.00966975、
失敗試行を含む実験全体は23 logical calls、推定US$0.01175525である。

したがって「providerが正常応答した場合の版選択品質」はgate通過、「外部providerの可用性」は
別の運用リスクという結論にする。次は候補をローカルquery flowへ統合し、同じ130問で総合回答
成功と退行を評価する。公開deployはその結果を確認した後に判断する。
