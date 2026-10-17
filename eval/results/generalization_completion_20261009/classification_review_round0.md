# 分類challengeの独立結果レビュー round 0

レビュー担当: validation_continuation。今回の分類fixture・runner・API実行・初期採点には参加していない。[事前採点規約](classification/scoring_protocol.md)、凍結質問・6文書、全88サービスの最終回答と関連する段階event、[意味採点](classification/semantic_review.jsonl)、[集計](classification/semantic_summary.json)、[実行担当レポート](classification/report.md)を照合した。レビュー中の時点固定原出力は[29件](classification_review_snapshot_029.jsonl)、[48件](classification_review_snapshot_048.jsonl)、[64件](classification_review_snapshot_064.jsonl)のsnapshotと各メモに残した。API、製品コード、原出力は変更していない。

## 判定

**既存Question Contract v2を今回の採用候補として次段階へ進めない判断を支持する。** 凍結oracle根拠の主指標12シナリオでは、両方式成功6、v2のみ2、v1のみ2、両失敗2で正味0。事前gateの正味+2に達せず、明確なA03・B02でv1からv2への新規composite退行がある。A01-paraphraseとB01両表現のgoldを曖昧としてA01/B01の2シナリオを除いても、v2のみ1・v1のみ2で正味−1。個別確定として読む代替感度もシナリオ正味−1。今回の開封済みchallengeで候補を修正して同じ問題を最終受入に使うべきではない。**レビュー由来のAPI再検証は不要（0/2回）。**

独立の全件意味照合で主composite、対象抽出、採否を変える採点誤りは認めなかった。レビュー中、index23のB02-paraphrase v2について、生成claimは質問事実とB1文書に支持されるのに後段分類器が`partially_supported`とした追加のfalse negativeを実行担当と照合した。採点担当はclaim支持判断の段階値を21/22から20/22へ訂正し、[全件採点](classification/semantic_review.jsonl)とレポートに理由を残した。主composite・採否・API出力は変わらず、これは**採点訂正であって実験再実行ではない**。

## 実行・再集計の独立監査

- [manifest](classification/manifest.json)が固定したchallenge/corpus/tasks/runnerと11の関連source/schema、計15ファイルのSHA-256は現保存ファイルと一致した。88凍結taskと88 service record・88意味採点はindex、質問ID、方式、根拠条件、反復が1対1で一致。214 API promptを調べ、`gold`、`review_note`、`required_answer_terms`、`forbidden_answer_terms`など採点キーの混入は認めない。全214呼出しは同じ`gemini-3.5-flash-lite`、retry 0、provider API error 0で、raw応答・parsed data・usageを保存した。
- 予定220から6 call少ないのは、B03 v2の6サービス（初回、反復、retrieved各2表現）がgeneration schema違反で止まり、後続分類callが実行されなかったため。service statusはSUCCESS 77、SERVICE_ERROR 6、GENERATION_INCOMPLETE 3、PIPELINE_INCONSISTENCY 2。API失敗0とサービス失敗11を混同しない。
- [料金訂正](classification/budget_price_correction.json)に従い、保存usageへ入力0.30/出力・思考2.50 USD/百万tokenを再適用すると、推定費用は合計**$0.1730593**（v1 $0.0504191、v2 $0.1226402）。元runner単価による合計$0.11354675とは区別する。214/400 call、0.1731/2 USD、実行約2602/3600秒で事前上限内。サービスlatency中央値はoracleでv1 24.081秒、v2 36.865秒で、12.2秒のAPI間隔を含む測定値である。
- 採点ファイルとは別の読み取り専用計算で、oracle表現成功v1 17/24・v2 19/24、scenario pairedは上記6/2/2/2と一致。retrieved12表現はv1 10/12・v2 7/12、6シナリオでは両成功2・v1のみ2・v2のみ0・両失敗2で[集計](classification/semantic_summary.json)と一致。反復16サービスは初回とstatus、最終回答、Question Contractが一致し、独立シナリオへ水増ししていない。

照合した原ログSHA-256は`api_attempts.jsonl`=`d880f5deab1844bc0f792c2deb4bd8519971184f2738963307c9ed2fac0eb247`、`service_records.jsonl`=`4520bcdccdbc7ea19861097f99207d90f88914095c1957b67b8ba54ff16eb5b5`。訂正後の採点SHA-256は`semantic_review.jsonl`=`45a3d52632e08326a2fec4a88387ff1e48de13a553fbccf5698d0c27209f87b5`。

## 失敗の意味と段階分離

- A03-formal v2は質問外の「確定できる場合の金額」facetを追加し、oracleで`GENERATION_INCOMPLETE`。retrievedでは最終保留回答が成功しても余分なfacetは残る。B02-paraphrase v2はfacetの文字化けに加え、正しく保留する生成claimを後段が`partially_supported`と誤判定し、安全停止した。A02-formal v2のfacet文字化けは初回・反復・retrievedで再現したが、最終表示は正しい。このため、最終compositeと質問対象抽出を別指標として扱う採点は必要である。
- C01-paraphrase v2は`根拠十分`のラベルでも、求めた補填額**6,000円**を本文に出さない。composite失敗の判定は妥当。B03 v2の6サービスは`cutoff_time`のschema違反で停止した。生成eventの`date_calculations`も起点・offsetと翌月3日の結果が合わず、時刻形式だけの問題とは評価しない。index78のB03 retrieved v1は同じ回答内の「2028年2月」＋「翌月3日17時」から2028年3月3日17時が一意なので、キーワードproxyに反して日付項目を意味成功とする判断を支持する。
- retrieved12表現はすべてoracle必須文書をBM25 top3に含む。A01-formalの旧/v2判定逆転、A02-paraphrase v2の不要な個別確認、C02-paraphrase v2の必要な個別確認における空`condition_ids`は、検索漏れより追加根拠下の解釈と参照整合性の問題。後二者はともに`REVIEW_WITHOUT_CONDITION`だが、前者はcase_fact自体が不要、後者はcase_factは必要でIDが欠けた。安全停止を正答へ数えない。

[段階別表](classification/report.md)のcoverage 22/22・10/10は「`insufficient`の有無」と文書不足goldの粗い二値一致、human 22/22・8/10は要確認typeの集合一致であり、各facetの完全な意味正答や`condition_ids`の参照整合性を意味しない。実行担当はレビュー中にこの定義をレポートへ明記した。生成時の文書不足6表現に誤った`case_fact`/`policy_judgment`があっても、後段分類器が最終表示から抑えたという段階差は残る。

## 解釈と未実施範囲

[別担当のgold監査](classification_gold_review.md)は、モデル予測を見ずにA01-paraphraseとB01両表現の読みの曖昧さを指摘した。ただし監査自体はAPI実行後で、API前に独立goldの意味を完全確定した証拠ではない。原goldは事後改変せず、除外・代替読みの感度を報告した。代替読みはシナリオ結果の感度であり、曖昧表現すべての新しい正式正解ではない。ユーザーへの分類解釈確認は進行中だが、曖昧さと無関係なA03/B02の退行および事前閾値未達により今回候補の採否は変わらない。

今回の比較は既存v1対既存Question Contract v2の**パイプライン全体**で、旧v1の過去goldを書き換えていない。明示的な2軸判定だけの因果効果、現行Qdrantを含む本番検索、代表的質問分布、既存100表現・130問の新規回帰、独立sealed holdout、検索からUI表示までの本番通し性能を証明しない。[汎化方針](../../GENERALIZATION_VALIDATION_PLAN.md)全体の完了ではない。候補が事前gateに落ちたので[採用プロトコル](../../INTERVENTION_ADOPTION_PROTOCOL.md)上の後続gateを省略した判断を支持する。v1の絶対的安全性や全分布での優越も本結果からは主張しない。
