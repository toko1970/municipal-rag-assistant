# 分類モデル比較preflight

## 1. 目的

承認済み36件benchmarkを実行する前に、現行Gemini、Jev系、ローカル多言語NLIの利用条件を確認する。費用や大容量downloadを発生させず、同じ入力を比較できる候補だけを次の有限runへ進める。

調査日は2026年9月28日。外部serviceの仕様と価格は実行直前に再確認する。

## 2. 結論

| 候補 | 判定 | 理由 |
|---|---|---|
| Gemini 3.1 Flash-Lite | baselineとして採用 | 現行実装を再利用でき、structured outputと長い入力を扱える |
| JevLM / TypeSafe Jev | 今回の直接比較から除外 | early accessで、利用者のラベルへfitする提供形態。公開価格・一般API契約を確認できない |
| OpenJev 0.8B long | 後続候補へ保留 | 公開weightsはあるが1.73GB、現在のTransformersがQwen 3.5設定を認識せず、model cardの言語表示はEnglish |
| mDeBERTa-v3-base multilingual NLI | 最初のlocal pilotに採用 | 日本語を含む27言語のNLI学習を明記し、既存環境でarchitectureを読める |
| multilingual MiniLMv2-L6 NLI | 速度controlとして保留 | 428MBと軽いが、NLI fine-tuningで日本語を明示していない |
| GLiClass multilang mini | 今回は除外 | native training 20言語に日本語がなく、追加libraryも必要 |

「Jevを比較した」と説明するには、公式Jevまたは同じtyped-decision契約を実際に動かす必要がある。今回のOpenJevや一般NLIをJevとして扱わず、`公開typed-decision候補`と`多言語NLI候補`を分けて記録する。

## 3. Jev系の確認結果

### 公式JevLM

[公式ページ](https://jevlm.ai/)は、Noul・Score・Choiceという固定型の質問を確率で返し、JevLMはlocal open weights、TypeSafe Jevはhosted serviceと説明している。一方、利用開始はearly accessで、利用者が持ち込むdecisionとlabelへmodelをfitする案内である。一般公開のmodel identifier、API仕様、価格表を確認できないため、36件をそのままzero-shot比較する候補にはできない。

本RAGの5 factorをNoulへ写像する考え方自体は適合する。ただし36件だけでfitと校正を行うと、評価データで学習することになる。独立した学習用annotationが増えるまでは公式Jevの本来の使い方を公平に評価できない。

### OpenJev

[OpenJev model card](https://huggingface.co/AlexWortega/openjev)は、Qwen 3.5をNLI cross encoderへ変換し、typed decisionをoptionごとのforward passで返す実装を公開している。0.8B long checkpointは4k contextで、repository sizeは約1.73GBである。[checkpoint files](https://huggingface.co/AlexWortega/openjev/tree/main/qwen3.5-0.8b-nli-v2s-long)

現在のlocal環境ではTransformers 4.57.6が`qwen3_5` configurationを認識せず、MPSも利用不可と判定された。8GB Apple M1上のCPU実行でdependency更新と1.73GB downloadを先に行う費用対効果は低いため、最初のcandidateにしない。

## 4. ローカルNLI候補

### 第一候補: mDeBERTa-v3-base

[model card](https://huggingface.co/MoritzLaurer/mDeBERTa-v3-base-xnli-multilingual-nli-2mil7)は、100言語対応のbase modelを、日本語を含む27言語・約270万組のNLI dataでfine-tuneしたと説明している。MIT license、約0.3B parameters、safetensorsは約558MBである。[model file](https://huggingface.co/MoritzLaurer/mDeBERTa-v3-base-xnli-multilingual-nli-2mil7/blob/main/model.safetensors)

最大入力は512 tokenである。[config](https://huggingface.co/MoritzLaurer/mDeBERTa-v3-base-xnli-multilingual-nli-2mil7/blob/main/config.json) 現在の36件は最大1,067文字・2,631 bytesだが、日本語token数はtokenizer取得後でなければ確定できない。採点前に36件すべてのtoken数を記録し、黙ってtruncateしない。

local環境にはPyTorch 2.14.0、Transformers 4.57.6、SentencePiece 0.2.1があり、DeBERTa v2 architectureを認識している。推論はCPU前提とする。

### 速度control: multilingual MiniLMv2-L6

[model card](https://huggingface.co/MoritzLaurer/multilingual-MiniLMv2-L6-mnli-xnli)は0.1B parametersのdistilled modelで、速度を優先する候補である。safetensorsは428MB、最大入力は514 tokenである。[files](https://huggingface.co/MoritzLaurer/multilingual-MiniLMv2-L6-mnli-xnli/tree/main)、[config](https://huggingface.co/MoritzLaurer/multilingual-MiniLMv2-L6-mnli-xnli/blob/main/config.json)

base modelは多言語だが、model cardが示すNLI fine-tuningはXNLI developmentと英語MNLIで、日本語を直接含むとは記載していない。mDeBERTaが動作しない場合、または速度差を示す必要が生じた場合だけ追加する。

## 5. Gemini baseline

[Gemini 3.1 Flash-Lite](https://ai.google.dev/gemini-api/docs/models/gemini-3.1-flash-lite)はstable model code、structured outputs、1,048,576 input tokensを提供する。現行`CLASSIFIER_MODEL_NAME`も`gemini-3.1-flash-lite`である。

[公式価格](https://ai.google.dev/gemini-api/docs/pricing)はStandard paid tierでtext input US$0.25 / 1M tokens、output US$1.50 / 1M tokensである。実行時は36 logical calls、retry 0、費用上限US$0.05、API error時fail-fastとする。free tierでも入力データがproduct improvementへ使われる記載があるため、架空文書だけを使う現状を維持する。

## 6. 公平な比較に必要な入力契約

NLIは5 factorを直接理解する専用分類器ではない。各factorを日本語の仮説へ変換し、question、evidence、claims、missing conditionsをpremiseとして評価する。

```text
retrieval_sufficient       取得根拠には、質問へ答えるために必要な情報が揃っている。
answer_fully_supported     回答の重要な主張は、取得根拠によってすべて支持されている。
requires_case_facts        質問が求める結論には、まだ示されていない個別事実が必要である。
requires_policy_judgment   必要事実が揃っても、制度所管部署の判断または複数解釈が残る。
version_conflict           質問へ適用する文書版を一意に決められない。
```

36件で5 factorを評価するため180 premise-hypothesis pairとなる。閾値を同じ36件へ最適化すると過適合になるため、最初はモデルの3 class argmaxを保存し、`neutral`を自動でtrueまたはfalseへ潰さず`abstain`としてGemini fallback対象にする。binary thresholdの調整は独立development dataを用意した後に行う。

## 7. Local pilotの実測結果

2026年9月29日にmodel revision
`b5113eb38ab63efdd7f280f8c144ea8b13f978ce`を1回downloadし、承認済み36件を
5 factorへ展開した180 premise-hypothesis pairのtoken数を監査した。

| 項目 | 実測 |
|---|---:|
| pair | 180 |
| 512 token超過 | 80 |
| 超過case | 16 / 36 |
| 最大 | 802 token |
| local inference | 0 pair |
| external API | 0 call |
| 外部推論費用 | US$0 |

超過16件はすべて保存済み回帰ケースで、取得Top-8を含む実運用に近い入力だった。
短いoracle control 20件だけを採点すると候補に有利な標本へ変わるため、予定した
fail-fastを適用し、model inferenceを実行しなかった。結果は
[`results/classifier_model_mdeberta_pilot_v1/token_audit.json`](results/classifier_model_mdeberta_pilot_v1/token_audit.json)
に保存した。

この結果から、512 tokenの一般NLI modelを現行分類器へそのまま差し替えることはできない。
次に比較を続ける場合は、次のどちらかを新しい入力契約として先に設計する。

1. claimとevidenceの対応単位でNLIを行い、factorへ集約する。
2. 4k以上を扱える日本語適性のあるlocal modelを選び直す。

1は長文を避けられる一方、`retrieval_sufficient`、`requires_case_facts`、
`requires_policy_judgment`のように取得集合全体を見るfactorを単純なpair判定へ分解できない。
2は現状の入力契約を保てる一方、8GB M1でのmemory・latencyと日本語性能を改めて確認する
必要がある。入力契約を変えずに比較できるGemini baselineを先に有料実行しても、local候補が
採点不能な現状ではモデル比較にならないため、まだ実行しない。

model downloadとtoken auditだけを実施した。外部API call、有料設定変更、sealed holdoutは
実施していない。
