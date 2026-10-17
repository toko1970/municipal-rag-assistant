# Question Contract Gate B1 実行記録

- 実行日: 2026-09-30
- 対象: 開封済み分類不一致12表現、既存成功control 6表現
- 上限: 18 logical external calls、retry 0、US$0.05
- sealed holdout: 未使用
- 結果artifact: [`results/question_contract_v1_gate_b1_v1`](results/question_contract_v1_gate_b1_v1)

## 結果

2件目でGemini無料枠の日次500 requests上限に達したため、fail-fastした。追加retryとB2は実行していない。

| 項目 | 結果 |
|---|---:|
| logical external calls | 2 |
| 完了 | 1 |
| provider error | 1 |
| 推定費用 | US$0.0005985 |
| B1判定 | 未判定 |

これはcandidateの不合格を意味しない。18件を完了できていないため、Gate B1は評価不能である。

## 完了した1件の確認

`QC-TH011-paraphrase_or_noisy`では、モデルは次を返した。

- facet 1: 補助金の金額、`amount`
- facet 2: 補助金の申請期限、`date`
- 質問に明記された受験日、受験料、他条件充足をinput factsへ保持

必要な構造は意味上すべて満たした。一方、最初の自動採点規則は「提出」だけを許し、同義の「申請期限」を不合格にした。これはモデルの失敗ではなく評価器の偽陰性である。

期待するfacet数、answer type、入力事実は変更せず、期限facetの表現だけを`提出|申請`へ修正した。実行時datasetは`dataset_snapshot.json`として保存し、修正理由を`post_run_analysis.json`へ記録した。

## 次の手順

1. Geminiの日次枠回復後、新しいoutput directoryでB1を最初から実行する。
2. 18件すべてで、facetと必要な質問入力が一致した場合だけB1を通過とする。
3. B1通過時だけ、固定したQuestion Contractを使うB2 paired比較を実行する。

失敗runを上書きまたは再開せず、別runとして保存する。これによりAPI障害とモデル品質を混同しない。

## 2回目の実行

- 結果artifact: [`results/question_contract_v1_gate_b1_v2`](results/question_contract_v1_gate_b1_v2)
- logical external calls: 13
- 完了: 12
- provider error: 1（13件目の503。retryなし）
- 推定費用: US$0.00635025

12件の出力を意味レビューした結果は次のとおりだった。

| slice | 成功 | 確認数 | 主な失敗 |
|---|---:|---:|---|
| 過剰保留 | 6 | 9 | 条件充足の入力落ち2件、日付別facetの統合1件 |
| 危険な断定 | 0 | 3 | 可否を手続きへ変更2件、質問外facet追加1件 |
| control | 0 | 0 | 503でcontrol開始前に停止 |

`TH022 paraphrase`は`15:00`を正しく保持していたが、採点器が`15時`だけを許可した偽陰性だった。期待する意味は変えず、両表記を許可した。

B1は**早期不合格**とした。事前条件は18/18であり、完了済み12件のうち6件にContract自体の失敗が確認されたため、未実行controlがすべて成功しても合格できない。503は品質失敗へ数えていない。計画どおりB2は実行しない。

この結果から、単純なprompt調整より先に次を検討する必要がある。

1. facetを「質問で直接回答を要求された項目」へ限定する一般規則。
2. 日付や対象ごとに答えが変わる複数対象を、別facetへ分ける規則。
3. 質問に明記された条件充足や不明状態を落とさないinput fact coverage検証。
