# 分類oracle反復まで64サービスの追加独立判定メモ

[固定snapshot](classification_review_snapshot_064.jsonl)はindex 0–63（oracle初回48、事前指定A02/A03/B03/C04の反復16）で、SHA-256 `6285aca142ad7a96db6c5050ab7493af02b677a0f2e1650908e05f0d895720b6`。[メタデータ](classification_review_snapshot_064.json)に保存。初回の詳細は[48件メモ](classification_review_snapshot_048_notes.md)を参照。これは最終採点ではない。

反復index 48–63は、各同一表現・方式の初回と最終表示の成功/失敗がすべて同じだった。A02ではv1 paraphraseの過剰保留とv2 formalの文字化けしたQuestion Contractが再現。A03ではv2 formalの質問外「確定できる場合の金額」facetが再び`GENERATION_INCOMPLETE`を起こした。B03ではv2両表現が再び`date_calculations.cutoff_time`のschema違反で`SERVICE_ERROR`。C04は両方式・両表現で`文書不足`を維持した。反復を初回主指標の独立シナリオとして数えない。

B03 v2の対象抽出自体はイベントに残った3 facet（調整休時間、申請期限、提出先）と入力事実を質問に照らして妥当と判定した。一方、generation eventには停止原因の時刻format違反に加え、起算の構造化計算も文書の「翌月3日」と整合しない。index25の`anchor_date=2028-02-01`、`offset_value=31`、`anchor_day_is_day_1`は`result_label=2028年3月3日`と一致しない。index27の同起点から`offset_value=3`、`next_day_is_day_1`も翌月3日を表さない。**時刻formatだけ修正すれば正答するという推定はできない。** 例外停止後の最終表示は存在せず、composite失敗である。
