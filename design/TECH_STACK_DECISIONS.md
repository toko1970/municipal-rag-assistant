# 技術選定と比較

## このページの読み方

採用理由を、実測した比較と設計上の比較に分けて記録する。実測比較は、評価条件をそろえて候補を動かした結果を示す。設計上の比較は、ポートフォリオの範囲、既存実装、運用責務から選んだ理由であり、性能が他候補より高いことを示すものではない。比較実験をしていない候補は、そのように明記する。

選定時点のポートフォリオ要件は、架空の制度文書を使う公開デモ、根拠と回答分類の表示、検索・回答の評価、文書とログの追跡である。実在自治体の本番業務や大規模運用を前提にした選定ではない。

## 採用技術と比較した候補

| 領域 | 採用 | 比較した候補と比較方法 | 採用理由・判断 |
|---|---|---|---|
| アプリ言語・UI | Python、Streamlit | 設計上の候補はGradio、FastAPIと別フロントエンド。UIフレームワーク間の負荷・操作性ベンチマークは未実施 | 既存のPython RAGと評価スクリプトを活用し、質問、回答、引用、分類を一つのデモ画面で確認できる。ポートフォリオでは画面と評価の反復を優先した。複雑な画面要件や多数同時利用を比較した結果ではない。 |
| RAG連携 | LangChain | Gemini SDKを直接呼ぶ構成が設計上の候補。両方式の性能比較は未実施 | 既存の検索・生成アダプターとPython実装へ接続しやすく、モデル呼出しをアプリ本体から分けられる。抽象化の費用や依存の少なさは候補間で計測していない。 |
| 回答生成・分類 | Gemini 3.1 Flash-Lite | 旧Gemini 2.5 Flashの実行結果、および分類器としてBGE-M3 zero-shot、mDeBERTa-v3-base multilingual NLIを比較。BGE-M3は36件中6件正解、mDeBERTaは入力長制限で評価前に停止 | Gemini 3.1は100問の実行を完了し、Top-5比較では旧モデルより表示失敗が少なく、構造化出力を継続評価できた。分類比較では36件中31件正解（accuracy 0.861）で、BGE-M3の6/36を上回った。評価は承認済み開発用36件で、未見データ全般の優位を示すものではない。 |
| Embedding | `gemini-embedding-001` | `gemini-embedding-2-768`、Ruri v3 310M。文書、質問、Top-kなどを固定し、formal 88件の検索根拠を比較 | 全根拠見出しHit@5は74/88でGemini 2と同率、MRRは0.861で3候補中最高だった。別候補への変更で総合的な改善がなく、現行profileを維持した。Ruriはローカル実行できる利点があるが、この検索評価では正味改善がなかった。 |
| ベクトル検索 | Qdrant | 移行前のChromaと16問で順位、Hit@K、ID整合性を比較。PostgreSQL pgvector等は設計上の代替候補で、同条件の実測比較は未実施 | ChromaとQdrantで取得文書・見出しの順位差は0/16、Hit@3とHit@5はともに16/16だった。Qdrantを精度向上のために選んだのではなく、payload filter、安定ID、PostgreSQL正本との責務分離を理由に移行した。 |
| 正本・ログDB | PostgreSQL | 旧JSONL保存を移行元として確認。SQLite等の小規模構成との負荷比較は未実施 | 文書、版、要素、質問、検索、回答、根拠、feedbackを関連付けて保存し、SQLで追跡・分析できる。Qdrantの検索indexを再構築できるよう、正本は別に保持する。JSONLは当初の記録方式であり、複数テーブルの関連やSQL分析に向けて置き換えた。 |
| 図表ファイル保存 | Google Cloud Storage | PostgreSQL内の画像保存、コンテナローカル保存が設計上の代替候補。保存方式の性能比較は未実施 | 図表画像をDBの構造化データと分け、非公開bucketに原画像を保存する。ローカル開発では同じAssetStore境界でローカル保存を使い、公開環境ではGCSへ切り替える。 |
| コンテナ・アプリ実行 | Docker、Cloud Run | ローカル直接実行とDockerを開発手順で併用。公開先としてVM等は候補になり得るが、ホスティング比較試験は未実施 | Dockerでローカルと公開用の実行環境をそろえ、Cloud Runへ同じイメージを配布できる。ポートフォリオのデモ公開とGitHub Actionsからのデプロイに適合する。公開構成ではCloud SQL等の継続費用も記録し、費用・運用とデモ要件を合わせて判断している。 |
| CI/CD・IaC | GitHub Actions、Terraform | 手動手順や他のCI/IaC製品との比較試験は未実施 | push時のlint・test・Terraform検証と、承認後のデプロイをワークフローに残せる。クラウド資源をコードで追跡し、planと適用後の差分を確認できる。GitHub上のソース・CIとの一貫性を優先した選択で、他製品より優れているという測定結果ではない。 |

## 実測比較の詳細

### QdrantとChroma

Embedding、文書、chunk、Top-kを固定した16問では、Hit@1が双方11/16、Hit@3とHit@5が双方16/16で、順位差はありませんでした。この比較で言えるのは「移行による検索退行を観測しなかった」ことです。Qdrant自体が検索精度を上げたとは評価していません。

[Qdrant移行評価](../eval/QDRANT_MIGRATION_EVALUATION.md)

### Embedding候補

formal 88問では、全根拠見出しHit@5が`gemini-embedding-001`とRuriで74/88、Gemini Embedding 2で72/88でした。最初の正解根拠の順位を測るMRRは現行モデルが0.861で最良でした。評価対象は文章検索であり、Gemini Embedding 2のマルチモーダル機能を評価した比較ではありません。

[Embeddingモデル比較](../eval/EMBEDDING_MODEL_EVALUATION.md)

### 回答分類モデル

開発用36件ではGeminiが31/36、BGE-M3が6/36でした。BGE-M3は`根拠十分`の正例を一度も検出できず、誤りを保留側へ寄せていたため、重大誤分類が0件というだけでは採用できませんでした。mDeBERTaは根拠が512 tokenを超えるため評価を完了できず、同じ責務での品質比較結果はありません。

[回答分類モデル比較](../eval/CLASSIFIER_MODEL_COMPARISON.md)

### 回答生成モデルとTop-k

Gemini 3.1 Flash-Liteに固定した8問比較では、Top-5からTop-8へ候補を増やすと必須内容一致は6/8から8/8になり、Generator概算費用は約36%増えました。これはTop-kの比較であり、同一条件の複数生成モデルを網羅したベンチマークではありません。モデル選択では、旧Gemini 2.5 Flashの表示失敗と100問完走実績も参照しています。

[Gemini 3.1とTop-kの評価](../eval/GEMINI_3_1_TOP_K_ANSWER_EVALUATION.md)

## 未比較の技術について

Streamlitと他UI、LangChainとSDK直接呼出し、PostgreSQLとSQLite、GCSとDB内保存、Cloud RunとVM、GitHub Actionsと他CI、Terraformと他IaCの比較ベンチマークは実施していません。これらはポートフォリオで必要な機能、既存実装との接続、データ責務、公開・再現手順を基に選びました。利用者数、費用、可用性などの要件が変われば再評価します。

Snowflake、Jev、画像Embedding、rerankerなどは、現時点の完成条件を超えるか、採用判断に必要な比較を終えていないため、必須構成には含めていません。特にSnowflakeは、ログ量と分析課題ができた後の拡張候補として扱っています。

## 参照

- [技術設計](TECHNICAL_DESIGN.md)
- [目標仕様](TARGET_RAG_SPEC.md)
- [公開RAG v2デプロイ記録](CLOUD_RAG_V2_DEPLOYMENT_PLAN.md)
- [精度改善の流れ](../eval/reports/ACCURACY_IMPROVEMENT.md)
- [評価レポート案内](../eval/reports/README.md)
