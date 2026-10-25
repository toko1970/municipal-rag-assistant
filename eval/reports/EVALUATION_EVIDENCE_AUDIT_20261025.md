# 評価比較の条件・公開証拠・再現できる範囲

- 確認日: 2026-10-25
- 基準コミット: `912f095130bfbd73bd9599cee25c6ff65bb91e75`
- 目的: 保存済み比較の数値、訂正、原資料の関係を追えるようにする。
- 今回の評価実行: LLM/Embedding API 0回。sealed gold、custodian原票、未開封のpaired予測を読まない。
- 新しいツール: [`audit_public_evaluation.py`](../audit_public_evaluation.py)。当時の生成runner・judgeの復元ではない。

## 1. 完了した範囲と制約

公開されている130ケース回帰・80表現challenge・44件モデル比較のaggregateについて、分子・分母、paired内訳、既存の限定訂正の算術を検査した。記載値との整合を確認したが、**回答・採点原票からのケース別再集計ではない**。同じ数値になる人工的なケース表は作成していない。

基準コミットの対象ディレクトリ、取り込んだGit履歴の指定パス、今回の作業領域を確認したところ、以下の原資料は見つからなかった。制作者のMacや未共有の保管場所にも存在しないという意味ではない。必要な原回答が回収されるまで、H03aの同一規約再採点とH04の完全再現は**資料不足**として残す。

## 2. 最新比較の条件と指標

### A. モデル比較（予約44表現）

| 項目 | 確認できた内容 |
|---|---|
| 評価ID・目的 | `model-tier-flash-vs-current-flash-lite-confirmation-test-20261019`。一回生成モデルの確認比較 |
| baseline / candidate経路 | 共通の`src.rag_chain.build_prompt`による自然文一回生成。独立分類器・検索は含まない |
| model / prompt版 | baseline `gemini-3.1-flash-lite`、candidate `gemini-3.8-flash`。prompt builder SHA `8b68aab88db7e01141fe9f245cc080924d7a4340d24d854152bdecd0a0c0b408`。温度0、上限1,024 tokens |
| データ集合・粒度 | 90件ブックの予約test分割、44表現・22シナリオ群、根拠固定。現在は開封済み |
| 規約・採点者 | `rag_refusal_evaluation_spec.md`と承認済みブック基準。原回答本文の手動採点と記録されるが、予約44件の初回判定者区分は公開artifactでは未確認。一部ユーザーレビューを別記。独立した全件二次レビューなし |
| 主指標・原値 | M3＋M4。Flash32/44、Lite37/44。シナリオ群はFlashのみ1、Liteのみ3、双方12、双方不成功6 |
| 訂正状態 | ユーザーによるFlash側3件だけの訂正で35/44、成功シナリオ群14/22。Lite37/44、15/22は未訂正。同規約・両側再採点は未完了 |
| 用途と限界 | 当時のモデル選択の記録。部分訂正後の差から厳密な公平比較・安全性優越を確定しない。新候補の調整・選定には再利用しない |
| 原資料 | [原レポート](../results/model_tier_test_confirmation_20261019/report.md) · [原manifest](../results/model_tier_test_confirmation_20261019/run_manifest.json) · [ユーザー訂正と選定](GENERATION_MODEL_SELECTION_20261019.md) |

分母の違いは、FlashのX016-T0とX016-T1を`REVIEW_REQUIRED`として項目別採点から除外したためである。原レポートでは両方が出力上限付近で不完全とされる。全体成功率の分母44からは除外していない。

| 指標の分母 | Flash | Flash-Lite | 扱い |
|---|---:|---:|---|
| 全体成功 | 44 | 44 | REVIEW_REQUIREDも全体では成功に数えない |
| A1 / M3 / M2 | 31 | 32 | Flash側でA1を1件保留判定 |
| A2/A3 / M4 / M1 | 11 | 12 | Flash側で保留対象を1件保留判定 |
| G1 | 42 | 44 | 採点可能な出力のみ。除外された2件の安全性を確認した意味ではない |
| REVIEW_REQUIRED | 2/44 | 0/44 | 評価不能・出力不完全を別記 |

Flash側の訂正は、X014-T0・X026-T0のM3加算、X014-T1のM4加算として集計された。X014-T0の不足条件の解釈をFlash-Liteにも適用する必要がある。X026-T3は両側G1とされた一方、「原則」を問う質問の読み方に曖昧さが残る。原票未取得のため、ここで分類や分母を都合よく変更せず、訂正後の同規約スコアは未算出とする。

### B. 130ケース統合回帰

| 項目 | 確認できた内容 |
|---|---|
| 評価ID・目的 | `freeform-integration-regression-20261024-01`。一回生成候補の統合回帰 |
| baseline経路 | **未確認**。元runner・原回答がなく、manifestの名称だけから従来の多段`production`とは断定できない |
| candidate経路 | 一回生成candidate。実行時の`src/simple_rag_flow.py`等のhashはmanifestに記録 |
| model / prompt版 | generator/judge `gemini-3.8-flash`、温度0、各2,048 tokens。candidate prompt SHA `cae1bafc46a98a30670f6e32c79508514a25580d80ba8f2a5d370e63a786ac0d`。baseline prompt版は未確認 |
| データ集合・粒度 | `formal_100`100ケース＋`visual_development_30`30ケース。独立シナリオ数は未確認。live設定のQdrant検索と保存contextの一致130/130という実行記録 |
| 規約・採点者 | Gemini 3.8 Flash judgeの暫定machine composite。judge prompt・詳細な規約版は未取得 |
| 指標・paired | 候補129/130、baseline125/130。候補のみ4、baselineのみ0、双方125、双方失敗1。図表30件では候補のみ4、双方26 |
| 訂正状態 | 公開scorecardの原機械集計。ケース原回答の人手確認は再現できていない |
| 用途と限界 | 開発回帰の暫定値。名称が同じ130問でも初期117→120とは構成・採点条件をそろえた比較ではない |
| 原資料 | [REPORT](../results/autoresearch/freeform-integration-regression-20261024-01/REPORT.md) · [scorecard](../results/autoresearch/freeform-integration-regression-20261024-01/scorecard.json) · [manifest](../results/autoresearch/freeform-integration-regression-20261024-01/run_manifest.json) |

改善ケースIDはVD014・VD016・VD019・VD024と記録されている。質問・根拠ID・両回答・judge理由の入った`answer_diff_review.csv`が未取得のため、ID一覧をケース別検証の証拠として代用しない。

### C. 80表現challenge

| 項目 | 確認できた内容 |
|---|---|
| 評価ID・目的 | `challenge-freeform-20261024-01`。一回生成promptだけを変更した比較 |
| baseline / candidate経路 | 元の一回生成prompt / 図表の備考・複数事項の回答を明示した一回生成prompt |
| model / prompt版 | 両側generatorとjudgeは`gemini-3.8-flash`、温度0、各2,048 tokens。baseline SHA `c585af4e413531c3f32697a83aaec7cc16911d68ec24f9edfee7906cceb83156`、candidate SHA `cae1bafc46a98a30670f6e32c79508514a25580d80ba8f2a5d370e63a786ac0d` |
| データ集合・粒度 | 手作成の40シナリオ・80表現、根拠固定。challenge packet hashはmanifestに記録 |
| 規約・採点者 | Gemini 3.8 Flashによる盲検ペアjudgeの暫定採点。judge promptは未取得。ユーザーによる限定レビューを別記 |
| 原指標 | 機械成功: candidate77/80、baseline76/80。シナリオ: 候補のみ1、baselineのみ1、双方37、双方不成功1 |
| 訂正後の参考値 | CH-I07-F/Pの両側failをsuccessへ訂正し79/80対78/80。シナリオ: 候補のみ1（CH-D05）、baselineのみ1（CH-D06）、双方38、双方不成功0 |
| 用途と限界 | prompt比較であり、多段経路から一回生成への効果ではない。全80件の人手再採点でも実利用分布の精度でもない。原機械集計を維持 |
| 原資料 | [評価](../results/autoresearch/challenge-freeform-20261024-01/evaluation.md) · [scorecard](../results/autoresearch/challenge-freeform-20261024-01/scorecard.json) · [manifest](../results/autoresearch/challenge-freeform-20261024-01/run_manifest.json) · [限定訂正](../results/autoresearch/challenge-freeform-20261024-01/human_review_adjudication.md) |

CH-D05は食堂の定休日を確認できない際の説明・確認案内の改善、CH-D06-Pは人事課への確認案内の欠落である。CH-D06-Pはユーザーが軽微・非ブロッカーと判断したが、スコア上の退行を消していない。両回答全文とjudge理由の原記録は未取得。

### D. Candidate fresh holdout

| 項目 | 確認できた内容 |
|---|---|
| 評価ID・目的 | `freeform-fresh-holdout-20261024-01`。固定候補の独立した受入評価 |
| baseline / candidate経路 | baselineなし、candidate一回生成＋検索。初回83/100とのpaired比較ではない |
| model / prompt版 | `gemini-3.8-flash`、温度0、2,048 tokens、candidate prompt SHAはB/Cと同じ。コード・contextの同一性は別にmanifestで確認する |
| データ集合・粒度 | 50シナリオ・100表現。独立Qdrant、Top-8、Gemini Embedding、検索込み |
| 規約・採点者 | 公開評価表の事前閾値。custodian採点とユーザーによるG1 flag極性の訂正。非公開原票は今回対象外 |
| 主指標・副指標 | 総合76/100（閾値95%）、分類macro F1 0.7691（0.80）、根拠hit@5 69/80（90%）、hit@3 62/80（80%）、stability35/50 |
| 訂正状態 | 重大な根拠外断定0/100・ゲートPass。冒頭の古いFail記述のみ表に一致させた。総合No-goを維持 |
| 用途と限界 | 消費済み受入結果。再調整・再評価へ再利用しない。summaryのsuccess_count=100はAPI生成完了数であり品質成功76とは異なる |
| 原資料 | [公開評価](../results/autoresearch/freeform-fresh-holdout-20261024-01/FRESH_HOLDOUT_EVALUATION.md) · [公開run manifest](../results/autoresearch/freeform-fresh-holdout-20261024-01/run_manifest.json) |

### E. Paired relative holdoutと導入判断の直接比較

| 評価 | 条件・確認できたこと | 指標・未確認範囲 |
|---|---|---|
| `freeform-paired-relative-20261024-01` | 50シナリオ100表現、両側Gemini 3.8 Flash・温度0・2,048 tokens、同じ検索context。baseline `src.rag_chain.py` prompt、candidate上記SHA。公開manifestとsummaryは予測凍結・gold未開封 | **品質値なし**。200応答や100完了pairから成功率を作らない。原予測・gold・採点packetには今回アクセスしない。[公開summary](../results/autoresearch/freeform-paired-relative-20261024-01/summary.json) · [公開manifest](../results/autoresearch/freeform-paired-relative-20261024-01/run_manifest.json) |
| `freeform-production-rollout-20261025`の直接比較 | 当時のdecisionは「従来公開経路とcandidate、130問と80表現の直接比較をユーザーが確認」と記録。実行コード、model、promptの対応と採点原票は未確認 | 各集合のM3で候補のみ成功5・従来のみ0、80表現Q4で候補のみ7・従来のみ1と記録。M3/Q4の該当母数、双方成功・双方失敗、規約版は未確認。B/Cのmachine compositeへ置換しない。[当時のdecision](../results/autoresearch/freeform-production-rollout-20261025/decision.md) |

## 3. 原資料の所在と回収に必要なもの

| 対象 | 公開・利用可能 | この作業領域と取得履歴で未発見 | 未完了になること |
|---|---|---|---|
| モデル予約44件 | report、manifest、選定記録の3件訂正 | `model_tier_test_confirmation_20261019/test_cases.jsonl`、`records.jsonl`、`judgments.jsonl`、`metrics.json`。承認済みブックの匿名化した対象44件・規約・訂正履歴 | 両側の同規約再採点、境界X014-T0/T1・X026-T0/T3の再確認 |
| モデル開発46件 | 2つのreportとmanifest | `model_tier_compare_20261019/development_cases.jsonl`、同`records.jsonl`、`model_tier_compare_flash_lite_20261019/records.jsonl`、`eval/run_model_tier_context_fixed.py` | 開発比較の回答原文監査と当時runnerの再実行 |
| 130統合回帰 | REPORT、scorecard、manifest | `eval/run_freeform_integration_regression.py`、同runの`answer_diff_review.csv`、両側回答・judge記録。manifestが参照する`simple_generation_e2e_20261019/`の5原資料 | baseline経路特定、VD014/016/019/024原回答確認、原票再集計 |
| 80challenge | evaluation、scorecard、manifest、限定訂正 | 同runの`records.jsonl`、hashに対応するchallenge packet、judge prompt・採点コード | 質問・根拠ID・両回答・理由をそろえたケース別再集計 |
| M3/Q4直接比較 | 導入decision | 130問・80表現それぞれの実行設定、両回答、匿名化採点表、指標別母数 | 導入判断の原票再現と他の比較との対応付け |

130回帰が参照する5資料は`final_run_manifest.json`、`practitioner_review.csv`、`practitioner_approved_review_draft.csv`、`retrieved_contexts.jsonl`、`visual_corrected_v1/records.jsonl`である。hashは[回帰manifest](../results/autoresearch/freeform-integration-regression-20261024-01/run_manifest.json)を正とし、回収時に一致を確認する。当時runnerのSHAは`6fda7b7bf04a67472a094222b4bde4672296f4997225029093adf7ba1a4be115`。今回の監査ツールとは別物である。

私有の採点ブックは、氏名・不要な個人情報を取り除いた対象分割と必要な規約だけでよい。公開custodian資料の取得や未開封holdoutの開封は回収対象に含めない。

### ローカル資料の追加探索（2026-10-25）

ユーザーからローカルフォルダ内に資料がある旨の指示を受け、アクセス可能な作業フォルダ、添付領域、別のレビュー用コピーを追加確認した。ignoredな通常ファイルも対象にしたが、上表の原票・元runner・承認ブックは新たに回収できなかった。ユーザー端末の元プロジェクトフォルダはこの実行環境に接続されておらず、端末内の不存在を確認したものではない。

90件の採点者確認に必要な別資料として、[2026-10-17の評価履歴](PORTFOLIO_EVALUATION_AND_IMPROVEMENT_HISTORY_20261017.md#参照資料)には「実務経験者回答レビュー用_90件統合版.xlsx」が明記されている。同書は実務者名を含むためリポジトリ外保管とされており、本体は未取得。この90件の採点ブックと、モデル比較44件の原回答・原採点を同一資料とは扱わない。公開済みの判断・分担記録から追加確認できた範囲は[制作者の関与](../../portfolio/01-ui.md#制作者の関与とai支援)へ反映した。

## 4. 外部APIなしでできる確認

リポジトリルートから次を実行する。

```bash
python -m eval.audit_public_evaluation
python -m pytest -q tests/test_public_evaluation_audit.py
```

監査は指定済みの公開7ファイルだけを読む。再帰探索、API呼出し、DB更新、judgeの再実行は行わない。結果の`AGGREGATE_CONSISTENT`は算術が整合したという意味で、回答品質の合格ではない。`case_level_reproduction=false`、`same_rubric_rescoring_complete=false`を出力する。

結果を保存する場合は新しいパスを指定する。既存ファイルがあれば非ゼロで停止し、上書きしない。

```bash
python -m eval.audit_public_evaluation --output /tmp/municipal-rag-public-audit-new.json
```

今回の保存結果: [公開aggregate監査結果](../results/public_evidence_audit_20261025/audit.json)。入力ファイルのSHA-256、原機械集計、限定訂正の出典を含む。訂正の算術は130回帰129/125、challenge77/76から79/78、モデルFlash32から35と一致した。ケース別スコアの復元や新しい人手採点は実施していない。

非APIテストでは、分母不一致、paired総数不一致、改善IDの重複、部分集合不一致、不正な数値型、二重訂正、REVIEW_REQUIREDの除外、訂正出典のhash変更、既存出力の保護を確認した。今回の対象テストは13件（追加subtest 4件）成功、変更PythonのRuffも成功。これは評価値の算術検査・失敗経路の検証であり、回答本文の品質検証ではない。

## 5. 原回答の回収後に進めること

同規約再採点は、新しいモデル呼出しをせず保存回答だけで実施できる。先にX014-T0/T1・X026-T0/T3について質問の範囲、提示根拠、期待対応、G1の定義を本人と確認する。その規約を両モデルへ同じように適用し、可能な範囲でモデル名を伏せる。原票を保持し、別ディレクトリに旧判定・新判定・理由・規約版・判定者区分を記録する。44件を新候補の調整や再選定に使わない。

生成からの再実行は別作業である。現時点では元runner・judge規約・入力が未回収のため、存在しない実行コマンドは掲載しない。必要なものがそろっても、過去の予算・許可を自動的に引き継いでAPIを実行しない。

| 再実行準備 | 130ケース回帰 | 80表現challenge |
|---|---|---|
| 前提 | baseline経路、原入力・原回答・judge規約を確定 | challenge packetとjudge規約を確定 |
| 環境 | Python 3.11、固定依存、使い捨てPostgreSQL/Qdrant、対象文書snapshot | Python 3.11、固定依存、保存contextのみ |
| 比較条件 | 両経路のコード・設定を凍結。model/top-k/context条件を記録 | 同一Flash model、温度0、2,048 tokens、prompt以外を固定 |
| 呼出し数の見積り（未承認） | **上限未設定。baseline経路を確定するまで実行不可。** 両側を一回生成と仮定すれば生成260＋ペアjudge130＝390だが、これは算術例であり上限ではない。独立分類・版解決等の呼出しとEmbeddingを含む全量を確定後に予約する | 両側160＋ペアjudge80＝240を計画。Embeddingなし |
| retry計画 | 自動retry 0。障害を記録して停止し、継続は別run | 自動retry 0。障害を記録して停止し、継続は別run |
| 費用 | 現時点の承認額0。回収後、入力token上限と公式単価から予約見積もりを作り、有限予算の許可を得てから開始 | 同左 |
| 出力 | 新run ID。凍結した旧runは上書きしない | 同左 |
| 停止 | 入力hash不一致、未確定規約、予算予約超過、providerエラー。未完了を成功扱いしない | 同左 |

この表は既存比較の再現準備で、新しい改善候補の実験ではない。既存[採用プロトコル](../INTERVENTION_ADOPTION_PROTOCOL.md)の閾値やNo-goを変更しない。
