# rag-portfolio-app

自治体の人事・給与制度に関する架空文書を検索し、根拠付きで回答するRAGの開発・評価・改善を説明するポートフォリオ。新規アプリを増やす前に、このリポジトリの完成度と説明可能性を高める。

## 技術と構成

- Python 3.11、Streamlit、SQLAlchemy/Alembic、PostgreSQL、Qdrant。モデル・Embeddingのprovider接続は既存adapterを通す。
- `app.py` はStreamlit UI、`src/` は検索・回答・分類・取込・保存のアプリ本体、`scripts/` は運用・取込用CLI。
- `tests/` は決定的なunit/regression testと、`tests/integration/` のローカルPostgreSQL・Qdrant統合test。
- `eval/` は評価set・runner・結果・報告。`design/` は仕様・設計・実装計画。`migrations/` はAlembic migration。`infra/` はTerraform。
- `docs/` 直下はRAGが検索する架空の制度文書。例外として`docs/rules/`はAI向け開発ルール専用で、RAG取込対象ではない。その他の設計説明は`design/`、評価説明は`eval/reports/`へ置く。

## 開発コマンド

- Lint: `python -m ruff check .`
- 決定的test: `python -m pytest -q -m "not integration" tests`
- ローカル統合test: `docker compose up -d postgres qdrant` の後に `python -m pytest -q -m integration tests/integration`
- ローカル起動: `streamlit run app.py`
- DB schema変更適用: `alembic upgrade head`（ローカル環境。適用前にmigrationルールを読む）

RAG品質評価は通常のtestとは別で、外部API費用・provider制限・holdout管理を伴う。評価を実行する場合は評価ルールを読み、ユーザーの依頼範囲・既存の評価計画に合う有限runにする。

## 作業前に読むルール

対象パスに一致するものをすべて読む。レビュー目的の読取でも適用する。

| 対象 | 必ず読む |
| --- | --- |
| `src/**`, `app.py`, `config.py` の実装・変更 | `docs/rules/architecture.md` |
| `tests/**`、テスト追加・変更 | `docs/rules/testing.md` |
| `eval/**`、回答品質・汎化評価の設計や実行 | `docs/rules/evaluation.md` |
| `migrations/**`、DB schemaや保存責務の変更 | `docs/rules/database.md` |
| `src/**`、`scripts/**` のログ・例外・秘密情報に関わる変更 | `docs/rules/logging.md` |
| PR前・差分レビュー | `docs/rules/review.md` |

機能変更・不具合修正では、可能なら要件や計画に根拠を持つテストを先に失敗確認してから実装する。適用可能な`$tdd` skillがある場合はその手順を使う。

## 回答品質の改善と評価の引継ぎ

回答品質の改善・汎化評価に着手する場合は、[汎化検証方針](eval/GENERALIZATION_VALIDATION_PLAN.md)と[採用判定プロトコル](eval/INTERVENTION_ADOPTION_PROTOCOL.md)を読む。検証済みの結果、未実施の計画、過去の正解規約と新しい分類規約を区別する。評価資料の入口は[評価レポート案内](eval/reports/README.md)。sealed holdoutのgoldはcustodian以外が開かず、候補調整にも使わない。

## 優先順位と不明点

明示されたユーザー要件、承認済み仕様・計画、該当する開発ルール、既存実装の順に根拠を照合する。既存実装だけを正解とみなさない。矛盾があり判断できないときは、影響と根拠箇所を示して止まり、推測で仕様・評価ゲートを変更しない。
