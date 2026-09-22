# 初回Terraform planの確認記録

2026-09-22に、既存のGoogle Cloud環境を参照して `terraform plan` を実行した結果です。**9件追加、変更0件、削除0件**でした。これは実行時点の差分であり、適用直前に再実行して確認します。

| 追加対象 | 目的 |
| --- | --- |
| Security Token Service API、Service Account Credentials API | GitHubのOIDC認証を利用する |
| Workload Identity Pool、Provider | 指定リポジトリのmainブランチだけを信頼する |
| デプロイ用サービスアカウント | GitHub Actionsのデプロイ権限を分離する |
| デプロイ用サービスアカウントへのなりすまし権限 | 短期的な認証情報で接続する |
| Cloud Run Developer権限 | 既存サービスの新しいリビジョンをデプロイする |
| Artifact Registry Writer権限 | 既存リポジトリへイメージを登録する |
| 実行用サービスアカウントの使用権限 | 既存のCloud Run実行IDを引き継ぐ |

2026-09-22に同じ9件追加・変更0件・削除0件のplanを取り直し、その保存済みplanを `terraform apply` しました。結果は **9件追加、変更0件、削除0件** です。適用後の `terraform plan -detailed-exitcode` は終了コード0で、変更なしでした。

既存のCloud Runサービス、Artifact Registryリポジトリ、実行用サービスアカウント、Secret Managerのシークレット本体は作り直していません。CDは `ENABLE_CD` が無効のため、まだデプロイを実行していません。
