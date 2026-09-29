# 公開リリース結果 2026-09-29

## 結論

PR #10をsquash mergeし、GitHub ActionsからCloud Run revision
`municipal-rag-assistant-00007-wt2`を作成した。CI、bootstrap Job、healthは成功したが、公開画面の
具体期限smokeで根拠にない起算規則の補完を検出したため、公開受入は不合格とした。trafficは直前の
`municipal-rag-assistant-00006-m8d`へ100%戻した。

根拠契約をコードで強制する修正をPR #11で反映し、revision
`municipal-rag-assistant-00008-9kt`を再リリースした。通常質問とhealthは合格した。一方、CDが新revisionを
作成してもrollback先に固定されたtrafficを自動で戻さない問題と、公開UIがすべてのGeminiエラーを
「利用上限」と表示する問題を発見した。trafficは手動で新revisionへ切り替えたが、具体期限と図表の
公開受入はprovider errorのため未完了である。確認できていない項目を合格とは扱わない。

## リリース証拠

- merge commit: `c1b8e4b6b0cefbed9b76379bca42c894e5697624`
- GitHub Actions run: `36569983269`
- 作成revision: `municipal-rag-assistant-00007-wt2`
- test / lint / Terraform: 成功
- Docker image build / push: 成功
- bootstrap Job: 成功
- Streamlit health: `ok`
- bootstrapの`provider_503_retry`記録: 0件

## 公開画面smoke

| 経路 | 質問 | 結果 | 判定 |
| --- | --- | --- | --- |
| 通常テキスト | 給与支給日はいつですか？ | 毎月21日、休日の場合は直前営業日。根拠表示あり | 合格 |
| 具体期限 | 2027年5月1日に住所変更した場合、住所変更届の提出期限日はいつですか？ | 文書は「14日以内」だけだが、当日を1日目と補って5月14日と断定 | **不合格** |
| 図表 | 通勤手当の申請書を受領した後、最初に何を確認しますか？ | 記載内容と添付書類を確認。図表根拠を1位で取得 | 合格 |

## 原因

期限計算promptは、取得根拠に暦日数と起算規則が明記された場合だけ`date_calculations`を返すよう
求めていた。しかし、LLMがこの契約に違反して`anchor_day_is_day_1`を返した場合、アプリケーションは
根拠本文と起算規則を照合せず計算していた。指数バックオフでは解決しない意味上の失敗である。

## rollback

- rollback先: `municipal-rag-assistant-00006-m8d`
- rollback後traffic: 100%
- rollback後Ready: `True`
- rollback後health: `ok`
- Cloud SQL、Qdrant、GCSの削除・変更: なし

## 修正方針

引用された根拠本文に、選択された起算規則を示す明示表現があるかコードで検証する。明示がなければ
日付計算を破棄し、「期限日を確定するための起算規則」をmissing conditionへ追加する。文書を観測した
回答に合わせて書き換えず、根拠契約をコードで強制する。

## PR #11による修正後の再リリース

### リリース証拠

- merge commit: `3ed3f4996d80e485aae28f85d9170d0bd3f7e610`
- GitHub Actions run: `36573652613`
- 作成revision: `municipal-rag-assistant-00008-9kt`
- test / lint / Terraform: 成功
- Docker image build / push: 成功
- bootstrap Job: 成功
- Streamlit health: `ok`

### 発見したCDの問題

Cloud Runのrollbackでtrafficをrevision `00006-m8d`へ固定した後は、deploy actionが新revision
`00008-9kt`を作成してもtrafficが自動でlatestへ戻らなかった。workflowのhealth checkはdeploy actionが
返したservice URLを使うため、実際には旧revisionへ到達したまま成功していた。公開受入のため、trafficを
`00008-9kt`へ手動で100%切り替え、Readyとhealthを再確認した。

次回からはdeploy後、health checkの前に
`gcloud run services update-traffic municipal-rag-assistant --to-latest`を実行する。これにより、revisionの
作成と公開trafficの切替を別々に検証できる。

### 公開画面smoke

| 経路 | 結果 | 判定 |
| --- | --- | --- |
| 通常テキスト | 給与支給日の回答と根拠表示に成功 | 合格 |
| 具体期限 | UIがGemini errorを「利用上限」と表示 | 未完了 |
| 図表 | provider error後に追加API呼び出しを停止したため未実施 | 未完了 |

UIは`ChatGoogleGenerativeAIError`を内容によらず429相当として表示していた。このため、実際の原因が
429 `RESOURCE_EXHAUSTED`か503 `UNAVAILABLE/high demand`か判別できなかった。Cloud Loggingにも
errorは残らず、DB上の失敗記録だけではprovider statusを確認できない。

## PR #12候補の運用修正

- 503だけを5.1秒、10.2秒の指数バックオフで最大2回再試行する処理をbootstrapとUIで共用する。
- 429は再試行せず利用上限、503は再試行後に一時混雑、それ以外は通信エラーとして表示する。
- deploy後にCloud Run trafficをlatestへ明示的に切り替えてからhealthを確認する。
- 修正後の公開受入では、通常テキスト、具体期限、図表の3経路を再確認する。

最初の3項目を実装し、外部APIを使わない回帰378件、実PostgreSQL・Qdrant統合3件、Ruff、Python構文、
diff検査が成功した。最後の公開受入はPRのreview、merge、deploy後に実施する。

## PR #12の本番反映結果

### リリース証拠

- merge commit: `112434860e50abf0773a083f53ad01cf9334ac9b`
- GitHub Actions run: `36579889004`
- 作成revision: `municipal-rag-assistant-00009-j49`
- test / lint / Terraform / deploy: 成功
- revision Ready: `True`
- traffic: latest revisionへ100%
- Streamlit health: `ok`

CDへ追加した`--to-latest`により、新revisionの作成後にtrafficが自動で`00009-j49`へ切り替わった。
serviceとcontainer imageのcommit SHAもmerge commitと一致した。PR #11で必要だった手動traffic切替は
不要になった。

### 公開画面smoke

| 経路 | 結果 | 判定 |
| --- | --- | --- |
| 通常テキスト | 毎月21日、休日の場合は直前営業日。根拠表示あり | 合格 |
| 具体期限 | 429を「Gemini APIの利用上限」と表示し、追加retryなしで停止 | provider制約により未完了 |
| 図表 | 429後の停止条件に従い未実施 | 未完了 |

新revisionのCloud Loggingに`provider_503_retry`は0件だった。今回の具体期限失敗は503ではなく429として
扱われ、503だけを再試行する契約とUI表示の分離は公開環境でも確認できた。429後は手動再送を行わず、
図表質問も実行しなかった。

アプリケーション、health、通常回答、CD traffic切替は合格しているため、trafficは`00009-j49`へ維持する。
具体期限の意味上の修正と図表経路の最終受入は、Gemini利用枠の回復後に各1回だけ再確認する。現時点では
未実施項目を公開受入合格とは扱わない。
