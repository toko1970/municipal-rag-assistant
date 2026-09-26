# RAGテスト・評価戦略

## 1. 目的

通常のcode regressionと、API費用を伴うRAG品質評価を分離する。CIは決定的なtestを毎回実行し、実検索・生成評価は条件を固定した明示実行にする。

## 2. Test pyramid

### 2.1 CIで毎回実行するtest

- lint、format、type check
- 同一run内の決定的ID、抽出世代切替、施行期間、版競合、chunk境界、classification mappingのunit test
- answer/classifier JSON Schema test
- 金額claimの省略、本文だけの期限、claim不一致を構造上生成できず、根拠付きclaimと事実主張のない固定案内だけを許可するanswer rendering test
- `requires_case_facts=true`、不足条件あり、検索不足の各factorから、最終ラベルと表示templateが必ず一致するcross-stage test
- fixture manifestとevaluation manifestのhash・参照整合性
- fake repositoryを使うquery flow test
- 同一scenarioの言い換えがsplitをまたがない検査

外部API、Cloud SQL、Qdrant Cloudは通常CIから呼ばない。

### 2.2 ローカルintegration test

DockerのPostgreSQLとQdrant、架空fixtureを使う。

- migrationのforward実行とclean DB再構築
- outboxのat-least-once処理と冪等upsert
- PostgreSQL commit直後、Qdrant upsert直前・直後、Qdrant generation activation前後、PostgreSQL active run切替前後、全indexのalias切替前後の障害注入
- 同一原本・同一idempotency keyを2回実行した重複0件
- withdrawal・抽出世代切替・再index・空collectionからの再構築
- request、retrieval、generation、feedbackのFKとSQL集計
- Qdrantが`QUERYABLE`でないpointの除外と、PostgreSQLが`READY + PUBLISHED`でない版・active run不一致の除外
- active runがある再抽出中・再抽出失敗時も旧runが検索でき、activation後だけ新runへ切り替わること
- 同じlocatorを持つ2つの抽出runを同時保存でき、active runを切り替えられるmigration-level test
- 旧世代pointが上位を占めてもoverfetch/refillにより、有効候補が5件以上あれば5件を返すこと

### 2.3 Extraction fixture test

架空fixtureはdevelopmentとholdoutで文書familyが重ならないよう、各必須図表に最低2 familyを用意する。少なくとも次を含む。

1. 申請処理フローチャート
2. 支給可否判断フロー
3. 期限タイムライン
4. 支給額・区分表
5. 申請書記入例
6. 改定前後比較
7. native text PDF
8. 日本語scan PDF
9. 回転ページ
10. 曖昧な矢印または低品質scan

期待値はページ、bbox、全文、表セル、node、edge、field、施行日をJSONで持つ。重要値の完全一致、必須要素のrecall、bbox intersection-over-unionを測る。初期gateは、重要値完全一致100%、必須要素recall 95%以上、bbox IoU 0.80以上とする。曖昧fixtureは誤って合格させず`REVIEW_REQUIRED`になることを確認する。detectorの出力順、bbox、要素数を変えた再抽出で、新runへ一括切替され旧runの要素・asset・pointが検索不能になるtestを含める。

## 3. RAG評価set

| Set | 用途 | 調整への利用 |
|---|---|---|
| 既存100 scenario / 500表現 v1.0 | text regressionと失敗分析 | 利用可。既に開発setである |
| 図表development 30 | PDF・図表実装とparameter調整 | 利用可 |
| 図表sealed holdout 20 | 最終受入 | 質問文だけ実行可。goldは結果確定まで利用不可 |

splitはscenario単位とし、同じ答え・根拠・文書版を共有する派生質問は同じsplitへ置く。ユーザーをgold custodianとし、質問文とgoldのSHA-256だけをrepositoryへcommitする。gold本体はcommit対象外のローカルartifactへ保存し、候補・run ID・予測結果を固定してから開封する。開封日時とhash一致をrun manifestへ記録し、開封後はそのsetを再びsealed扱いにせず次版のholdoutを作る。実装後に不具合を発見しても、holdoutを削除せず失敗として残す。

holdout 20件は事前に次の構成へ固定する。

- 図表: 処理flow 4、判断flow 4、表4、帳票3、timeline 2、改定比較3
- 期待分類: 根拠十分12、判断要4、文書不足4
- 難度: direct 6、複数要素6、境界・改定4、言い換え・誤字4
- 文書family: developmentと重複0

20件では区分別の推定幅が大きいため、区分別は件数とWilson 95% intervalを併記し、合否は事前定義した全体指標と重大誤り0件で判断する。

## 4. 評価軸

### 4.1 検索

- answerable質問だけを分母にしたevidence hit@3 / hit@5
- document、version、page、visual assetの各hit率
- multi-document質問で必要根拠がすべて揃う率
- 表現5種類間のscenario安定性

### 4.2 回答とgrounding

- expected answer keyに対する内容正解
- claimごとのevidence entailment
- 金額、日付、期限、要件、可否の根拠なし断定件数
- 引用したelement、page、bboxの正しさ
- flow path、table cell、form fieldの正答率

内容評価は設定名を伏せた人手判定を正とする。LLM evaluatorを補助に使う場合は、人手sampleとの一致率を別に示す。

### 4.3 分類

- `根拠十分`、`判断要`、`文書不足`のprecision、recall、F1、macro F1
- factorごとの一致率
- oracle evidence入力とretrieved evidence入力の差
- low confidence、fallback、API errorの件数

`expected_corpus_answerability`は評価harnessがgold annotationから設定し、分類器出力とオンラインログには含めない。oracle evidenceで誤る場合は分類失敗、oracleでは正しくretrieved evidenceで誤る場合は検索または根拠不足として扱う。

### 4.4 非機能

- p50 / p95 response latency
- query、document ingestionごとのtokenと推定・実費
- API error、retry、rate limit件数
- 日次利用上限と月額estimate

end-to-end success率は全attemptを分母にし、retryで成功した質問も成功に含めるが、retry分のlatency、token、costをすべて加算する。品質指標は成功回答だけを分母にして別表示する。

## 5. Experiment contract

各runは次を固定する。

- git commit
- evaluation setとdocument snapshotのversion・SHA-256
- chunk schema、parser/OCR/model/prompt version
- embedding provider、model、dimensions、prefix
- Qdrant collection、distance、sparse vocabulary、RRF設定、top-k
- generation/classifier model、temperature、JSON Schema、prompt
- 実行日時、region、件数、error、tokens、cost、latency

変更要因を一つだけ変え、raw resultsを保存する。`文書不足`質問をretrieval failureの分母へ含めず、API errorを不正解へ混ぜず別件数で示す。

## 6. Release gate

公開候補は[`IMPLEMENTATION_PLAN.md`](IMPLEMENTATION_PLAN.md)のDefinition of Doneを満たし、次を追加確認する。ここでstagingとは、Cloud上に常設環境を増やさず、ローカルDockerの専用DB schema、専用Qdrant collection、一時GCS相当directoryを使うintegration環境を指す。cloud固有の接続はPhase 0の短時間spikeとdeploy後の非公開revisionで確認する。

- high severityのsecurity findingが0件
- migrationとrollback手順がstagingで成功
- PostgreSQL backup restoreとQdrant rebuildが成功
- public UIのrate limit、文字数、非公開asset accessが確認済み
- 10並列requestでもsession 5件/日・global 50件/日の予約を超過せず、kill switch後に新規外部API callが0件
- 同一sessionのfeedbackは1回答1件に制限され、10件/日・global 200件/日を並列送信でも超えず、別sessionから他者のrequestへ登録できない
- READMEの数値が対応するmanifestとraw resultへ辿れる

閾値未達時は「未達の実測結果」として残す。機能を完成扱いにするかは数値を書き換えず、公開範囲を縮小するdecisionとして記録する。
