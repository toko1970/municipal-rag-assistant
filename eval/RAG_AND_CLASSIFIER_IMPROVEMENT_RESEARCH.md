# RAG・回答分類器の精度改善調査

## 1. 目的

本調査は、総合回答成功率を高めるために、一般的なRAG改善と、このアプリ固有の回答分類器改善を一つの計画へ統合する。2026年9月28日時点の公式資料、モデルカード、原著論文を参照し、観測済みの失敗へ対応しない技術は実装候補から外す。

本RAGの主要指標は、期待ラベル、回答内容、根拠整合性、表示契約をすべて満たした質問の割合である。検索・生成・分類の指標は原因診断に使い、どれか一つだけの改善を総合精度とは呼ばない。

現在のdevelopment固定出力回帰は、質問範囲規約によるgold訂正後、次の状態である。

| 主原因 | 件数 |
|---|---:|
| 総合成功 | 117 / 130 |
| 検索 | 3 |
| 回答生成 | 6 |
| 回答分類 | 4 |

Version Resolver統合後の保存済み出力へ訂正後goldを適用した分類ラベル正解は121/130である。この数値は新規end-to-end runや未使用holdoutの結果ではない。Q006、Q046、Q076、Q086、Q176、Q301、Q316のgold訂正7件はモデル改善として数えない。

## 2. 改善対象を二系統に分ける

```text
RAG側
  文書取込 -> 検索 -> 回答生成

分類器側
  生成済みclaims + 取得根拠 -> 5要因判定 -> コードでラベル・表示

総合成功
  RAG側と分類器側の両方が合格した場合だけ成功
```

一般的なRAGは取得と生成を主対象にする。本アプリは、人事・給与制度を根拠なしに断定しないため、`根拠十分`、`判断要`、`文書不足`を決める分類・表示工程を追加している。この工程の改善には、検索手法だけでなく、テキスト分類、自然言語推論、確率校正、selective classificationの知見を使う。

## 3. RAG側の一般的手法と適用判断

### 3.1 Hybrid Search

dense検索とBM25等のsparse検索を統合する。Qdrantはnamed vector、sparse vector、RRF/DBSF、multi-stage queryを提供する。[Qdrant Hybrid Search](https://qdrant.tech/documentation/search/text-search/hybrid-search/)、[Hybrid Queries](https://qdrant.tech/documentation/search/hybrid-queries/)

本RAGでは届出名、日数、施行日などの完全一致語が重要であり、`Q291`、`Q436`への適合度が高い。現在のQdrant構成を活用でき、追加LLM callなしで比較できるため、検索候補の第一優先とする。

### 3.2 Query Decomposition

複数事項の質問を副質問へ分け、副質問ごとに検索して候補を統合する。2025年の研究では、質問分解とrerankerを組み合わせてmulti-hop質問の根拠coverageを改善している。[Question Decomposition for Retrieval-Augmented Generation](https://arxiv.org/abs/2507.00355)

検索失敗3件はいずれも複数文書質問であるため適合度が高い。ただし、分解用LLMの費用、遅延、分解誤りが増える。Hybrid Searchで残った複数文書失敗だけに適用する条件付き候補とする。

### 3.3 Reranking

最初に候補を広く取得し、queryへ答える度合いで並べ替える。Qdrantはdense・sparse候補をColBERT等のlate interactionでrerankできる。[Qdrant Hybrid Search with Reranking](https://qdrant.tech/documentation/tutorials-basics/reranking-hybrid-search/)

Google CloudのRanking APIも、Embedding検索後のchunkを質問への関連度でrerankする用途を示している。[Vertex AI Ranking API](https://cloud.google.com/generative-ai-app-builder/docs/ranking)

`Q291`の正解chunkは9位なので効果が期待できる。一方、候補集合にない根拠はrerankerで回復できない。Hybrid Searchでcandidate recallを確認した後に比較する。

### 3.4 質問要求事項の構造化

回答前に`required_facets`を作り、各要求へclaimまたは不足条件を対応させる。`Q066`、`Q131`、`VD019`の回答項目欠落へ直接対応する。

これは検索結果を変えず、Generatorの網羅性を改善する候補である。質問分解を検索と生成へ同時導入すると原因を分離できないため、検索用分解と生成用facetは別experimentとする。

### 3.5 矛盾検出と回答検証

`Q391`のように複数根拠の可否が食い違う場合、断定せず確認事項へ変換する。包括的なSelf-RAGやCRAGは、自己評価や検索修正を行う一般手法である。[Self-RAG](https://arxiv.org/abs/2310.11511)、[Corrective RAG](https://arxiv.org/abs/2401.15884)

本RAGにはclaim検証、分類、Version Resolver、表示契約が既にある。全面的なagentic loopは責務と費用を増やすため、観測済みの矛盾型だけを扱う小さなvalidatorまたは専用判定を優先する。

### 3.6 優先度を下げる手法

- Embedding交換: Gemini Embedding 2とRuriを比較済みで正味改善がなかった。
- GraphRAG: corpus規模が小さく、現在の失敗はgraph traversal不足ではない。
- Fine-tuning Generator: 根拠付き回答の学習dataが少なく、先にprompt・Schema・検索を検証できる。
- 全質問へのSelf-RAG/CRAG: 追加call、遅延、原因追跡の負担が大きい。

## 4. 回答分類失敗4件の再整理

主原因が回答分類である4件を、同じ対策で扱えるとは限らない。

| 類型 | 件数 | ID | 主な対策層 |
|---|---:|---|---|
| 個別事情の誤検出 | 1 | Q126 | 分類器 |
| 版競合の誤検出 | 1 | Q176 | 分類器 |
| 未確認条件が残る表示境界 | 1 | Q196 | 生成契約＋表示契約 |
| 図表の類似事例を別事由へ適用する境界 | 1 | VD024 | 分類器＋評価例 |

Q126、Q176は質問が直接求める命題を満たす根拠と回答claimがあり、分類器だけで改善できる可能性が高い。Q196はgeneratorが質問外の届出状況を`missing_conditions`へ残しており、分類だけの変更では表示契約と衝突する。VD024は安全な棄却はできているものの、`判断要`と`文書不足`の意味境界にgold disagreementの余地がある。7件のgold訂正は、質問範囲規約の統一による評価整備として失敗集合から除外した。

## 5. 分類器側の一般的手法

### 5.1 構造化出力LLM

現在のGemini方式である。質問、取得根拠、生成claimsを読み、5つのboolean factorとconfidenceをJSON Schemaで返す。

利点:

- 長い日本語の根拠と複数文書の関係を扱える。
- zero-shotで要因定義を変更できる。
- 現行Schema、ログ、fallbackを再利用できる。

課題:

- factorを同時に変更すると相互干渉する。
- 自己申告confidenceをそのまま確率と解釈できない。
- prompt変更で既存正解が退行する。

改善候補は、few-shot例を無制限に追加することではなく、factorごとの責務分離、hard positive/negative control、同一入力での再現性確認である。Version Resolverはこの方針で成功した例である。

### 5.2 Jev型のtyped decision model

Jevは自由文を生成せず、事前に宣言したChoice、Score、Noulへ確率付きで答えるdecision modelとして2026年9月に公開された。[JevLM](https://jevlm.ai/)

現行5 factorは排他的な3クラスではなく、同時に複数がtrueになり得る。したがって、Jevを比較する場合は3ラベルの`Choice`ではなく、5つの独立したyes/no判断として扱う。

```text
retrieval_sufficient        -> Noul
answer_fully_supported      -> Noul
requires_case_facts         -> Noul
requires_policy_judgment    -> Noul
version_conflict            -> Noul
```

利点:

- 出力型が固定され、JSON parse・Schema失敗を減らせる。
- 各factorの確率をコード側の閾値とfallbackに使える。
- 生成LLMより低費用・低遅延となる可能性がある。
- factorを一つずつ観察しやすい。

未確認事項とリスク:

- 公開直後で、日本語の制度文書、複数根拠、図表説明に対する独立評価が不足している。
- providerのconfidenceを本データで校正せず閾値に使えない。
- 型が正しいことは意味が正しいことを保証しない。
- 長いstateで重要箇所を正しく比較できるか未測定である。
- 外部API、データ取扱条件、可用性、利用地域を確認する必要がある。

2026年9月の独立preprintは、typed decision headがoption名やrubricの割当てに敏感で、型安全でも意味上の正解は保証されないと報告している。[Type-Safe Is Not Error-Free](https://arxiv.org/abs/2609.26758)

Jevは有力な比較候補だが、現時点でGeminiからの置換を前提にしない。同じ保存済み入力と人手goldで、factor精度、重大退行、確率校正、日本語安定性、費用、遅延を測る。

### 5.3 Zero-shot NLI

各factorを仮説へ変換し、取得根拠と生成回答が仮説をentail、contradict、neutralのどれとして支持するかを判定する。

例:

```text
premise: 質問、取得根拠、生成claims
hypothesis: この回答には、利用者の個別事情を確認しなければ確定できない条件が残っている。
```

`mDeBERTa-v3-base-xnli-multilingual-nli-2mil7`は多言語NLIとzero-shot classification向けの公開モデルで、local実行できる。[モデルカード](https://huggingface.co/MoritzLaurer/mDeBERTa-v3-base-xnli-multilingual-nli-2mil7)

利点:

- API費用と外部送信がない。
- 各factorを独立に評価できる。
- entailment・contradiction・neutralを使い、単純なtrue/falseより保留を表現しやすい。

課題:

- 長いTop-8根拠は入力上限へ収まらず、要約・claim単位判定が必要になる可能性がある。
- 日本語の自治体制度文書に特化していない。
- 複数文書の施行日や優先関係など、複雑な推論は弱い可能性がある。

小規模local pilotには適するが、production候補にするには130問全体とclass別評価が必要である。

### 5.4 Fine-tuned encoder classifier

日本語BERT等へ分類headを追加し、5 factorをmulti-label学習する。東北大学の日本語BERTは公開され、Transformersで利用できる。[BERT Japanese](https://huggingface.co/docs/transformers/main/en/model_doc/bert-japanese)

利点:

- localで高速・低費用に実行できる。
- 固定taxonomyで安定した出力を得やすい。
- probability calibrationを別途適用できる。

課題:

- 現在の130件だけでは、5 factor、3ラベル、図表、難易度を分離した学習dataとして少ない。
- 同じ質問scenarioの言い換えをtrain/testへ分けるとdata leakageになる。
- evidenceとanswerを含む長い入力への設計が必要である。
- label定義を変えるたびに再学習が必要になる。

500質問候補のラベルだけでは足りない。実際のretrieved evidence、generated claims、factor goldをscenario単位で付けた後の中期候補とする。

### 5.5 Rule＋model cascade

決定可能な条件をコードで処理し、意味判断だけをmodelへ渡す。

例:

- 引用IDが取得外: コードで失敗
- `missing_conditions`が非空: `根拠十分`を禁止
- active版metadataで適用版が一意: version候補をコードで確認
- 意味上の個別事情・所管判断: modelで判定

利点は説明可能性と安定性である。欠点は、規則を観測例へ合わせすぎると過適合することにある。規則は文言パターンではなく、Schema・metadata・状態など決定的な事実に限定する。

### 5.6 階層・段階分類

5 factorを一度に判定せず、次の順に分ける。

1. claimsが取得根拠に支持されるか。
2. 質問へ答えるための情報が揃うか。
3. 個別事情・所管判断・版競合が残るか。
4. コードで最終ラベルを導出する。

各段階の入力を狭くできる一方、call数と遅延が増える。すべてを分離せず、失敗が集中するfactorだけ専用resolverにする現行方針が費用との均衡を取りやすい。

### 5.7 Ensembleとdisagreement routing

GeminiとJev/NLIが一致した場合だけ自動採用し、不一致または低confidenceを既存Gemini、別model、人手確認へ回す。

全質問を二重実行すると費用が増えるため、次に限定する。

- 基準分類器が`判断要`要因を検出した場合
- confidenceが閾値付近の場合
- `missing_conditions`とfactorが矛盾する場合
- factor間に不整合がある場合

accuracyだけでなく、coverage対errorの関係を測るselective classificationとして評価する。

### 5.8 Confidence calibrationとabstention

modelのconfidenceは、そのまま正解確率ではない。2026年のACL研究でも、Transformer分類器は高いaccuracyでも過信し得ると報告されている。[When High Accuracy Hides Poor Calibration](https://aclanthology.org/2026.acl-long.2128/)

候補modelのconfidenceを使う場合は、development calibration splitで閾値を固定し、次を記録する。

- Brier scoreまたはclass-balanced calibration指標
- confidence bin別accuracy
- 自動回答coverage
- coverageごとの重大誤回答率
- 閾値未満のfallback・保留率

holdoutを見て閾値を調整しない。dataが少ない段階では、複雑なconformal手法より、閾値別のcoverage-risk表を先に作る。

## 6. 分類器候補の比較表

| 候補 | 学習data | 日本語・長文 | 確率 | 費用 | 現時点の判断 |
|---|---|---|---|---|---|
| Gemini structured factors | 不要 | 実績あり | 自己申告 | API従量 | baseline維持 |
| factor別Gemini Resolver | 不要 | 実績あり | 自己申告 | 条件付きAPI | versionで採用候補、他factorも個別比較 |
| Jev 5 Noul | 不要 | 未検証 | provider確率 | 低額API候補 | 優先比較候補 |
| multilingual NLI | 不要 | 長文に制約 | softmax | local | 低費用pilot候補 |
| 日本語BERT fine-tune | 多数必要 | 入力設計が必要 | 校正可能 | local | data蓄積後 |
| direct 3-label Choice | 不要 | model依存 | 分布 | model依存 | 要因を失うため非推奨 |
| 全面LLM ensemble | 不要 | 高い | model依存 | 高い | 条件付きroutingのみ検討 |

## 7. 分類器比較の評価設計

### 7.1 固定条件

- Retrieval、Generator、Top-8、Embedding、取得根拠を固定する。
- 現在の130件には最終3ラベルのgoldはあるが、5 factorすべてのgoldはない。この状態でfactor精度を130件分測ったとは説明しない。
- 第一段階では、既存の分類prompt development case、現在の分類失敗、hard negative controlから分類専用benchmarkを作り、5 factorを人手annotationする。対象一覧とgoldをmodel実行前に固定する。
- 同じ分類専用benchmarkを現行Gemini、Jev 5 Noul、多言語NLIへ渡す。
- 第二段階では、第一段階のgateを通った候補だけを保存済み130件へ適用し、最終3ラベルと総合回答成功を測る。全候補を130件実行しない。
- textとvisual、期待3分類、難易度を分けて集計する。
- API errorを誤分類と混ぜない。
- sealed holdoutは候補選択に使わない。

### 7.2 指標

| 層 | 指標 |
|---|---|
| 総合 | 候補適用後の総合回答成功率 |
| ラベル | Accuracy、class別Precision/Recall/F1、macro F1 |
| factor | factor別Precision/Recall/F1 |
| 安全性 | `判断要`・`文書不足`を`根拠十分`へ変える重大退行 |
| 校正 | Brier、confidence bin、coverage-risk |
| 安定性 | 同一入力の再実行一致、label名・順序の摂動 |
| 運用 | latency、token、費用、API error、local memory |

### 7.3 採用gate

- 分類専用benchmarkでfactor macro F1と最終ラベルmacro F1を記録する。
- `判断要`・`文書不足`を`根拠十分`にする重大誤りを、現行Geminiより増やさない。
- 有望候補の130件確認では、gold訂正後の分類正解121/130を1件以上改善する。同率の場合は、費用・遅延・失敗率を明確に改善しなければ現行を維持する。
- 現在正しい`判断要`・`文書不足`を`根拠十分`へ変える重大退行0件。
- 総合回答成功率を1件以上改善する。
- Q196のcross-layer問題を、分類だけで見かけ上成功にしない。
- confidenceを使う場合、閾値はholdout前に固定する。
- provider失敗時のfallbackとログを実装できる。

## 8. 限界効果に基づく改善優先順位

主原因の件数だけで優先順位を決めない。施策ごとに、次の値を比較する。

```text
期待効率 = 直接改善が見込める件数 × 成功確度
           ------------------------------------
           実装工数 + 評価工数 + API費用 + 退行リスク
```

これは厳密な金額換算ではなく、候補を同じ観点で比較するためのdecision ruleである。「分類失敗9件」をそのまま分類器の期待改善9件として扱わず、他層を直さず総合成功へ変えられる件数だけを分子に置く。

| 順位 | Work Package | 主対象 | 理由 |
|---:|---|---|---|
| 1 | 分類器モデルの段階比較 | 分類全体 | 技術選定の証拠を作り、候補を小benchmarkで絞ってから130件確認する |
| 2 | Qdrant Hybrid Search | 検索3件 | 追加LLM callなしで比較でき、Q291は正解chunkが9位にある |
| 3 | Generator required facets | 生成の項目欠落3件 | Q066、Q131、VD019へ直接対応できる |
| 4 | 分類境界の追加対策 | Q126、Q176、VD024 | モデル比較後の残存失敗を見て、専用resolverの価値を再判定する |
| 5 | 不足条件の型付け | cross-layer | Q196など質問外の不足条件を区別するにはSchema・分類・表示の変更を伴う |
| 6 | 条件付きQuery Decomposition | 検索multi-document | Hybridで残るcaseだけに限定する |
| 7 | Reranking | 検索順位 | candidate recall確保後に効果を測る |
| 8 | 単発境界の対策 | Q126、VD024、Q391等 | 追加例を用意してから過適合を避ける |

分類器の比較自体には、「既存modelを無検証で使い続けず、本RAGの日本語・根拠付き判断で選定した」というポートフォリオ上の価値がある。そのため改善件数だけでなく、技術選定の説明可能性も便益へ含め、最初のWork Packageへ置く。

ただし、現行Gemini、Jev、多言語NLIを最初から130件すべてで比較しない。最初にfactor gold付きの分類専用benchmarkで候補を絞り、gate通過候補だけを130件確認する。Jevは外部APIのaccess、費用、入力長、データ条件をread-only preflightで確認してから有限runを行う。NLIはlocal pilotで入力長と日本語factor判定が成立するかを先に確認する。Fine-tuningはfactor goldを持つ独立scenarioが増えるまで開始しない。

モデル選定後、残る分類境界を再確認する。少数ケースだけなら専用resolverを追加するより、Hybrid SearchまたはGenerator required facetsを先に進める。語句だけで最終ラベルを決める規則は追加しない。

## 9. 結論

総合回答成功率を上げるには、RAG側と分類器側を別々に改善し、最後に同じend-to-end成功条件で統合評価する必要がある。

- RAG側: Hybrid Search、必要時の質問分解、reranking、required facets。
- 分類器側: factor別判定、Jev/NLI比較、決定的規則とのcascade、校正されたabstention。
- 共通: 同じ入力・同じgold・重大退行0件で比較し、効かなかった候補も保存する。

Jevは本タスクのtyped multi-label decisionと形が合うが、公開直後である。低価格や型安全を採用理由にせず、本RAGの日本語130件でGeminiと同じ条件に置き、意味精度と安全性を先に測る。
