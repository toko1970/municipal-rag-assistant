# GitHub デプロイ用のIaC

このディレクトリは、GitHub Actionsから既存のGoogle Cloudプロジェクトへ接続する認証基盤と、公開RAG v2のCloud SQL・Secret Manager構成を定義します。Cloud Runサービス、Artifact Registryリポジトリ、実行用サービスアカウント、Gemini APIキーのシークレットは再作成しません。

## 管理するもの

- GitHub Actions用のWorkload Identity PoolとProvider。`toko1970/municipal-rag-assistant` の `main` ブランチだけを受け入れます。
- デプロイ専用サービスアカウントと、そのアカウントへの短期的ななりすまし権限。
- 既存のArtifact Registryへの書き込み、Cloud Runサービスの更新、既存の実行用サービスアカウントの使用に必要な権限。
- Workload Identity Federationに必要なAPI。
- Cloud SQL for PostgreSQLの最小zonal instance、database、user、接続URL secret。
- Qdrant Cloud APIキーを格納するsecret container。secret versionはcluster作成後に別途登録します。
- Cloud Run runtime service accountのCloud SQL接続権限と、RAG v2用secretの参照権限。
- 対象project限定のCloud Billing月額予算と通知しきい値。
- レビュー済み図表のための非公開Cloud Storage bucketと、runtime service accountのobject作成・参照権限。
- 公開APIのsession署名鍵secret containerとruntime参照権限。
- 匿名sessionのkey HMAC・quota識別値だけを削除するCloud Run Job、専用IAM、paused状態のCloud Scheduler、実行失敗/2時間未実行alert。

サービスアカウント鍵とQdrant APIキーの値はTerraformに保存しません。Terraformが生成するDB passwordと接続URLはsensitive valueとして非公開GCS stateへ保存します。

## 現在の状態

2026-09-22時点で、Cloud Runサービス `municipal-rag-assistant` は `asia-northeast1` に存在し、実行用サービスアカウント `municipal-rag-runtime` とSecret Managerの `gemini-api-key` を参照しています。同日、GitHub Actions用の認証基盤と権限をTerraformで適用しました。適用後の `terraform plan` は変更なしです。既存のCloud RunサービスはTerraformの管理対象に含めていません。

2026-09-27に対象project限定の月額2,000円予算を先行適用し、50%、80%、100%の通知しきい値を確認しました。続いてRAG v2公開用resourceを`12 added, 0 changed, 0 destroyed`で適用しました。Cloud SQLは`RUNNABLE`で、適用後のTerraform planは`No changes`です。2026-09-28にQdrant Free clusterをGCP Sydneyで作成し、最終database API keyをSecret Managerの`qdrant-api-key` version 5へ登録しました。旧Qdrant keyは削除し、Secret Manager version 1〜4は無効化済みです。

2026-09-28に図表公開用bucket `municipal-rag-portfolio-visual-assets-280649014820`を`4 added, 0 changed, 0 destroyed`で適用した。uniform bucket-level accessとpublic access preventionを有効にし、soft deleteは7日、`force_destroy=false`とした。runtimeにはbucket単位の`objectCreator`と`objectViewer`だけを付与し、削除権限は与えていない。6 fixtureのページ画像は約0.48 MiBで、東京Standard storageを月額US$0.022/GiBとして換算した保存費用は月US$0.000011未満である。適用後のTerraform planは`No changes`で、GitHub production variable `GCS_VISUAL_ASSET_BUCKET`も設定済みである。

## 検証と適用の順序

CIは `terraform fmt -check` と `terraform validate` だけを実行します。`terraform init -backend=false` を使うため、この検証ではクラウドの状態ファイルにアクセスせず、リソースも変更しません。

状態保存用のCloud Storageバケット `municipal-rag-portfolio-tfstate-280649014820` は2026-09-22に一度だけ作成し、非公開、バケット単位のアクセス制御、バージョニングを設定しました。旧バージョンが無制限に増えないよう、[state-lifecycle.json](state-lifecycle.json) で新しい版が10件ある旧版を削除します。Terraformの状態はこのバケットに保存します。`terraform plan` の新規作成・変更・削除を確認してから `terraform apply` します。初回の差分は [INITIAL_PLAN.md](INITIAL_PLAN.md) に記録しています。既存のCloud RunなどをIaCの管理対象へ広げる場合は、別途インポートして変更予定が意図どおりか確認します。

図表bucketのapplyを戻す場合は、先にCloud Runとbootstrap JobからGCS設定を外す。bucketにobjectがある間は`force_destroy=false`によりTerraformの削除を失敗させ、意図しないデータ削除を防ぐ。保存データが不要だと確認した後だけobjectとbucketを明示的に削除する。Storage APIは`disable_on_destroy=false`のため、この差分をstateから除いてもAPIを無効化しない。

CDジョブはGitHub Actionsに定義され、リポジトリ変数 `ENABLE_CD` を `true` に設定しています。認証基盤と状態保存先の設定は完了しました。GitHubの `production` Environmentは所有者の承認を必須とし、`main` ブランチからの候補revision準備とpromotionだけを許可します。Artifact Registryへの候補image build/pushはCI成功後に単独jobで行い、digestを出力します。候補image jobはCloud Runを変更しません。

この段階のIaCは認証基盤だけを対象とします。既存のCloud RunサービスやSecret Manager設定をコード管理へ移す場合は、現在の構成を確認してからインポートし、デプロイ処理とTerraformが同じ設定を競合して更新しないよう管理範囲を決めます。

## React/FastAPI移行の運用前提

移行コードはCloud Runへまだ適用していません。Cloud Run serviceはCI deployが管理し、Terraformはcleanup Job/Scheduler/alertとsession secret containerを追加します。`main`へのpush後、CI成功を条件にArtifact Registryへ候補imageをbuild/pushします。このjobはCloud Runを変更せず、固定digestをworkflow summaryへ出します。そのdigestでTerraform planを作成・レビューし、明示承認後のapplyでScheduler pausedのcleanup Jobとsession secret containerを作成します。session signing key versionとGitHub production variablesを設定した後、GitHub `production` Environment承認を経てdeploy jobを実行します。deploy jobはDB migrationと既存のbounded smokeを行い、同じdigestのCloud Run revisionをtag付き・traffic 0%で準備します。CI artifactのreview evidenceを使って候補を確認し、5項目すべてのsemantic/UI reviewがPASSした場合に限り、`promote.yml`を別途手動実行します。promotion jobもGitHub `production` Environment承認を要求し、traffic更新を検証して失敗時は直前のtrafficへrollbackします。Scheduler有効化用のplanは別に作り、レビュー・承認後に適用します。

- Terraform planには候補image jobが出力した固定digestを`public_api_cleanup_image`へ渡します。`eval/`はDocker build contextから除外され、CI container smokeでimage内に含まれないことを確認します。
- `public_api_cleanup_notification_channel`は`projects/PROJECT/notificationChannels/ID`形式です。Schedulerを有効にするplanでは必須で、未指定ならpreconditionが失敗します。
- Terraformは`rag-session-signing-keys`というsecret containerを作りますが、secret versionの値は作成しません。デプロイ前に32 byte以上のランダム鍵を生成し、key IDを含むJSONをSecret Managerへ登録します。鍵値をTerraform state、Git、GitHub variableへ置かないでください。
- GitHub `production` Environmentへ`CANONICAL_ORIGIN`（既存Cloud Run service URLのoriginのみ。末尾slashなし）と`SESSION_CURRENT_KEY_ID`をvariableとして設定します。候補revisionごとにCIが安定service originとレビュー用tag originだけから`CANONICAL_ORIGINS_JSON`を生成します。APIはOrigin文字列を完全一致で照合し、wildcardやsuffix matchingは使いません。secret JSONはCloud Runが`rag-session-signing-keys:latest`から読み込みます。
- session鍵rotationではcurrentと直前の鍵をcookie最大寿命24時間以上重複して残し、`SESSION_CURRENT_KEY_ID`だけを新しいkey IDへ切り替えます。
- production承認後のdeploy jobはDB migrationを実行し、traffic 0%のtag付き候補revisionを作成します。CI artifactの候補URLでReact root・FastAPI liveness/readinessと5件のsemantic/UI reviewを確認し、全項目PASS後にだけ別workflow `promote.yml` をdispatchします。同workflowがtrafficを切替え、失敗時は直前trafficへ戻します。候補imageのpublishはCloud Runのrevision/trafficを変更しません。Terraform apply、候補revision作成、traffic promotion、Scheduler有効化はそれぞれ別の承認点です。
