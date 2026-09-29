# Sealed holdoutで判明した弱点への対策調査

## 1. 目的

Text sealed holdoutの結果を使い、次の実装候補を選ぶ。ただし、開封済みholdoutへ直接合わせて
コードを調整しない。観測した失敗を仮説へ変換し、新しいdevelopment fixtureで比較してから
本番候補を決める。

本調査は、Loop Libraryの
[The claim-ledger research loop](https://signals.forwardfuture.com/loop-library/loops/claim-ledger-research-loop/)
をこのリポジトリ向けに3 roundへ縮小して実施した。

| Round | 対象 | 停止条件 |
| --- | --- | --- |
| 1 | 回答分類の校正 | 一次資料、実装候補、比較gateが揃う |
| 2 | 具体的な期限計算 | LLMとコードの責務境界、対象範囲、比較gateが揃う |
| 3 | 表示契約の不整合 | 安全なfallbackと精度評価を混同しない設計が決まる |

各主張を「観測済み事実」「外部資料」「このアプリへの推論」「未確定事項」に分けた。実装候補ごとに
改善可能件数の上限、費用、退行リスク、採用条件を定めた時点で停止した。外部APIによる追加評価と
本番コード変更は行っていない。

## 2. 現在の証拠

受入結果の詳細は[`TEXT_HOLDOUT_ACCEPTANCE_RESULTS.md`](TEXT_HOLDOUT_ACCEPTANCE_RESULTS.md)を
正とする。

| 指標 | 結果 |
| --- | ---: |
| 総合回答成功 | 83 / 100 |
| scenario stability | 39 / 50 |
| 回答分類 | 86 / 100 |
| 回答内容 | 94 / 100 |
| 実行成功 | 98 / 100 |
| document / evidence retrieval | 100 / 100 |

17件の総合失敗に対して、理由は重複している。

- 分類失敗14件のうち、実行できたラベル不一致は12件だった。
  - `根拠十分 → 判断要`: 9件
  - `判断要 → 根拠十分`: 3件
  - 残り2件は表示契約で実行失敗し、ラベルを出せなかった。
- 内容失敗6件のうち、4件は取得済みの起算規則を具体日へ計算しなかった。
- 実行失敗2件は、Classifierが`根拠十分`相当の要因を返した一方、Generatorが
  `missing_conditions`を返し、表示契約が矛盾を検出した。
- 検索は100件すべて成功した。今回の受入結果だけを根拠にRetriever、Embedding、Qdrantを
  変更する理由はない。

RAGCheckerは、RAGの総合指標と、Retriever・Generatorごとの診断指標を分ける必要を示している。
このアプリも総合成功を最終指標に保ち、分類・内容・実行・検索を原因診断へ使う。
[RAGChecker, NeurIPS 2024](https://proceedings.neurips.cc/paper_files/paper/2024/hash/27245589131d17368cccdfa990cbf16e-Abstract.html)

## 3. 単体施策の改善上限

「失敗理由の件数」と「その施策だけで総合成功へ戻せる件数」は異なる。

| 施策 | 直接対象 | 単体で総合成功へ戻せる観測上限 | 理由 |
| --- | ---: | ---: | --- |
| 分類校正 | ラベル不一致12件 | **11件** | TH011 noisyは日付内容も失敗している |
| 具体日計算 | 内容失敗4件 | **3件** | TH011 noisyは分類も失敗している |
| 表示契約fallback | 実行失敗2件 | **0件の可能性** | 実行できても正しい分類・内容を作らなければ総合成功にならない |
| Retriever変更 | 検索失敗0件 | **0件** | 現在のholdoutでは根拠を全件取得済み |

これは施策の効果を保証する数字ではなく、他の条件を悪化させず対象をすべて直せた場合の上限である。
とくに分類校正は上限が大きい一方、過去の一括prompt変更で重大退行が発生しているため、期待値と
不確実性を分けて扱う。

## 4. Round 1: 回答分類の校正

### 4.1 Claim ledger

| 区分 | 内容 |
| --- | --- |
| 観測済み事実 | 12件の実行済みラベル不一致のうち9件が過剰な`判断要`、3件が危険側の`根拠十分`だった |
| 観測済み事実 | 現行はLLMが5 boolean factorを同時に返し、`derive_label`が優先順位で3ラベルへ変換する |
| 観測済み事実 | 36件の既存比較ではGemini 3.1 Flash-Liteが31/36、BGE-M3 zero-shotが6/36だった |
| 外部資料 | Selective classificationは、自動判定するcoverageと誤りriskの交換関係を明示する |
| 外部資料 | 日本語一般NLI benchmarkは存在するが、自治体制度文書の判断境界での性能を保証しない |
| 推論 | 単純なモデル置換より、意味判定を分け、重大誤りと過剰保留を別々に測る方が現在の失敗へ合う |
| 未確定 | 9件の過剰保留が同じfactorの誤りか、複数の意味境界に分かれるかは追加annotationが必要 |

Selective classificationは、低信頼時に判定を保留し、coverageとriskを一緒に評価する考え方である。
ただし、現行Geminiの自己申告`confidence`を正解確率とはみなせない。
[El-Yaniv and Wiener, JMLR 2010](https://jmlr2020.csail.mit.edu/papers/v11/el-yaniv10a.html)

日本語NLIの一般能力を測るJGLUE/JNLIはモデル候補の事前選別には使えるが、質問範囲、個別事情、
所管判断、版競合という本アプリ固有の定義を置き換えない。
[JGLUE, LREC 2022](https://aclanthology.org/2022.lrec-1.317/)

### 4.2 推奨する構造

5 factorを一つの自由な意味判断として同時に変えるのではなく、次の3層へ分ける。

```text
取得根拠 + 生成claims
  │
  ├─ A. support判定
  │     retrieval_sufficient / answer_fully_supported
  │
  ├─ B. 未解決条件判定
  │     requires_case_facts / requires_policy_judgment / version_conflict
  │
  └─ C. 決定表
        factor + missing condition type -> label / safe fallback
```

- Aは「claimが根拠に支持されるか」を扱う。RefCheckerが用いるclaim単位の検査は、文章全体を
  一括評価するより失敗箇所を追跡しやすい。本アプリはすでにclaimとevidence IDを持つため、
  新しい自由文形式を増やす必要はない。
  [RefChecker, EMNLP 2024](https://aclanthology.org/2024.emnlp-main.395/)
- Bは「正しいclaimがあっても、質問の結論に未解決条件が残るか」を扱う。入力中に個別事情が
  登場した事実と、結論に個別事情が不足している状態を区別する。
- Cはコードで再現可能にする。意味判定そのものを規則化せず、factorの組合せと
  `missing_conditions`の型の整合だけを決定表にする。

`missing_conditions`は現在ただの文字列配列である。分類不整合を減らすには、次のenumを持つ
構造へ変える案が適する。

```json
{
  "type": "case_fact | policy_judgment | missing_document | version_conflict",
  "description": "確認すべき内容",
  "evidence_element_ids": ["..."]
}
```

これにより、Generatorが不足条件を出したのにClassifierがすべてfalseとする矛盾をコードで検出
できる。文言パターンへ規則を合わせず、意味型と状態の不変条件だけを固定する。

### 4.3 モデル候補の扱い

| 候補 | 今回の位置付け | 判断 |
| --- | --- | --- |
| Gemini 3.1 Flash-Lite | 日本語・長文・複数根拠で既存実績があるbaseline | 維持して構造変更と比較 |
| multilingual NLI / mDeBERTa | claim supportの補助候補 | 長文と日本語制度文書をdevelopment setで再検証するまで本採用しない |
| Jev | 5 factorをtyped decisionとして返すchallenger | 公式主張だけで採用せず、同じ入力で精度・校正・費用を比較 |
| fine-tuned日本語encoder | data蓄積後の候補 | 現在のfactor gold件数では早い |

mDeBERTaは102言語を対象としXNLIのzero-shot結果を公開しているが、日本語はXNLI表に含まれず、
本アプリの長いTop-8入力にも制約がある。
[Microsoft DeBERTa repository](https://github.com/microsoft/DeBERTa)

Jevはtyped outputと確率を提供するため分類器の比較候補には合う。ただし、公開直後のvendor資料が
主な根拠で、自治体制度文書の独立評価は確認できない。型が正しいことは意味上の正解を保証しない。
導入する場合は5個のyes/no decisionとして同じ固定benchmarkで比較する。
[TypeSafe AI: Introducing System One Models & Jev](https://typesafe.ai/blog/introducing-system-one-models-and-jev)

Abstentionを学習で改善する研究もあるが、モデル学習を伴う。現在の規模では、既存modelの選択的な
fallbackとdevelopment校正を先に試す方が小さい。
[Abstain-R1, Findings of ACL 2026](https://aclanthology.org/2026.findings-acl.985/)

### 4.4 最小実験

1. 開封済みholdoutの失敗から類型だけを抽出し、異なる制度・日付・文言の新規development
   scenarioを作る。holdout本文や正答をそのままfew-shot例にしない。
2. scenarioごとに5 factor、missing condition type、最終ラベルを人手annotationする。
3. 現行Geminiをbaselineとし、最初のcandidateは「typed missing conditions + 決定表」に絞る。
4. baselineとcandidateへ同じ取得根拠・生成claimsを渡し、Classifierだけを比較する。
5. candidateが通った場合だけ、保存済み130問でend-to-end総合成功を確認する。

評価はAccuracy一つにしない。

- `判断要/文書不足 → 根拠十分`: 危険な断定
- `根拠十分 → 判断要/文書不足`: 過剰保留
- class別Precision、Recall、F1とmacro F1
- 同じscenarioのformal / noisy両方が成功するscenario stability
- confidenceを使う場合だけcoverage-risk曲線とBrier score
- 追加token、API費用、遅延、provider error

危険な断定と過剰保留の重みは業務判断であり、根拠なく一つの加重scoreへ潰さず件数を並記する。

## 5. Round 2: 具体的な期限計算

### 5.1 Claim ledger

| 区分 | 内容 |
| --- | --- |
| 観測済み事実 | TH011とTH039の各2表現で、正しい起算規則は取得・引用したが具体日を出さなかった |
| 観測済み事実 | 日付内容だけ直した場合、総合成功へ直接戻るのは最大3件 |
| 外部資料 | TimeBenchは、LLMの時間推論に人間との大きな性能差とカテゴリ別のばらつきがあると報告する |
| 外部資料 | PALは、LLMを問題の分解へ使い、算術・記号処理をPython等のruntimeへ委譲する |
| 推論 | 「計算するよう強くpromptする」より、規則抽出と日付演算を分離する方が再現可能である |
| 未確定 | 営業日、閉庁日、休日繰越など、文書ごとのcalendar規則をどこまで初期scopeに含めるか |

[TimeBench](https://aclanthology.org/2024.acl-long.66/)は時間推論を独立した弱点として評価している。
[PAL, ICML 2023](https://proceedings.mlr.press/v202/gao23f.html)は、自然言語の分解をモデルへ、
計算をruntimeへ分ける設計を示す。本RAGでは任意コードをLLMに生成・実行させず、許可した演算だけを
Python関数で行う方が安全で説明しやすい。

### 5.2 推奨する構造

```text
質問 + 取得根拠
  -> LLMが期限演算を構造化
  -> Schemaと引用IDを検証
  -> 許可済みPython関数で計算
  -> 計算結果をanswer claimへ追加
  -> Classifierと表示
```

構造化する最小項目は次のとおりである。

```json
{
  "anchor_date": "2027-10-10",
  "offset_value": 20,
  "offset_unit": "calendar_day",
  "counting_rule": "next_day_is_day_1",
  "cutoff_time": "12:00:00",
  "business_calendar_id": null,
  "evidence_element_ids": ["..."]
}
```

- 初期scopeは暦日、翌日を1日目とする包含・除外、時刻の合成に限定する。
- 営業日や閉庁日を扱う場合は、Python標準の曜日だけで推測せず、文書で定義したcalendar IDと
  休日dataをPostgreSQLで版管理する。
- 入力値、規則、算出結果、引用IDをログへ残す。面接では「LLMに計算を任せず、規則の抽出と
  決定的演算を分けた」と説明できる。
- 構造化不能、未対応の規則、矛盾する起算日は推測せず`判断要`または`文書不足`へ送る。

Geminiのstructured outputはJSON Schema準拠の形を作れるが、公式資料も値をアプリ側で必ず検証
するよう求めている。日付としてparseできることと、制度上正しい計算であることを分けて検査する。
[Gemini structured output](https://ai.google.dev/gemini-api/docs/structured-output)

### 5.3 最小実験

1. 新規development fixtureを最低12 scenario作る。
   - 暦日と翌日起算
   - 月末、閏年、年越し
   - 時刻境界
   - 計算不要のcontrol
   - 未対応の営業日規則
2. baselineは現行回答、candidateは同じGenerator入力へ期限演算結果を付与する。
3. Python日付関数は表形式testで独立検証する。
4. LLM抽出精度とPython演算精度を別々に記録する。

採用gate:

- 対応scopeの具体日を全件正答する。
- 日付計算不要のcontrolへ計算結果を追加しない。
- 未対応規則を推測しない。
- 根拠外の日付や時刻を作らない。
- 保存済み130問で総合成功の退行0件。

## 6. Round 3: 表示契約の不整合

### 6.1 Claim ledger

| 区分 | 内容 |
| --- | --- |
| 観測済み事実 | `根拠十分`なのに`missing_conditions`が非空という矛盾で2件が例外終了した |
| 観測済み事実 | Schema妥当性は通過しており、問題はJSON構文ではなくfield間の意味的不整合だった |
| 外部資料 | Gemini公式資料もSchema準拠後の値検証とsemantic error handlingを求める |
| 推論 | 例外を握り潰して回答を表示するのではなく、不変条件違反を安全な状態へ変換して記録する必要がある |
| 未確定 | typed missing condition導入後、どの矛盾を決定表だけで解消し、どれを再分類へ送るか |

### 6.2 推奨する構造

オンライン処理の結果を次の4状態として扱う。

| 状態 | 意味 | 利用者への表示 |
| --- | --- | --- |
| `SUCCESS` | 契約と意味的不変条件を満たす | 通常回答 |
| `NEEDS_REVIEW` | 個別事情または所管判断が残る | 根拠付き回答と確認事項 |
| `INSUFFICIENT` | 取得根拠では回答できない | 文書不足 |
| `PIPELINE_INCONSISTENCY` | GeneratorとClassifierが矛盾 | 断定せず、回答処理で不整合が生じた旨を表示 |

`PIPELINE_INCONSISTENCY`は500 errorにせず安全な表示を返す。一方、評価ではこれを正解扱いしない。

- execution success: true
- classification success: falseのまま
- content success: goldと一致した場合だけtrue
- composite success: 必要条件をすべて満たした場合だけtrue
- log: `degraded=true`、`invariant_code`、生成claims、missing conditions、分類factorを保存

これにより、公開デモの停止を減らしながら、分類誤りを精度改善として隠さない。

### 6.3 最小実験

外部APIなしで先に実施できる。

1. 5 factor、claim有無、typed missing conditionの組合せをdecision tableにする。
2. propertyまたはtable-driven testで全組合せの結果を検査する。
3. TH014/TH026と同じ構造だが異なる文書・表現のdevelopment fixtureを作る。
4. semantic validatorが不整合を検出し、安全表示と監査ログを残すことを確認する。

採用gate:

- 未処理例外を0件にする。
- `PIPELINE_INCONSISTENCY`を総合正解へ数えない。
- 元のclaimsとfactorを失わずログへ残す。
- `判断要`と`文書不足`を機械的に`根拠十分`へ緩和しない。

## 7. 今は採用しない大きな手法

### Self-RAG / CRAGの全面導入

Self-RAGはモデルを学習し、検索要否、根拠関連性、支持、回答有用性をreflection tokenで制御する。
有力な研究だが、既存Gemini APIを使うこのポートフォリオへprompt一つで追加できる手法ではない。
検索成功100/100の現状に対して、学習・推論・評価範囲が大きすぎる。
[Self-RAG, ICLR 2024](https://proceedings.iclr.cc/paper_files/paper/2024/file/25f7be9694d7b32d5cc670927b8091e1-Paper-Conference.pdf)

### Semantic entropyによる常時不確実性測定

複数回答を生成して意味的な分布を見る方式はconfabulation検出に有用だが、API呼出と費用が増える。
今回の主な分類失敗は、根拠を取得できないことより、質問範囲と未解決条件の境界である。typed condition
とdecision tableを先に比較する。
[Detecting hallucinations in large language models using semantic entropy, Nature 2024](https://www.nature.com/articles/s41586-024-07421-0)

### Retriever・Embeddingの変更

今回のholdoutでは検索が全件成功した。既存回帰を保持し、新規の分類・日付変更で検索が悪化して
いないことを確認する対象に留める。

## 8. 推奨する実装・検証順

### 1. Semantic contractと安全fallback

- 外部API不要で実装・testできる。
- 公開デモの未処理例外を減らす。
- typed missing conditionを後続の分類改善でも使える。
- 単体では総合成功の向上を主張しない。

### 2. 期限計算の小vertical slice

- 原因が同質で、決定的なコードへ委譲できる。
- 観測上の単体上限は総合成功+3件。
- 日付抽出と演算を分けて評価でき、学習成果を説明しやすい。

### 3. 分類校正の比較

- 観測上の単体上限は総合成功+11件で最も大きい。
- 退行リスクも最大なので、typed contractを先に整え、新規development setで比較する。
- 最初はGemini baselineと構造変更を比較する。JevやNLIは同じbenchmarkへ追加するchallengerとし、
  モデル名だけを入れ替えない。

### 4. 保存済み130問の回帰

- 各candidateの小gateを通過した後だけ実施する。
- 総合成功、危険な断定、過剰保留、内容、実行、費用を同じ条件で比較する。

### 5. 新しいsealed holdout

- developmentと130問回帰で候補を一つに固定した後に作る。
- 今回開封した100表現は、以後は受入holdoutではなく観測済み回帰setとして扱う。
- 新holdoutで改善が再現しなければ、原因分析へ戻る。評価setを改善案へ合わせて変更しない。

## 9. 実装候補の比較表

| 候補 | 期待する直接効果 | 追加API | 実装量 | 退行リスク | 優先 |
| --- | --- | ---: | --- | --- | ---: |
| typed missing conditions + semantic validator | 例外削減、分類境界の明示 | 0 | 小〜中 | 低 | 1 |
| deterministic date calculator | 内容失敗4件、総合最大3件 | 抽出方式次第 | 中 | 低〜中 | 2 |
| Gemini分類の責務分離 | 分類失敗12件、総合最大11件 | 同等または条件付き増 | 中 | 中〜高 | 3 |
| Jev challenger | 費用・latency・確率比較 | あり | 中 | 未知 | 3の比較候補 |
| multilingual NLI support checker | claim支持判定のlocal化 | 0 | 中 | 長文・日本語で未知 | 3の比較候補 |
| Self-RAG全面導入 | 広い自己検証 | 大 | 大 | 高 | 見送り |

## 10. 学習上説明できること

- 総合成功とモジュール別診断を分け、失敗理由の重複を扱える。
- 施策の対象件数と、単体で総合成功へ寄与できる上限を区別できる。
- LLMが得意な自然言語からの規則抽出と、コードが得意な決定的演算を分けられる。
- JSON Schemaによる構文保証と、field間のsemantic invariant検証を区別できる。
- 分類器のaccuracyだけでなく、危険な断定、過剰保留、coverage-risk、費用を比較できる。
- 開封済みholdoutへ過適合せず、新しいdevelopment fixtureと新しいsealed holdoutを使う理由を
  説明できる。

## 11. 結論

今回の弱点に対して、汎用的なRAG機能を追加するより、観測した責務境界を明確にする方が費用対効果が
高い。最初にtyped missing conditionとsemantic fallbackを整え、次に期限演算を決定的コードへ
分離する。その上で、総合成功への改善上限が最大の分類校正を、新規development setで比較する。

分類改善は最も大きな効果を持つ可能性があるが、既存の正しい`判断要`を`根拠十分`へ変える退行を
1件でも起こせば安全面の価値を損なう。したがって、実装順は「効果上限の大きい順」ではなく、
後続実験を安全かつ観測可能にする基盤、同質で決定的に直せる問題、最後に不確実な意味分類とする。
