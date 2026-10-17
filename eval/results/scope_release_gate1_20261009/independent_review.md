# scope-classification-v2-candidate 独立レビュー

レビュー日：2026-10-09。担当：実装担当とは別のレビューエージェント。
対象：固定された `src/classification_scope_contract.py`、`src/query_service.py`、`src/rag_v2.py`、`src/answering.py`、`app.py`、`eval/evaluate_scope_release.py`、関連テスト・設計資料。
API呼び出し、候補ソース変更、holdout開封は行っていない。Gate 1 API実行中に実装と評価設計をレビューしたため、この文書はAPI全結果の最終採点ではない。

## 判定

**本番採用は保留。P1の版解決後の内容整合性不備を解消する必要がある。**
Gate 1の分類器単体結果にかかわらず、この候補の本番経路ではVersion Resolver後に不完全な回答を「根拠十分」と表示できる。今回の固定候補を途中で変更せず、修正は新roundとして記録することを推奨する。

ユーザーが確認した一般的権限と個別支給判断の境界は、POLICYの規約と整合している。文書不足と生成不足の分離、生成不備のラベルなし・claim非表示、既定値をv1に保つ方針は妥当。

## P1：版競合を解決しても、保留claimの支持と回答充足を再確認していない

場所：`src/classification_scope_contract.py:225-239`。

Classifierが「200円と300円が競合するため適用単価を確定できません」というclaimを `supported`・`answer_complete=true` とし、`version_conflict` のreviewを付けた場合、Version Resolverが基準日から一意に決まると判定すると、コードはreviewだけ削除する。元のclaimも支持・充足フラグも変更しないため、`decide_scope_answer` は `根拠十分` に昇格させる。求められた適用単価を回答しないまま、解決済みの競合があると断定する回答になる。

APIを使わないfake providerで以下を再現した。

- 質問：「2027年4月1日の適用単価はいくら？」
- 取得根拠：「2026年まで200円。2027年から300円。」
- 生成claim：「200円と300円が競合するため、適用単価を確定できません。」
- Classifier：対象=適用単価、規則あり、支持あり、充足あり、版競合reviewあり。
- Resolver：`version_conflict=false`、`resolution_basis=question_date`、confidence=0.95、既知根拠ID。
- 実際の返却：`status=SUCCESS`、`label=根拠十分`、上記の保留claimをそのまま表示。

ClassifierとResolverの不一致こそResolverが処理する場面なので、Classifierの初期出力が完全に正しいことを前提にはできない。新しい情報で版を決めた後、claimの支持・充足が成立する確認を必要とする。確認できない場合はラベルなしの安全な失敗へ落とすか、元の判断要を維持し、競合解決だけで根拠十分へ昇格させない。正しい単価claimと誤った保留claimの両方を回帰テストに入れる必要がある。

現在の `test_scope_version_resolution_is_guarded` は単価を回答するclaimだけを使うため、この不整合を検出しない。

## P2：Resolverの判断根拠とconfidenceを監査ログから再構成できない

場所：`src/classification_scope_contract.py:219-247,256-263`。

成功した解決で保存するのはprovider metadata、status、version_conflict、根拠IDのみであり、`resolution_basis` と `confidence` は欠落する。分類試行のconfidence列にも明示的にNoneを渡す。低confidence fallbackでは判定内容・根拠IDも保存されない。生のResolver出力を別に記録していないため、request IDで「なぜ版が解決したか」「どの閾値判断をしたか」を後から確認できない。旧v1経路はこれらを記録しており、新経路の監査性が後退している。

採用プロトコルGate 4の監査要件に合わせ、解析結果の `resolution_basis`、`confidence`、根拠ID、元出力または同等の診断を成功・fallbackの双方で保存すること。実際のpromptはversion-resolution-v1なのにログがversion-resolution-v2になっている点も、バージョンの意味を明示または統一する必要がある。

## 評価手法の確認と限界

- Gate 1は既知20表現・4診断・4表現反復の各両方式56呼出しで、独立したholdoutではない。旧goldを維持し、D03/D04の生成不備を新契約として別に採点する設計は妥当。
- promptへquestion/evidence/generated_answerだけを渡し、期待ラベルや不足条件goldを渡していない。入力・prompt・schema・主要ソースのhashを保存し、既存出力への上書きと実験再試行を防いでいる。
- `eval/evaluate_scope_release.py:101-115` は分類器と表示関数のみを比較し、本番のResolver、検索、生成、例外経路を実行しない。Gate 1用途として妥当だが、P1の安全性や本番全体の改善の証拠にはならない。今後の回帰では本番compositionを通す必要がある。
- 総合正味改善と危険側退行を分ける条件は妥当。未完走のsummaryは未実行をfalseとするため途中のimproved/regressedは暫定値にすぎず、完走前に改善数として報告すべきではない。
- known20の採点は主に最終label一致で、対象抽出や各claim支持の意味妥当性を独立に採点していない。Gate 2以降では計画通り対象・支持・充足・reviewの正解と意味レビューを追加する必要がある。
- 予算料金は管理仮定で公式料金ではないと明記されている。実運用のprovider設定と実験SDKのseed/出力上限が同一ではないため、採用前に本番経路の費用とlatencyを別途測定する必要がある。

## 実行した検証

次のAPIなしローカルテストが **47 passed**。

```text
.venv/bin/python -m pytest -q tests/test_classification_scope_contract.py tests/test_scope_release_evaluation.py tests/test_query_service.py tests/test_rag_v2_query_flow.py tests/test_app_smoke.py
```

これに加え、上記P1をメモリ内fake providerで再現した。既存テストが通ることと、本番採用の安全性が確保されたことは区別する。

P1の独立再現テストを `tests/test_scope_release_review_regressions.py` に `xfail(strict=True)` として保存した。元候補で **1 xfailed** を確認。これは既知欠陥を期待失敗として可視化するものであり、受入合格には数えない。修正後はxfailを外して通常の回帰テストとして実行する。

## 別roundのdraft修正確認（元候補の評価とは別）

上記レビュー確定後、実装担当は元候補ソースを `frozen_source/` に退避し、working copyを `scope-classification-v2.1-draft` に更新した。draftは高confidenceの版競合解消時、claimを昇格させず `GENERATION_INCOMPLETE`・ラベルなし・claim非表示・`VERSION_RESOLUTION_REQUIRES_REVALIDATION` へ安全停止する。

独立再現テストのxfailを外し、上記status/label/非表示/コード/Resolverメタデータをassertする通常テストへ変更した。**1 passed** を確認し、P1の具体的な不整合経路が安全停止になることを確認した。この保守策は正しい回答でも停止し得るため、回答率の影響は別roundの評価が必要である。draftをAPI評価済み、holdout合格、採用済みとは扱わない。

この確認時点ではP2の監査項目は未修正。元候補に対する「本番採用保留」の結論は維持する。

### P2のdraft修正を追加確認

その後のdraft修正について独立に再確認した。解析成功時は版解消・競合維持・低confidence fallbackのすべてで、`resolution_basis`、`confidence`、`version_conflict`、根拠ID、`raw_output`を保持する。解析失敗時も得られた生出力を残す。分類試行のconfidence列へ解析値を記録し、promptバージョンも実際の指示に対応するversion-resolution-v1へ統一された。

独立回帰テストを版解消・低confidence・競合維持・schema不備の4条件に拡張し、返却結果と監査イベントを確認した。**4 passed**。P2の指摘箇所はdraftで解消した。元候補のAPI成績・採用判断は書き換えず、draftの未実施の品質評価・回帰・holdoutを代替する証拠にはしない。
