# Project loops

このファイルには、本リポジトリで繰り返し使うloopを保存する。各loopは実行前にCodex利用率を確認し、対象artifact、有限の作業範囲、停止条件を宣言してから開始する。

## Phase 0 evidence-first slice

一つのfixture familyについて、現行仕様とコードの証拠を確認してから、fixture、gold annotation、validator、testを縦に通す。

- 保存日: 2026-09-26
- 種別: 公開loopのプロジェクト向けadaptation
- 元loop: [The evidence-first feature loop](https://signals.forwardfuture.com/loop-library/loops/evidence-first-feature-loop/)
- 元loop更新日: 2026-06-24
- catalog record SHA-256: `d60bef000a1767e363ea8ab70b994abc5301c7e4bb45295a9beb0f0012ea9931`

### Prompt

Phase 0のfixture familyを一つだけ実装する。開始時にAGENTS.md、確定済みdesign、現在の評価コード、依存関係、testを読み、学習目標、確認できた事実、代替案、対象ファイル、永続化への影響、検証方法を示す。fixture、gold annotation、manifest、semantic validator、testのうち、そのfamilyを端から端まで検証するために必要な最小変更だけを行う。未知のデータと無関係な変更を保持し、外部APIや課金serviceは使用しない。Schema validation、semantic validation、hash・参照整合性、目視確認を実施する。修正は最大2 roundとし、同じ失敗が改善しない、仕様変更や課金・production操作が必要、または利用率が80%以上になった場合はcheckpointを残して停止する。完了時に変更、検証証拠、限界、学んだ概念、次のfamilyを返す。

## Fixture validation quality streak

fixture validatorの現実的な正常系・異常系を固定順で実行し、見つかった失敗を回帰testへ変える。

- 保存日: 2026-09-26
- 種別: 公開loopのプロジェクト向けadaptation
- 元loop: [The quality streak loop](https://signals.forwardfuture.com/loop-library/loops/quality-streak-loop/)
- 元loop更新日: 2026-06-17
- catalog record SHA-256: `87e61c0cf74eb37b170f12ca5c9194bb7df2e3fbec83fd73b014f8915f64acff`

### Prompt

実行前に対象fixture family、品質基準、有限のscenario一覧、Nを固定する。同じSchema、validator、実行環境でscenarioを一件ずつ実行し、結果を保存する。失敗した場合は原因を記録し、その失敗を再現する回帰testを追加して最小修正を行い、失敗caseと関連caseを通してからstreakを0へ戻す。難しいcaseを除外したり基準を下げたりしない。最大2 repair roundとし、N件連続成功、blocked、approval required、利用率80%以上、または2 roundで改善なしのいずれかで停止する。完了時にscenario、失敗、修正、回帰test、連続成功数、残課題を返す。

## Phase 0 contract conformance

Phase 0の仕様要求を証拠ledgerへ変換し、実装・test・文書との対応を確認する。

- 保存日: 2026-09-26
- 種別: 公開loopのプロジェクト向けadaptation
- 元loop: [The product contract conformance loop](https://signals.forwardfuture.com/loop-library/loops/product-contract-conformance-loop/)
- 元loop更新日: 2026-07-07
- catalog record SHA-256: `5fb38a9a64b35681948ddc328bddc177387e98fd9fa3418e1c257f533aeda7b5`

### Prompt

Phase 0に関係するTARGET_RAG_SPEC.md、TECHNICAL_DESIGN.md、DATA_MODEL.md、IMPLEMENTATION_PLAN.md、TEST_STRATEGY.mdから、具体的な要求、非目標、品質基準をledgerへ抽出する。各項目についてコード、fixture、manifest、test、READMEの現在の証拠を探し、proved、weak、contradicted、unimplemented、not applicable、blockedのいずれかと理由を記録する。確認できたhigh-impact mismatchだけを一件ずつ修正し、可能なら回帰testを追加する。節約モードでは監査1回、high-impact mismatchの修正を最大2件、再監査1回までとする。全要求が証拠付きで分類されsilent gapがない、blocked、approval required、利用率80%以上、または修正上限到達で停止する。未実装を合格扱いにせず、最終ledger、証拠、修正、test、残課題を返す。

## Text sealed holdout custody

未知のtext文書familyに対する最終受入setを、契約実装と非公開artifact作成に分ける。契約はEvidence-first feature loop、custodianの最終検査はQuality streak loopに基づく。

- 保存日: 2026-09-27
- 種別: 公開loop 2件を組み合わせたプロジェクト向けadaptation
- 元loop 1: [The evidence-first feature loop](https://signals.forwardfuture.com/loop-library/loops/evidence-first-feature-loop/)
- 元loop 1更新日: 2026-06-24
- catalog record SHA-256: `d60bef000a1767e363ea8ab70b994abc5301c7e4bb45295a9beb0f0012ea9931`
- 元loop 2: [The quality streak loop](https://signals.forwardfuture.com/loop-library/loops/quality-streak-loop/)
- 元loop 2更新日: 2026-06-17
- catalog record SHA-256: `87e61c0cf74eb37b170f12ca5c9194bb7df2e3fbec83fd73b014f8915f64acff`

### Prompt

契約実装では、AGENTS.md、TEST_STRATEGY.md、既存text development set、visual holdout contractを証拠として読み、50 scenario / 100表現のblueprint、公開manifest、Schema、semantic validator、test、README、custodian handoffだけを作る。source Markdown、公開質問、goldは作らず、別custodianタスクへ渡す。Schemaは形、validatorは件数・意味・hash・状態遷移・family分離を受け持つ。修正は最大2 roundとし、対象testと全test、lint、diff検査が成功、blocked、仕様変更が必要、または利用率80%以上で停止する。

CustodianはEvidence-first feature loopでTH001からTH050を一つずつ作り、各scenarioへformalとparaphrase_or_noisyを1件ずつ割り当てる。全artifact作成後、固定順の50 scenarioをQuality streakとして検査する。失敗時は原因と回帰testを残し、最小修正後にstreakを0へ戻す。50 scenario連続成功、最大2 repair round、同じ失敗が改善しない、仕様変更が必要、または利用率80%以上でcheckpointを残して停止する。実装タスクへ返すのは公開質問、hash、集計、検証結果だけとし、source本文とscenario別goldを漏らさない。

## Visual extraction versioned experiment

図表抽出のprompt、正規化、評価器を、保存済みraw出力と固定評価revisionで一要因ずつ比較する。

- 保存日: 2026-09-28
- 種別: 公開loopのプロジェクト向けadaptation
- 元loop: [The Revolve versioned-experiment loop](https://signals.forwardfuture.com/loop-library/loops/revolve-self-improvement-loop/)
- 元loop更新日: 2026-06-19

### Prompt

6件のvisual development fixture、モデル、prompt、Schema、評価revision、raw出力を固定し、baselineを保存する。各roundは記録済み失敗から一つの仮説だけを実装し、同じraw出力を再評価する。重要値、Recall、bbox IoU、semantic validation、token、遅延を比較し、回帰のない明確な改善だけをcheckpointへ昇格する。評価器を変えた場合は新revisionとしてincumbentから再採点する。合格、改善なし、過適合リスク、blocker、利用率80%以上で停止し、最良checkpoint、失敗例、rollback、次の判断を記録する。
