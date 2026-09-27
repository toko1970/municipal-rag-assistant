# GCS object round-trip spike 実行票

- 作成日: 2026-09-27
- 状態: `READY_FOR_REVIEW`
- 対象service: Google Cloud Storage
- 対象project: `municipal-rag-portfolio`
- 対象region: `asia-northeast1`
- 外部resource: 短命bucket 1件、架空object 1件
- 費用上限: **$0.01 USD**
- 証拠出力予定: `eval/results/gcs_connection_spike_phase0.json`

## 1. 学習目標

このspikeでは、object storageへの接続確認を、認証、最小権限、整合性、競合防止、削除確認、費用の証拠として残す方法を学ぶ。

完了後に説明できることは次の5点とする。

1. bucketを操作するcontrol plane identityと、objectを操作するruntime identityを分ける理由。
2. uniform bucket-level accessとpublic access preventionで公開事故を防ぐ方法。
3. generation preconditionで上書き・誤削除を防ぐ方法。
4. local SHA-256、object metadata、download結果を照合する理由。
5. soft delete、versioning、retentionが削除後の費用へ与える影響。

## 2. このspikeが証明すること

- 開発者ADCで専用bucketを作成し、設定とbucket-level IAMを管理できる。
- `municipal-rag-runtime@municipal-rag-portfolio.iam.gserviceaccount.com`として、objectをcreate、read、deleteできる。
- 固定した131 bytesの架空JSONを上書き防止条件付きでuploadできる。
- metadata、generation、custom SHA-256を取得し、download後のSHA-256と一致させられる。
- 指定generationだけを削除し、objectとbucketの不在を再照会できる。
- 操作数と当日のlist priceから費用上限内であることを説明できる。

このspikeだけでは次を証明しない。

- Cloud Run containerからGCSへのnetwork・ADC経路。
- 本番用bucketのTerraform管理、命名、backup、versioning、lifecycle。
- PDF・画像の大容量upload、並列処理、signed URL、障害時reconciliation。
- Cloud Billingへ反映された最終請求額。請求反映には遅延があり、このspikeではlist priceによる推定を記録する。

## 3. 設計判断

### 3.1 既存bucketを流用しない

read-only確認で、次の2 bucketが存在する。

| bucket | location | 用途 | 判断 |
|---|---|---|---|
| `municipal-rag-portfolio-tfstate-280649014820` | `ASIA-NORTHEAST1` | Terraform state | object追加・削除試験に使わない |
| `municipal-rag-portfolio_cloudbuild` | `US` | Cloud Build | region・責務が異なるため使わない |

stateやbuild artifactへの誤操作を避けるため、専用の短命bucketを作成して試験後に削除する。これは本番用application bucketの作成ではない。本番bucketはPhase 1のTerraform変更として別にreviewする。

### 3.2 identityを分離する

| 操作 | identity | 権限方針 |
|---|---|---|
| bucket作成、設定確認、bucket IAM、bucket削除 | 開発者ADC | control planeだけ |
| object upload、metadata取得、download、object削除 | `municipal-rag-runtime`のimpersonation | 試験bucketにだけ`roles/storage.objectUser` |

`roles/storage.objectUser`はobjectのcreate、read、update、deleteを含む。runtime service accountへproject-wideの`roles/storage.admin`は付与しない。impersonation tokenをterminalや証拠fileへ出力しない。

### 3.3 短命bucketでは削除可能性を優先する

固定設定は次のとおり。

| 項目 | 固定値 |
|---|---|
| bucket name | `municipal-rag-portfolio-phase0-spike-280649014820` |
| location | `asia-northeast1` |
| storage class | `STANDARD` |
| uniform bucket-level access | enabled |
| public access prevention | enforced |
| soft delete | disabled、`0` |
| Object Versioning | disabled |
| Autoclass | disabled |
| retention policy / lock | なし |
| hierarchical namespace | disabled |

Cloud Storageは新規bucketへ既定7日のsoft deleteを設定する。短命試験では削除後の保持を避けるため、bucket作成時に`--soft-delete-duration=0`を明示する。retention、versioning、Autoclassは有効化しない。

## 4. 固定payload

object pathは`spike/gcs-connection/v1/payload.json`とする。

```json
{"document_id":"gcs-spike-001","title":"架空給与通知","content":"この文書は接続試験用の架空データです。"}
```

末尾にLFを1文字持つUTF-8 fileとして扱う。

| 項目 | 固定値 |
|---|---|
| size | 131 bytes |
| SHA-256 | `87bf4ff37425748dfe97869eef5253f163440d2927b953ace680d92c98c70448` |
| content type | `application/json` |
| custom metadata | `sha256=87bf4ff37425748dfe97869eef5253f163440d2927b953ace680d92c98c70448` |

本番文書、個人情報、repository内のPDF、credentialは送信しない。

## 5. 費用gate

2026-09-27に確認したsingle-region Standard storageのlist priceを使う。

- Class A: `$0.005 / 1,000 operations`
- Class B: `$0.0004 / 1,000 operations`
- delete operations: free
- 東京regionはCloud Storage Always Freeの対象外

gcloud CLIは1 commandで複数operationを使う場合があるため、実行前上限はClass A 10回、Class B 10回として保守的に置く。

```text
operation_cost_upper_bound =
  10 * 0.005 / 1,000
  + 10 * 0.0004 / 1,000
  = $0.000054
```

131 bytesを試験時間だけ保存する費用とdata transferはこの上限に比べても小さいが、ゼロとは断定しない。全体の実行上限を`$0.01`とし、価格変更、想定外の保持設定、10回を超えるClass A/B相当の操作が必要な場合は実行しない。

## 6. 実行前checklist

すべて満たした場合だけ`READY_TO_EXECUTE`へ進める。

- [ ] ユーザーがbucket作成、bucket-level IAM追加、object round trip、object・bucket削除を明示的に承認した。
- [ ] Codexの5時間枠と週間枠を確認し、5時間枠が80%未満である。
- [ ] `git status`を確認し、無関係な変更を把握した。
- [ ] bucket名が存在しないことをread-onlyで確認した。存在する場合は削除・流用せず停止する。
- [ ] Cloud Storage APIが有効である。
- [ ] 開発者ADCのactive accountとprojectを確認した。account情報は結果fileへ保存しない。
- [ ] runtime service accountのimpersonationが可能である。access tokenは出力しない。
- [ ] 当日の東京Standard storage、Class A/B、soft deleteの公式仕様を再確認した。
- [ ] 固定payloadのsizeとSHA-256をlocalで再計算した。
- [ ] bucket作成commandがsoft delete `0`、uniform access、public access preventionを明示している。
- [ ] cleanup手順を先に用意し、失敗後も追加objectを作らず削除へ進める。

## 7. 固定実行手順

application levelでは各mutating stepを1回だけ実行する。失敗時に同じstepを自動再実行しない。gcloudまたはservice側の内部retry回数は別途取得できないため、generation preconditionで同じ名前への重複変更を防ぐ。

1. bucket名の不在を確認する。
2. runtime service accountのimpersonation可否を、tokenを表示せず確認する。失敗したらresource作成前に停止する。
3. `/tmp`へ固定payloadを生成し、sizeとSHA-256を照合する。
4. 専用bucketを東京、Standard、uniform access、public access prevention、soft delete `0`で作成する。
5. bucketをdescribeし、location、storage class、uniform access、public access prevention、soft delete、versioning、retentionを検査する。不一致ならobjectを作らずcleanupへ進む。
6. 試験bucketに限り、runtime service accountへ`roles/storage.objectUser`を付与する。
7. runtime identityで`if-generation-match=0`を付けてobjectを1件uploadする。
8. runtime identityでobject metadataを取得し、generation、size、content type、custom SHA-256を記録する。
9. 取得したgenerationを指定してruntime identityでdownloadし、local SHA-256を照合する。
10. 同じgenerationを`if-generation-match`へ指定してruntime identityでobjectを削除する。
11. objectをdescribeして`404 Not Found`を確認する。別のgenerationやobjectがあればbucketを削除せず停止する。
12. 開発者ADCで空のbucketを削除する。
13. bucketをdescribeして`404 Not Found`を確認する。
14. `/tmp`のsourceとdownload fileを削除する。

## 8. cleanup優先順位

bucket作成後に失敗した場合は、原因調査よりcleanupを先に行う。

1. 既知のgenerationがあれば、そのgenerationだけを条件付き削除する。
2. bucket内を一覧し、固定object以外が存在した場合は自動削除せず`CLEANUP_BLOCKED_UNEXPECTED_OBJECT`で停止する。
3. 固定objectだけならgenerationを再取得して条件付き削除する。
4. bucketが空であることを確認して削除する。
5. bucket不在を再照会する。

想定外objectを一括削除するcommandは実行票に含めない。既存2 bucketにはcleanup commandを実行しない。

## 9. 結果record

`eval/results/gcs_connection_spike_phase0.json`へ、次の非機密情報だけを保存する。

```json
{
  "schema_version": "gcs-connection-spike-v1",
  "executed_at": "UTC timestamp",
  "outcome": "terminal state",
  "project_id": "municipal-rag-portfolio",
  "region": "asia-northeast1",
  "bucket_name": "municipal-rag-portfolio-phase0-spike-280649014820",
  "runtime_identity": "municipal-rag-runtime@municipal-rag-portfolio.iam.gserviceaccount.com",
  "bucket_settings_verified": false,
  "object_path": "spike/gcs-connection/v1/payload.json",
  "object_generation": null,
  "size_bytes": 131,
  "expected_sha256": "87bf4ff37425748dfe97869eef5253f163440d2927b953ace680d92c98c70448",
  "downloaded_sha256": null,
  "round_trip_seconds": 0.0,
  "application_attempts": {},
  "estimated_operation_cost_usd": 0.0,
  "object_absence_verified": false,
  "bucket_absence_verified": false,
  "error_category": null,
  "error_summary": null
}
```

access token、ADC credential、IAM token、credential path、stack trace、環境変数一覧は保存しない。generationはcredentialではなく、条件付き操作と監査に必要なobject識別子として保存する。

## 10. terminal state

| 状態 | 意味 |
|---|---|
| `SUCCESS` | identity分離、設定、round trip、hash、object不在、bucket不在をすべて確認 |
| `BLOCKED_APPROVAL` | resource作成・IAM・削除の承認がないため開始しない |
| `BLOCKED_BUCKET_EXISTS` | 固定bucket名が既に存在するため触らず停止 |
| `BLOCKED_IMPERSONATION` | runtime identityを使用できず、resource作成前に停止 |
| `BUCKET_CONFIGURATION_FAILED` | 作成後の設定が固定値と一致しない。objectを作らずcleanup |
| `IAM_FAILED` | bucket-level role付与に失敗。objectを作らずcleanup |
| `UPLOAD_FAILED` | 条件付きuploadに失敗。再uploadしない |
| `METADATA_FAILED` | generation、size、metadataを検証できない |
| `HASH_MISMATCH` | download fileのSHA-256が固定値と異なる |
| `DELETE_FAILED` | 指定generationのobject削除に失敗 |
| `CLEANUP_BLOCKED_UNEXPECTED_OBJECT` | 固定object以外を検出。自動削除しない |
| `CLEANUP_INCOMPLETE` | objectまたはbucketの不在を確認できない |
| `LOCAL_VALIDATION_FAILED` | payload、費用gate、result validationに失敗し、resourceを作らない |

## 11. 成功条件

- [ ] bucket設定が固定値と一致する。
- [ ] runtime identityによるupload、metadata get、download、deleteが各1 application attemptで成功する。
- [ ] object generationを取得し、downloadとdeleteの対象に固定する。
- [ ] expected、metadata、downloadedのSHA-256が一致する。
- [ ] object不在とbucket不在を`404`で確認する。
- [ ] 推定operation費用が`$0.01`未満である。
- [ ] credentialや個人情報がresult、terminal、Git差分にない。
- [ ] `SUCCESS`の場合だけP0-15のGCS最小接続を完了として記録する。

## 12. 承認境界

この実行票の作成は、Google Cloud resource変更の承認ではない。実行すると、短命bucket作成、bucket-level IAM binding追加、架空objectのupload・download・delete、bucket削除が発生する。実行直前にread-only preflightと価格を再確認し、具体的なbucket名、identity、費用上限、cleanupを提示してユーザーの明示的な承認を得る。

## 13. 公式根拠

- [Cloud Storage authentication and ADC](https://docs.cloud.google.com/storage/docs/authentication)
- [IAM roles for Cloud Storage](https://docs.cloud.google.com/storage/docs/access-control/iam-roles)
- [Uniform bucket-level access](https://docs.cloud.google.com/storage/docs/uniform-bucket-level-access)
- [Public access prevention](https://docs.cloud.google.com/storage/docs/public-access-prevention)
- [Soft delete](https://docs.cloud.google.com/storage/docs/soft-delete)
- [Request preconditions](https://docs.cloud.google.com/storage/docs/request-preconditions)
- [Cloud Storage pricing](https://cloud.google.com/storage/pricing)

