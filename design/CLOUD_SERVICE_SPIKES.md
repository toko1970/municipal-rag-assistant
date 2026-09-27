# Cloud service connection / cost spikes

- 調査日: 2026-09-27
- 調査方式: read-only Research-to-artifact loop
- 対象: Cloud SQL for PostgreSQL、Cloud Storage、Qdrant Cloud、Gemini Developer API
- 対象リージョン: 既存Cloud Runに合わせて原則`asia-northeast1`
- 費用表記: USD、税・為替・契約別割引を含まない
- 現在の結論: **接続試験の実行前。4 serviceとも承認後の最小spikeが必要**

## 1. この文書が支える判断

Phase 0の最後に、各serviceの最小接続試験をどの順序・認証・費用上限・停止方法で行うかを判断する。このread-only調査ではresource作成、API有効化、権限変更、外部API呼出、課金設定を行わない。

受入条件は次のとおり。

1. serviceごとに接続先、認証、最小試験、費用発生条件、停止・削除方法が分かる。
2. repositoryとGoogle Cloudの観測事実を、公式文書から得た仕様や将来案と分ける。
3. 無料の確認と、承認が必要なresource作成・API呼出を分ける。
4. 未確認事項を実装済み・接続済みとして扱わない。

## 2. Loop run record

- 使用loop: [The research-to-artifact loop](https://signals.forwardfuture.com/loop-library/loops/research-to-artifact-loop/)
- 公開・更新日: 2026-06-22
- catalog record digest: `bbe159f974d972c26073aa441b613eb592a64ea1d30bb4f223788d390e5e6dbc`
- 対象artifact: この文書
- 有限範囲: 4 service、最大2 research pass
- 停止条件: 受入条件を満たす、重要な不確実性を明示する、またはresource作成・課金・外部API呼出の承認境界に達する
- 実行結果: **Success（read-only artifact）**。実接続spikeは`APPROVAL_REQUIRED`

## 3. 現状の観測

### 3.1 Repository

- 現行アプリはChromaをローカル永続化し、ログとfeedbackをJSONLへ保存する。Qdrant、PostgreSQL、Cloud Storageのclient依存と接続コードはまだない。
- `config.py`の現行回答モデルは`gemini-2.5-flash`、Embeddingは`gemini-embedding-001`である。
- 目標仕様はPostgreSQLを正本、Qdrantを再構築可能な検索index、Cloud Storageを原本・画像の保存先にする。分類器の基準候補は`gemini-3.1-flash-lite`である。
- `.env`の内容は読まず、変数名だけを確認した。存在したのは`GOOGLE_API_KEY`だけで、Qdrant・PostgreSQL・Cloud Storage用の変数はなかった。

### 3.2 Google Cloud（read-only）

| 観測対象 | 確認結果 | この結果から言える範囲 |
|---|---|---|
| Cloud Run | `municipal-rag-assistant`は`asia-northeast1`で、`municipal-rag-runtime` service accountを使用 | 現在の実行identityとregionを確認した |
| Gemini secret | Cloud Runの`GOOGLE_API_KEY`はSecret Managerの`gemini-api-key` version 1を参照 | secret参照は存在する。keyの種類・tier・現在のAPI疎通は未確認 |
| Cloud SQL | Cloud SQL Admin APIは無効。確認時のenable確認には`N`で応答され、変更なし | instanceの存在・接続・費用は未検証。repositoryにも接続実装はない |
| Cloud Storage API | 有効 | control planeへのread-only accessを確認した |
| 既存GCS | Terraform state bucketは東京、Cloud Build bucketはUS。合計使用量は72,788 bytes | 既存bucketは別責務であり、アプリ文書保存先には流用しない |
| Qdrant Cloud | endpoint、API key、client依存がrepositoryにない | accountやclusterが存在しないとは断定できない。今回のscopeからは接続不能 |

Terraform state bucketには非current versionを新しい版10件で削除するlifecycleがある。Cloud Run runtime service accountを対象にしたproject IAMのread-only照会は直接bindingを返さなかった。ただし、継承role、bucket単位IAM、custom roleまではこの結果だけで否定できない。

## 4. Service別の調査結果

### 4.1 Gemini Developer API

**状態: `READY_FOR_APPROVAL`（既存secret参照は`VERIFIED`、今回のAPI呼出は未実施）**

| 項目 | 方針・証拠 |
|---|---|
| 接続先 | 現行コードと同じGemini Developer API。Phase 0の最小試験は`gemini-3.1-flash-lite`を使用する |
| 認証 | Cloud RunではSecret Managerからkeyを環境変数へ渡す。Googleは2026年9月にstandard keyを拒否する移行方針を記載しているため、既存keyがservice accountに紐づくauthorization keyかを先に確認する |
| 最小試験 | 固定JSON Schemaへ1回だけ構造化出力させ、model名、input/output token、request ID、latency、概算費用を記録する。架空の短い入力だけを使う |
| 料金 | `gemini-3.1-flash-lite` Standard paid tierはtext input `$0.25 / 1M tokens`、output `$1.50 / 1M tokens`。Free tierはtoken料金なしだがquotaがある |
| 試験費用上限案 | 2,000 input tokens + 500 output tokensならlist price計算で約`$0.00125`。1回に固定し、想定外の再試行をしない |
| 継続費の例 | 100回を同じtoken量で実行すると約`$0.125`。tool利用やthinking tokenは別に増え得る |
| 停止 | 呼出を止め、必要ならkeyをrevokeする。Paid tierではAI Studioのproject spend capを設定候補にする |

Free tierとPaid tierでは、rate limitだけでなく送信内容の取扱いも異なる。評価や公開demoの運用判断では、価格だけでなくtierとデータ取扱いを記録する。

公式資料: [API key](https://ai.google.dev/gemini-api/docs/api-key)、[pricing](https://ai.google.dev/gemini-api/docs/pricing)、[billing and spend caps](https://ai.google.dev/gemini-api/docs/billing)

### 4.2 Cloud Storage

**状態: `READY_FOR_APPROVAL`（既存bucketのread-only確認は`VERIFIED`、アプリ用bucketは未作成）**

| 項目 | 方針・証拠 |
|---|---|
| 接続先 | アプリ原本・ページ画像専用のregional Standard bucketを`asia-northeast1`へ新設する。Terraform stateやCloud Build bucketは流用しない |
| 認証 | localはADC、Cloud Runはruntime service accountのADCを使う。鍵fileをrepositoryやcontainerへ置かない |
| 最小試験 | 小さな架空objectをgeneration precondition付きでuploadし、metadata・SHA-256を確認してdownloadし、同一性確認後にobjectと試験bucketを削除する |
| 権限 | 試験bucketだけに必要なobject read/write/delete権限を付ける。project全体の広いStorage Adminをruntimeへ付けない |
| 料金 | 公式ページで現在表示されたregional Standardの参考価格は`$0.000027397 / GiB-hour`（約`$0.02 / GiB-month`）。region selectorが動的なため東京の確定表示は作成直前に保存する。Class Aは`$0.005 / 1,000`、Class Bは`$0.0004 / 1,000` |
| 無料枠 | 5 GiB等のAlways Freeは`us-west1`、`us-central1`、`us-east1`だけで、東京には適用されない |
| 費用例 | 上の参考単価なら、1 GiB、Class A 1,000回、Class B 10,000回で概算`$0.029 / month` + data transfer・保持世代。実fixtureはこれより小さい見込み |
| 停止 | uploadを止め、必要なexport/hashを確認してobjectとbucketを削除する。soft delete、versioning、lifecycleにより削除後も保持費が残り得るため設定を記録する |

現在確認できた2 bucketの合計72,788 bytesは約0.000068 GiBで、storage単体の概算は月`$0.000002`未満である。これは操作回数、network、soft-deleted objectを含まないため、請求額の実測ではない。

公式資料: [authentication and ADC](https://docs.cloud.google.com/storage/docs/authentication)、[pricing and free tier](https://cloud.google.com/storage/pricing)、[object lifecycle](https://docs.cloud.google.com/storage/docs/lifecycle)、[delete buckets](https://docs.cloud.google.com/storage/docs/deleting-buckets)

### 4.3 Qdrant Cloud

**状態: `READY_FOR_APPROVAL`（account・cluster・疎通は未確認）**

| 項目 | 方針・証拠 |
|---|---|
| 接続先 | Phase 0はFree clusterを候補にする。Cloud Runからcluster endpointのRESTまたはgRPCへ接続する |
| 認証 | database API keyをSecret Managerへ保存し、期限とcollection scopeを設定する。Cloud Management Keyとdatabase API keyの用途を分ける |
| 最小試験 | `/readyz`、collection一覧、試験collection作成、少数vector upsert、filter付きsearch、試験collection削除を1回行う |
| Free cluster | card不要、1 node、1 GB RAM、0.5 vCPU、4 GB disk。未使用1週間でsuspend、4週間で削除される |
| 料金 | Free clusterは`$0`。StandardはCPU・memory・diskで決まり、構成とregionを選んでcalculatorで確定する |
| 継続採用条件 | 仕様の月3,000円上限以内で、demoの休止・再起動特性を許容できること。Free clusterの自動suspendは常時公開demoの初回latencyへ影響し得る |
| 停止 | database API keyをrevokeし、試験collectionまたはclusterを削除する。Free clusterの自動削除だけに依存せず、run recordへ削除確認を残す |

Free clusterは接続・filter・named vectorの学習には適する。一方でSLA、専用resource、高可用性を本番構成の証拠にはできない。

公式資料: [create a cluster and Free tier](https://qdrant.tech/documentation/cloud/create-cluster/)、[cluster access](https://qdrant.tech/documentation/cloud/cluster-access/)、[database API key](https://qdrant.tech/documentation/cloud/authentication/)、[billing](https://qdrant.tech/documentation/cloud-pricing-payments/)

### 4.4 Cloud SQL for PostgreSQL

**状態: `READY_FOR_APPROVAL`（API無効、instance・疎通・実費は未確認）**

| 項目 | 方針・証拠 |
|---|---|
| 接続先 | `asia-northeast1`のCloud SQL for PostgreSQL。Phase 0はzonal・shared-coreの最小構成を候補にし、本番相当HAとは区別する |
| 認証 | Cloud Run runtime service accountへCloud SQL Clientを与え、Cloud SQL Python ConnectorまたはAuth Proxyでautomatic IAM database authenticationを使う |
| 最小試験 | API有効化、試験instance/database/user作成、`SELECT 1`、架空rowのtransaction insert/read/delete、接続pool再利用を確認する |
| 料金構造 | instance CPU/memoryまたはshared-core、storage、backup、network、DNS等。shared-coreはinstance稼働秒数で課金され、SLA対象外 |
| 参考額 | 公式価格ページの現在表示される`db-f1-micro`は`$0.0105/hour`、730時間で約`$7.67/month` + storage等。ただし表示のregion選択は動的なため、東京・選択version・storageのcalculator quoteを承認直前に保存する |
| 最小試験費 | GoogleのCloud Run接続quickstartは迅速に完了すれば通常`$1`未満としている。Phase 0では`$1`を試験上限案とし、作成前に見積もりを再確認する |
| 一時停止 | activation policyを`NEVER`にするとinstance chargeを避けられる。storageやbackup等の残存費用をゼロとみなさない |
| 完全停止 | 必要なexportがないことを確認し、deletion protectionを解除して試験instanceを削除する。instanceとbackupが消えたことを再照会する |

最小shared-coreは接続方式とSQL永続化の学習用であり、IAM database authenticationの負荷により接続latencyやtimeoutが起き得る。公開demoの最終構成は実測後に別判断する。

公式資料: [pricing](https://cloud.google.com/sql/pricing)、[connect from Cloud Run](https://docs.cloud.google.com/sql/docs/postgres/connect-run)、[IAM database authentication](https://docs.cloud.google.com/sql/docs/postgres/iam-authentication)、[start and stop](https://docs.cloud.google.com/sql/docs/postgres/start-stop-restart-instance)、[delete instance](https://docs.cloud.google.com/sql/docs/postgres/delete-instance)

## 5. 環境別の認証境界

| 環境 | GCS / Cloud SQL | Qdrant / Gemini | 判断 |
|---|---|---|---|
| local | 開発者ADC。Cloud SQLはconnectorを介す | local `.env`。値はGit対象外 | 個人keyをcontainer imageへ埋め込まない |
| Cloud Run | `municipal-rag-runtime` service accountのADC | Secret Managerからruntimeへ注入 | runtimeへservice単位の最小権限を付ける |
| GitHub Actions | WIFのdeploy identity。Terraformのcontrol plane操作だけ | runtime secret値を取得させない | deployerとruntimeの権限を分離する |

## 6. 承認後の推奨実行順序

| 順序 | Spike | 理由 | 承認時に固定する上限 |
|---:|---|---|---|
| 1 | Gemini | 既存secret参照があり、1 requestで認証・token計測・構造化出力を確認できる | 1 request、概算`$0.01`未満 |
| 2 | GCS | Google Cloudの既存projectとregionを再利用でき、binary保存の責務を先に検証できる | 小object 1件、試験後削除 |
| 3 | Qdrant Cloud | Free clusterで検索APIとfilterを検証できるが、account/resource作成が必要 | Free clusterだけ、Standardへupgradeしない |
| 4 | Cloud SQL | 継続費とIAM・connector設定が最も重い | 作成前quote、試験費`$1`、試験後stopまたはdelete |

各spikeは一つずつ行い、次をrun recordへ残す。

- 実行日時、service、region、構成
- 認証方式と付与role。secret値は記録しない
- 実行した最小操作とresponseの非機密部分
- latency、token/operation数、見積費、後日確認した請求実績
- stop/delete操作と、再照会による停止確認

## 7. 残る不確実性

1. 既存Gemini keyの種類、Free/Paid tier、現在のquota、project spend capはread-only CLIから確認していない。
2. アプリ用GCS bucketはなく、runtime service accountによるobject round tripは未確認である。
3. Qdrant Cloud account、利用可能region、Free clusterのwake-up latencyは未確認である。
4. Cloud SQL Admin APIは無効で、東京の確定quote、instance、IAM login、継続費は未確認である。
5. 料金表は変更され得る。resource作成直前のconsole/calculator表示と、作成後のbilling reportを最終証拠にする。

## 8. 設計判断と代替案

| 採用候補 | 代替案 | 今回の判断 |
|---|---|---|
| Gemini Developer API | Vertex AI経由のGemini | 現行codeとSecret Manager設定を小さく検証できるためPhase 0はDeveloper APIを使う。key管理からADCへ統一する価値はあるが、Vertex AI移行は別の変更要因として比較する |
| regional Cloud Storage | PostgreSQLへbinaryを保存 | 大きな原本・画像と関係データの更新特性が異なるため、binaryはobject storage、metadataはPostgreSQLへ分ける |
| Qdrant Cloud Free | Qdrant self-host、pgvector | managed serviceの接続と運用特性を学べる。Free tierのsuspendがdemo要件に合わなければ、self-host費用またはpgvectorへの集約と再比較する |
| Cloud SQL shared-core | local PostgreSQL、serverless PostgreSQL | Phase 0はGoogle Cloud上のIAM・connector・停止方法を学ぶ最小構成とする。shared-coreの性能や費用が不適切なら、実装interfaceを保ったまま別hostingを比較する |

この調査を終えた時点で、面接では「serviceの役割」だけでなく、「何を観測済みか」「何が未検証か」「どこから課金されるか」「どう停止を証明するか」を分けて説明できる。

## 9. 結論

4 serviceの責務と最小試験は設計可能で、実行順序も決められる。現在証明できたのは既存Cloud Run・Gemini secret参照・GCS control planeのread-only状態までであり、Phase 0の接続要件はまだ完了していない。

Gemini spikeの具体的な入力、1回の費用上限、成功条件、secret/key確認、停止手順は[`GEMINI_CONNECTION_SPIKE_RUNBOOK.md`](GEMINI_CONNECTION_SPIKE_RUNBOOK.md)へ固定した。次は外部呼出をしないlocal runnerとmock testを用意し、dry-run結果をreview可能にしてから、credential取得とAPI 1 requestの承認を得る。
