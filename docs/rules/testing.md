# テスト規律

**適用対象:** `tests/**`、pytest設定、およびテストの追加・変更。

## 何をどこで検証するか

- 純粋な計算、正規化、契約validation、分岐は決定的なtestで検証する。
- PostgreSQL/Qdrantをまたぐ保存・再構築・再実行・切替・障害回復は`tests/integration/`で実サービスを使って確認する。
- 外部LLM/Embedding APIを使う品質評価は`eval/`の評価runnerへ分離する。通常のCIをprovider APIや秘密鍵に依存させない。
- 既存のテスト配置やfixtureを確認し、似たテストを別の仕組みで重複させない。

## テストの強度

- 期待動作は依頼、承認済み仕様、計画、schema、評価規約のいずれかに結び付ける。現行実装だけから期待値を作らない。
- 変更に対応するtestを追加・更新し、可能な場合は実装前に該当testが期待した理由で失敗することを確認する。最初から通るなら、既存動作かassertの弱さかを調べる。
- `assert`や期待値を消す、弱い存在確認へ置き換える、常時成功するmockを使う、`.skip`で失敗を隠すことをしない。
- 境界条件は両側と境界そのもの、空・欠落・不正値、外部依存失敗を、変更に関係する範囲で検証する。
- mockは外部境界や失敗注入など必要な箇所に限定する。対象となる業務ロジックをmockで置き換えない。
- test同士を独立させ、順序・共有mutable state・既存ローカルDBの汚れへ依存させない。統合testは一時DB等の後片付けを確認する。

## 実行

- CI相当の通常test: `python -m pytest -q -m "not integration" tests`
- DB/Qdrant統合test: `docker compose up -d postgres qdrant` の後に `python -m pytest -q -m integration tests/integration`
- 変更に関係するtestを先に実行し、その後、影響範囲に応じてCI相当の範囲を選ぶ。実行していない確認を「通過」と報告しない。
- 外部API評価を通常testの代わりにしない。詳細は`docs/rules/evaluation.md`に従う。
