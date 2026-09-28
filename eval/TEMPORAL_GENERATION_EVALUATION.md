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
