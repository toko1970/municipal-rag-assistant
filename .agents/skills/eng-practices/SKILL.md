---
name: eng-practices
description: 実装完了後に差分をGoogle Engineering Practicesの設計・機能・複雑さ・テスト・命名観点でセルフレビューし、PR前に直す。commit、push、PR作成前やセルフレビュー依頼で使う。
---

# eng-practices

出典: Google Engineering Practices, https://github.com/google/eng-practices (CC BY 3.0)。このチェックは独立レビューagentや人間のレビューを置き換えない。

1. `git status --short`と`git diff`、必要なら`git diff --cached`を読み、変更の目的と範囲を整理する。ブランチ名を決めつけた`main...HEAD`比較は避け、必要なら実在するbaseを確認する。
2. 次を確認する。
   - 設計: 既存のarchitecture/schema/契約に自然に沿い、目的に必要な最小変更か。
   - 機能: 正常系だけでなくRAGの根拠・保留・版・失敗経路が意図どおりか。
   - 複雑さ: 不要な抽象化、重複、広すぎる責務がないか。
   - テスト: 対応testが仕様を検証し、mockや期待値で骨抜きになっていないか。
   - 命名・コメント: 意図と「なぜ」が伝わり、古い説明が残っていないか。
   - データ・評価: migration、評価契約、holdout境界、API費用と結果報告を壊していないか。
3. 指摘は根拠と影響を添えて修正する。仕様や評価の裁定が必要なら自己判断で変えない。テスト未実施を実施済みと書かない。
4. 必要に応じ`docs/rules/review.md`の優先度で残課題とレビューしてほしい箇所をまとめる。
