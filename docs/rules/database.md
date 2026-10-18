# PostgreSQL・Qdrant・migrationの規律

**適用対象:** `migrations/**`、`src/persistence/**`、`src/qdrant_index.py`、vector/asset保存責務の変更・レビュー。

## データの責務

`design/DATA_MODEL.md`と`design/TECHNICAL_DESIGN.md`を正本として確認する。概ねPostgreSQLはdocument/version/extraction/query/eventの永続記録、Qdrantは検索用index、GCS/asset adapterはvisual asset本体の保存を担う。実際の現行schemaと設計資料を変更前に確認し、この説明を理由に既存責務を再設計しない。

## Migration

- 適用済みmigrationを書き換えない。変更は新しい前進migrationで行い、upgrade経路を守る。
- 制約追加・型変更・削除・データ変換では、影響データ、既存参照、再実行時の挙動を先に検査する。破壊的なDB操作や本番操作を自律実行しない。
- migrationのupgrade/downgradeを既存プロジェクトの方式で確認する。運用上forward-onlyの資料と矛盾するdowngrade前提を追加しない。
- PostgreSQL更新とQdrant更新の間で失敗した場合の整合性・再実行・generation/activation動作を、既存設計とintegration testに照らして確認する。
- ローカルDBのresetは、そのDBが使い捨て開発環境だと確認できる場合だけ行う。外部・共有・本番環境のデータ変更は明示的な承認と手順なしに行わない。

## Invariants

- 一意性、参照整合性、値域、同時実行に関する不変条件はDB制約で守れるか検討する。
- 認可・業務手順・provider/GCS/Qdrantとの整合をDB制約だけで解決できると仮定しない。
- schema・migration・repository・Qdrant payload・asset参照・関連fixture/testを一体で確認し、途中状態や旧世代データの扱いも報告する。
