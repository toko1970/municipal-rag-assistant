# GitHub デプロイ用のIaC

このディレクトリは、GitHub Actionsから既存のGoogle Cloudプロジェクトへ接続するための認証基盤を定義します。Cloud Runサービス、Artifact Registryリポジトリ、実行用サービスアカウント、Gemini APIキーのシークレットは再作成しません。デプロイに必要な権限は、既存のリポジトリと実行用サービスアカウントに追加します。

## 管理するもの

- GitHub Actions用のWorkload Identity PoolとProvider。`toko1970/municipal-rag-assistant` の `main` ブランチだけを受け入れます。
- デプロイ専用サービスアカウントと、そのアカウントへの短期的ななりすまし権限。
- 既存のArtifact Registryへの書き込み、Cloud Runサービスの更新、既存の実行用サービスアカウントの使用に必要な権限。
- Workload Identity Federationに必要なAPI。

シークレットの値やサービスアカウント鍵はTerraformに保存しません。

## 現在の状態

2026-09-22時点で、Cloud Runサービス `municipal-rag-assistant` は `asia-northeast1` に存在し、実行用サービスアカウント `municipal-rag-runtime` とSecret Managerの `gemini-api-key` を参照しています。GitHub Actions用のWorkload Identity Poolはまだありません。この設定は新しい認証基盤だけを定義した段階で、Google Cloudには未適用です。

## 検証と適用の順序

CIは `terraform fmt -check` と `terraform validate` だけを実行します。`terraform init -backend=false` を使うため、この検証ではクラウドの状態ファイルにアクセスせず、リソースも変更しません。

状態保存用のCloud Storageバケット `municipal-rag-portfolio-tfstate-280649014820` は2026-09-22に一度だけ作成し、非公開、バケット単位のアクセス制御、バージョニングを設定しました。旧バージョンが無制限に増えないよう、[state-lifecycle.json](state-lifecycle.json) で新しい版が10件ある旧版を削除します。Terraformの状態はこのバケットに保存します。`terraform plan` の新規作成・変更・削除を確認してから `terraform apply` します。初回の差分は [INITIAL_PLAN.md](INITIAL_PLAN.md) に記録しています。既存のCloud RunなどをIaCの管理対象へ広げる場合は、別途インポートして変更予定が意図どおりか確認します。

CDジョブはGitHub Actionsに定義済みですが、リポジトリ変数 `ENABLE_CD` が `true` でない間は実行されません。認証基盤の適用、状態保存先の設定、GitHubの `production` Environmentでの承認ルール設定が完了してから、この変数を有効にします。有効化後は `main` へのpushでCIの両ジョブが成功したときだけ、コミットSHAをタグにしたイメージを登録し、既存Cloud Runサービスの新しいリビジョンとしてデプロイします。

この段階のIaCは認証基盤だけを対象とします。既存のCloud RunサービスやSecret Manager設定をコード管理へ移す場合は、現在の構成を確認してからインポートし、デプロイ処理とTerraformが同じ設定を競合して更新しないよう管理範囲を決めます。
