# Holdout後の対象限定release gate

## 結論

開封済みtext holdoutで見つかった具体期限の弱点に対し、通常質問の回答契約を変更せず、具体的な
起算日から暦上の期限日を求める質問だけを`answer-output-v1.1`と決定的Python計算へrouteした。
固定500問への影響監査、新規表現のend-to-end評価、既存130問の保存済み回帰を統合したrelease
gateは合格した。sealed holdoutは再利用せず、production deployも行っていない。

## なぜ130問を再生成しなかったか

旧routeと新routeを固定500問へ適用した結果は次のとおりだった。

| 対象 | 質問数 | 旧route発火 | 新route発火 | 判定変更 |
| --- | ---: | ---: | ---: | ---: |
| 全variant | 500 | 0 | 0 | 0 |
| formal | 100 | 0 | 0 | 0 |

130問回帰はformal text 100問と別処理のvisual 30問で構成される。formal 100問で日付routeが変わらず、
visual 30問はこのtext composition rootを通らないため、今回の変更で既存130問の回答生成結果は変わらない。
全件を再生成すると、同じ処理へGeminiの揺らぎとAPI費用を加えるだけになるため、保存済みの
120/130（92.3%、退行0）を維持値として再利用した。

この120/130は日付改善による上昇値ではない。日付改善の効果は次のtargeted評価として分けて示す。

## 新しいroute表現のend-to-end評価

route関数だけの32件評価を通過した後、既存pilotとは表現が異なる4問を、生成、日付演算、分類、
表示まで通した。

- ISO日付と「提出期限日」
- slash日付と「締め切り日」
- ISO日付と「登録の期限日」
- 名前付き受理日と「期限となる日」

| 指標 | 結果 |
| --- | ---: |
| 総合成功 | 4/4 |
| route選択 | 4/4 |
| `date_calculations`生成 | 4/4 |
| 期待する具体日と分類・表示 | 4/4 |
| logical external calls | 8/12 |
| 推定費用 | US$0.002326 / US$0.01 |
| provider error | 0 |

最大2 repair roundのbounded loopとして開始したが、第1 roundで全件成功したため停止した。503だけ
最大2 retryを許可し、実際のretryは発生しなかった。sealed holdoutとproductionは使用していない。

## 表示fallbackの扱い

GeneratorとClassifierの意味的不整合は、安全表示へ変換して監査情報を残す。未処理例外を減らすが、
`PIPELINE_INCONSISTENCY`は総合成功へ数えない。したがって実行安定性と精度を混同しない。
この不変条件は`tests/test_query_service.py`の回帰testで検証する。

## release gate

- 既存130問: 120/130を維持。今回のroute変更対象0件
- 新規日付表現: 4/4総合成功
- 危険な断定の新規発生: 0件
- sealed holdout再利用: なし
- 新規API使用: 8 calls、US$0.002326
- 非integration test: 368件成功
- PostgreSQL・Qdrant integration smoke: 3件成功
- Ruff・diff検査: 成功
- release gate: **合格**

機械可読な統合結果は
[`post_holdout_targeted_release_gate_v1.json`](results/post_holdout_targeted_release_gate_v1.json)に保存した。

## 主張できることと限界

主張できるのは、既存development回帰を変えず、対象限定の4表現で具体期限のend-to-end処理が
成功したことまでである。改善後の総合holdout成功率は未測定であり、初回sealed holdoutの83/100を
改善後の値として書き換えない。和暦、相対日付、営業日・休日計算も対応範囲外である。
