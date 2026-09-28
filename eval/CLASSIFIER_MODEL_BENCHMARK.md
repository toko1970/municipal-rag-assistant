# 分類器モデル比較benchmark

## 1. 目的

Gemini、Jev、多言語NLIを、同じ質問・取得根拠・生成回答で比較する。RetrievalとGeneratorを固定し、分類器だけの差を測る。モデルの実行前にfactor goldを固定し、結果を見てgoldを変更しない。

## 2. 構成

`classifier-model-benchmark-v1`はdevelopment専用の36ケースである。sealed holdoutではない。

| 項目 | 件数 |
|---|---:|
| 合計 | 36 |
| 根拠十分 | 21 |
| 判断要 | 9 |
| 文書不足 | 6 |
| Text | 27 |
| Visual | 9 |
| factor control | 22 |
| observed failure | 5 |
| hard negative | 9 |

factorのtrue件数は次のとおりである。

| factor | true | false |
|---|---:|---:|
| `retrieval_sufficient` | 30 | 6 |
| `answer_fully_supported` | 30 | 6 |
| `requires_case_facts` | 5 | 31 |
| `requires_policy_judgment` | 3 | 33 |
| `version_conflict` | 2 | 34 |

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

## 4. 回答範囲のadjudication結果

モデル比較前に、質問が直接求める命題で分類する規約をユーザーと確認し、次の4ケースを確定した。

| Case | 確定したfactor / label | 理由 |
|---|---|---|
| `CPD-T05` | case facts=true、policy=true、判断要 | 職員事情が不足し、事情を踏まえた決定にも所管判断が残る |
| `REG-Q046` | 全判断要因=false、根拠十分 | 確認先は文書から一意に答えられる |
| `REG-Q086` | 全判断要因=false、根拠十分 | 必ず一括ではないことを文書から答えられる |
| `REG-Q316` | 全判断要因=false、根拠十分 | 期限後の受付可否は文書から答えられる |

一括レビューでは同じ規約を残り30ケースにも適用し、Q006、Q076、Q176、Q301にも旧goldとの不整合を発見した。これらを含む4シナリオ20表現を500問評価セットv1.2で`根拠十分`へ訂正した。少数クラスを6件維持するため、明確な文書不足controlを2件追加した。全36ケースのfactor annotationを承認し、benchmarkを`approved`として固定した。これらはgold整備であり、モデルの改善件数に含めない。

## 5. 評価段階

### Stage A: 小benchmark

- 現行Geminiと多言語NLIへ同じ36入力を渡す。
- factor別Precision・Recall・F1、最終ラベルmacro F1、重大誤分類を測る。
- `判断要`または`文書不足`を`根拠十分`へ変える誤りを重大誤分類とする。
- API errorと分類誤りを分ける。
- latency、token、推定費用、local memoryも保存する。

read-only preflightの結果、公式Jevはearly accessかつ利用者のlabelへfitする提供形態で、36件だけを使うzero-shot比較を実行できないと判断した。公開OpenJevもlocal環境との互換性とresource条件からこのroundでは保留する。詳細は[`CLASSIFIER_MODEL_PREFLIGHT.md`](CLASSIFIER_MODEL_PREFLIGHT.md)を参照する。

### Stage B: 保存済み130件

Stage Aで現行Geminiを上回る可能性がある候補だけを適用する。130件にはfactor goldがないため、ここでは最終ラベルと総合回答成功を測る。全候補を130件実行しない。

## 6. 採用gate

- Stage Aで重大誤分類を現行Geminiより増やさない。
- Stage Bでgold訂正後の分類正解121/130を1件以上改善する。
- 現在正しい`判断要`・`文書不足`から`根拠十分`への退行は0件。
- gold訂正後の総合回答成功117/130を1件以上改善する。
- 同率なら、費用・遅延・失敗率を明確に改善しない限り現行Geminiを維持する。

## 7. 再生成と検証

```bash
.venv/bin/python -m eval.build_classifier_model_benchmark
.venv/bin/python -m eval.validate_classifier_model_benchmark \
  eval/classifier_model_benchmark_v1.json
.venv/bin/python -m pytest -q tests/test_classifier_model_benchmark_validation.py
```

builderは既存14ケースと保存済みretrieved-evidence回帰を読み、APIを呼ばずにbenchmarkを再生成する。保存済みTop-8が一致しない場合は停止する。datasetには入力元のSHA-256を記録している。
