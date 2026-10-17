# 表示信頼性の独立レビュー round 0

レビュー担当: validation_continuation（今回の表示fixture・runner・採点の作成と実行には不参加）。2026-10-09。追加API呼出し0、製品・runner・原出力・採点ファイルの変更0。

## 結論

`display_corrected/` の**合成provider入力を使ったサービス層fault injection**として、方法・保存結果・意味採点を受け入れる。正常対照はv1/v2とも3/3。異常9条件のうち「例外を送出せず、安全な表示を返した」は両方式3/9。根拠に反する支給確定claimは両方式1件表示した。v2は個別可否の未確認条件が残る2条件を`根拠十分`と表示し、v1はその2条件を`判断要`にした。サービス例外はv1が5件、v2が4件。この結果からv2を表示安全性の改善策として採用する根拠はない。

これは実LLM出力やWeb UIでの発生率・可視性の評価ではない。サービスが例外を送出した条件を「安全に回復した」と数えない。根拠付きの保留説明を表示することと、個別の支給可否を確定できることを区別する。今回の表示部分についてレビュー由来の再検証は不要（0/2回）。期限・分類を含むキャンペーン全体のレビューとは別の部分判定である。

## 方法と原記録の照合

ルートAGENTS、[汎化検証方針](../../GENERALIZATION_VALIDATION_PLAN.md)、[採用判定プロトコル](../../INTERVENTION_ADOPTION_PROTOCOL.md)、[Rubric v2](../../../design/CLASSIFICATION_RUBRIC_V2.md)を確認した。案内先`docs/rules/`は現ツリーに存在しない。以下では相対パスをこのキャンペーン直下から記す。

- [修正版manifest](display_corrected/manifest.json)の`task_sha256`は保存`tasks.json`と一致。記載された5ソースのSHA-256は現ファイルと一致し、保存`executed_runner.py`は現runnerと同一バイトだった。runnerはmain内で出力先新規性を確認し、タスク・manifestを書いてから24条件を実行する順序である。時刻の外部証明ではないが、ローカル記録とコード順序は整合する。
- 12種類×2方式の24タスク・24記録・24意味採点はID/armの順序が一致。各対の質問と根拠は同一。v1/v2は既存サービスのschemaと分類契約に合わせてpayloadを変えている。`Index`、`Provider`、`Logger`は固定スタブで、実検索・実モデル・実UIを通していない。
- 保存した全24件の`answer`、`answer_label`、`claims`、`degraded`、`invariant_code`、例外、イベント列を元fixtureと照合した。正常の`文書不足`は支給日規則を含まない修正根拠で、表示が根拠不在を正しく伝える。異常時のイベントは例外を送出した場合に`GENERATION_FAILED`/`CLASSIFICATION_FAILED`へ分かれ、返却された縮退表示と混同されていない。
- 自動[summary](display_corrected/summary.json)と[semantic_review](display_corrected/semantic_review.json)を独立再集計した。自動のv2 `fault_returned_safe_display=4/9`は誤確定claimの文字列だけを見るため`contradictory_missing`を安全と誤算する。意味採点ではそのラベル矛盾を不合格へ訂正し、[reviewed_summary](display_corrected/reviewed_summary.json)の3/9と一致する。自動値の上書きはない。

初回`display/`は`normal_insufficient`に支給日を含む根拠を与えていた。`display/invalidation.json`は全体を`superseded_pre_review_fixture_correction`として扱い、修正版へ置き換えたことを明記する。初回の数値はここへ合算していない。この自己点検は外部レビューに伴う再検証回数へ数えない。

## 条件ごとの意味判定

| 条件 | v1 | v2 | レビュー理由 |
|---|---|---|---|
| 正常：根拠十分、判断要、文書不足 | 3/3正しい | 3/3正しい | 根拠と個別条件、根拠不在の表示をそれぞれ全文確認 |
| `empty_claims` | 安全表示 | 安全表示 | claimなしを確定回答にしない |
| `contradictory_missing` | 安全な`判断要` | 不合格 | v2は「在籍日数の確認が必要」と言いながら、個別対象可否の質問へ`根拠十分`を付ける |
| `false_support_missing` | 不合格 | 不合格 | 両方式が根拠外の「支給が確定」を表示。v2はさらに`根拠十分` |
| `unknown_evidence` | 例外 | 安全表示 | v2は未知IDのclaimを非表示にして不整合を返す。v1はValueError |
| `unsupported_flag` | 安全表示 | 安全表示 | いずれもunsupported claimを表示しない。v2は`GENERATION_INCOMPLETE` |
| 生成/分類Schema不正、生成/分類provider失敗 | 4例外 | 4例外 | サービス返却なし。表示回復成功に数えない |

したがって異常9条件の内訳は、v1が安全表示3・誤claim表示1・例外5、v2が安全表示3・不適切な`根拠十分`1（`contradictory_missing`）・誤claimと不適切ラベルを併発1・例外4。項目は重複を明記したうえで数える。`false_support_missing`のv1も`判断要`へ縮退しただけでは安全ではない。

## 限界と再検証判定

比較対象は既存v1と既存v2のサービス関数で、新しい回復コードの前後比較ではない。固定した分類payloadをあえて誤らせる条件があり、v2の2件は実際の分類器が同じ誤りを出す頻度を示さない。実検索、LLMの自然な誤出力、UIの例外捕捉、正常入力への偽陽性の広い分布、反復揺らぎ、費用・latencyは対象外。API利用は0で、人工スタブの処理時間をモデル運用latencyとして報告していない。

有効な合成結果として再実行は不要。表示回復の採用可否を主張するには、誤支持フラグを含む根拠外claimを非表示にする対策と、Schema/provider例外から利用者へ安全に返す境界を具体化し、その変更前後を同条件で再評価する必要がある。`false_support_missing`と`contradictory_missing`は開封済みdevelopment例として扱い、新しい未使用条件で後続検証する。今回のレビュー由来再検証は **0/2回**。
