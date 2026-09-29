# 日付計算route判定のbounded loop

## 結論

日付改善の最初の実装でも「小pilot、失敗分析、責務縮小、再pilot」という反復は行ったが、開始前に
対象artifact、最大round、停止条件、費用を固定した正式なloopにはしていなかった。この不足を補うため、
`should_use_deadline_calculation()`だけを対象に、外部APIを使わないbounded loopとして再評価した。

## loopを選んだ理由

- 対象: [`src/temporal_evidence.py`](../src/temporal_evidence.py) の日付計算route判定
- 学習目標: LLMに渡す前の決定的なroute判定を、適合率と再現率で評価する方法を説明できること
- 採用loop: `LOOPS.md`に保存済みの「Fixture validation quality streak」と
  「Visual extraction versioned experiment」の組合せ
- loop適性: 各roundの誤判定が次の一般ルール変更へ直接つながり、同じ固定ケースを約5秒で再実行できる
- 費用: Gemini・Embedding・クラウド呼び出し0回、推定API費用US$0
- 代替案: 130問のend-to-end回帰は、route関数だけの修正に対して時間とAPI費用が大きいため、
  この局所評価では採用しない。日付生成全体を本番反映する前の総合回帰は別gateとする

公開Loop Libraryのlive catalogは実行時に取得できなかったため、公開loop名や更新情報を新しく推測せず、
取得済みの出典とhashを持つプロジェクト保存版を使用した。

## 実行契約

- 入力artifact: [`deadline_route_cases.json`](deadline_route_cases.json)
- 開発split: 20件（具体期限10、非対象10）
- 凍結acceptance split: 12件（具体期限6、非対象6）
- 1 roundで変更するもの: route条件の一まとまりだけ
- 最大修正round: 2
- 停止条件: 開発split全件成功、2 roundで改善なし、仕様変更が必要、利用率80%以上のいずれか
- acceptance: 開発splitの停止後に1回だけ実行し、その結果を見て追加修正しない
- sealed holdout: 不使用。acceptance splitは同じ開発者が作成した小規模な未知言い換え確認である

## 結果

| 段階 | 正解 | 適合率 | 再現率 | FP | FN | 修正 |
| --- | ---: | ---: | ---: | ---: | ---: | --- |
| baseline | 11/20 | 54.5% | 60.0% | 5 | 4 | 変更前 |
| round 1 | 20/20 | 100% | 100% | 0 | 0 | 一般化したroute契約へ変更 |
| acceptance | 12/12 | 100% | 100% | 0 | 0 | 追加修正なし |

round 1では次の条件をコード化した。

1. 西暦年月日を和文、slash、ISO形式で受け付ける。
2. 日付が起算日として使われていることを、日付後の助詞または名前付き起算日で確認する。
3. 「期限日」「提出期日」など、具体的な暦上の日を求める表現に限定する。
4. 営業日、開庁日、休日除外は決定的calculatorの対象外としてrouteしない。

baselineの誤りごとの特例や質問IDはproduction codeへ入れていない。第1 roundで停止条件を満たしたため、
第2 roundは実施しなかった。acceptance splitは実行後に回帰testへ昇格した。

## 限界と次のgate

- 32件はroute契約を狙った小規模評価であり、RAG全体の回答成功率や日本語全般への汎化を示さない。
- 和暦、相対日付、年月だけ、営業日・休日計算は意図的に通常経路へ残す。
- 新しい起算日の名詞は列挙へ追加が必要になる可能性がある。運用ログでfalse negativeを監視する。
- 本番反映前には、日付生成・分類・表示までを含む回帰と既存130問の退行確認を別に行う。

## 後続のrelease gate

固定500問を旧routeと新routeで監査した結果、formal 100問を含めて発火・判定変更は0件だった。
そのため既存130問を再生成せず、保存済み120/130を維持値として再利用した。新しく対応した表現4件は
生成、決定的計算、分類、表示まで4/4で成功した。8 logical calls、推定US$0.002326、provider error
0である。詳細は[`POST_HOLDOUT_TARGETED_RELEASE_GATE.md`](POST_HOLDOUT_TARGETED_RELEASE_GATE.md)を
参照する。

## 再実行

```bash
.venv/bin/python -m eval.evaluate_deadline_route \
  --input eval/deadline_route_cases.json \
  --split development \
  --output-dir eval/results/<new-output-directory>
```

`--output-dir`は既存directoryを拒否するため、過去の実験結果を上書きしない。
