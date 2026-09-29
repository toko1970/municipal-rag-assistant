# 公開リリース実行票

## 目的

公開前gateを通過した候補を、同じcommitのDocker imageでCloud Runへ反映し、CI/CD、依存サービス、
代表質問、公開画面を確認する。一度限りのrelease checklistとして実行し、精度改善loopにはしない。

## 固定条件

- 対象PR: `#10`
- 対象service: `municipal-rag-assistant` / `asia-northeast1`
- deploy経路: `main`へのpushで起動するGitHub Actions `CI`
- 新規cloud resource: なし
- Gemini smoke: bootstrap Jobの代表質問1件
- provider retry: `503 UNAVAILABLE`だけを最大2回
- backoff: 5.1秒、10.2秒
- 503以外のAPI error、設定不整合、回答処理失敗: retryせず停止
- reset credit・追加credit: 使用しない

## 実行順序

1. PRのhead SHA、CI成功、merge conflictなしを確認する。
2. PRをReadyへ変更し、`main`へmergeする。
3. GitHub Actionsのtest、Ruff、Terraform検査を確認する。
4. commit SHA付きimageのbuildとArtifact Registryへのpushを確認する。
5. bootstrap Jobでmigration、5文書・6図表fixtureの冪等取込、PostgreSQL・Qdrant整合性を確認する。
6. bootstrap Jobの代表質問を実行する。503だけは固定backoffで再試行し、回数を結果へ残す。
7. Job成功後に同じimageがCloud Runへdeployされたことを確認する。
8. `/_stcore/health`、revision、traffic 100%を確認する。
9. 公開画面で通常質問、具体期限質問、図表質問の主要経路を確認する。
10. commit SHA、revision、workflow URL、503 retry回数、smoke結果をcheckpointへ記録する。

## 停止条件

- CI、Terraform検査、bootstrap Jobのいずれかが失敗した場合はservice deploy前に停止する。
- 503が初回を含む3試行すべてで続いた場合はprovider障害として停止する。
- PostgreSQLとQdrantの要素IDが一致しない場合は停止する。
- deploy後のhealth、主要経路、根拠表示のいずれかが失敗した場合は新revisionを合格としない。

## rollback

公開後に重大な問題が見つかった場合は、一つ前のCloud Run revisionへtrafficを戻す。Cloud SQL、
Qdrant、GCSは削除しない。原因修正は別commitとし、失敗したworkflowとsmoke artifactを保持する。
