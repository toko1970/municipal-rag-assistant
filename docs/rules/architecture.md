# アーキテクチャと変更境界

**適用対象:** `src/**`、`app.py`、`config.py` の実装・変更・レビュー。

## 実際の構成を起点にする

作業前に変更経路と呼び出し元を追う。既存のフラットな`src/`構成に、根拠なく `features/` や別レイヤーを作らない。新規ファイルは1つの責務を持たせ、既存モジュール間の境界に沿って配置する。移動・分割は依頼範囲に必要なときだけ行う。

- `app.py`: Streamlitの画面とユーザー操作の入口。
- `src/query_service*.py`: 問い合わせのユースケースと検索・生成・分類の連携。
- `src/persistence/`: PostgreSQLのmodel、session、repository。
- `src/*index*`, `src/vector_store.py`, `src/retriever.py`: ベクトル検索adapterと検索処理。
- `src/ingestion.py`, `src/visual_ingestion.py`, `src/visual_extractor.py`: 文書・図表の取込経路。
- `scripts/`: CLIや運用処理。評価用runnerは`eval/`に置く。

一覧は目安である。変更前に現行呼び出し経路を確認し、実装と設計資料が異なる場合は差を報告する。

## 責務・依存

- 業務判断、正規化、決定的計算は可能な限り外部I/Oから分け、入力と結果を明示できる形にする。
- DB、LLM/Embedding provider、Qdrant、GCS、時刻、環境変数などの副作用は既存のadapterやcomposition rootに寄せ、純粋な判断ロジックへ漏らさない。
- 一つの関数・ファイルは変更理由を一つに保つ。共通化は複数の実利用が確認でき、呼び出し側の責務が明瞭になる場合に行う。
- PostgreSQL、Qdrant、GCSの責務は`design/DATA_MODEL.md`と`design/TECHNICAL_DESIGN.md`を確認する。Qdrant等の派生indexを正本のように扱わない。
- `docs/`直下のMarkdownはRAG検索対象データである。例外として`docs/rules/`はAI向け開発ルール専用で、現在の取込処理では検索対象にならない。その他の開発判断・設計説明は`design/`、評価の説明は`eval/reports/`へ置く。

## 変更の進め方

- 受け入れ条件とデータの流れを先に整理し、変更に必要な最小の範囲を実装する。
- 既存のpublic interface、DB schema、回答schema、分類契約、retrieval/answeringの段階境界を変える場合、該当する設計・schema・評価手順を先に確認する。
- 既存仕様と実装が食い違うとき、実装へ仕様を寄せてテストを弱めない。根拠を確認し、解決できなければ止めて報告する。
