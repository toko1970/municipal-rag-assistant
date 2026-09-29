# 回答分類モデル比較

## 1. 目的

RetrievalとGeneratorを固定し、回答分類器だけを変えたときの品質、費用、速度、実行可能性を
比較する。対象は承認済みdevelopment benchmark 36件で、sealed holdoutではない。

評価前に5 factorのgoldと日本語仮説を固定し、結果を見て変更していない。比較後の閾値調整も
行っていない。

## 2. 比較対象

| 候補 | 入力 | 結果 |
|---|---|---|
| Gemini 3.1 Flash-Lite | 現行production prompt、Top-8を含む全根拠 | 完走 |
| mDeBERTa-v3-base multilingual NLI | 同じ全根拠をpremise化 | 512 token制限で推論前停止 |
| BGE-M3 zero-shot v2.0-c | 同じ全根拠をpremise化 | 完走 |

公式Jevはearly accessかつlabel fit型で、一般公開API・価格と独立した学習用annotationを
用意できないため、このroundでは実行していない。OpenJevも日本語適性、local dependency、
8GB環境の費用対効果から除外した。

BGE-M3には、商用利用向けデータだけで学習した`-c`版を使用した。model cardは多言語用途と
最大8192 tokenを案内している。model configは8194 positionsだがtokenizer metadataは512の
ため、最長886 tokenの1 pairを先に実行し、index errorがないことを確認してから180 pairへ
進んだ。

## 3. 結果

| 指標 | Gemini 3.1 Flash-Lite | BGE-M3 zero-shot v2.0-c |
|---|---:|---:|
| 最終ラベル正解 | **31 / 36** | 6 / 36 |
| 最終ラベルaccuracy | **0.861** | 0.167 |
| 最終ラベルmacro F1 | **0.862** | 0.153 |
| 5 factor完全一致 | **26 / 36** | 4 / 36 |
| 重大誤分類 | 0 | 0 |
| 外部API call | 36 | 0 |
| retry / API error | 0 / 0 | 対象外 |
| 推定外部費用 | US$0.0110875 | US$0 |
| 推論時間 | 203.88秒 | 94.13秒 |
| 1件または1 pair平均 | 5.66秒 / case | 0.523秒 / pair |
| local peak RSS | 対象外 | 約1.85 GiB |

重大誤分類は、goldが`判断要`または`文書不足`なのに`根拠十分`と返すケースである。
BGE-M3が0件なのは高精度だからではなく、`根拠十分`を一度も予測しなかったためである。
安全側の誤りだけを見ず、macro F1とクラス別件数を併記する必要がある。

### Factor別F1

| factor | Gemini | BGE-M3 |
|---|---:|---:|
| `retrieval_sufficient` | **0.929** | 0.286 |
| `answer_fully_supported` | **0.947** | 0.000 |
| `requires_case_facts` | **0.714** | 0.000 |
| `requires_policy_judgment` | **0.667** | 0.000 |
| `version_conflict` | 0.000 | **0.267** |

Geminiは31件を正解したが、誤り5件はすべて`判断要`への過剰判定だった。特に
`version_conflict`は真の競合2件を両方見逃し、偽陽性3件を出した。これは既に導入した
専用Version Resolverが対象にしている弱点と整合する。

BGE-M3は`answer_fully_supported`、`requires_case_facts`、
`requires_policy_judgment`の正例を一つも検出できず、`version_conflict`は真の2件を拾う一方で
偽陽性11件だった。一般NLIのentailmentを、制度文書RAGの5つの判定責務へzero-shotで直接写像
する方法は、この入力契約では成立しなかった。

## 4. 採用判断

現行Geminiを維持する。BGE-M3は速度、local実行、外部API費用では有利だが、採用gateの
「Geminiより重大誤分類を増やさない」に加え、モデル候補として必要な品質を満たさない。
Stage Bの保存済み130問へ適用しても改善が見込めないため実行しない。

mDeBERTaをTop-4だけで評価する案も採用しない。全ケースは512 token以内になるが、6件では
生成claimが5位以下の根拠も参照しており、入力を短縮すると分類器以外の条件まで変わる。

## 5. 学べる設計判断

- モデル比較では、モデル名だけでなく入力長とtokenizer/model configの整合も確認する。
- local modelは費用と速度で有利でも、日本語、業務定義、出力責務が合わなければ置換できない。
- 「危険な誤判定が0件」だけでは、全件を保守側へ倒すモデルを高評価してしまう。
- 5 factorを一つの汎用NLIへ置換するより、観測済みの弱点だけを専用resolverで補う方が、
  少ない変更で総合成功率へつながる。
- 比較用benchmarkで閾値や仮説を調整すると同じデータへ過適合する。次にlocal classifierを
  改善するなら、独立したtraining/calibration splitが必要である。

## 6. 証拠

- Gemini: [`results/classifier_model_gemini_baseline_v1/evaluation.json`](results/classifier_model_gemini_baseline_v1/evaluation.json)
- BGE-M3 token audit: [`results/classifier_model_bge_m3_preflight_v1/token_audit.json`](results/classifier_model_bge_m3_preflight_v1/token_audit.json)
- BGE-M3 1 pair smoke: [`results/classifier_model_bge_m3_preflight_v1/single_pair_smoke.json`](results/classifier_model_bge_m3_preflight_v1/single_pair_smoke.json)
- BGE-M3 evaluation: [`results/classifier_model_bge_m3_preflight_v1/evaluation.json`](results/classifier_model_bge_m3_preflight_v1/evaluation.json)
- mDeBERTa token audit: [`results/classifier_model_mdeberta_pilot_v1/token_audit.json`](results/classifier_model_mdeberta_pilot_v1/token_audit.json)

外部API実行は最大36 call、retry 0、US$0.05を上限とした。実績は36 call、
US$0.0110875、error 0である。sealed holdout、production設定、reset creditは使用していない。
