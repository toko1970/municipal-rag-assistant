# 公開リリース手順

更新日：2026-10-25。対象は既存Cloud Runサービス `municipal-rag-assistant`（`municipal-rag-portfolio` / `asia-northeast1`）。この手順のコードと非APIテストを整備した段階であり、変更後のworkflowを実クラウドで実行した記録ではありません。

## 1. 公開までの二段階

通常CIの成功後、**trafficを移さない候補revisionの作成、同一image・接続設定のsmoke、候補URLのhealth確認**までを行います。ここでは公開の合格になりません。5ケースすべての意味と実UIを担当者が確認し、対象revisionに結び付けた確認票を `Promote reviewed revision` workflowへ渡した後に、明示したrevisionへtrafficを切り替えます。

| 段階 | 検証する内容 | 公開traffic |
|---|---|---|
| CI（`ci.yml`） | lint、通常テスト、PostgreSQL/Qdrant統合テスト、Terraform検証 | 維持 |
| 候補の準備（CIの`deploy` job） | digest固定image、no-traffic revision、同一runtimeのJobによる5件の構造判定、タグURLのhealth | 維持 |
| 人による確認 | 同じタグURLで5件の回答の意味・根拠・図表・保留表示を確認 | 維持 |
| 昇格（`promote.yml`） | 元CI run、確認票、revision、commit、image、runtime、現在のtrafficの一致 | 合格したrevisionへ100% |
| 切替後 | 切替先revision/割合と通常URLのhealth | 失敗時は準備前の割合へ復旧 |

既存の `production` Environment、`ENABLE_CD == true`、`production-deploy` concurrency（実行中cancelなし）、Workload Identityによる権限分離を両workflowで維持します。手動昇格は`main`からだけ実行できます。Environmentの承認設定はGitHub側で確認し、保護を弱めません。

## 2. 事前に固定する対象と実行量

- 対象commitはCIがテストしたmainのSHA。imageはそのbuildの`@sha256:...`で固定します。
- 候補revision名は `municipal-rag-assistant-r<run_id>-<run_attempt>`、タグは `review-<run_id>-<run_attempt>`。
- 既存の `municipal-rag-bootstrap` Jobを使用しますが、通常リリースでは**smoke専用コマンド**を実行します。migration、文書再取込、図表再取込は実行しません。
- Jobは1 task、parallelism 1、task retry 0、timeout 15分。アプリのsmokeは5ケース、最大5問い合わせ試行、503再試行0。
- 意味・実UI確認は同じ5問をタグURLで各1回送信し、手動で追加送信しません。**送信操作はJob5件＋UI5件の10件**ですが、実UIは[`app.py`](../app.py)の既存503 backoffにより1送信につき最大3回、問い合わせ全体を実行し得ます。UIは最大15試行、Jobと合わせて**最大20試行**です。失敗したケースを通るまで手動で繰り返しません。
- この5つの固定質問は追加のquery分解を行わないため、公開candidateでは1試行あたり生成1回・Embedding1回です。通常予定は生成10回＋Embedding10回、503によるUI再実行を含む生成試行上限は20回です。Embedding SDK内部のHTTP retryはこの数と別であり、厳密な課金・HTTP回数の上限とは呼びません。入力token、画像入力、SDK retry設定を別に確認し、費用を予約します。
- LLM/Embeddingの実呼出し、監査ログ書込み、Cloud Run/Artifact Registryの利用料金を伴います。実行前に使用モデルの現行料金・利用枠で見積もり、費用上限を承認済みの作業票へ記録します。今回の作業は新しいAPI予算や公開実行の許可を付与しません。

`ci.yml`が指定する `autoresearch_candidate` の一回生成経路を検査します。構造検査だけを通過したことを、fresh holdoutのNo-go解除や回答品質の全面保証とは扱いません。

## 3. 候補の準備

1. 通常テスト・統合テスト・Terraform検証を通します。
2. buildしたimageのdigestを取得します。可変tagや`latest`では同一性を判断しません。
3. 既存serviceの`status.traffic`から、revision名と割合を準備前の復旧先として保存します。
4. `deploy-cloudrun@v3`の`no_traffic: true`、明示suffix、タグを用いて候補revisionを作成します。
5. 同じdigest、環境変数、Secret Managerの**版指定**、runtime service account、Cloud SQL接続で既存Jobを設定します。
6. Job実行前に`release_gate check-runtime`で環境変数／secret参照・service account・Cloud SQL/VPC接続・volume・working directoryがrevisionと一致することを確認します。imageは同じdigestなら一致とし、Cloud RunがOCI indexをplatform別digestへ解決した場合は、Artifact Registryから取得してdigest検証したOCI indexに含まれる`linux/amd64`子manifestであることを確認します。Web固有のport、probe、concurrencyとJobの実行制限は同一性判定の対象外です。
7. 以下の固定コマンドをJobで一度実行します。

```bash
python -m scripts.manage_rag_v2 smoke \
  --max-cases 5 --max-attempts 5 --max-503-retries 0
```

8. 不合格・未実行ケースが残る場合はCLIが非ゼロで終了します。Cloud Run Executionの`Completed=True`、成功task 1、失敗・cancel・retry 0と、凍結された実行image・コマンド・設定を検証します。
9. タグが対象revisionを指し、公開trafficが準備前と変わっていないことを確認します。通常URLを新revisionのhealth確認に使用しません。
10. タグURLの`/_stcore/health`が成功した場合に、`release-candidate-<run_id>-<run_attempt>` artifactを保存します。

artifactには、`candidate.json`、未記入の`review-template.json`、digest検証済みの`image-index.json`が入ります。前者はrevisionの解決済みimage、Jobの要求image、OCI indexからplatform manifestへの関係、実行run、Job execution、runtime hash、タグURL、復旧先を関連付けます。rawなservice/job設定、secret値、provider応答はartifactへ保存しません。Jobのstdoutは構造判定の簡潔JSONで、実回答と根拠は既存の監査記録からrequest IDで確認できます。Cloud Loggingの読取権限をこの変更で追加しません。

同一imageのJobはアプリの処理と依存接続を検査するもので、Streamlitの質問操作・根拠展開・図表表示を検査したことにはなりません。タグURLのhealthだけでもこれらは確認できません。

## 4. 意味と実UIの確認票

ケースの質問、期待分類、期待根拠、意味確認項目の正本は [`SMOKE_CASES`](../src/smoke_validation.py) です。新しい質問へ置き換えず、次の5ケースを同じタグURLで実行します。

| ケースID | 意味の確認 | 実UIの確認 |
|---|---|---|
| `salary_day` | 毎月21日、土日祝なら直前営業日という規定を正しく説明する | 質問・分類・本文が表示され、給与支給日の根拠本文を開ける |
| `missing_document` | 退職手当の計算式を作らず、必要な規程・確認先を示す | 文書不足の説明と次の確認内容を読める。参照0件だけを失敗にしない |
| `missing_case_facts` | 住居手当について本人名義・家賃額・届出状況を確認し、個別可否を確定しない | 判断要と具体的な不足事実が表示される |
| `visual_table` | 常勤・月15日以上の行と12,000円の上限を対応させる | 対象表のページ画像を開き、回答との対応を確認できる |
| `missing_counting_rule` | 14日以内の規定と不明な初日算入規則を分け、具体期限を推測で確定しない | 保留理由、根拠、不足する規則の確認案内を読める |

`review-template.json`をコピーし、各ケースの`semantic`と`ui`を確認できた場合だけ`PASS`へ変更します。`notes`に実際に確認した根拠・表示、可能ならrequest IDや確認証跡を記入します。実在個人情報・secretを記入しません。`reviewed_by`とtimezone付き`reviewed_at`も記入します。判定不能は`PENDING`、不合格は`FAIL`のまま残します。

revision・commit・resolved image・requested image・manifest hash・run ID/attempt・タグURLはテンプレートから変更しません。構造PASSから自動的に意味PASSを生成しません。公開必須項目が1件でも未確認なら、昇格validatorは非ゼロで停止します。

## 5. 検査済みrevisionの昇格

GitHub Actionsの **Promote reviewed revision** を`main`から実行し、以下を入力します。

- `candidate_run_id`：候補を準備したCI run ID。
- `candidate_run_attempt`：artifactと同じrun attempt。
- `review_json`：記入済み確認票のJSON全体。

workflowはまず同じリポジトリのsource runと指定artifactを取得します。source runがmainへのpushで起動したCIであり、completed/success、SHAとattemptが一致することを確認します。別run・別image・異なるタグURLの確認票、欠落・重複ケース、PENDING/FAIL、記録のないPASSは受け付けません。

切替直前にCloud Runから取得したrevisionとtrafficを再照合します。準備後に別リリースが公開されてtrafficが変わった場合は、古い復旧先で上書きせず停止します。候補を再準備・再確認してください。concurrencyは両workflowの同時更新を防ぎますが、コンソール等からの手動変更とは調整が必要です。昇格中は別経路からのtraffic変更を行いません。

合格後に実行するtraffic切替は、validatorが出力した明示revisionに限定します。

```bash
gcloud run services update-traffic municipal-rag-assistant \
  --project=municipal-rag-portfolio --region=asia-northeast1 \
  --to-revisions="$VERIFIED_REVISION=100"
```

`VERIFIED_REVISION`はレビュー票から直接信用せず、`candidate.json`、元CI、現行Cloud Runとの照合を通過した値を使用します。実際のworkflowは`promotion.json`の`traffic_argument`から取得します。`--to-latest`は使用しません。

切替後は`status.traffic`が対象revision 100%であること、通常service URLのhealthが正常であることを確認します。`promotion.json`、確認票、候補manifestを昇格runのartifactへ保存します。Webの生成・意味品質は直前のタグURL確認に基づくものであり、health成功から推論しません。

## 6. 失敗時の処理と復旧範囲

- CI、runtime照合、smoke、候補healthが失敗した場合：候補は昇格させません。元の公開trafficを維持し、失敗runとJob executionを調査します。
- 確認票やidentity照合が失敗した場合：traffic切替コマンドを実行しません。
- traffic切替の開始後、割合確認・health・結果記録が終わる前に失敗、明示的な`exit`、SIGINT、SIGTERMが発生した場合：`EXIT` handlerから`previous_traffic`の明示revisionと割合への復旧を試みます。開始状態はgcloud呼出しの前に設定するため、gcloud clientが成功を返さずにサーバー側だけ変更された場合も復旧対象です。
- 復旧の成功は、再取得した`status.traffic`が元の配分と一致したときだけ`outcome.json`に`ROLLED_BACK`として記録します。コマンド失敗・再確認失敗は`ROLLBACK_UNCONFIRMED`とし、次の手動手順を使います。
- 正確な切替先、health、結果receiptの保存をすべて確認した時点を昇格の完了点とします。完了点の後に通知出力等が失敗した場合やcancelされた場合は、確認済みrevisionを自動的に戻しません。run全体の結論だけでなく`outcome.json`と実trafficを確認します。
- **SIGKILL、runnerの消失、cancel猶予後の強制停止では、自動復旧やartifact保存を保証できません。** SIGINT/TERM handlerも利用可能な猶予内での復旧試行です。昇格runが中断し結果を確認できない場合は、必ず以下の手動確認へ進みます。
- 失敗したsmokeを通すための回数追加や期待条件の緩和は行いません。原因を修正し、別runとして再準備します。

手動復旧では、まず元CI runに保存された候補artifactを取得します。昇格runのartifactが残っていなくても、この準備artifactの`candidate.json`に対象revisionと`previous_traffic`が残っています。Cloud Runから`spec.traffic`（要求した配分）、`status.traffic`（反映された配分）、状態を取得し、途中の更新や別担当のリリースがないか確認します。

```bash
gcloud run services describe municipal-rag-assistant \
  --project=municipal-rag-portfolio --region=asia-northeast1 \
  --format='yaml(metadata.generation,status.observedGeneration,spec.traffic,status.traffic,status.conditions)'
```

他の意図的なリリースが進んでいないことを確認してから、準備artifactの`previous_traffic`を復旧先にします。`promotion.json`があれば`rollback_argument`を利用できます。昇格artifactが失われていれば、ローカルで`candidate.json`から同じ値を作成します。

```bash
RECORDED_ROLLBACK_ARGUMENT=$(python -c 'import json; from scripts.release_gate import validate_manifest, rollback_argument; data=json.load(open("candidate.json")); validate_manifest(data); print(rollback_argument(data))')
```

複数revisionへ配分していた場合も、その割合を保持します。復旧コマンドの完了後、要求した配分と反映された配分が一致し、healthが正常であることまで確認します。途中状態やAPIエラーが残る場合は復旧済みと判断しません。

```bash
gcloud run services update-traffic municipal-rag-assistant \
  --project=municipal-rag-portfolio --region=asia-northeast1 \
  --to-revisions="$RECORDED_ROLLBACK_ARGUMENT"
gcloud run services describe municipal-rag-assistant \
  --project=municipal-rag-portfolio --region=asia-northeast1 \
  --format='yaml(status.traffic,status.url)'
```

これは**実行コードとtrafficの復旧**です。Cloud SQL、Qdrant、GCSや問い合わせ監査ログを巻き戻しません。通常releaseにはschema/index変更を混ぜません。将来migrationが必要な場合は、旧revisionが新schemaと共存できること、データ移行中の互換性、別のbackup・復旧手順を先に確定します。初期導入の`bootstrap-cloud`（migration＋取込）は別の承認済み作業として行い、smokeだけのために繰り返しません。

## 7. ローカル検証と未実施の範囲

```bash
python -m pytest -q tests/test_release_gate.py tests/test_smoke_validation.py tests/test_manage_rag_v2.py
python -m ruff check scripts/release_gate.py tests/test_release_gate.py
```

`test_release_gate.py`は、image・接続・commit・revision・source run不一致、Job失敗/未完了、未確認ケース、異なるタグ、準備後traffic変更、非ゼロ終了、workflowの公開停止条件、シェル構文をAPIなしで確認します。また実際の昇格shellを実行し、外部gcloud/curl境界だけをfake化して、途中のclient失敗、health失敗、切替中／切替後のSIGINT・SIGTERM、明示exit、復旧失敗、完了後cancelを注入します。これらは実Cloud Runの受入結果ではありません。

実クラウドでは次が未確認です。初回実行時に、現行gcloudが返すv1 JSONの実形状、deployer権限、Secret Manager版と接続、同一image Jobの完了、タグURLでの5件の実UI、promotion・復旧を確認し、日時・commit・revision・run/attempt・artifactを記録してください。実行前の成功値を記入しません。

## 8. 使用版の公式資料

- [deploy-cloudrun v3 inputs](https://github.com/google-github-actions/deploy-cloudrun/blob/v3/README.md)：`no_traffic`、`suffix`、`tag`、Jobの`wait`。
- [gcloud run deploy](https://docs.cloud.google.com/sdk/gcloud/reference/run/deploy)：`--no-traffic`、`--revision-suffix`、`--tag`。
- [gcloud run services update-traffic](https://docs.cloud.google.com/sdk/gcloud/reference/run/services/update-traffic)：`--to-revisions`による明示切替。
- [gcloud run jobs execute](https://docs.cloud.google.com/sdk/gcloud/reference/run/jobs/execute)：`--wait`で実行完了を待つ。
- [Cloud Run v1 YAML reference](https://docs.cloud.google.com/run/docs/reference/yaml/v1)：service/revisionとJob/Executionの構造・接続annotation。
- [Artifact Registryのimage digest取得](https://docs.cloud.google.com/build/docs/securing-builds/generate-validate-build-provenance)：`image_summary.fully_qualified_digest`。
- [upload-artifact v4](https://github.com/actions/upload-artifact/blob/v4/README.md)・[download-artifact v4](https://github.com/actions/download-artifact/blob/v4/README.md)：runを指定したartifact保存・取得。

2026-09-29時点の初回導入で使ったPR #10、migration/取込後にそのままdeployする手順は履歴です。現在の通常リリースにはこの改訂手順を使用します。
