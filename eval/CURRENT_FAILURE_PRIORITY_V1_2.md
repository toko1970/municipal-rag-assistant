# 評価セットv1.2の残存失敗と次の優先順位

## 1. 現在値

保存済みの同一130問へ、評価gold v1.2とVersion Resolver適用済み出力を使った現在値である。
新しいAPI呼び出しや再生成は行っていない。

| 主原因 | 件数 |
|---|---:|
| 成功 | 117 |
| 回答生成 | **6** |
| 回答分類 | 4 |
| 検索 | 3 |

総合回答成功率は117/130、90.0%である。分類モデル比較の結果、現行Geminiを維持するため、
次の一手はモデルの一括置換ではなく、最大の残存原因へ限定した変更にする。

回答生成6件は、残存失敗13件の46.2%、全130件の4.6%である。回答分類4件との差は2件なので、
圧倒的な最大原因ではない。また「生成modelがAPI errorになった」という意味でもない。検索済み
根拠から、質問に必要な項目を漏れなく、質問外の断定を加えず、根拠間の不一致を保持して回答へ
変換する工程を最初に失敗原因として割り当てた件数である。

## 2. 分類4件を先に一括修正しない理由

| ID | 保存出力 | 論点 | 分類器だけで直せるか |
|---|---|---|---|
| `Q126` | `requires_case_facts=true` | 質問に日付、距離、通勤手段が揃う | 高い |
| `Q176` | `version_conflict=true` | 「必ず支給できるか」は追加要件の存在から否定できるが、Generatorも版確認を不足条件にした | 低い |
| `Q196` | `version_conflict=true` | Resolverは版競合を解消できたが、Generatorの無関係な`住居届の提出状況`により表示契約fallback | 低い |
| `VD024` | `文書不足` | 出生の記入例を転居へ適用できない境界を、個別確認として答える必要がある | 低い |

4件は同じfactorの同じ誤りではない。Q176とQ196はGeneratorの`missing_conditions`、VD024は
Visualの類似事例適用境界を含む。専用resolverを一つ追加しても最大4件を安全に直せる状態では
ない。Q126だけのために追加LLM resolverを常時呼ぶと、費用・遅延・複雑性に対する改善幅が
小さい。

今回の36件benchmarkの再実行ではQ126は正解した一方、別の5件を誤った。温度0でも外部model
の出力は完全に固定されないため、保存済み1ケースだけへ規則を合わせない。

## 3. 回答生成6件の内訳

| ID | 観測した問題 | 対策候補 |
|---|---|---|
| `Q066` | 「翌月以降の場合がある」は答えたが、反映月の個別確認を不足条件にしない | 未確定部分を`missing_conditions`へ残す |
| `Q131` | 距離と期限は回答したが、実通勤と届出が必要という要求facetを落とす | 質問が求めるfacetを列挙して全件確認する |
| `Q386` | 期限後の影響は答えたが、個別確認を落とし、「書類不備なら受付不可」を余分に追加 | facet外のclaimを追加しない |
| `Q391` | 相反する「受付不可」と「不足書類提出後に認定」を並べたまま一方を結論化 | 根拠間の不一致を`missing_conditions`へ残す |
| `VD004` | 読みにくさが「不備」に当たる根拠がないのに、差戻し対象と断定 | 図の分岐条件と質問事実の対応がなければ断定しない |
| `VD019` | 判断要ラベルは正しいが、条件付き金額を示さず無関係な申請フローを追加 | 必須facetを答え、無関係なclaimを除く |

単純な欠落だけではないが、6件とも「質問が求める命題を先に固定せず、取得根拠から書ける
内容を広げた」ことが共通している。

## 4. 既存Visual prompt実験との重複回避

`VD004`には既に`answer-claims-v2`とv3を試している。VD004単体は改善したが、通常の誤字を
含むcontrol `VD003`を「不備」と対応付けられなくなり、表示契約errorでfail-fastしたため
不採用だった。詳細は[`VISUAL_ANSWER_BASELINE.md`](VISUAL_ANSWER_BASELINE.md)に残している。

したがって、今回のprompt pilotへVD004・VD019を混ぜない。Visual 2件は、同じ自然言語規則を
再試行せず、node・edge・cell locator付きSchemaまたは表示契約の構造変更として別に扱う。

## 5. 次の一手

テキスト失敗4件（Q066、Q131、Q386、Q391）に限定し、Generatorへ`required facets`確認を
追加する小比較を行う。出力Schemaは変えず、promptだけに次の順序を追加する。

1. 質問が明示的に求める命題・項目を内部で列挙する。
2. 各facetについて取得根拠から支持できるclaimを作る。
3. 支持できないfacet、個別確認、根拠間の不一致は`missing_conditions`へ残す。
4. 質問のfacetに不要なclaimを追加しない。

これは自由文を長くする変更ではない。既存の構造化`claims`と`missing_conditions`へ、質問範囲
を漏れなく写すための生成順序である。

### 公開研究との対応

- NAACL 2025のSub-question Coverageは、複合質問をcore・background・follow-upへ分け、
  sub-questionを検索と生成へ利用した方式がbaselineに対して74%の比較勝率を得たと報告する。
  本pilotでは質問が明示的に求めるcore facetだけを対象にし、回答の長文化を避ける。
  [Do RAG Systems Cover What Matters?](https://aclanthology.org/2025.naacl-long.301/)
- Google Cloudのgrounding checkは回答をclaimへ分解し、claim全体が根拠で支持されるかを個別に
  判定する。一部だけ正しい複合claimを支持済みと扱わない考え方は、Q386とVD004の余分な断定
  を検出する基準に合う。
  [Check grounding](https://cloud.google.com/generative-ai-app-builder/docs/check-grounding)
- Google Researchの2025年研究は、RAGの根拠衝突を一種類として扱わず、衝突類型を明示して
  LLMへ与えると回答の適切さが改善すると報告する。Q391では、どちらかを多数決で採用せず、
  「同時適用できない規定」として`missing_conditions`へ残す。
  [(D)RAGged Into a Conflict](https://research.google/pubs/dragged-into-a-conflict-detecting-and-addressing-conflicting-sources-in-retrieval-augmented-llms/)
- RAGCheckerはRetrieverとGeneratorをclaim単位の複数指標へ分けて診断する。本pilotでも総合成功
  だけでなく、facet coverage、根拠外claim、質問外claimを別々に数える。
  [RAGChecker](https://arxiv.org/abs/2408.08067)

生成後の全回答を別LLMで再検証・再生成する方式もあるが、常時の外部call、遅延、検証modelの
誤りが増える。現在は13件中6件だけが生成主原因なので、まず1回の生成内でfacet確認を行う。
小pilotで改善しなければ、次段階として次の構造変更を比較する。

1. Schemaへ`required_facets`と各facetの`answered`・`needs_confirmation`・`conflict`を追加する。
2. 各claimをfacet IDとevidence IDへ対応付ける。
3. codeで未対応facet、根拠IDのないclaim、質問外claimを拒否または`判断要`へ縮退させる。
4. 高リスクまたは矛盾検出時だけ生成後verifierを呼び、全質問の二重LLM化はしない。

## 6. 有限pilot

- 対象: テキスト失敗4件と、既に正しいテキストcontrol 6件。
- baseline: 保存済み出力を使い、再課金しない。
- candidate: 保存済みretrievalを固定し、Generatorと現行Classifierだけを呼ぶ。
- sealed holdout: 使用しない。
- retry: 0。
- pilot通過前に130問を実行しない。

採用gateは次のとおりである。

- 失敗4件の総合成功を2件以上改善する。
- controlの総合成功を1件も退行させない。
- 根拠にない断定を増やさない。
- 質問が求める必須facet coverageを改善する。
- 質問外claimを増やさない。
- API errorと表示契約errorを分類誤りに混ぜない。

pilotを通過した場合だけ、同じ保存済み130問へ候補を適用する。通過しない場合は本番promptを
維持し、次に検索3件の再順位付けまたはQuery Decompositionを検討する。

## 7. pilot結果

`answer-claims-required-facets-v1`を上記10件で実行した。20 logical calls、retry 0、実測
US$0.01053975で完了し、sealed holdoutは使用していない。厳密gateでの改善は0件、control退行は
4件だった。Q391は意味上改善したが、これを人手成功として数えても1件で採用条件へ届かない。

候補promptは不採用とし、本番promptとSchemaは変更しない。回答生成6件は最大の件数ではあるが、
一つの介入で直せる同質な集合ではないことが実測できた。詳細は
[`GENERATION_FACETS_PROMPT_EXPERIMENT.md`](GENERATION_FACETS_PROMPT_EXPERIMENT.md)を参照する。

次は、同じ複数文書検索の不足としてまとまっている検索失敗3件へ、追加LLM callを必要としない
Hybrid Searchまたはrerankingの小比較を優先する。回答生成へ戻る場合は、facet付きSchema、
衝突時だけの専用処理、質問外claim validatorを個別experimentとして扱う。

## 8. BM25 Hybrid Searchの結果

現行gold v1.2のformal 100問を使い、contextual dense baselineと、Sudachi SplitMode Cによる
BM25 sparseをRRFで統合した候補を比較した。Embedding cacheは再利用し、外部API callと費用は0、
sealed holdoutは未使用である。

対象のQ156・Q291・Q436は1件も改善しなかった。全根拠見出しHit@5は80/90から73/90へ低下し、
既存成功8件が退行したため不採用とした。詳細は
[`BM25_HYBRID_EVALUATION.md`](BM25_HYBRID_EVALUATION.md)を参照する。

Q156の住所変更根拠はdense Top-30外、Q436の住所変更期限は27位だった。rerankerは候補集合外の
根拠を回復できず、Q291だけを直しても検索失敗3件中2件が残る。そのため次の一手はrerankerの
導入ではなく、複数事項を個別検索へ分けるQuery Decompositionの有限比較とする。

## 9. Query Decompositionの結果

質問本文だけを使う決定的なQuery Decompositionにより、Evidence Hit@5は80/90から82/90へ
改善し、Q291とQ436を回復した。Hit@5の退行はなかった。一方、回答回帰ではQ291が旧ルールを
選択し、検索改善だけでは総合回答成功にならなかった。Q436のbaselineはGemini 503でpaired比較
が成立していないため、candidateはまだ本番へ反映しない。

次の優先事項は、日付付き質問でGeneratorへ渡す前に新旧根拠と適用時期を整理する最小実験で
ある。後段のVersion ResolverはClassifierがversion conflictを検出した場合だけ動くため、今回の
Q291のようにGeneratorとClassifierが旧情報を採用したケースを回復できなかった。

生成前版注記のpilotでは、Q291と改正前後比較control 3件がすべて分類・内容・根拠支持に成功した。
Q291はQuery Decompositionで根拠を揃え、版注記でGeneratorの旧記載採用を防ぎ、既存Version
Resolverが適用期間から最終分類を解決した。9 logical calls、retry 0、推定US$0.00501575、API
error 0、sealed holdout未使用である。

同じ決定ロジックの適用範囲はformal 100問中7問で、未評価はQ186、Q191、Q286の3件である。
追加評価ではQ186とQ286が総合成功し、Q191も「15,000円ちょうどは対象外」という回答内容は
正しかったが、Version Resolverが`RESOLUTION_FAILED`となり`判断要`へfallbackした。pilot
再利用分を含む影響範囲は6/7で、採用gateは不合格である。

これは版選択・生成の失敗ではなく、条件付きResolverの実行失敗である。失敗理由を保存して
いなかった観測欠陥を修正し、追加retryなしで結果を固定した。次はQ191だけを修正済み観測処理で
独立検証し、API障害と構造化出力違反を区別する。

修正済み観測処理によるQ191単一診断は、最初のGenerator呼び出しでGemini 3.1 Flash-Liteの
`503 UNAVAILABLE`となりfail-fastした。Resolverへ到達せず、token 0、推定費用US$0、retry 0
だったため、Q191の版判定品質について新しい結論は出していない。同じendpointの高負荷が確認
されたことは前回Resolver失敗のprovider起因仮説と整合するが、前回の詳細がないため確定しない。

## 10. 学習上の要点

- 最大件数だけでなく、同じ一手で直せる同質性を確認して優先順位を決める。
- 分類ラベルが誤っていても、原因がGeneratorの不足条件なら分類器だけを変えない。
- 評価goldの訂正によって失敗分布が変わったら、古い改善計画をそのまま使わない。
- 小pilot、control、採用gateを固定してからAPIを呼び、効かなければ130問評価の費用を使わない。
- 過去に退行したpromptと同じ介入は、対象を変えただけで再実行しない。
