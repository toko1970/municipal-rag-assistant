# 分類器モデル比較benchmark

## 1. 目的

Gemini、Jev、多言語NLIを、同じ質問・取得根拠・生成回答で比較する。RetrievalとGeneratorを固定し、分類器だけの差を測る。モデルの実行前にfactor goldを固定し、結果を見てgoldを変更しない。

## 2. 構成

`classifier-model-benchmark-v1`はdevelopment専用の34ケースである。sealed holdoutではない。

| 項目 | 件数 |
|---|---:|
| 合計 | 34 |
| 根拠十分 | 14 |
| 判断要 | 14 |
| 文書不足 | 6 |
| Text | 26 |
| Visual | 8 |
| factor control | 21 |
| observed failure | 7 |
| hard negative | 6 |

factorのtrue件数は次のとおりである。

| factor | true | false |
|---|---:|---:|
| `retrieval_sufficient` | 28 | 6 |
| `answer_fully_supported` | 30 | 4 |
| `requires_case_facts` | 7 | 27 |
| `requires_policy_judgment` | 4 | 30 |
| `version_conflict` | 3 | 31 |

少数factorのF1は1件の影響が大きい。順位だけで優劣を断定せず、個別結果と件数を併記する。

## 3. factor annotation規約

分類対象は、質問、今回取得した根拠、生成済みclaims、`missing_conditions`である。

- `retrieval_sufficient`: 質問が求める範囲へ答える根拠が取得集合にある。
- `answer_fully_supported`: 生成済みの重要claimが取得根拠で支持されている。要求された最終値を取得できない場合でも、「別規程が必要」というclaimが支持されるならtrueになり得る。
- `requires_case_facts`: 質問が求める結論を変える個別事実が不足している。
- `requires_policy_judgment`: 必要事実が揃っても、根拠が裁量・複数解釈・所管判断を残す。
- `version_conflict`: 質問へ適用する版を基準日・施行日・優先規則で一意に解決できない。

質問と無関係な実務条件はfactorをtrueにしない。たとえば家賃要件だけを聞く質問で、住居届の提出状況は`requires_case_facts`にしない。

最終ラベルはproductionの`classification-decision-v1`と同じ順序で導出する。

```text
case facts / policy judgment / version conflictが一つでもtrue -> 判断要
上記がfalseで、retrievalまたはsupportがfalse              -> 文書不足
それ以外                                                   -> 根拠十分
```

## 4. 要確認の4ケース

benchmarkは現在`draft`であり、次の4ケースをモデル比較前に確定する必要がある。

| Case | 現在の案 | 確認する境界 |
|---|---|---|
| `CPD-T05` | `requires_case_facts=true` | 職員事情の不足として扱うか、裁量判断もtrueとするか |
| `REG-Q046` | `requires_policy_judgment=true` | 「確認先はどこか」への回答だけで根拠十分とするか、控除額の正否が未解決として判断要とするか |
| `REG-Q086` | `requires_case_facts=true` | 「必ず一括か」への一般回答だけで根拠十分とするか、返納方法を決める職員事情が不足すると扱うか |
| `REG-Q316` | `requires_policy_judgment=true` | 「期限後も受付可能か」への回答だけで根拠十分とするか、その後の認定・支給時期まで判断要とするか |

`REG-Q046`、`REG-Q086`、`REG-Q316`は既存の最終ラベルでは`判断要`としてユーザー確認済みだが、5 factorのどれに対応させるかと、質問の回答範囲を明文化するために再確認する。

## 5. 評価段階

### Stage A: 小benchmark

- 現行Gemini、Jev 5 Noul、多言語NLIへ同じ34入力を渡す。
- factor別Precision・Recall・F1、最終ラベルmacro F1、重大誤分類を測る。
- `判断要`または`文書不足`を`根拠十分`へ変える誤りを重大誤分類とする。
- API errorと分類誤りを分ける。
- latency、token、推定費用、local memoryも保存する。

### Stage B: 保存済み130件

Stage Aで現行Geminiを上回る可能性がある候補だけを適用する。130件にはfactor goldがないため、ここでは最終ラベルと総合回答成功を測る。全候補を130件実行しない。

## 6. 採用gate

- Stage Aで重大誤分類を現行Geminiより増やさない。
- Stage Bで現在の分類正解116/130を1件以上改善する。
- 現在正しい`判断要`・`文書不足`から`根拠十分`への退行は0件。
- 総合回答成功112/130を1件以上改善する。
- 同率なら、費用・遅延・失敗率を明確に改善しない限り現行Geminiを維持する。

## 7. 再生成と検証

```bash
.venv/bin/python -m eval.build_classifier_model_benchmark
.venv/bin/python -m eval.validate_classifier_model_benchmark \
  eval/classifier_model_benchmark_v1.json
.venv/bin/python -m pytest -q tests/test_classifier_model_benchmark_validation.py
```

builderは既存14ケースと保存済みretrieved-evidence回帰を読み、APIを呼ばずにbenchmarkを再生成する。保存済みTop-8が一致しない場合は停止する。datasetには入力元のSHA-256を記録している。
