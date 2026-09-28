# Visual answer baseline

## 目的

図表を説明文として検索するだけでなく、検索された元画像をGeminiへ渡した回答について、同じdevelopment 30 scenarioで検索・分類・内容を分けて評価する。

## 固定条件

- dataset: `eval/visual_fixtures/development_evaluation_set.json`
- split: `development`のみ。sealed holdoutは開かない
- corpus: reviewed済み6 fixture、インメモリQdrantの専用collection
- generator / classifier: `gemini-3.1-flash-lite`
- embedding: `gemini-embedding-001`
- retrieval: dense top 5
- image input: 検索順位上位3枚まで
- retry: 0
- 最初のscenario errorで停止
- 各scenario開始前にUS$0.01を費用枠として予約
- token単価: Gemini 3.1 Flash-Lite標準料金の入力US$0.25/100万token、出力US$1.50/100万token（2026-09-28確認）
- Embeddingは現adapterがtoken使用量を返さないため、呼出回数を別記し、LLM token費用へ含めない

評価は次を分離する。

1. 必須fixtureが検索結果へ含まれたか
2. 期待する3分類と一致したか
3. 回答内容が`expected_answer_key`とrequired evidenceに一致するか（人手review）

## Pilot

### v1

モデル応答後、claim内UUIDをJSONへ保存できずharnessが停止した。結果を上書きせず、`visual_answer_pilot_gemini_3_1_v1/failure.json`へ失敗を保存した。API retryは行っていない。

### v2

| 項目 | 結果 |
|---|---:|
| scenario | VD001 |
| completed | 1/1 |
| classification | 正解（根拠十分） |
| required fixture retrieval | 成功 |
| input tokens | 17,871 |
| output tokens | 247 |
| 標準料金換算 | US$0.00483825 |
| elapsed | 15.38秒 |

回答は「申請書を受領した後、最初に記載内容および添付書類の確認を行う」で、期待値と一致した。これにより、図表検索、元画像3枚の添付、構造化回答、分類、portable artifact保存までの経路を確認した。

## 30 scenario baseline実行票

```bash
.venv/bin/python -m eval.evaluate_visual_answers \
  --output-dir eval/results/visual_answer_baseline_gemini_3_1_v1 \
  --max-scenarios 30 \
  --max-cost-usd 0.25 \
  --per-scenario-cost-reserve-usd 0.01
```

最大論理外部call数は91（corpus Embedding 1、質問Embedding 30、回答生成30、分類30）。途中停止時は同じ引数へ`--resume`を加え、保存済みscenarioを再実行しない。

## 30 scenario baseline結果

| 指標 | 結果 |
|---|---:|
| 完了 | 30/30 |
| API error | 0 |
| 必須fixture検索 | 30/30 |
| 分類一致 | 28/30 |
| agent初回内容review | pass 27 / partial 1 / fail 2 |
| input tokens | 573,290 |
| output tokens | 9,468 |
| 標準料金換算 | US$0.1575245 |
| 平均 / 中央 / 最大遅延 | 10.08 / 9.59 / 23.15秒 |

分類の内訳は、`grounded` 18/18、`insufficient_documents` 6/6、`needs_judgment` 4/6だった。失敗2件はいずれも`boundary_or_revision`で、必須fixtureは検索できていた。したがって、このrunで最も明確な弱点は検索ではなく、「資料にない適用基準を個別判断として案内する境界」の生成・分類である。

### 失敗例

- `VD004`: 「読みにくい記載」を図中の「不備」と同一視し、図に運用基準がないのに登録不可と断定した。期待は`needs_judgment`、実際は`根拠十分`。回答生成が根拠を広げ、分類器も支持済みと判定した。
- `VD024`: 出生の記入例を転居へ適用できるかという質問を安全に棄却したが、期待`needs_judgment`に対して`文書不足`となり、個別確認の案内が表示されなかった。検索は成功しており、分類境界またはgold定義の再確認対象である。目標値へ合わせるためgoldは変更しない。

### 部分合格

- `VD019`: 「職員区分が不明なので金額を確定できない」という中心回答と`判断要`は正しいが、申請不備時の差戻しという質問に不要なclaimを混在させた。

内容reviewはCodexによる初回確認であり、`content_review.json`の`requires_user_confirmation`を`true`としている。面接資料の確定値に使う前にユーザー確認を行う。

### 次の一手

改善対象を検索へ広げず、上記2種類の境界に絞る。まず、claimが引用するvisual element内のnode・edge・cellまでlocatorを返す契約と、「根拠にない語を既存の制度用語へ読み替えない」生成規則を候補にする。`VD024`は文書不足と判断要の定義に関するgold disagreementとして残し、評価セットを書き換えずに分類要因を比較する。

## Prompt候補のRevolve結果

最初の候補`answer-claims-v2`は、質問表現を根拠内の判断区分と推測で同一視しない規則を追加した。`VD004`単体では`根拠十分`から`判断要`へ改善し、根拠外claimも0件になった。しかし全体比較では、3問目の`VD003`にある誤記「モレ」まで資料中の「不備」と対応付けられなくなった。生成側が不足条件を返し、分類側が根拠十分と判定したため、表示契約が不整合を検出してfail-fastした。

次の`answer-claims-v3`では通常の誤字・言い換えを許可し、主観的基準だけを禁止したが、`VD003`で同じ不整合を再現した。最大roundの停止条件に従い追加prompt調整を行わず、production候補はbaselineの`answer-claims-v1`へ戻した。

このexperimentから、自然言語の一文だけで誤字許容と制度判断の境界を安定させるのは難しいと分かった。次の候補は、node・edge・cell locatorをclaimへ持たせるSchema変更、または`missing_conditions`と分類要因の不整合を安全側へ解決する決定的規則とする。結果は`eval/results/visual_answer_prompt_experiment_summary.json`に保存した。
