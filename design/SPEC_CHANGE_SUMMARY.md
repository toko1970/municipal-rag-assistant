# 仕様・設計の変更概要

## 1. 位置づけ

最初の仕様案から独立レビュー後の最終仕様までに変わった点を、学習と面接説明のために記録する。ここでいう「以前」は、`TARGET_RAG_SPEC.md`が単独の方針案だった時点を指す。

## 2. 変更した点

| 項目 | 以前 | 現在 | 変更理由 |
|---|---|---|---|
| 設計資料 | 目標仕様1文書が中心 | 技術設計、データモデル、実装計画、テスト戦略、JSON Schemaへ分離 | 二人の実装者が同じ構成を作れる粒度にするため |
| PostgreSQLとQdrant | point IDを対応させ、Qdrantを再構築可能にする方針 | transactional outbox、staged/active抽出世代、reconciliation、全index更新時だけalias切替 | DBと検索indexの部分失敗を回復できるようにするため |
| 文書の状態 | `DRAFT / PROCESSING / ACTIVE / FAILED / RETIRED` | 取込準備状態、`PUBLISHED / WITHDRAWN`、施行期間を分離 | 過去版を基準日検索しつつ、誤登録だけを除外するため |
| 再抽出 | 同じ安定IDで更新 | 抽出runごとに全要素を作り、検証後にactive世代を一括切替 | OCR・図表検出の順序やbboxが再実行で変わるため |
| 初期検索 | denseとキーワード検索の統合を基本構成に含める | dense-onlyをbaselineにし、BM25 sparse + RRFは独立実験 | 既存のhybrid検索で退行があり、一要因ずつ効果を測るため |
| PDF・図表抽出 | 高水準の10段階処理 | PyMuPDF、Gemini structured output、LibreOffice、座標規則、review gateを具体化 | 実装・再現・失敗時動作を決めるため |
| 図表データ | 説明文と構造JSONを保存する方針 | version付きvisual JSON Schemaとsemantic validationを追加 | 表、flow、帳票、timelineの出力差をなくすため |
| 回答生成 | LLMが自由文回答と参照を生成 | LLMは根拠付きclaimsだけを返し、表示文はコードが構築 | 回答本文にだけ未根拠の金額や期限を書く抜け道を防ぐため |
| 回答分類 | Gemini分類器の要因をコードで3分類へ変換 | オンライン分類はretrieval sufficiency、claim support、個別事情、制度解釈、版競合を返し、corpus answerabilityは評価annotationへ分離 | オンラインではcorpus不在を証明できず、検索失敗との混同を防ぐため |
| Generatorと分類器 | 両者の出力を順番に利用 | 最終ラベルと表示templateはclassifier factorsからコードが一度だけ決定 | 回答内容と分類ラベルの矛盾を防ぐため |
| 既存100シナリオ | 固定評価セット | 既に改善へ利用したdevelopment / regression set | 調整に使った評価を最終受入に使わないため |
| 図表評価 | 約50問を追加 | 50シナリオをdevelopment 30 / sealed holdout 20へ文書family単位で分離 | 同じ図表構造の漏洩を避けるため |
| 完成条件 | 指標一覧が中心 | hit率、内容正解、macro F1、根拠なし断定、API error、復元、費用の閾値を設定 | 完成を客観判定するため |
| 公開demo | 非公開uploadとSecret管理が中心 | 質問・feedback quota、kill switch、HMAC、30日削除、並列testを追加 | API費用と無制限書込みを防ぐため |
| 実装順序 | 縦方向実装後に図表評価セットを作る | fixture、gold、holdout、cloud接続spikeを実装前に行う | 実装に都合のよい評価問題を作ることと後半のcloud手戻りを避けるため |

## 3. 変更していない方針

- 想定利用者は自治体の給与事務担当者と制度所管担当者。
- ポートフォリオでは架空文書・架空質問だけを使う。
- 正本はPostgreSQL、検索indexはQdrant、binary原本はCloud Storageへ分ける。
- 必須対象は6種類の図表で、業務画面captureと組織図は後続候補。
- 画像Embeddingは完成条件ではなく比較実験。
- 回答生成と回答分類を別工程にする。
- Geminiを基準分類器とし、Jev等は比較候補にする。
- SnowflakeはRAG本体の完成後、分析課題とデータ量が揃った場合だけ検討する。

## 4. 新たに追加した作業上の制約

- 各Phaseを学習目標、現状確認、設計比較、最小実装、検証、振り返りへ分割する。
- 大きな工程の開始前にCodexの5時間枠・週間枠を確認する。
- 使用率80%以上では新しい長時間loopや広範囲実装を始めず、checkpointを優先する。
- reset creditや追加creditを自動で使わない。

詳細は[学習・Codex利用枠運用計画](LEARNING_AND_USAGE_PLAN.md)を正とする。
