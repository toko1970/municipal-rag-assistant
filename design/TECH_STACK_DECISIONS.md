# 技術選定と比較

## このページの範囲

READMEに掲載している構成について、何を実現するために採用したか、どの候補と比べたか、どこまで検証したかを記録する。比較試験をした選択と、要件・運用・学習目標から決めた選択を区別する。比較していないものについて、性能や費用が他製品より優れるとは主張しない。

本アプリは、架空の制度文書を使う転職用デモである。質問から根拠検索、回答・分類、引用表示、フィードバック保存までを一つの流れで説明できることを優先した。後続の設計では一部の技術を見直しているため、旧構成の採用理由と後続構成の判断も分けている。

StreamlitとLangChainについては、当時の選定記録や候補比較の証跡が十分に残っていない。以下に記す理由は、実装内容と要件から整理し直した事後的な設計説明であり、当時その候補を実測・正式比較したという意味ではない。後続プロジェクトの技術判断は、設計を見直した理由を補うために参照し、旧版の実測結果としては扱わない。

## 判断の要約

| 領域 | 採用 | 比較・判断の軸 | 結論 |
|---|---|---|---|
| アプリ | Python / Streamlit | Gradio、FastAPI + Reactとの画面構成比較 | 小さな対話画面、根拠・分類・図表の表示をPython中心で実装できる。負荷や操作性の比較試験はしていない。 |
| RAG連携 | LangChain | Google公式SDKを直接つなぐ構成 | 初期版ではLLM、Embedding、vector store、retrieverを共通の部品として組み合わせる目的で利用。運用制御の明示性を重視した後続設計では公式SDK・薄いadapterへ移行。 |
| 回答生成・分類 | Gemini 3.1 Flash-Lite | Gemini 2.5 Flashの旧run、分類器BGE-M3等 | 100問を完走し、分類比較では36件中31件正解。BGE-M3は6/36。評価範囲内の判断で、未見データ全般の優位ではない。 |
| Embedding | `gemini-embedding-001` | Gemini Embedding 2、Ruri v3 310M | 全根拠見出しHit@5で最高同率、MRR最高。候補変更による改善がなく維持。 |
| 検索index | Qdrant | Chroma実測比較、pgvector設計比較 | Chromaと順位・Hit@Kは同じ。精度向上ではなく、検索indexを正本DBから分け、filterや検索方式の拡張を試し、専用vector DBの構築・同期・再構築を学ぶ目的で選択。 |
| 正本・ログ | PostgreSQL | 旧JSONL、SQLite等の単純構成 | 文書・版・抽出要素・質問・検索・回答・feedbackを関係と制約付きで保存し、SQLで追跡・分析するため。SQLiteとの性能優位を測ったものではない。 |
| 画像・原本 | Google Cloud Storage | コンテナ内ローカル保存、DBへのbinary保存 | PDFやページ画像の原本を、アプリの一時領域やDB行から分けて保管する。Cloud Run上で原本を永続管理する境界として採用。保存方式間の性能試験はない。 |
| 実行環境 | Docker / Cloud Run | 手元の個別環境、VM等 | DockerでDB・検索index・アプリの実行条件をそろえ、同じアプリimageをCloud Runへ配布。公開デモに必要な運用範囲を抑え、起動停止をサービスへ委ねる。VMとの負荷・費用比較は未実施。 |
| CI/CD・IaC | GitHub Actions / Terraform | 手動デプロイ、他製品 | PR・pushで検査し、承認後にデプロイする経路と、クラウド資源の差分をコードで確認する経路を残す。製品間の性能比較ではなく、変更履歴と再現性を優先。 |

## アプリとRAG連携

### Python / Streamlit

画面の中心は質問入力と回答結果の確認である。回答区分、本文、引用、ページ画像、フィードバックを同じ画面で扱い、画面側に複雑な状態管理や独立したAPI公開面を設ける必要は小さい。そのため、PythonのRAG処理と同じ実行環境で画面を作れるStreamlitを初期版に選んだ。Gradioはモデルの入出力を試すデモ候補、FastAPI + Reactは画面とAPIを分けて細かなUI・契約を管理する候補として考えられるが、同じ画面を作って比較したわけではない。

この判断には明確な境界がある。公開利用者が増える、画面状態やアクセシビリティ要件が複雑になる、APIを別クライアントから使う、といった要件にはStreamlitが最適とは限らない。後続設計ではフロントエンドとAPIの契約を明示し、React + FastAPIを一つのCloud Runサービスから配信する構成を選んだ。これはStreamlitの性能が劣ると実測した結果ではなく、フロント・バックエンド分離と型付きAPIを実装して学ぶ目標を加えたためである。

### LangChain

初期版では、Googleの生成・Embedding、検索store、retriever、promptをRAGの部品として組み合わせるためにLangChainを採用した。モデルと検索実装をつなぐ共通interfaceを使い、ChromaからQdrantへの移行や検索・生成の実験を同一アプリ内で行う構成に合っていた。LangChainと公式SDK直結を同じ機能・負荷・障害条件で比較した記録はないため、「より高性能」「より低コスト」とは評価していない。

後続設計では、retry回数、入力・出力上限、費用予約、エラー分類、構造化応答の検証をアプリ側から明示的に制御する必要が強くなった。そのため、新しいRAG frameworkを追加せず、公式SDKと小さなadapterを中心にする方針へ移った。これは、初期版のLangChainを選んだ理由が無効だったというより、制御要件が具体化した段階で抽象化の境界を見直したもの。

## 生成・検索モデル

### Gemini 3.1 Flash-Lite

Gemini 3.1 Flash-Liteは回答生成と回答分類に用いる。回答生成では、旧Gemini 2.5 Flashの比較runに表示失敗があり、3.1 Flash-LiteはTop-5の8問を完了し、既存のformal 100問も完走した。分類モデル比較では開発用36問中31問正解（accuracy 0.861）だった。BGE-M3 zero-shotは6/36で、`根拠十分`の正例を一度も検出できなかった。mDeBERTaは実際の根拠入力が512 token制限を超えて採点前に停止した。

この比較は、生成モデル同士を大規模な同一条件で網羅したベンチマークではない。分類結果も小規模な開発用setである。現行モデルを維持した判断は、評価完了性、構造化出力、対象setでの分類結果に基づく。

### `gemini-embedding-001`

Embedding単独を比較するため、Qdrant、文書、chunk、Top-k、formal 88問を固定し、Gemini Embedding 2（768次元）とRuri v3 310M（768次元）を比較した。全根拠見出しHit@5は現行モデルとRuriが74/88、Gemini 2が72/88。最初の正解根拠順位のMRRは現行モデルが0.861で最良だった。Gemini 2は根拠Hit@5で正味2問悪化、Ruriは改善と退行が各4問で正味差なしだったため、現行profileを維持した。

ここで比較したのはモデル名だけでなく、次元と各モデル固有のquery/document入力規則を含むEmbedding profileである。Gemini Embedding 2の画像対応や画像そのものの検索品質は対象外。

## データストアと責務

### Qdrant — PostgreSQL内vector検索との比較

pgvectorをPostgreSQLへ追加すれば、DBサービスを一つ減らし、文書データとvectorを同じDBで管理できる。これは有力な代替案である。一方、このポートフォリオでは、文書・版・問い合わせ・費用・feedbackのトランザクション負荷と、類似度検索・metadata filterを分け、検索用データを独立して再生成できることを要件にした。Qdrantはpayload filter、複数のnamed vector、dense/sparse/hybrid検索を独立した検索層として扱える。加えて、PostgreSQLを正本、Qdrantを再構築可能な検索indexとする同期・照合・復旧を実装し、専用vector DBの運用境界を学ぶ目的があった。

ChromaからQdrantへの移行試験では、同一Embedding・chunk・Top-kの16問でHit@1、Hit@3、Hit@5が一致し、文書・見出し順位差も0件だった。したがってQdrantの採用を検索精度の改善とは説明しない。pgvectorとQdrantを直接同条件で性能比較した記録もない。選定は、責務分離、検索機能の拡張、学習目標に基づく設計判断である。

[Qdrant移行評価](../eval/QDRANT_MIGRATION_EVALUATION.md) / [目標仕様のvector store選定条件](TARGET_RAG_SPEC.md#9-ベクトルストア選定条件)

### PostgreSQL — JSONL・SQLite等との比較

質問と回答だけを一つのJSONLへ記録する小さな試作なら、ファイル保存は準備が少ない。しかし本アプリでは、文書と版、抽出要素、図表asset、検索結果、回答claim、根拠link、feedbackが相互に参照し、状態遷移・重複防止・一貫した更新が必要になる。PostgreSQLなら主キー・外部キー・一意制約・transactionで関係を保ち、migrationでschema変更を追跡し、SQLで一つのrequestに関わる検索・生成・分類・feedbackを分析できる。Qdrantに正本を持たせず、indexを消失時に再構築できる境界も作れる。

SQLiteはローカル単一プロセスの軽量代替になり得るが、公開構成のCloud SQL PostgreSQLと異なるDBで統合検証することになる。後続プロジェクトでは「SQLiteで代用してPostgreSQL特有の制約・transaction挙動を未検証にしない」方針を明記し、実PostgreSQLを開発・CI統合確認にも使った。PostgreSQLをSQLiteより高性能と測定したわけではなく、複数関係の正本、SQL分析、公開先との同一性、DB運用を学ぶ要件に合わせた判断である。

### Google Cloud Storage — DB・コンテナfilesystemとの比較

PDF原本、ページ画像、切り出した図表は、文書metadataや回答ログに比べて大きなbinaryである。これらをPostgreSQLの行へ埋め込まず、DBにはURIとSHA-256等を記録し、object storageへ分ける。Cloud Runのコンテナfilesystemを原本の永続保存先にするとrevisionの入れ替えやinstance破棄に結びつくため、非公開bucketを永続境界とした。アプリは`AssetStore` interfaceを通し、local開発ではLocalAssetStore、公開時にはGCSを使うことで、同じ処理から原本の保存・取得・hash照合を行える。

比較は容量・費用・速度のベンチマークではない。管理されたobject storageとCloud Runの接続・権限を確認し、原本・画像を別管理する設計判断である。

[データ保存責務](TARGET_RAG_SPEC.md#8-保存先と責務) / [公開構成](CLOUD_RAG_V2_DEPLOYMENT_PLAN.md#8-図表機能の公開差分)

## 実行・配布・変更管理

### Docker

開発者ごとのPython package、OS依存、起動順の差があると、ローカルで動いたコードをCloud Runで再現しにくい。Docker imageにアプリと実行依存をまとめ、PostgreSQL・Qdrantを含むCompose構成でmigration、取込、質問、feedbackまで起動できるようにした。同じimageをbootstrap JobとWeb serviceに使い、CIでbuildしてArtifact Registryへ格納するため、開発・初期化・公開で実行物をそろえられる。

venvからの直接起動も開発手順に残している。DockerがVMやmanaged containerより性能面で優れるという比較をしたわけではなく、環境再現とデプロイ単位を固定する役割である。

### Cloud Run

公開用Webアプリと初期データ投入Jobをコンテナで実行し、Cloud Runのrevision単位でimageと設定を特定できる。個別VMのOS、process supervisor、patch、常時稼働Web serverを自分で管理する案と比べ、短期ポートフォリオで必要な公開・更新・rollbackの運用範囲を抑えやすい。利用のない時間にWeb instanceを縮小できる点も小規模デモに適する。

ただしWeb instanceがscale-to-zeroしても、Cloud SQLなど常時稼働する依存サービスの料金は残り得る。実際にCloud SQLの固定費を別見積にし、利用がないだけで無料とは扱っていない。VM等と同条件の負荷・費用比較は未実施である。初回起動遅延、外部DB接続、secret/IAM、rollbackを含めて公開構成を記録した。

[公開RAG v2デプロイ記録](CLOUD_RAG_V2_DEPLOYMENT_PLAN.md) / [Cloud Run構成差分と費用](CLOUD_RAG_V2_DEPLOYMENT_PLAN.md#3-費用)

### GitHub Actions / Terraform

手動のconsole変更だけでは、どの設定がいつ変わったか、同じ構成をどう作り直すかをレビューしにくい。GitHub Actionsはpush/PRでtest・lint・Terraform検証を実行し、production environmentの承認後にのみデプロイする。TerraformはCloud Run、Cloud SQL、IAM、bucket等の構成をコードに置き、適用前planと適用後planを照合する。CIの短期認証と最小権限を使い、長期service account keyをrepository secretへ置かない構成を採用した。

他CI製品やIaC製品を同じworkflowで比較したものではない。既存GitHub repositoryの変更履歴とPRレビューをつなぎ、クラウド構成の差分を追跡すること、構成管理と承認手順をポートフォリオで示すことを選定軸にした。

## 選定を見直す条件

- UI要件が増え、画面状態や利用者向けAPIを独立管理する必要が出た場合は、Streamlitを継続するか再検討する。
- LangChainの抽象化がretry、費用、構造検証、障害分類の追跡を妨げる場合は、公式SDKとadapterの境界を優先する。逆に新しい統合が増え、共通interfaceの便益が運用負担を上回る場合は再評価する。
- データ量や運用人数が小さく、専用vector DBのfilter・hybrid・独立再構築が不要ならpgvectorを再比較する。
- Cloud Runのscale特性、固定費、region、cold startがデモ要件に合わなくなれば、別のcontainer hostingを費用・運用条件込みで比較する。
- 原本の保持、非公開アクセス、復旧条件が変わる場合はGCSの配置・bucket policy・backupを見直す。

## 詳細な評価記録

- [精度改善の流れ](../eval/reports/ACCURACY_IMPROVEMENT.md)
- [Embeddingモデル比較](../eval/EMBEDDING_MODEL_EVALUATION.md)
- [回答分類モデル比較](../eval/CLASSIFIER_MODEL_COMPARISON.md)
- [Gemini 3.1とTop-kの評価](../eval/GEMINI_3_1_TOP_K_ANSWER_EVALUATION.md)
- [技術設計](TECHNICAL_DESIGN.md)
- [データモデル](DATA_MODEL.md)
