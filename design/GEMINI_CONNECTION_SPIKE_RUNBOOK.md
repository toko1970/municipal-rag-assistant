# Gemini one-call connection spike 実行票

- 作成日: 2026-09-27
- 状態: `EXECUTED_SUCCESS`
- 対象service: Gemini Developer API
- 対象model: `gemini-3.1-flash-lite`
- 外部API呼出上限: **1回**
- retry上限: **0回**
- 費用上限: **$0.01 USD**
- 証拠出力予定: `eval/results/gemini_connection_spike_phase0.json`

## 1. 学習目標

このspikeでは、外部LLMへの接続確認を「回答が返った」という感覚ではなく、認証、構造、利用量、費用、停止状態の証拠として残す方法を学ぶ。

完了後に説明できることは次の4点とする。

1. 接続試験と回答品質評価の違い。
2. API呼出回数と費用を実行前に制限する方法。
3. 成功、認証失敗、quota失敗、Schema失敗を分ける理由。
4. input/output tokenから概算費用を計算する方法。

## 2. このspikeが証明すること

- 実行時点で、指定したcredentialがGemini Developer APIに受理される。
- `gemini-3.1-flash-lite`へ1 requestを送信できる。
- 固定JSON Schemaに適合する応答を取得できる。
- response metadataからinput/output tokenを取得し、同日のlist priceで費用を計算できる。
- 失敗時に自動retryせず、原因分類を残して停止できる。

このspikeだけでは、次は証明しない。

- RAG回答全体の正しさや分類精度。
- Cloud Run containerからのend-to-end疎通。
- 長時間運転、rate limit、同時実行時の安定性。
- Free/Paid tierの継続的な利用上限。
- request IDをSDKが必ず返すこと。

Cloud RunにはSecret Manager参照が設定されていることをread-onlyで確認済みだが、今回の1 requestはその設定全体の本番受入試験ではない。

## 3. 既存証拠と今回追加する証拠

2026-09-23のformal 100問評価では`gemini-3.1-flash-lite`が100/100件を生成エラーなしで完了している。

| 既存評価の証拠 | 値 |
|---|---:|
| input tokens | 57,993 |
| output tokens | 6,825 |
| 概算費用 | $0.02473575 |
| 平均応答時間 | 4.004秒 |

既存評価はmodel比較用で、固定JSON Schemaを使っていない。結果CSVの100件ではrequest IDも空欄だった。今回追加する証拠は、**現在のcredential、構造化応答、1 requestのtoken・費用、明示的なretry 0**である。

既存証拠: [`GEMINI_3_1_FORMAL_EVALUATION.md`](../eval/GEMINI_3_1_FORMAL_EVALUATION.md)、[`model_gemini_gemini-3.1-flash-lite_formal.csv`](../eval/results/model_gemini_gemini-3.1-flash-lite_formal.csv)

## 4. 実行前に固定する設定

| 項目 | 固定値・条件 |
|---|---|
| model | `gemini-3.1-flash-lite` |
| temperature | `0` |
| 最大output | 128 tokens |
| 最大input想定 | 2,000 tokens。固定prompt以外を渡さない |
| API request | 1回だけ |
| retry | SDK、HTTP client、applicationの全層で無効 |
| timeout | 60秒。timeout後も再送しない |
| 入力データ | 下記の架空文書だけ。repository文書、ログ、個人情報を送らない |
| credential | Secret Managerの`gemini-api-key` version 1。process memoryだけへ読み、値、末尾、hashを標準出力や結果fileへ書かない |
| key metadata | authorization keyか、利用tier、spend capの有無をAI Studioで確認し、値ではなく確認結果だけを記録する |

key metadataを確認できない場合、またはversion 1がstandard keyだった場合はAPIを呼ばず、`BLOCKED_KEY_METADATA`で停止する。key migrationはこの1 requestとは別の学習単位にする。

## 5. 固定入力と期待Schema

### 入力

```text
次の架空文書から届出期限の日数を抽出してください。
evidence_textには架空文書を一字一句そのまま引用してください。
架空文書: 扶養親族変更届は、事由発生日から15日以内に提出する。
```

### JSON Schema相当の期待値

```json
{
  "connection_status": "ok",
  "deadline_days": 15,
  "evidence_text": "扶養親族変更届は、事由発生日から15日以内に提出する。"
}
```

実装では次を強制する。

- `connection_status`: enum `ok`
- `deadline_days`: integer
- `evidence_text`: string
- 3項目すべてrequired
- 追加propertyは禁止

responseがparseできても、`connection_status != "ok"`、`deadline_days != 15`、または`evidence_text`が固定文と一致しない場合は`SCHEMA_OR_VALUE_FAILED`とする。これは回答品質の評価ではなく、構造化応答経路を決定的に確認するための小さい検査である。

## 6. 費用gate

2026-09-27に確認したStandard paid tierのlist priceを使う。

- input: `$0.25 / 1,000,000 tokens`
- output: `$1.50 / 1,000,000 tokens`

計算式は次のとおり。

```text
estimated_cost_usd =
  input_tokens * 0.25 / 1,000,000
  + output_tokens * 1.50 / 1,000,000
```

上限想定の2,000 input tokensと128 output tokensでは`$0.000692`で、実行上限`$0.01`を下回る。thinking tokenがoutput usageへ含まれる場合もresponse metadataのoutput tokensで計算する。

価格は実行直前に[Gemini Developer API pricing](https://ai.google.dev/gemini-api/docs/pricing)で再確認する。価格が変わり、上限内と確認できない場合はAPIを呼ばない。

## 7. 実行前checklist

すべて満たした場合だけ`READY_TO_EXECUTE`へ進める。

- [x] ユーザーが、この実行票による1 requestを明示的に承認した。
- [x] Codex利用率が80%未満である。
- [x] `git status`を確認し、無関係な変更を把握した。
- [x] model IDが現在利用可能であることを公式model pageで確認した。
- [x] Gemini keyの種類とtierをAI Studioで確認した。
- [x] Paidの場合、project spend capの有無を確認した。Free tierのため`not_applicable`。
- [x] credential値を表示・保存しない取得経路を確認した。
- [x] runnerのmock testでAPI clientの呼出回数が1回、retry 0回になることを確認した。
- [x] 固定入力とSchemaがこの文書と一致する。
- [x] 最新priceで上限費用を再計算し、`$0.01`未満である。
- [x] 結果fileにsecret、prompt以外の入力、個人情報が入らないことを確認した。

## 8. 実行手順

実行時には、先にlocal runnerとmock testを追加する。mock testは外部APIを呼ばず、次を検査する。

1. API clientの`invoke`相当が1回だけ呼ばれる。
2. 例外、timeout、Schema不一致でも再呼出しない。
3. 正常responseからtoken、model、request ID、latencyを取得する。
4. request IDがSDK metadataにない場合は`null`と理由を記録する。
5. 費用式と`$0.01` gateを検査する。
6. error messageをsanitizeし、credentialを結果へ含めない。

mock testとdry-runの成功後、承認済みcredentialをprocess memoryへだけ読み込み、固定promptを1回送る。実行中に失敗しても同じturnで修正・再送しない。

## 9. 結果record

`eval/results/gemini_connection_spike_phase0.json`へ、次だけを保存する。

```json
{
  "schema_version": "gemini-connection-spike-v1",
  "executed_at": "UTC timestamp",
  "outcome": "SUCCESS or terminal state",
  "api_call_count": 1,
  "retry_count": 0,
  "requested_model": "gemini-3.1-flash-lite",
  "returned_model": "model metadata or null",
  "credential_source": "secret_manager",
  "credential_version": "1",
  "key_type": "authorization or standard or unknown",
  "usage_tier": "free or paid or unknown",
  "parsed_response": {
    "connection_status": "ok",
    "deadline_days": 15,
    "evidence_text": "fixed fictional sentence"
  },
  "input_tokens": 0,
  "output_tokens": 0,
  "total_tokens": 0,
  "elapsed_seconds": 0.0,
  "estimated_cost_usd": 0.0,
  "pricing_observed_at": "UTC timestamp",
  "request_id": null,
  "error_category": null,
  "error_summary": null
}
```

credentialそのもの、credentialの一部、hash、HTTP header、stack trace、環境変数一覧は保存しない。APIを呼ぶ前に停止した場合は`api_call_count: 0`とする。

## 10. 終了状態

| 状態 | API呼出 | 判定 |
|---|---:|---|
| `SUCCESS` | 1 | 認証成功、Schema・固定値一致、usage取得、費用`$0.01`未満 |
| `BLOCKED_KEY_METADATA` | 0 | key種類・tier・価格・credential取得経路を安全に確認できない |
| `AUTH_FAILED` | 1 | 認証・key restriction・permission error。再送しない |
| `QUOTA_FAILED` | 1 | rate limitまたはquota error。再送しない |
| `SCHEMA_OR_VALUE_FAILED` | 1 | responseは得たがSchemaまたは固定値が不一致。再送しない |
| `USAGE_METADATA_MISSING` | 1 | token usageを取得できず費用証拠を作れない。再送しない |
| `COST_LIMIT_EXCEEDED` | 1 | 実測tokenによる概算が`$0.01`を超えた。追加呼出を禁止 |
| `API_FAILED` | 1 | 上記以外のtimeout・provider error。再送しない |
| `LOCAL_VALIDATION_FAILED` | 0 | mock test、dry-run、結果保存先の検査に失敗。APIを呼ばない |

request IDは既存LangChain経路で取得できなかった実績があるため、欠落だけでは失敗にしない。`request_id: null`とSDK metadataに存在しなかった事実を記録する。

## 11. 実行後の検証

- [ ] `api_call_count`が0または1で、2以上ではない。
- [ ] `retry_count`が0である。
- [ ] 結果JSONがparseでき、定義したfieldを持つ。
- [ ] token合計と費用計算を独立に再計算して一致する。
- [ ] secret patternと個人情報が結果・diff・terminal出力にない。
- [ ] terminal stateと実際の証拠が一致する。
- [ ] `SUCCESS`の場合だけP0-15のGemini接続を`verified`として更新する。
- [ ] 失敗時は原因、次の最小修正、再実行には新しい承認が必要なことをcheckpointへ残す。

## 12. 承認境界

この実行票の作成はAPI呼出の承認ではない。local runnerとmock testは外部呼出なしで準備できる。Secret Manager version 1のpayload取得とGeminiへの1 requestは、実装とdry-run結果をreview可能にした後、ユーザーの明示的な承認を得て実行する。この方法はCloud Runが参照するsecretの有効性を確かめるが、Cloud Run runtime service accountのsecret accessとcontainerからの疎通までは証明しない。

## 13. Local preparation結果

- 実装: [`gemini_connection_spike.py`](../eval/gemini_connection_spike.py)
- mock test: [`test_gemini_connection_spike.py`](../tests/test_gemini_connection_spike.py)
- Quality streak対象: dry-run、正常系、key metadata block、認証失敗、quota失敗、Schema不一致、usage欠落、費用超過
- 修正round: 2回。Secret取得後のclient初期化例外もSecretでsanitizeし、preflight block時にSecret取得関数を呼ばない回帰testと、client初期化失敗時にSecretを結果へ書かない回帰testを追加した
- 対象test: `11 passed`
- 全test: `117 passed`。既存dependency由来のDeprecationWarning 5件あり
- Ruff: success
- dry-run: `DRY_RUN_OK`、`api_call_count=0`、`retry_count=0`、`secret_accessed=false`
- projected max cost: `$0.000692`、上限`$0.01`
- 証拠file: dry-runでは未作成

この時点ではSecret Manager payloadの取得もGemini API呼出も行っていない。

## 14. Account preflight結果

2026-09-27にAI StudioとGoogle Cloudをread-onlyで確認した。

- AI Studioに表示されたのは`Default Gemini Project`（`gen-lang-client-0752406780`）の1 keyだけだった。
- 表示されたkeyの作成日は2026-06-07、tierはFreeだった。Paid tierではないためspend capは`not_applicable`とする。
- Google Cloudの`municipal-rag-portfolio`に対するAPI Keys APIの一覧結果は0件だった。
- `municipal-rag-portfolio`をAI Studioへimportする操作や、key・billing設定の作成・変更は行っていない。
- 公式仕様では、AI Studioで新規作成されるkeyはauth keyであり、2026年9月以降はstandard keyが拒否される。このためauth key確認を実行gateとして維持する。
- Secret Manager version 1がAI Studioに表示されたkeyと同一かは、payloadを開かないread-only metadataだけでは証明できなかった。

この時点のterminal stateは`BLOCKED_KEY_METADATA`で、API呼出は0回だった。その後、ユーザーの明示的な承認を得てSecretをprocess memoryへだけ取得し、画面へ表示せずAI Studioのmasked keyと照合した。

## 15. 実行結果

- 実行日時: 2026-09-27 15:29 JST
- terminal state: `SUCCESS`
- model: request/responseともに`gemini-3.1-flash-lite`
- key: masked keyとの照合成功、authorization key、Free tier
- API request: 1回
- retry: 0回
- latency: 1.408788秒
- input: 54 tokens
- output: 51 tokens
- total: 105 tokens
- 価格表上の推定請求額: Free tierは`$0`。Paid list price換算は`$0.00009000`
- structured response: 固定Schemaと期待値に一致
- request ID: SDK metadataになく`null`
- Secret: terminal、結果JSON、Git差分への混入なし
- 証拠: [`gemini_connection_spike_phase0.json`](../eval/results/gemini_connection_spike_phase0.json)

費用の独立再計算は`(54 × 0.25 + 51 × 1.50) / 1,000,000 = $0.00009000`で、結果JSONと一致し、上限`$0.01`を下回った。このspikeでGeminiの認証、構造化出力、usage取得、費用計算、retry 0を確認できた。Cloud Run containerからの疎通とRAG品質は別の検証対象である。
