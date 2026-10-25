# 2026-10-25 改善作業の実施記録

## 対象と開始状態

- 依頼: 2026-10-25の改善引継ぎ資料 H00〜H09。作業中の追加指示により、次の改善実験 H07 は今回対象外。
- 開始HEAD: `912f095130bfbd73bd9599cee25c6ff65bb91e75`（引継ぎの基準と一致）。
- 作業ブランチ: `work/handoff-improvements-20261025`。
- 開始時: 新規clone、`main`、未コミット変更なし。既存のユーザー作業は上書きしていない。
- 作業範囲: 文書訂正、公開済み保存結果の検査、コード変更、外部API不要の検証。push・merge・公開切替、新しいLLM/Embedding API、sealed gold開封は実施しない。
- 環境: Python 3.11.17の隔離venvに固定requirements-devを導入。Docker・ghは未導入。GitHubは読取接続を使用。API秘密値は表示していない。
- 規約: AGENTS.md、architecture/testing/evaluation/logging/database/review、汎化検証方針、採用判定プロトコルを確認。

## タスク表

| ID | 担当 | 依存 | 作業範囲と状態 | 必要資料・残件 |
|---|---|---|---|---|
| H00 | 統括 | なし | 開始状態・規約・環境を確認 | 公開状態はActionsの履歴確認とライブ確認を区別 |
| H01 | 評価担当 | H00/H03/H04 | 総括の更新 | 原レポート・公開集計 |
| H02 | 統括 | H00 | 現行経路・公開判断の説明統一 | 公開理由の未記録部分は本人確認 |
| H03 | 評価担当 | H00 | 確定訂正、比較条件の整理 | 両モデル44件の原回答・原採点不足 |
| H04 | 評価担当 | H00/H03 | 公開資料棚卸し・非API集計検証 | 130回帰runner・差分CSV、challenge原票不足 |
| H05 | smoke担当 | H00 | 判定・smoke専用CLI・非APIテスト | ライブ回答の意味確認は別途 |
| H06 | リリース担当 | H05 | no-traffic候補・検査revision固定・承認手順 | 実クラウド確認は未実施 |
| H07 | ― | ― | 対象外（作業中のユーザー指示） | 候補実装・実験・評価準備は行わない |
| H08 | 統括 | H01/H02 | README導線・画面と担当範囲の確認 | 保存応答再生とlive生成を区別 |
| H09 | 独立レビュー担当 | 上記 | 関連テスト・差分レビュー | P0/P1解消を確認 |

## 実施結果

| ID | 状態 | 主な変更ファイル | 検証・証拠 | 残件 |
|---|---|---|---|---|
| H00 | 完了 | 本書 | 基準HEAD一致、clean clone、規約と環境確認 | なし |
| H01 | 完了 | `eval/reports/ACCURACY_IMPROVEMENT.md`、評価入口 | 6段階の意思決定、各原資料へのリンク、独立レビュー | なし |
| H02 | 完了／本人判断待ち | README、portfolio/04・05、技術選定・設計 | コードと分岐を照合、公開履歴を一箇所へ集約 | No-go下の公開理由・受け入れた制約の本人確認 |
| H03 | 資料不足（一部完了） | モデル選定、fresh holdout冒頭、比較条件監査 | 既存polarity訂正との整合、母数・判定者・訂正範囲を明記 | 保存された両モデル44件の原回答・原票による同規約再採点 |
| H04 | 資料不足（一部完了） | `eval/audit_public_evaluation.py`、監査レポート、audit.json、関連テスト | 公開7ファイルの算術整合が一致、13 tests＋4 subtests | 130回帰・80challenge・M3/Q4の原票レベル再現 |
| H05 | 実装済み・外部評価未実施 | smoke判定、管理CLI、cloud_bootstrap、関連テスト | 5ケース、正常/異常/予算/CLIの67 tests、独立レビュー | 実LLM応答の意味確認・実クラウドsmoke |
| H06 | 実装済み・外部評価未実施 | CI、promote.yml、release_gate、runbook、関連テスト | identity・未確認拒否・失敗/中断復旧の39 tests、独立レビュー | 実cloudの設定形状・IAM・Job・UI・promotion/rollback |
| H07 | 対象外 | 変更なし | ユーザーの追加指示を反映。候補実装・準備差分を除去 | 今回実施しない |
| H08 | 完了／本人判断待ち | README、portfolio/01、画像2枚・manifest、UI再生スクリプト | 旧公開保存応答を実app.pyへ再生して撮影、全hash一致、独立目視確認 | 未確認の制作分担、live公開UI品質 |
| H09 | 完了（非API検証と独立レビュー） | 本書、`compose.integration.yaml`とREADME | 下記648 tests、lint、リンク、独立レビュー | Docker統合・Terraform実行・実cloudは未実施 |

## 主な変更と効果

1. 初回holdoutから期限改善、分類・claim候補の不採用、一回生成の比較、fresh holdout、公開判断までを一つの総括から追えるようにした。
2. 公開一回生成とローカル既定の従来経路を統一した表で説明し、モデル、独立分類、claim根拠対応、期限計算、版解決、ログの違いを明確にした。
3. 公開aggregateを検査する新しいオフラインツールを追加した。原runnerの復元、ケース別再採点、新たな精度評価を行ったとは主張しない。
4. 不完全な回答dictをbootstrapが正常終了として通す問題を修正した。文書不足の参照0件は一律失敗にせず、通常・図表は期待根拠を必須にした。
5. 次回の通常CIをno-traffic候補の準備までにし、5件の意味・UI確認と候補identityの照合が済むまで公開を止める。明示revisionで切り替え、失敗・中断時は保存された配分への復旧を試み、未確認の復旧を成功と記録しない。
6. 通常回答と保留回答の実UIを掲載した。2026-09-23のFlash-Lite応答の再生であり、現在のFlashの新規出力の証明ではない。
7. 統合テスト用のDB、volume、127.0.0.1の別ポートを専用Composeへ分離した。実Docker起動は未実施。

## 実行した検証

環境はPython 3.11.17、固定`requirements-dev.txt`。次の通常検証を実行した。

```bash
.venv/bin/python -m pytest -q -m "not integration" tests
.venv/bin/python -m ruff check app.py config.py src scripts tests eval/audit_public_evaluation.py
.venv/bin/python -m eval.audit_public_evaluation
git diff --check
```

- pytest: **648 passed、3 skipped、3 deselected、4 subtests passed**（6.95秒）。
- skip 3件は既存のsealed gold非同梱条件によるもの。新しいskipや失敗を隠す変更は追加していない。goldは取得していない。
- deselected 3件は実PostgreSQL/Qdrantを使うintegration。Docker未導入のため実行していない。
- Ruff: 指定対象すべて成功。新規eval Pythonも含む。変更していない既存eval全体のlintを合格と主張しない。
- public audit: `AGGREGATE_CONSISTENT`。保存audit.jsonとの一致と7入力hash一致を確認。`case_level_reproduction=false`、同規約再採点未完了を明記。
- workflow: YAMLの読取、全run shellの`bash -n`、実workflow shellに対する外部gcloud/curl境界の失敗注入を確認。actionlintは未導入。
- UI: Streamlit 1.58.0、Chromium 134.0.6998.35／Playwright 1.51.1でローカル再生。2枚の質問・分類・回答・開いた根拠本文を目視。ソース・画像・再生応答のhash一致。
- リンク: 変更・追加した15 Markdownのローカルファイル参照に欠落なし。
- 差分: whitespace検査成功。`app.py`、`config.py`、`src/rag_chain.py`、`src/simple_rag_flow.py`、凍結promptは基準HEADから変更なし。

## 独立レビューと裁定

著者とは異なる担当・セッションで、docs/rules/review.mdと指定reviewer観点に基づいてレビューした。

| 対象 | 独立担当 | 指摘と処置 | 最終状態 |
|---|---|---|---|
| H05 | 評価資料担当 | P2: Markdown区切りだけを本文と扱う。文字・数字の有無で空本文を検査し、元の再現例と正常対照を追加 | 再レビューで解消 |
| H06 | 新規read-onlyリリースレビュー担当 | P1: traffic切替後のSIGINT/TERMでrollbackされない。開始/完了状態、EXIT/INT/TERM handler、実shell失敗注入11条件を追加 | 再レビューで解消 |
| H01〜H04/H02/H08 | smoke実装担当（この範囲の著者ではない） | P2: baseline未確認の回帰を390呼出しの上限とした。上限未設定・経路確定まで実行不可と訂正 | 再レビューで解消 |

追加の統括確認で、実UIの503 retryが「送信10件」と「問い合わせ試行の最大20回」を分けて記載すべき点を修正した。CLIのretry 0と実UIの既存retryを混同しない。独立リリースレビュー担当も既存retry・固定質問・candidateの分岐との一致を再確認した。

確認範囲の未解消P0/P1/P2はない。SIGKILL、runner消失、強制停止中の自動復旧・artifact保存は保証できないため、元の準備artifactから手動で実trafficを確認・復旧する手順を残した。実環境の権限・UI意味品質をローカルレビュー済みと読み替えていない。

## 評価値・記述の訂正

- fresh holdout冒頭の古い「重大誤りゲート失敗」を、既存の公開polarity訂正後の**0/100・当該ゲートPass**へ一致させた。総合**76/100・No-go**、採点原票・凍結manifestは変更していない。
- モデル予約44件の原値はFlash32/44、Lite37/44。過去のユーザー限定訂正後Flash35/44を算術確認しただけで、今回新たに3件を採点したものではない。両側同一規約の再採点は未完了。
- challenge原77/80対76/80、既存の限定訂正後79/80対78/80の算術を確認した。原機械scorecardは保持し、全件人手確認とは表現していない。
- 130回帰129/130対125/130と改善4件は暫定machine composite。初回83/100や別のM3/Q4直接比較と混ぜない。

## 不足資料・本人確認事項

### 原資料が必要なもの

- `eval/results/model_tier_test_confirmation_20261019/`の`test_cases.jsonl`、`records.jsonl`、`judgments.jsonl`、`metrics.json`、対応する匿名化済み承認ブック・規約。
- X014-T0/T1・X026-T0に適用した訂正規約と、X026-T3の解釈。元の両モデル回答に同じ規約を適用するために必要。
- `eval/run_freeform_integration_regression.py`、130回帰の`answer_diff_review.csv`、両回答・judge理由、manifestが参照する旧入力5資料。
- 80challengeの`records.jsonl`、入力packet、judge prompt／規約。
- 導入判断に記されたM3/Q4直接比較の原票、各指標の母数、両経路の実行設定。

公開リポジトリ・この作業領域では確認できなかった。ユーザーのMac等にも存在しないとは判断していない。詳細は[原資料一覧](../eval/reports/EVALUATION_EVIDENCE_AUDIT_20261025.md)。sealed・custodian資料や未開封相対評価は回収対象にしない。

### 本人確認が必要なもの

1. fresh holdoutのNo-goを維持しながら公開した技術的理由と、独立分類・claim検証・期限計算を外すことで受け入れた制約。
2. 要件定義全体、および下記の確認済み個別判断以外の評価軸について、本人が最終決定した範囲。
3. 基準90件の「実務経験者」の採点が本人によるものか。
4. コード・文書の執筆全体、AI支援、本人レビューの具体的な分担。

確認済みのモデル選定・限定訂正・統合指示に加え、追加探索で分類改善方針、分類境界、期待ラベル訂正、分類失敗分析に限った本人とAIの分担を確認し、[制作者の関与](../portfolio/01-ui.md#制作者の関与とai支援)へ出典付きで反映した。全工程の担当範囲へ広げていない。

## 外部実行・公開待ち

- 新しいLLM/Embedding API: **0回**。新しい改善実験・holdout開封: **なし**。
- GitHubへpush・PR投稿・merge・公開deploy・traffic変更: **なし**。ローカル作業ブランチで変更をまとめる。
- 次回のsmokeは固定5件、問い合わせ全体の試行上限5、CLIとJob retry 0。公開candidateでは通常1生成＋1Embedding/質問。SDK内部HTTP retryまでの厳密な上限とは区別する。
- タグ付き実UIの手動確認は最大5質問、手動の追加retryなし。アプリの既存503 retryは1質問につき最大2回なので、UI生成のprovider試行は最大15回となり得る。JobとUIを合わせた通常予定は10生成＋10Embeddingで、LLMの最大試行は20回。Embedding側は別途provider設定を確認する。
- 外部実行の承認予算は今回0。実行前に使用単価・入力上限・出力上限・画像入力を含む有限費用を記録する。予算の許可がなければ実行しない。
- 不合格・provider障害・入力/identity不一致・未確認の意味/UI項目・予算不足で停止し、元trafficを維持する。出力は新しいrun/attempt別のcandidate・review・promotion artifact。
- 実cloud未確認項目と復旧手順は[公開リリース手順](PUBLIC_RELEASE_RUNBOOK.md)を参照。今回の結果を新しい回答品質の向上や公開受入成功とは説明しない。

## ローカル資料の追加探索（2026-10-25）

ユーザーの追加指示により、アクセス可能な作業フォルダ・添付領域・別のレビュー用コピーを探索した。sealed・custodian・未開封相対評価・秘密設定を除外し、ignoredな通常ファイルも確認した。元runner・回答原票・採点ブックの新規回収はない。ユーザーのMacの元フォルダはこの環境に接続されていないため、原資料は「未共有・未取得」のままとする。

- 追加で確認した判断: 分類器へ質問範囲の規約を渡す方針の選択、一般的権限と個別支給判断の境界確認、v1.1の3シナリオ15表現の期待ラベル訂正。
- 追加で確認した分担: 分類失敗分析で、期待ラベルはユーザー承認、主原因の初回割当てはCodex。当該分析に限る。
- 90件の採点資料の具体名: 「実務経験者回答レビュー用_90件統合版.xlsx」。当時のレポートはリポジトリ外保管と明記。本体は未取得で、採点者が本人であるとはまだ断定しない。
- 根拠は既存の公開作業記録であり、新しい本人発言の原本・採点ブックの回収ではない。生成された面接回答は担当実績の一次証拠として採用しない。
- README、portfolio/01、原資料監査、本書を更新。H07、新規API、採点変更、公開操作は実施していない。
- 追加差分4文書の参照先とwhitespaceを検査し、著者以外の担当が指定出典と照合してP0/P1/P2なしと判定した。文書のみの追加変更のため、既存のコードテストは再実行していない。
