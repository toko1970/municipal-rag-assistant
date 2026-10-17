# 精度改善策の採用判定プロトコル

- 作成日: 2026-09-30
- 対象: 初回Text sealed holdout後の改善候補
- 目的: 既知の失敗だけを直す対策を採用し続けることを避け、一般化、退行、安全性、費用を同じ手順で判定する

回答分類候補の語義と決定順序は[`../design/CLASSIFICATION_RUBRIC_V2.md`](../design/CLASSIFICATION_RUBRIC_V2.md)を正とする。本書は候補を採用するための評価手順を定め、過去のv1結果は当時の定義のまま保持する。

## 1. 初回holdoutで最大だった失敗

初回Text sealed holdoutは50シナリオ・100表現で、総合回答成功83/100だった。

| 原因 | 件数 | 単独失敗 | 他原因との重複 |
|---|---:|---:|---:|
| 回答分類 | 14 | 11 | 3 |
| 回答内容 | 6 | 3 | 3 |
| 実行 | 2 | 0 | 2 |
| 文書検索 | 0 | 0 | 0 |

実行できた分類不一致12件の内訳は次のとおりである。

- `根拠十分 → 判断要`: 9件
- `判断要 → 根拠十分`: 3件

したがって最大原因は回答分類であり、特に、正しい回答と根拠があるのに不要な個別確認を加える**過剰保留**だった。

内容失敗6件のうち4件は具体期限の未計算である。決定的日付計算はこの4件のうち総合最大3件へ作用し得るが、分類失敗14件全体の解決策ではない。

## 2. 最大原因へ対応する一般化候補

### 2.1 問題の構造

現在のClassifierは、質問、取得根拠、生成回答を一度に読み、次の5 factorを同時に返す。

- retrieval sufficient
- answer fully supported
- requires case facts
- requires policy judgment
- version conflict

この方式では、質問が何を直接求めたか、生成回答がその要求を満たしたか、回答外の情報が本当に必要かが一つのprompt内で混ざる。結果として、質問に不要な条件まで「不足」とみなし、`判断要`へ寄せやすい。

### 2.2 推奨候補: Question Contractとclaim検証

自然文質問を先に次の構造へ変える。

```json
{
  "schema_version": "1.0",
  "status": "SUCCESS",
  "requested_facets": [
    {
      "facet_id": "facet-1",
      "requirement": "所属だけで決定できるか",
      "answer_type": "eligibility"
    }
  ],
  "input_facts": [],
  "error_code": null
}
```

Generatorの出力は、各claimがどのfacetへ答え、どの文書根拠・入力値・検証済み計算に支持されるかを示す。質問内の入力事実だけで最終分類は決めない。

```json
{
  "claims": [
    {
      "claim_id": "claim-1",
      "facet_ids": ["facet-1"],
      "input_fact_ids": [],
      "calculation_ids": [],
      "evidence_element_ids": ["<取得根拠ID>"]
    }
  ]
}
```

コードは次を別々に判定する。

1. requested facetへclaimが対応しているか。
2. claimは取得根拠に支持されるか。
3. 取得文書に判断基準があり、その結論を一意にするための人による確認要件が残るか。
4. 文書不足、生成不足、人による確認を混同せず、Rubric v2の決定順序で結果を導く。

Claim単位の根拠検証は、回答全体の一括判定より、unsupported、contradiction、under-evidenceを分けて診断できる。RAGCheckerは検索と生成を細粒度に分けた診断の必要性を示し、Q-CAREはqueryをsubquery、回答をatomic claimへ分解してcoverageとverifiabilityを測る。[RAGChecker](https://arxiv.org/abs/2408.08067)、[Q-CARE](https://arxiv.org/abs/2608.11238)

### 2.3 factor別判定と決定表

一つのLLM callで最終ラベルを直接決めず、意味の異なるfactorを独立に観察する。

```text
Evidence coverage       = 取得文書に規則または判断基準があるか
Claim support           = 各claimを根拠・入力・検証済み計算が支持するか
Human review            = 個別事実・明示的裁量・未解決の版競合が残るか
```

最後にコードの決定表で3分類へ変換する。Version Resolverはこの分離を版factorだけに適用した例である。

ただしfactorを5回のLLM callへ分ける必要はない。共通Schemaで一度に抽出し、各fieldを独立評価できるようにする方法と、失敗が多いfactorだけ専用判定へ送る方法を比較する。

### 2.4 selective classificationの扱い

低confidence時に回答を保留するselective classificationは、危険な`判断要 → 根拠十分`を減らす候補になる。一方、初回holdoutの最大失敗はすでに過剰保留なので、単純に保留を増やすと主問題を悪化させる。

採用時はaccuracyだけでなく次を分ける。

- 危険な断定率: 本来`判断要/文書不足`を`根拠十分`にした割合
- 過剰保留率: 本来`根拠十分`を`判断要/文書不足`にした割合
- coverage: 自動回答できた割合
- selective risk: 自動回答した集合での誤り率

LLMのabstentionは独立した評価課題であり、answerable/unanswerable confusion matrixによる評価が提案されている。[Do LLMs Know When to NOT Answer?](https://aclanthology.org/2025.coling-main.627/)

## 3. 現在の採用判定の評価

現在行っている次の比較は、必要だが十分ではない。

```text
既知の失敗質問が成功したか
既知の成功質問が失敗しなかったか
```

### 妥当な点

- 同じ質問でbaselineとcandidateを比較するため、変更の直接効果を追いやすい。
- 既存成功controlを含めるため、明らかな退行を早期に検出できる。
- 小さいpilotで効果のない候補を止め、API費用を抑えられる。
- 質問単位のpaired比較なので、単純な平均値だけより原因を追いやすい。

### 不足する点

- 対策を考えるときに見た失敗質問は、採用評価用の未見データではない。
- controlが少数または選択的だと、別の質問分布への退行を見逃す。
- 同じ意味の未知言い換えへ効くか分からない。
- 失敗件数が少ないため、1〜2件の変化を一般的効果と誤認しやすい。
- 複数候補を同じ評価セットで繰り返し選ぶと、評価セット自体へ適応する。

Test setを繰り返し見て改善判断へ使うと、後の候補がそのsetへ適応する問題はadaptive data analysisとして知られている。[Test-set reuseとoverfitting](https://proceedings.mlr.press/v97/feldman19a.html)

したがって既知失敗は**原因診断とmechanism確認**には使えるが、最終採用の一般化証拠にはしない。

## 4. 新しい採用判定の5段階

### 4.1 Gate 0: 仮説を事前固定

実装前に次を記録する。

- 対象とする失敗family
- 作用するpipeline層
- 改善を予想するslice
- 悪化し得るslice
- 変更しない条件
- 採用閾値
- 費用・call・retry上限

実測後に対象や閾値を変えない。仮説と異なる改善は探索的結果として記録し、次の独立検証へ回す。

### 4.2 Gate 1: 既知失敗によるmechanism test

既知の失敗質問を使い、意図した内部機構が動くか確認する。

例:

- Query Plannerが二つのintentを返すか。
- question scope外のconditionを`not_requested`にできるか。
- claimと根拠IDを対応付けられるか。

このgateはunit/integration testに近い。ここで成功しても採用しない。

### 4.3 Gate 2: 未知の同型challenge set

既知失敗と同じ原因だが、文書、日付、表現、制度を変えた問題を、実装結果を見る前に固定する。

初回分類改善なら最低限、次を含める。

| slice | 目的 |
|---|---|
| 根拠十分だが関連する個別条件が存在 | 過剰`判断要`を測る |
| 本当に個別条件が不足 | 危険な`根拠十分`を測る |
| 文書不足 | `判断要`との境界を測る |
| 複数文書 | facet coverageを測る |
| 版境界 | version factorを測る |
| formal / paraphrase / noisy | 表現依存を測る |

RAGは小さなquery perturbationでも構成要素ごとに性能が変わるため、言い換えだけでなく、誤字、冗長表現、語順、具体値の変更をsystematicに含める。[Query-level RAG robustness](https://aclanthology.org/2025.gem-1.38/)

既知失敗から単語だけを置き換えた問題ではなく、別文書familyと別業務eventを含める。

### 4.4 Gate 3: 代表回帰setでpaired比較

既存130問を、候補選択用のdevelopment regressionとして使う。baselineとcandidateを同じ質問で比較し、次を記録する。

- 両方成功
- baselineだけ成功
- candidateだけ成功
- 両方失敗

重要なのは総合成功率だけでなく、candidateだけ改善した件数とcandidateだけ退行した件数の対応である。NLP評価では、同じinstanceに対するpairingを無視した平均だけでなく、paired comparisonを使う重要性が指摘されている。[Better than Average](https://aclanthology.org/2021.acl-long.179/)

このプロジェクトではbinary composite successについて次を併記する。

- 正味改善件数
- 改善・退行の質問IDとfailure family
- scenario単位のpaired bootstrap confidence interval
- discordant pairが十分ある場合のexact McNemar test

100〜130件では統計的検出力が低い可能性がある。`p > 0.05`を同等性の証明には使わず、効果量とconfidence intervalを中心に説明する。

### 4.5 Gate 4: 安全性・費用・運用gate

Accuracyが上がっても、次を満たさなければ採用しない。

- 危険な`判断要/文書不足 → 根拠十分`の新規退行0件
- 根拠外claimの新規発生0件
- Schema、provider、fallback失敗が安全表示になる
- call、token、p50/p95 latency、費用が事前上限内
- plannerやclassifierの判断をrequest IDで監査できる

過剰保留と危険な断定はコストが異なるため、同じ1誤りとして相殺しない。

### 4.6 Gate 5: 候補固定後のfresh sealed holdout

Gate 0〜4を通過した候補だけを固定し、開発に使っていない2回目のsealed holdoutで最終受入する。

- goldをcandidate固定後に開封する。
- holdout結果を見てcandidateを修正しない。
- 不合格ならholdoutは開封済みdevelopment evidenceへ移し、別のfresh holdoutを次回用に用意する。
- 同じholdoutへ候補を繰り返し送らない。

公開validation setと非公開test setを分ける設計は、benchmark contaminationや適応を抑える一般的な方法でもある。[MMLU-CF](https://aclanthology.org/2025.acl-long.656/)

## 5. 初回holdout分類改善へ適用する具体案

### 5.1 Candidate

`Question Contract + facet coverage + typed missing condition`を第一候補にする。

具体的なSchema、LLMとコードの責務、決定表、費用上限、既知失敗へのdry-runは[`design/QUESTION_CONTRACT_CLASSIFICATION_CANDIDATE.md`](../design/QUESTION_CONTRACT_CLASSIFICATION_CANDIDATE.md)に固定した。

```text
質問
  ↓
requested facetsを構造化
  ↓
claimごとにfacetと根拠IDを対応
  ↓
missing conditionをrequested / not_requestedへ型付け
  ↓
factor別判定
  ↓
コードの決定表で3分類
```

これは初回holdoutの過剰保留へ直接対応し、Query Decomposition、期限計算、版選択にも共通のQuery Planを利用できる。

### 5.2 事前gate

| gate | 条件 |
|---|---|
| Mechanism | 既知9件で質問外conditionを識別し、危険側3件では必要conditionを保持 |
| Unseen challenge | 新規scenarioで過剰保留を改善し、危険な断定を増やさない |
| 130問回帰 | compositeの正味改善、危険な新規退行0 |
| Robustness | formalと未知paraphraseの両方で同じfactor判定 |
| Operations | 追加費用・latency・failure率を記録し上限内 |
| Acceptance | candidate固定後の2回目sealed holdout |

既知9件を9/9直すことを最終採用条件にはしない。既知ケースの改善が一部でも、未知challengeと代表回帰で一貫した効果があれば一般化候補として価値がある。逆に既知9件が全て成功しても、未知challengeやcontrolを悪化させれば不採用とする。

## 6. 評価setの役割

| set | 使用目的 | 候補選択に使うか | 再利用 |
|---|---|---|---|
| 既知失敗 | 原因診断・mechanism確認 | 補助のみ | 可 |
| 同型challenge | 一般化候補の開発 | 使用する | 可。結果を明示 |
| 130問回帰 | 広い退行と正味効果 | 使用する | 可。development扱い |
| perturbation pairs | 表現安定性 | 使用する | 可 |
| fresh sealed holdout | 最終受入 | 候補固定後のみ | 開封後は再利用しない |

## 7. 判断ルール

新しい対策は、次をすべて満たした場合に採用候補とする。

1. 観測した最大原因へ理論上作用する。
2. 既知失敗で意図したmechanismが動く。
3. 未知の同型事例でも効果が再現する。
4. 代表回帰で正味効果が正である。
5. 危険な断定を新規に増やさない。
6. 表現変更で効果が消えない。
7. 費用、latency、運用複雑性が効果に見合う。
8. 候補固定後のfresh holdoutで受入条件を満たす。

この手順では、既知の失敗を直したことは必要な証拠の一部であり、採用の十分条件ではない。

## 8. 一般的なRAG評価プロセスとの照合

RAG改善策の採用手順には単一の国際標準があるわけではない。ただし、近年の評価研究では次の原則が共通している。

| 一般的な評価原則 | 本プロトコルでの対応 | 根拠 |
|---|---|---|
| RetrievalとGenerationを分けて診断する | Gate 0〜2で作用層とmechanismを固定 | [RAGChecker](https://arxiv.org/abs/2408.08067) |
| Scenario・難度・質問形式ごとに評価する | 未知同型challengeとslice集計 | [RAGEval](https://aclanthology.org/2025.acl-long.418/)、[HieraRAG](https://arxiv.org/abs/2606.12789) |
| 言い換えやquery perturbationへの頑健性を測る | formal、paraphrase、noisyのpaired評価 | [Query-level RAG robustness](https://aclanthology.org/2025.gem-1.38/) |
| 同じinstance上のpaired比較を使う | Gate 3の改善・退行pair、bootstrap、McNemar | [Better than Average](https://aclanthology.org/2021.acl-long.179/) |
| Groundingと回答保留を別に測る | claim support、過剰保留、危険な断定 | [GaRAGe](https://aclanthology.org/2025.findings-acl.875/)、[Abstention評価](https://aclanthology.org/2025.coling-main.627/) |
| 繰り返し選定に使ったsetと最終testを分ける | 開封済みsetをdevelopmentへ移し、fresh holdoutを1回だけ使用 | [Test-set reuse](https://proceedings.mlr.press/v97/feldman19a.html) |

したがってGate 0〜5の骨格は、一般的なRAG評価と機械学習のmodel selection手順に整合する。

## 9. 正式採用前に追加する4つの保護策

### 9.1 評価分布を事前に定義する

Failure familyを均等に集めたchallenge setは弱点検出に適するが、実運用の成功率を推定する分布ではない。

このプロジェクトでは、次の二種類を分ける。

- **Challenge評価**: 複数文書、版境界、期限、文書不足などを意図的に多く含め、弱点を検出する。
- **Representative評価**: 想定利用者の質問構成比を事前に定め、全体性能を見る。

実利用ログはまだ十分でないため、representative比率は「給与事務担当者が想定する質問構成」として設計資料へ明記する。将来ログが蓄積した場合は、個人情報を除いた集計から比率を見直す。

Challenge setの成功率を、そのまま実運用の成功率として説明しない。

### 9.2 Gold annotationの信頼性を確認する

対策効果が1〜3件の場合、goldの1件の誤りが結論を変え得る。

次を受入条件へ追加する。

- Question Contract、期待facet、期待分類、必須根拠をmodel実行前に固定する。
- 分類境界と内容判定が難しいcaseは、少なくともユーザーとCodexの二者で確認する。
- 不一致は第三の自動judgeへ多数決させず、判定理由を見て合意する。
- gold訂正は候補の改善件数と分け、訂正履歴を残す。

GaRAGeのようなRAG benchmarkも、question、long-form answer、grounding passageを人手で対応付けている。自動judgeだけで受入goldを確定しない。[GaRAGe](https://aclanthology.org/2025.findings-acl.875/)

### 9.3 LLMの再現性を別に測る

`temperature=0`でもprovider、model revision、構造化生成の揺れ、503などにより結果は完全には固定されない。

費用を抑えるため、全130問を何度も実行せず、次のsubsetを2〜3回実行する。

- candidateで改善した質問
- candidateで退行した質問
- classification boundary
- plannerが分解する質問
- plannerが分解してはいけないcontrol

記録する値:

- Query Plan完全一致率
- factor・最終label一致率
- composite successのrun間一致率
- provider error率

内容品質とprovider可用性を同じ失敗率へ混ぜない。ただし公開運用の成功率では両方を報告する。

### 9.4 多数候補からの選択を制限する

同じdevelopment setで候補、prompt、閾値を多数試すほど、そのsetへ適応する。

各改善roundで次を固定する。

- 比較する主候補は原則1つ、最大でも2つ
- primary metricを1つ固定する
- safety gateはprimary metricと相殺しない
- 候補数と実行回数をmanifestへ記録する
- 結果を見て作った次の候補は新しいroundとして扱う
- development setへ多数回適応した場合は、fresh challenge setを追加する

複数候補を試した後で最も良い数値だけを報告しない。採用候補だけでなく、不採用候補と試行回数を残す。

## 10. 公開後の監視

Offline holdoutを通過しても、実際の質問分布やprovider挙動は変わる。公開後は、個人情報を含めない範囲で次を集計する。

- 回答分類の比率
- `判断要`へ寄った主なfactor
- 文書不足と検索0件
- fallback、Schema error、provider error
- feedback
- latencyと推定費用

新しい失敗は、直ちにkeyword ruleへ追加しない。同じfailure familyが複数確認された場合にdevelopment fixtureへ加え、次の改善roundで一般化候補を比較する。
