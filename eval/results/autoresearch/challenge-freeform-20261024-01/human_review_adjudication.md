# Challenge失敗差分レビュー結果

- レビュー者: ユーザー
- 対象run: `challenge-freeform-20261024-01`
- 候補config SHA-256: `cae1bafc46a98a30670f6e32c79508514a25580d80ba8f2a5d370e63a786ac0d`

## 判定

| Case | 人手レビュー結果 | judge採点の扱い | 重大度 | ブロッカー |
|---|---|---|---|---|
| CH-D05-F | 問題なし | judge採点を維持 | 軽微 | いいえ |
| CH-D05-P | 問題なし | judge採点を維持 | 軽微 | いいえ |
| CH-D06-F | baselineと候補に実質的な差なし。レビュー票の見出しが誤り | 個別スコアはbaseline/candidate双方successのため維持。見出しを訂正 | 軽微 | いいえ |
| CH-D06-P | 人事課への案内欠落はあるが、文書不足の全件で所管課への案内が必須ではない | judgeが指摘した欠落は記録する。重大な失敗とは扱わない | 軽微 | いいえ |
| CH-I07-F | 質問は個別の精算可否より制度上の取扱いを尋ねていると読むのが妥当。回答を失敗とするjudge判定は不適切 | baseline/candidate双方のjudge failを人手で成功へ訂正 | 軽微 | いいえ |
| CH-I07-P | CH-I07-Fと同じ | baseline/candidate双方のjudge failを人手で成功へ訂正 | 軽微 | いいえ |

## 集計への反映

元の`scorecard.json`と`records.jsonl`は機械judgeの原記録として変更しない。人手による訂正はこの文書で別管理する。

CH-I07のformal/paraphrase 2表現について、baselineとcandidate双方の判定を不成功から成功へ人手訂正すると、challenge全体の参考値はcandidate 79/80 (98.75%)、baseline 78/80 (97.50%)となる。シナリオ単位ではcandidateのみ成功1 (`CH-D05`)、baselineのみ成功1 (`CH-D06`)、双方成功38、双方不成功0。これは80表現全てを人手再採点した値ではなく、機械judge結果に今回の限定レビューで合意した2表現の訂正だけを適用した参考値である。

## 次工程への影響

本レビューで重大・ブロッカーとされたケースはない。候補promptの修正要求もないため、候補config hashを維持して自由文経路の統合候補作成・統合回帰・未使用fresh sealed holdoutの準備へ進める。`CH-D06-P`の確認先案内の欠落は軽微な注意点として統合回帰で再確認する。
