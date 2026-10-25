# 4. 根拠に沿って回答し、回答可否を分類する

[READMEの構成図へ戻る](../README.md#仕組み) · [機能一覧へ](README.md)

## 1. 公開デモの機能

公開デモは、検索した制度文書・図表をGeminiへ渡し、回答本文と`根拠十分`・`判断要`・`文書不足`の分類を一回の生成で出します。参照欄では、検索されたチャンク本文、取得できた版情報、図表の元ページ画像を確認できます。分類が欠落した応答や生成不完全は、正常回答として扱いません。

検索された参照の表示と、回答中の各主張がどの根拠に支持されるかの検証は別です。公開デモはclaim単位の根拠対応、独立分類、決定的期限計算、従来のVersion Resolverを使いません。これらを持つ従来経路も、ローカル用として保持しています。

## 2. 実行経路の正本（2026-10-25更新）

この表を現行構成の案内の正本とします。設定名`production`は**ローカル既定の従来経路**を指し、現在の公開デモを意味しません。

| 項目 | 公開デモと同じ一回生成経路 | ローカル既定の従来経路 |
|---|---|---|
| `ANSWER_GENERATION_FLOW` | `autoresearch_candidate` | `production` |
| 生成モデル | `gemini-3.8-flash`。候補コードの固定値 | `LLM_MODEL_NAME`。既定`gemini-3.1-flash-lite` |
| 回答と分類 | 同じ生成で返す | 生成と独立分類を組み合わせる |
| 独立classification attempt | なし | あり |
| claim単位の根拠対応 | なし | あり |
| 決定的な期限計算 | なし | 根拠と入力が揃う限定条件のみ |
| 従来のVersion Resolver | 使用しない | 経路・条件に応じて使用 |
| 図表入力 | 取得した図表の構造内容と元画像 | 対応する従来経路の契約に従う |
| ログ | request、検索、生成attempt、最終回答、feedback | 分類・claim等を含む詳細記録 |

コード照合: [`src/rag_v2.py`](../src/rag_v2.py)、[`src/simple_rag_flow.py`](../src/simple_rag_flow.py)、[`config.py`](../config.py)。候補promptは[`src/freeform_prompt_candidate.py`](../src/freeform_prompt_candidate.py)に固定されています。prompt SHA-256は`cae1bafc46a98a30670f6e32c79508514a25580d80ba8f2a5d370e63a786ac0d`です。このhashだけでは、context・モデル設定・実装まで同じ評価対象であることは保証しません。

### ローカルで経路を選ぶ

[初回セットアップ](../README.md#ローカルで起動する)後、`.env`で次のいずれかを選びます。変更後はStreamlitを再起動します。

```dotenv
# 公開デモと同じ一回生成方式
ANSWER_GENERATION_FLOW=autoresearch_candidate
```

この経路では生成モデルは候補コードの固定値です。`LLM_MODEL_NAME`を変えても候補モデルは変わりません。ローカルのDB・index・画像を用意する必要があり、方式が同じでも公開環境とのデータ一致を保証する設定ではありません。

```dotenv
# ローカル既定の従来経路
ANSWER_GENERATION_FLOW=production
LLM_MODEL_NAME=gemini-3.1-flash-lite
CLASSIFICATION_CONTRACT_VERSION=v1
```

`simple`や分類契約`v2`・`scope_v2`は別の実験・検証用分岐です。この表の公開経路の成績や機能を、そのまま適用しません。

## 3. 公開状態の確認記録

**記録確認日時: 2026-10-25 20:27 JST。確認方法: GitHub Actionsの実行情報・deploy Jobログの読取。Cloud Runへの直接照会や新しい質問の生成は行っていません。**

| 項目 | 最後に確認できた公開実行の記録 |
|---|---|
| commit | `912f095130bfbd73bd9599cee25c6ff65bb91e75` |
| workflow | [CI #175](https://github.com/toko1970/municipal-rag-assistant/actions/runs/40170084210) |
| revision | `municipal-rag-assistant-00012-wdm` |
| ログ上のtraffic | 2026-10-25 15:54:21 JSTに100% LATEST、その時点のrevisionが上記 |
| CI結果 | 通常テスト・lint、PostgreSQL/Qdrant統合テスト、Terraform検証、deployが成功 |
| 画面確認の範囲 | health checkの成功はログで確認。今回の新規質問・実画面での意味品質確認は未実施 |

この表は**上記の実行履歴のsnapshot**です。現在のtrafficが同じであることを継続監視した結果ではありません。過去の#172（revision `00011-kwv`）の記録から更新しました。以後の公開状態はこの表だけを更新し、他ページは本節へリンクします。

今回整備した[リリース手順](../design/PUBLIC_RELEASE_RUNBOOK.md)は、次回から候補revisionをtraffic未切替で作成し、検査したrevisionを特定して公開するための変更です。上記#175がその新手順で実行されたとは扱いません。

## 4. 品質受入と公開判断

### 品質受入: No-goを維持

一回生成候補のfresh sealed holdoutは50シナリオ・100表現で総合76/100、事前閾値95%に未達です。分類macro F1は0.7691で、検索等にも未達項目があります。重大な根拠外断定はpolarity訂正後0/100で当該gateはPassですが、総合の**No-goは変わりません**。消費済みsetを新たな未見評価として再利用しません。[評価結果](../eval/results/autoresearch/freeform-fresh-holdout-20261024-01/FRESH_HOLDOUT_EVALUATION.md)

従来経路の日付改善後の2回目Text holdoutが未実施であることと、別の一回生成候補でfresh holdoutを実施したことは別の状態です。また、従来の図表sealed holdoutも分類閾値未達で総合不合格です。[図表評価](../eval/reports/VISUAL_RAG_STATUS.md)

### 公開判断: 品質合格とは別の履歴

[2026-10-25の導入判断](../eval/results/autoresearch/freeform-production-rollout-20261025/decision.md)には、制作者が130ケース回帰・80表現challengeの直接比較を確認し、追加修正なしで候補統合を指示したことが記録されています。その後のmainへの統合と公開は上記Actionsで確認できます。元のdecisionにある「未merge・未deploy」は判断時点の記録として保持しています。

判断材料のうち、公開集計で追えるものは以下です。直接比較に使ったM3/Q4と暫定machine compositeの成績は同一視しません。

| 材料 | 公開記録で確認できる結果 | 解釈の限界 |
|---|---|---|
| 130ケース統合回帰 | 暫定machine composite: candidate 129/130、baseline 125/130。改善4、退行0 | 改善4件は図表開発ケース。元runner・ケース別原票が不足し、baselineを従来の多段経路と断定できない |
| 80表現challenge | 限定訂正後candidate 79/80、baseline 78/80 | 元の一回生成promptと改良promptの比較。40シナリオでは候補のみ成功1・baselineのみ成功1。全件人手再採点ではない |
| 別途実施された直接比較 | M3/Q4等を使った採用判断の記述 | 原票と対応する母数・経路の照合が不足し、上の機械集計から再現したとは主張しない |

[評価の入口](../eval/reports/README.md)から原レポートと再現範囲へ進めます。初回holdoutの83/100と別集合の129/130をつないで、汎化精度の改善幅とは説明しません。

**本人確認が残る点:** No-goを維持しながら公開した技術的理由、独立分類・claim検証・期限計算を外した際に受け入れた制約、その制約をどの用途で許容したかは、公開記録だけでは確定できません。CI成功や「デモ」という位置付けで品質受入の未達を埋め合わせず、次回の公開にはsmokeの意味確認・実UI確認を別に記録します。

## 5. モデル・方式を選ぶまでの比較

生成モデル比較では、保存記録上、予約44件の総合成功はFlash 35/44、Flash-Lite 37/44でした。ユーザーが安全性を優先してFlashを選んだ経緯が記録されています。ただしFlash側だけに適用された訂正があり、両モデルの同一規約による再採点は原回答・原票不足で未完了です。この数値でモデルの優劣を確定しません。[選定記録と訂正上の制約](../eval/reports/GENERATION_MODEL_SELECTION_20261019.md)

従来の独立分類器は、開発用36件でGemini 3.1 Flash-Lite 31/36、BGE-M3 zero-shot 6/36の比較を経ています。これは公開中の一回生成方式の分類成績とは別です。[分類器比較](../eval/CLASSIFIER_MODEL_COMPARISON.md)

初回holdoutから、期限改善、過剰保留への対策、不採用候補、一回生成の比較までの判断は、[精度改善の総括](../eval/reports/ACCURACY_IMPROVEMENT.md)へまとめています。
