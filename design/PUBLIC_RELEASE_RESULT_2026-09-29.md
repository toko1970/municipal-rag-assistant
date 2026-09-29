# 公開リリース結果 2026-09-29

## 結論

PR #10をsquash mergeし、GitHub ActionsからCloud Run revision
`municipal-rag-assistant-00007-wt2`を作成した。CI、bootstrap Job、healthは成功したが、公開画面の
具体期限smokeで根拠にない起算規則の補完を検出したため、公開受入は不合格とした。trafficは直前の
`municipal-rag-assistant-00006-m8d`へ100%戻した。

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
