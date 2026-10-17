# 質問範囲と判定規約を明示する分類候補

2026年10月9日。ユーザーが選択した「質問の判定対象を明確にし、その規約を分類器へ実際に渡す」方針の最初の比較候補。採用方針は[既存プロトコル](../eval/INTERVENTION_ADOPTION_PROTOCOL.md)、分類の語義は[Rubric v2](CLASSIFICATION_RUBRIC_V2.md)による。

実行後の結果は[比較レポート](../eval/results/classification_scope_policy_v1_20261009/report.md)を参照。Gate 1は合格したが、本番採用は未評価であり、主張支持と回答充足を同じfactorへまとめる問題が残った。

## 変更するもの

候補`classification-scope-policy-v1-candidate`は、分類LLMに渡す指示へ次を追加する。

1. 原質問の全要求を判定対象とし、文書に現れる質問外の実務条件を追加しない。
2. 一般規則・権限・確認先、条件付き算定、個別結論を区別する。「確定できるか」という語だけで区別しない。
3. 5つのfactorについて、true/falseを判断する条件を明記する。
4. 根拠の有無、回答の支持・充足、個別結論を変える不足事実や裁量を別々に判断する。

実際にモデルへ渡す文字列は[`src/classification_scope_policy.py`](../src/classification_scope_policy.py)を正とする。評価時に全文を`policy.txt`へ凍結し、各API呼出しの完全なpromptとhashを保存する。規約を文書に書いただけでモデルへ届かない状態を避ける。

## 最初の比較で固定するもの

質問・取得根拠・根拠順序・生成回答・出力schema・ラベル決定コードを固定し、旧指示と候補指示だけを切り替える。旧方式も同時期に新規実行し、保存時点の旧出力を対照として代用しない。例題のID・制度名に応じた分岐は追加しない。

この段階では別の対象抽出LLM呼出しやfacet schemaを導入しない。質問の対象は分類器が原質問から読む。したがって、対象抽出の説明を別fieldで監査する能力はない。対象を正しく読めたかは、一般規則と個別結論の対照で評価する。指示全体の介入であり、対象説明とfactor定義それぞれの寄与は分離しない。

## v1への評価用適用の限界

`answer_fully_supported`へ質問項目の充足も要求する。重要claimが正しくても、質問が求める具体額や項目が欠ければfalseとする。この意味をcandidate versionに明記する。

v1の最終決定表は`GENERATION_INCOMPLETE`を表現できないため、生成不足の診断2例はfactorを採点し、`文書不足`を正解goldにしない。単にこのpromptを本番経路へ接続すればRubric v2準拠になるとは扱わない。生成失敗の状態分離と表示契約は、別の変更と評価が必要である。

## Gate 1の固定条件

入力は開封済み[分類challenge](../eval/results/generalization_completion_20261009/classification/report.md)の既存v1が受け取ったoracle根拠・生成回答である。

- 既知10シナリオ・各2表現。曖昧なA01/B01を除外し、goldは変更しない。
- 診断4例：明示的裁量、未解決の版競合、根拠と矛盾するclaim、質問項目の欠落。新規作成だが独立した未見評価とは扱わない。
- 反復4表現：A02-paraphrase、A03-formal、A04-formal、C01-formal。初回に加えて両方式を各1回反復する。
- 合計56呼出し。モデルは実行前のローカル設定`gemini-3.1-flash-lite`、温度0、seed42、出力上限1024token。
- ケース順は固定seedで並べ替え、方式の先行順を交互にする。HTTP retryと実験retryはともに0、API開始間隔12.2秒、timeout45秒、全体20分。
- 予算管理用単価は入力1・出力10 USD/百万token、管理上限0.60 USD。公式料金の実測や請求額ではない。入力byte数・schema・余裕分と最大出力で次callを予約し、エラー時の不明費用も予約額を計上する。

主指標は、両表現でラベル一致と表示処理成功を満たすシナリオ数。正味改善1以上、表現単位の新規退行0、候補の危険な根拠十分0、診断4例の全factor一致、反復対象の両回正答、全呼出し正常完走を進行条件とする。失敗を反復で置き換えない。

既知入力と一人で作成した診断goldによるmechanism testであり、本番採用条件ではない。成功した場合も、独立したchallenge設計、境界goldのユーザー確認、代表回帰・安全性・fresh holdoutが残る。失敗した場合は結果を保存し、同じroundの候補を事後調整して再採点しない。

## 実装と再現

- [比較runner](../eval/evaluate_classification_scope_policy.py)
- [保存先](../eval/results/classification_scope_policy_v1_20261009/manifest.json)：API実行前に入力・task・schema・指示・source hashを固定。
- [検証テスト](../tests/test_classification_scope_policy.py)：payload不変・gold非混入、比較の対応、表示契約、危険な確定、生成不足診断、未完走時の不合格。

```sh
.venv/bin/python -m eval.evaluate_classification_scope_policy --output-dir /tmp/scope-policy-new
.venv/bin/python -m eval.evaluate_classification_scope_policy --output-dir /tmp/scope-policy-new --run
```

最初のコマンドは準備のみ。2つ目が課金APIを呼ぶ。既存出力へ上書きせず、実行開始済みのrunは再開しない。再実行には別のroundとして入力・予算の固定が必要である。
