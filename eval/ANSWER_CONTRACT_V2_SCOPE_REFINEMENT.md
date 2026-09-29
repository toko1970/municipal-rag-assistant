# 回答契約v2の質問範囲gate

## 目的

回答契約v2の合成fixture 12件pilotは12/12だったが、実際の開発質問でも退行しないかを確認した。
総合回答成功の採用条件は、回答要点、根拠支持、分類、表示契約がすべて成功し、既存成功を退行
させないことである。sealed holdoutは使用していない。

## 全面回帰を早期停止した理由

最初のv2.0回帰はGemini 503を2回挟み、成功済みrecordと使用量を引き継いで17問まで進んだ。
累計38 logical calls、US$0.01959875、retry 0である。

17問の時点で、既存成功だった`Q011`、`Q021`、`Q041`、`Q071`、`Q081`の5件が失敗した。
Generatorが質問に不要な個別事情まで`missing_conditions`へ追加し、表示契約が
`PIPELINE_INCONSISTENCY`へ安全縮退したためである。この時点で退行0の採用gateは達成不能に
なったため、残りのテキスト83問と図表30問を実行しなかった。

これはAPI障害による中断とは別の、内容品質による早期停止である。残りを完走しないことで、
最大US$0.18の評価予算と人手reviewを次の仮説へ回した。

## v2.1: missing conditionを質問範囲へ限定

Schemaや追加LLM callは増やさず、次の一般規則をGenerator promptへ追加した。

- 不足条件は、質問が明示的に求める結論に必須のものだけにする。
- 一般ルール、選択肢、項目一覧を答えられる場合、個別適用時の事情を不足条件にしない。
- 「この規程だけで判断できるか」という質問に対し、別規程によることを根拠から答えられる場合、
  別規程自体を不足文書にしない。

観測済み失敗、既存成功、判断要を含む10件で、分類・semantic status・回答要点を10/10で確認した。
20 logical calls、US$0.0102655、provider error 0だった。

ただし`Q071`は正解要点に加えて、質問対象外の諸手当停止条件も回答した。根拠付きではあるが
質問関連性が弱いため、厳密には全面回帰へ進めないと判断した。

## v2.2: claimも質問範囲へ限定

`claims`も質問対象へ限定し、異なる手当・対象者・手続を追加しない規則を加えた。
`Q001`、`Q066`、`Q071`は内容、分類、semantic statusがすべて成功し、`Q071`の余分な諸手当説明を
除去できた。`Q081`は最初の試行でGemini 503となったため品質判定から分け、時間を空けた独立runで
成功した。4件はすべて内容、分類、semantic statusに成功した。失敗試行を含むv2.2確認は
9 logical calls、US$0.00395175、各run内retry 0である。

## 現在の判断

- 表示契約の安全fallbackは、矛盾を隠さず監査できるため維持する。
- 決定的な暦日計算は合成fixtureで成功しており維持候補とする。
- v2.0の広い不足条件抽出は不採用とする。
- v2.2は質問範囲を狭める一般規則として小さな影響範囲gateを通過した。
- 全面回帰へ進む場合も、まずテキスト100問を評価し、退行を確認してから図表30問を実行する。
  テキストで採用gateを落とした場合は図表費用を使わない。

## 学習上の要点

- 合成fixtureは機能の動作確認には有効だが、実質問分布での退行を保証しない。
- safe fallback件数が増えた場合、単なる分類失敗ではなく、GeneratorとClassifierの意味契約を
  調べる必要がある。
- 全件を完走する前に採用gateが数学的に達成不能になったら停止する方が、費用対効果が高い。
- prompt修正は個別IDの語句へ合わせず、「質問の明示範囲」という再利用可能な規則にする。

## 全テキスト回帰とv2の不採用

v2.2をformal 100問で評価した。最初のrunは8問成功後に15 RPMの429で停止したため、成功recordと
失敗試行を引き継ぎ、既存holdout runnerで検証済みの5.1秒pacerと503限定bounded backoffを再利用した。
最終runは100問を完走し、累計204 logical calls、US$0.1070345、provider error 0、provider retry 0
だった。

内容review前の機械gateで、分類一致88/100、semantic success 93/100だった。不一致または
`PIPELINE_INCONSISTENCY`は15件あり、既存成功だった質問も含むため退行0の採用条件を満たさない。
`date_calculations`は100問では0件であり、広いtyped condition変更の退行を、日付計算の便益で
相殺する構成にもなっていない。この時点で図表30問は実行せず、v2をproduction候補から外した。

## 最終採用候補: 日付限定v1.1

変更を分離し、既存v1の文字列`missing_conditions`へ`date_calculations`だけを加えた
`answer-output-v1.1`を作成した。通常質問は既存v1を使い、具体的な起算日が質問にあり、具体的な
期限日を尋ねる場合だけv1.1へ決定的にrouteする。

最初のv1.1 pilotでは日付計算6/6、control 2/2だったが、classifier v1が質問中の日付を個別事情と
解釈し、日付6件を`判断要`にした。そこで日付routeだけに、質問中の起算日は既知事実であり、
アプリが追加した具体日claimは検証済みと伝える補足を加えた。再評価は日付6/6、control 2/2の
総合成功で、16 logical calls、US$0.0040205、provider error 0だった。

最終的な判断は次のとおりである。

- 通常質問は、既に120/130を確認したv1生成・classifier v1を維持する。
- 具体的な暦日期限だけ、v1.1、決定的date calculator、日付専用classifier補足を使う。
- typed missing conditionと広いclassifier v2は、実測退行により不採用とする。
- safe fallbackは、pipeline矛盾を隠さず表示・監査できるため維持する。
- 日付routeの未知表現は次の小さいholdout対象とし、同じ100問を再生成しない。

今回のv2.0以降の回帰・scope pilot・日付pilotは、失敗試行を含め303 logical calls、推定
US$0.1488915だった。上限US$0.20以内で、採用不能が判明した時点では後続の図表30問を停止した。

## Artifact

- `eval/results/answer_contract_v2_text_regression_v1`
- `eval/results/answer_contract_v2_text_regression_v2`
- `eval/results/answer_contract_v2_scope_pilot_v1`
- `eval/results/answer_contract_v2_claim_scope_pilot_v1`
- `eval/results/answer_contract_v2_claim_scope_q081_v1`
- `eval/results/answer_contract_v2_text_regression_v5`
- `eval/results/deadline_calculation_v1_1_pilot_v1`
- `eval/results/deadline_calculation_v1_1_pilot_v2`
