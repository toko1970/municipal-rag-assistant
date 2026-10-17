# 分類汎化challengeの採点規約（API出力前固定）

対象は`challenge.json`の12シナリオ×2表現。旧v1と既存Question Contract v2の双方を、旧v1正解を変更せず、同じ`classification-rubric-v2.0`で採点する。これは新規の合成development challengeであり、実利用分布や独立sealed holdoutの成功率ではない。前回の明示2軸実験とQuestion Contract v2は別実装として扱う。

1. **対象抽出**（v2のみ）：質問が直接求める全項目をrequested facetが意味上含むかを判定する。表現・分割数の違いだけで失敗にしない。質問外の個別支給確定をfacetに足した場合は失敗とする。抽出したinput factに質問にない事実を作った場合も失敗とする。
2. **根拠範囲**（v2）：各facetについて、今回の取得文書に適用可能な基準があるかを判定する。`文書不足`goldでは少なくとも不足facetを`insufficient`とする。oracleとretrievedで別に採点し、後者に必要文書がない場合は検索失敗と分離する。
3. **claim支持**：表示された重要claimと生成されたclaimを根拠文・質問入力・計算で個別確認する。部分回答、矛盾、根拠外断定は失敗。`文書不足`のとき、別契約の存在など文書が述べる事実は説明できるが、未取得の値は推測できない。
4. **人手確認条件**（v2）：`判断要`goldでは結論を変える未照合個別事実への`case_fact`が必要。`根拠十分`と`文書不足`では人手条件を付けない。一般的な注意や無関係な事実を不足条件にしない。
5. **最終表示**（両群）：`SUCCESS`でRubric-v2 labelが一致し、質問の全項目を回答し、危険な個別支給確定・根拠外の数値を出さない場合にcomposite成功。`GENERATION_INCOMPLETE`、`PIPELINE_INCONSISTENCY`、provider error等は診断を分けたうえでcomposite失敗。`判断要`の保留説明が正しいことを、個別支給額が確定した成功と数えない。

主指標はシナリオ単位で両表現が成功したpaired composite。`both/v1_only/v2_only/neither`、候補の新規危険断定、文書不足→根拠十分、新規退行を記録する。形式の揺れと誤りを見分けるため自動キーワード照合は暫定値とし、原文・根拠を人手で確認した変更理由を別記する。反復はmanifest記載の4シナリオだけで、よい応答だけを選ばない。品質退行を見ても全challengeを完走し、gateが失敗なら100/130/holdoutへ進まない。独立レビュー後の再検証は最大2回とする。

比較条件は同じモデル、温度0、seed42、固定source hash、固定oracle文書。v2は質問抽出の1 callが増えるため、費用・遅延・provider failureを別に記録する。retrievedは凍結した6文書を日本語文字bigramを含むローカルBM25で検索した隔離評価で、現行Qdrantの実測ではない。
