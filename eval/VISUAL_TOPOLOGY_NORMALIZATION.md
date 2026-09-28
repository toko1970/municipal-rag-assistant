# Visual flowchart topology normalization

## 目的

消費済みvisual sealed holdoutで、内容とedgeを抽出できていても、先頭・末端nodeを`process`と返したためSchema検証で停止する失敗が見つかった。LLMを再試行せず、graph topologyから一意に判断できる役割だけを決定的に補正する。

## 設計

補正対象は`flowchart`に限定する。

1. node IDが一意で、全edgeの参照先が存在することを確認する。
2. incoming edgeがないrootが1件だけであることを確認する。
3. rootから全nodeへ到達できることを確認する。
4. startが未設定でrootが`process`なら`start`へ変更する。
5. outgoing edgeがない`process`を`end`へ変更する。

rootが複数ある、未知node参照がある、非連結である、別位置にstartがある場合は補正しない。曖昧なgraphを推測で有効化せず、既存validatorへ失敗として渡す。

## 代替案

- promptへstart/endの説明を追加する: モデル出力の揺れが残り、同じ入力へのretryを誘発しやすいため採用しない。
- Schemaからstart/end制約を外す: 経路の始終点を保証できなくなるため採用しない。
- あらゆるnode typeをtopologyで上書きする: decisionの意味を壊す可能性があるため採用しない。

## Development回帰評価

保存済みdevelopment raw 6件を再利用し、外部API call 0で同じgoldと比較した。

| 指標 | 変更前 | topology normalization |
|---|---:|---:|
| fixture | 6 | 6 |
| Schema valid | 6 | 6 |
| invalid / error | 0 | 0 |
| extraction gate pass | 4 | 4 |
| API call | 0 | 0 |

既存2 flowchartはすでに正しいstart/endを持つため補正件数0で、metricsも変化しなかった。table shapeの既存補正1件も維持した。

加えて、development flowchartのstart/endだけを`process`へ変えた回帰入力を単体テストへ追加した。変更前の意味ではstartが0件となる入力に対し、topology normalizationは2 nodeを補正し、同じSchema validatorを通過した。raw応答は保持し、normalized出力だけを変更する。

## 判断

developmentの既存品質を悪化させず、発見した失敗型をAPI retryなしで処理できるため採用候補とする。消費済みholdoutでは再実行しない。次回は新しいholdoutを用意して、未知図表での改善効果を測る。

結果artifactは`eval/results/visual_extraction_candidate_topology_v1/`に保存した。
