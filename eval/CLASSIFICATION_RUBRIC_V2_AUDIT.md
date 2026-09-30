# 回答分類Rubric v2の既存gold監査

- 実施日: 2026-09-30
- 対象: 開封済みText sealed holdout v1、50 scenario・100表現
- 外部API呼出: 0回
- 機械可読結果: [`classification_rubric_v2_audit.json`](classification_rubric_v2_audit.json)
- 再生成: `.venv/bin/python -m eval.build_classification_rubric_v2_audit`

## 1. 目的

新しい[`回答分類Rubric v2`](../design/CLASSIFICATION_RUBRIC_V2.md)を既存gold全件へ適用し、定義の矛盾と意図しない正解変更がないかを確認した。これはcandidate実装の精度評価ではなく、仕様の整合性監査である。

既存holdoutはこの監査より前に開封済みである。goldは書き換えず、元ファイルのSHA-256とv2による解釈を別artifactに保存した。

## 2. 結果

| v2の表示分類 | scenario数 | 判定理由 |
|---|---:|---|
| 根拠十分 | 30 | 適用規則があり、必要なclaimが完全支持され、人による確認要件がない |
| 判断要 | 10 | 適用する判断基準はあるが、結論を変える個別事実が未確認 |
| 文書不足 | 10 | review済みgold上、質問へ適用できる規則・判断基準がない |

- 旧goldから期待ラベルが変わったscenario: **0件**
- 人による確認要件: `case_fact` 10件
- `policy_judgment`正例: 0件
- `version_conflict`正例: 0件

判断要となったcaseは`TH008`、`TH014`、`TH016`、`TH025`、`TH031`、`TH033`、`TH035`、`TH036`、`TH045`、`TH050`である。

文書不足となったcaseは`TH003`、`TH012`、`TH013`、`TH017`、`TH019`、`TH021`、`TH026`、`TH038`、`TH040`、`TH048`である。

## 3. この結果が示すこと

Rubric v2は、既存goldの三分類を変更せずに判定理由を次の三軸へ分解できた。

1. 取得文書に適用可能な規則または判断基準があるか。
2. 生成claimが文書、質問の入力値、検証済み計算に支持されるか。
3. 文書の判断基準を使っても人が確認すべき事項が残るか。

この分解により、文書が取れていない状態と、文書はあるがGeneratorが答えを作れない状態を別のfailureとして測れる。質問内の「不明」「他条件は満たす」といった記述も、それだけで分類せず、文書の判断基準との関係から扱う。

## 4. 制約と次の検証

今回の監査だけではv2実装の精度向上を主張できない。既存goldから規範的なv2項目を割り当てたため、モデルがその構造を正しく生成できるかは未検証である。

また、既存holdoutの判断要10件はすべて`case_fact`であり、`policy_judgment`と`version_conflict`の境界を検証できない。この不足を補う仕様例として[`classification_rubric_v2_boundary_cases.json`](classification_rubric_v2_boundary_cases.json)に次の開発用controlを固定した。

- 文書が明示的に裁量を残す`policy_judgment`正例と、単なる注意書きの負例
- 基準日や優先規則では解消しない`version_conflict`正例と、通常の版選択で解消する負例
- 文書不足と人による確認要件を同時に返してはいけない意味的不整合例

これらはdevelopment fixtureとして使い、fresh sealed holdoutの代わりにはしない。runtime実装ではこのcontrolをunit testへ変換し、モデル評価では未知の言い換えと別制度familyを追加する。
