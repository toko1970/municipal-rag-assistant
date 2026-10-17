# 訂正履歴

## 2026-10-12: CH10の質問範囲を明確化

独立レビューで、旧質問は「本要領の対象か」と「別制度も含め補助を利用できるか」の両方に読めると指摘された。ユーザーは後者を明示し、他制度の根拠がないため文書不足とする境界を確認した。作者は候補コード・生出力を閲覧せず、実行前に修正した。これは候補性能の改善ではなく評価入力の曖昧さの訂正である。

変更: CH10のformal / paraphrase / noisyのquestion、goldのtarget・required_answer_elements・reason・review履歴。取得根拠、固定生成回答、期待status/label、他23シナリオは変更なし。旧版は `revisions/20261012_before_ch10_scope_clarification/` に保存。corpus.jsonは変更なし。独立再レビュー待ち、API実行0、Gate2実行禁止を維持する。

| ファイル | 修正前SHA-256 | 修正後SHA-256 |
|---|---|---|
| inputs.json | `f60d4f77b93a5f006271512897a98192f0e794ae9705f007c914f2f26ea51a14` | `1883ae16749581df46f9d4c714e924783012b12e17bdcf22f0c914fd366b8698` |
| gold.json | `d7622de074cc84ee4c15948363692fbec43257fb7605c2e75fff8bad971294c5` | `3141cba5fa9eddc01d4b613a6943c53724e9dc03e6675708545685cac8f1e29e` |
| corpus.json | `43c62b4c9616fefc4c2a32291cdc8b4735d6b410ee3063e20829f1f80a2c444f` | `43c62b4c9616fefc4c2a32291cdc8b4735d6b410ee3063e20829f1f80a2c444f` |
