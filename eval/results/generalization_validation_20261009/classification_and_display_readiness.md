# 分類・表示の実装範囲と検証準備状況

作成日: 2026-10-09。担当: classification_probe（実施補助。独立結果レビュー担当ではない）。API呼出し0、本番コード編集0。

## 結論

前回の2軸実験そのものを質問からの対象抽出・最終表示まで通す実装は確認できない。一方、Question Contract v2候補は質問からfacetを自動抽出し、根拠支持と人手確認要件を分離して3分類へ変換する処理が既にある。両者の語義を同一視しないこと。

| 評価対象 | 現行の状態 | 根拠 |
|---|---|---|
| Question Contractの自動抽出 | 質問のみからrequested_facets/input_factsを抽出する実装あり | `src/query_service_v2.py:41`、同`:288` |
| facet単位の支持・個別確認 | evidence_coverage/claim_support/human_review_requirementsが存在 | `src/query_service_v2.py:71`、`src/classification_contract_v2.py:97` |
| facet最終表示 | 決定表と正常/不完全/不整合の表示あり | `src/classification_contract_v2.py:438`、同`:466` |
| 前回2軸の行政判断対象 | decision_targetをTHケースIDから人手指定。自動抽出でない | `eval/verify_failure_two_axes_20261009.py:16`付近 |
| 前回2軸の出力表示 | answer_supported/requested_value_determinableは探索実験のみ。srcに専用表示なし | 同スクリプトのschemaとsrc検索 |
| 本番での選択 | config既定はv1。環境変数v2で候補ルートを選択可能 | `config.py:40`、`src/rag_v2.py:68` |

`CLASSIFICATION_CONTRACT_VERSION`の実行時環境値やデプロイ先値は本調査では調べていない。上記「既定v1」を稼働環境の実測と扱わない。

## 表示回復候補

既存v1には `render_display_answer` が空claimや未解決条件を矛盾として検出し、`answer_question` が `render_pipeline_inconsistency` で安全表示へ戻す経路がある（`src/answering.py:356,400`、`src/query_service.py:485`）。したがって前回のrender関数単体の例外再現は、現在のサービス全体の未回復を証明しない。

v1回復ではmissing_documentのみなら文書不足、それ以外は判断要。answer_fully_supportedがtrueならclaim表示を許す。構造上の不整合時に支持フラグだけに依存してclaim表示することの安全性は別途検証対象となる。v2候補はPIPELINE_INCONSISTENCY/GENERATION_INCOMPLETEでlabel=None、claim非表示にする。これは安全な中断・縮退であり、質問への正答が回復した意味ではない。

## 今回新規に実行したAPI不要テスト

```text
.venv/bin/python -m pytest -q tests/test_answering.py tests/test_query_service.py tests/test_query_service_v2.py tests/test_classification_contract_v2.py tests/test_rag_v2_query_flow.py
49 passed in 4.21s
```

対象に正常表示、v1不整合回復、provider失敗の記録、v2不完全回答の非表示、未知claim参照のfail-closed、Question Contract失敗時の生成停止、候補配線を含む。FakeProvider/FakeIndex等のスタブ検証であり、実モデルの対象抽出精度・検索品質・未知制度汎化を測ったものではない。実行後の通常出力をこの文書に記録したが、全テストのログ別ファイルは保存していない。

## 比較可能な候補とrunner

1. **既存v1 vs 既存Question Contract v2**: `answer_question` / `answer_question_v2` を同一の固定SearchHit・モデル設定で呼ぶ評価用runnerを追加する方法。候補は追加抽出callを含むのでcall/token/latencyを別計測し、抽出facet・支持・人手確認・最終表示を分解採点する。旧v1 goldを修正せず、v2 goldの規約変更効果と同一規約でのモデル精度を分離する。evalのPython検索では `answer_question_v2` を直接評価する既存runnerは見当たらなかった。
2. **明示2軸候補**: 前回スクリプトの `requested_value_determinable` に至る自動対象抽出と表示を新しく固定する必要がある。既存Question Contractをそのままこの候補の実装済み証拠にしない。複合質問は対象ごとに評価し、保留説明が支持されることと給付可否が決まることを分離する。
3. **表示信頼性**: 同じ異常入力と正常対照をv1現行回復/v2安全停止へ与え、例外率、誤って止めた正常回答、根拠なし断定、表示claim数、degraded/invariant_codeを計測できる。異常入力を増やしたfault injectionはAPI不要。ただし回復策変更の効果を測るなら変更前baselineと変更点を固定する必要がある。

注意: `eval/compare_answer_contract_v2.py` のv2はanswer-output-v2と期限計算の候補であり、classification contract v2ではない。名前だけでこのrunnerを分類v2の評価として利用しない。

## 全方針達成に残る条件

今回の49テスト合格だけでは、未使用同型シナリオ、制度ごとの分離、意味保持変形、実検索から表示まで、反復、現行100表現/130問の新規paired回帰、独立sealed holdout、シナリオ単位の不確実性、費用/latency gateを満たさない。これらの実行を別に設計・記録し、未実施を「合格」へ置き換えない。

分類境界が難しいgoldのユーザー確認要件は採用プロトコル9.2に存在する。既存規約で明確なケースは評価できるが、新たな2軸規約の境界を自動判定だけで最終受入goldと確定しない。

開発ルールの案内先 `docs/rules/` は現作業ツリーに存在しない。ルートAGENTS、汎化方針、採用プロトコル、Rubric v2を読み、別の `ai-driven-development/docs/rules/testing.md` も参考に確認した。後者をルートへ適用されるAGENTS配下ルールと断定していない。
