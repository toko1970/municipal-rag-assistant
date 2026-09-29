# 図表sealed holdout v2

## 目的

v1で見つかったflowchart抽出失敗を修正した候補を、未知のPDFと質問で一度だけ受入評価する。v2は改善箇所へ焦点を当てた4文書・10問の回帰受入であり、6種類すべての図表能力を再測定する完全調査ではない。

## 事前固定した構成

- 文書: process flow、decision flow、table、formを各1件、合計4件
- 質問: 10件（grounded 6、needs judgment 2、insufficient documents 2）
- retry: 0
- logical external call上限: 35（抽出4、文書Embedding 1、質問Embedding 10、回答生成10、分類10）
- 最低費用予約: USD 0.14、実行上限は候補固定時に記録する

受入閾値は[`scenario_blueprint.json`](scenario_blueprint.json)に事前固定した。評価結果が閾値未満でも質問やgoldを変更せず、失敗として原因を記録する。

## 未見性と状態遷移

1. `PLANNED`: このタスクで公開blueprintだけを固定する。
2. `SEALED`: 別タスクのcustodianが`.sealed/`にPDFとgoldを作り、公開質問とhashだけをcommitする。
3. `CANDIDATE_FROZEN`: development evidenceだけで候補commitと設定を固定する。
4. `PREDICTIONS_FROZEN`: PDFを一度だけ実行し、goldを読まず予測hashを固定する。
5. `OPENED`: hash照合後にgoldを開く。
6. `CONSUMED`: 採点結果と失敗分析を保存する。

PDFとgoldは`eval/visual_holdout_v2/.sealed/`へ保存し、Gitへ含めない。実装担当は`PREDICTIONS_FROZEN`になるまで内容を開かない。

## 公開検証

```bash
.venv/bin/python -m eval.validate_visual_holdout_protocol \
  eval/visual_holdout_v2/public_manifest.json
```

`--sealed-root`はcustodianが実体とhashを照合するときだけ使う。

## 学習上の要点

- development setは改善の選択に使い、sealed holdoutは選択後の受入判定に使う。
- 小さいv2は改善箇所の回帰確認に範囲を限定し、対象外のtimelineとrevision comparisonを合格実績として扱わない。
- 候補、予測、gold開封の順を固定すると、正解を見てから実装を合わせる情報漏洩を防げる。
