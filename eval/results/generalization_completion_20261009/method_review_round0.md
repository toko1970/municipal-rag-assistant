# 期限・分類の評価方法に対する独立レビュー round 0

レビュー担当: validation_continuation（今回の期限・分類のrunner、fixture、API実行、採点に不参加）。2026-10-09、両評価の実行中に方法だけを点検した。原出力・採点・runner・製品コードは変更せず、API呼出しも行っていない。結果の独立レビューは完走後に別途行う。

## 先行結論

現時点で実行停止を要する**正解のモデル入力混入、両armのモデル不一致、候補の実行中変更は確認しない**。期限と分類は異なるGeminiモデルを使用するので、両評価の数値を合算した性能比較には使えない。期限は現行指示対1文追加の固定根拠生成比較、分類は既存v1対既存Question Contract v2のサービス比較であり、表示の合成fault injectionとも別の作用層である。

分類の費用単価だけは事前manifestと公式料金が食い違う。[費用補正記録](classification/budget_price_correction.json)が33試行後に保存され、候補・モデル・問題順・出力を変えずに集計額を補正したことは妥当。ただし実行runnerの内部費用上限は旧単価のままなので、**補正累計額と次回分の余裕を別途監視**し、2 USDの予算遵守をrunner単独の保証と説明しないこと。現保存値は上限から十分低い。レビューによる実験再実行は現段階で要求しない（0/2回）。

## 期限の固定条件と再試行

- [事前manifest](deadline/manifest.json)は24シナリオ×2表現×両armの96タスクと、事前指定の6シナリオの反復24タスク、計120を固定。fixture/tasks/schema/runnerのhashは保存ファイルと一致した。全promptのハッシュを保存し、先行作成された`question`と4項目の`evidence`だけで構築され、`gold`・`review_note`は入らない。両armは同じGemini 3.1 Flash-Lite、温度0、seed42、schema、上限1024、固定根拠を使い、候補promptは1文追加だけ。
- 120有効タスク、総API試行上限160、1タスク最大3試行、開始間隔6.2秒、推定費用1 USD、壁時計2400秒を設定。content qualityを見てよい応答だけを再取得する経路はない。反復6シナリオは結果を見る前に固定した。前キャンペーンの3.1/2.5/3.5の部分出力は混ぜず、このディレクトリで新規に対比較している。
- 初回runnerは無効JSON/schemaを再試行対象にしていた。9有効API試行の後、[継続manifest](deadline/continuation_manifest.json)と保存`runner_continuation.py`に、無効なモデル出力は形式失敗として保持し、429/503/timeout/transportのみ限定再試行する規則へ修正した。最初の9試行は全て有効であり、訂正前規則に該当する出力の置換はない。元記録のhashと初回runnerを残し、結果を見た変更として隠していない。
- 継続runnerは既存試行からタスクと試行数を復元し、元の120タスクと総160試行上限を維持する。`quality_early_stop=false`で、既知の失敗を理由に途中選別しない。429は前キャンペーンで毎分上限だったため、時間を空けた再実行の設計は合理的。費用はprovider usageに基づく推定で、失敗呼出しの課金は確定できない。

## 分類の固定条件と採点設計

- [事前manifest](classification/manifest.json)、[採点規約](classification/scoring_protocol.md)、challenge、6文書corpus、88 frozen tasksのhashを確認した。runner hashは`eval/run_generalization_classification_20261009.py`と一致。12シナリオ×2表現を両armでoracle固定根拠に1回、4シナリオは両armで反復、6シナリオはローカルBM25取得根拠でも両armで1回、計88サービス実行・再試行前220 API callである。v2には質問facet抽出callが1回増えるため、call/token/latencyとprovider失敗を別集計する必要がある。
- 両armは同じGemini 3.5 Flash-Lite、温度0、seed42。v1とv2を**双方ともRubric v2**で評価する規約がAPI出力前に固定されている。これにより過去v1 goldの再定義を今回の同一規約下の精度改善として数えない。`challenge.json`には`gold`・`review_note`・期待語句があるが、サービスへ渡すのは`question`とoracleで指定された、またはBM25で検索された文書。既保存の47 API promptでも採点項目名やreview_noteの漏洩は確認しなかった。oracleの根拠ID選択は評価条件そのもので、正解ラベルをpromptに渡すこととは区別する。
- 質問からのfacet自動抽出（v2のみ）、根拠範囲、claim支持、人手確認条件、最終label・表示を別採点する設計は方針に沿う。ただし既存Question Contract v2と前回の明示的な`answer_supported/requested_value_determinable`の2軸実験は同じ実装ではない。結果レポートでは「2軸の専用表示実装まで検証」と言い換えないこと。
- 日本語文字bigramを含む凍結6文書のローカルBM25は検索ノイズを入れる隔離条件で、現行Qdrantの検索実測ではない。oracleとretrievedの差を検索寄与として分け、必要文書がTop-3から外れた場合を分類器の誤りと一括しないこと。シナリオ単位の成功には同じシナリオの2表現をまとめ、反復を独立標本へ水増ししない。
- `required_answer_terms`や`forbidden_answer_terms`による自動採点は暫定。採点規約どおり全重要claim、質問範囲、誤った個別確定を本文・根拠から確認し、方式名を可能な範囲で伏せた訂正履歴を残す必要がある。A02/A03等の分類境界は開発用合成goldであり、独立sealed受入goldとする前には採用プロトコル9.2のユーザーとの確認が必要。

## 費用・停止・一般化の制限

分類manifestは当初入力0.25・出力1.50 USD/100万tokenで固定したが、Gemini 3.5 Flash-Liteの[公式料金](https://ai.google.dev/gemini-api/docs/pricing)は入力0.30・出力2.50。補正記録は33試行時点の累計を公式単価で再計算し、以後の監視方法を明記する。**事前価格の誤りは実測モデル出力を無効にしないが、費用gateの判定には補正額を使う。** 元manifestと補正の前後関係を残し、事後の価格変更を「事前固定」と説明しない。分類runnerは実行途中再開に対応しないため、異常停止があれば同一タスクへ無断で新規実行を重ねず、保存済み試行の扱いと新計画を先に固定する必要がある。

いずれも開発用challengeで、代表質問分布、独立制度のsealed holdout、現行Qdrantを含む本番一連のRAG、既存100表現/130問回帰はこの2評価単体で満たさない。後続gateを止める場合も「候補不採用の理由」と「方針全体の未完了」を区別する。期限の採用判定は前キャンペーンの開封済み反例を参照しつつ、この完走データを別に報告する。分類と表示の結果を結合して同一リクエストの総合成功率にしない。
