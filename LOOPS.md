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
