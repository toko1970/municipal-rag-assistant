"""給与事務担当者を想定した500問の評価セットを生成する。"""

from pathlib import Path
import csv


OUTPUT_FILE = Path("eval/evaluation_questions_500.csv")
VARIANT_TYPES = ("formal", "staff_consultation", "concise", "colloquial", "noisy")
FIELDS = (
    "question_id",
    "scenario_id",
    "question",
    "topic",
    "variant_type",
    "expected_document_ids",
    "expected_heading",
    "expected_answer_type",
    "difficulty",
    "expected_evidence",
    "expected_answer_key",
    "review_status",
)


E = {
    "scope": "DOC-001::給与制度規程 > 2. 適用対象",
    "payday": "DOC-001::給与制度規程 > 3. 給与支給日",
    "payday_example": "DOC-001::給与制度規程 > 3. 給与支給日 > 例",
    "period": "DOC-001::給与制度規程 > 4. 給与計算期間",
    "payslip": "DOC-001::給与制度規程 > 5. 給与明細",
    "deduction": "DOC-001::給与制度規程 > 6. 控除",
    "account": "DOC-001::給与制度規程 > 7. 給与振込口座",
    "account_deadline": "DOC-001::給与制度規程 > 7. 給与振込口座 > 提出期限",
    "salary_stop": "DOC-001::給与制度規程 > 8. 給与の支給停止",
    "repayment": "DOC-001::給与制度規程 > 9. 過払給与の返納",
    "reporting": "DOC-001::給与制度規程 > 10. 届出義務",
    "salary_contact": "DOC-001::給与制度規程 > 11. 制度所管部署",
    "commute_target": "DOC-002::2. 通勤手当 > 2.1 支給対象",
    "commute_req": "DOC-002::2. 通勤手当 > 2.2 支給要件",
    "commute_change": "DOC-002::2. 通勤手当 > 2.3 通勤経路変更",
    "commute_stop": "DOC-002::2. 通勤手当 > 2.4 支給停止",
    "housing_target": "DOC-002::3. 住居手当 > 3.1 支給対象",
    "housing_req": "DOC-002::3. 住居手当 > 3.2 支給要件",
    "housing_docs": "DOC-002::3. 住居手当 > 3.3 必要書類",
    "housing_stop": "DOC-002::3. 住居手当 > 3.4 支給停止",
    "dependent_target": "DOC-002::4. 扶養手当 > 4.1 支給対象",
    "dependent_relatives": "DOC-002::4. 扶養手当 > 4.2 扶養親族",
    "dependent_req": "DOC-002::4. 扶養手当 > 4.3 認定要件",
    "dependent_change": "DOC-002::4. 扶養手当 > 4.4 扶養親族変更届",
    "dependent_start": "DOC-002::4. 扶養手当 > 4.5 支給開始時期",
    "dependent_stop": "DOC-002::4. 扶養手当 > 4.6 支給停止時期",
    "overtime_target": "DOC-002::5. 時間外勤務手当 > 5.1 支給対象",
    "overtime_req": "DOC-002::5. 時間外勤務手当 > 5.2 支給要件",
    "overtime_excluded": "DOC-002::5. 時間外勤務手当 > 5.3 支給対象外",
    "allowance_report": "DOC-002::6. 手当変更時の届出",
    "allowance_note": "DOC-002::7. 注意事項",
    "faq_late_dependent": "DOC-003::2. 扶養手当に関するFAQ > Q2. 扶養親族変更届の提出が遅れた場合はどうなりますか？ > 回答",
    "faq_separate_parent": "DOC-003::2. 扶養手当に関するFAQ > Q3. 別居している父母を扶養親族として認定できますか？ > 回答",
    "faq_common_law": "DOC-003::2. 扶養手当に関するFAQ > Q4. 内縁関係の相手は扶養手当の対象になりますか？ > 回答",
    "faq_routes": "DOC-003::3. 通勤手当に関するFAQ > Q5. 通勤経路を複数利用している場合はどうなりますか？ > 回答",
    "faq_temp_workplace": "DOC-003::3. 通勤手当に関するFAQ > Q6. 一時的に勤務地が変わった場合も通勤経路変更届が必要ですか？ > 回答",
    "faq_bicycle": "DOC-003::3. 通勤手当に関するFAQ > Q7. 自転車通勤の場合も通勤手当は支給されますか？ > 回答",
    "faq_family_house": "DOC-003::4. 住居手当に関するFAQ > Q8. 家族名義の住宅に住んでいる場合、住居手当は支給されますか？ > 回答",
    "faq_split_rent": "DOC-003::4. 住居手当に関するFAQ > Q9. 家賃を夫婦で折半している場合はどうなりますか？ > 回答",
    "faq_late_form": "DOC-003::5. 届出手続きに関するFAQ > Q10. 提出期限を過ぎた場合でも届出は可能ですか？ > 回答",
    "faq_missing_docs": "DOC-003::5. 届出手続きに関するFAQ > Q11. 添付書類が不足している場合はどうなりますか？ > 回答",
    "faq_email": "DOC-003::5. 届出手続きに関するFAQ > Q12. 電子メールで届出を提出できますか？ > 回答",
    "faq_judgment": "DOC-003::6. 制度所管部署確認が必要なケース",
    "faq_unknown": "DOC-003::7. FAQで判断できない場合",
    "address_trigger": "DOC-004::2. 住所変更届 > 2.1 提出が必要な場合",
    "address_deadline": "DOC-004::2. 住所変更届 > 2.2 提出期限",
    "address_docs": "DOC-004::2. 住所変更届 > 2.3 必要書類",
    "address_process": "DOC-004::2. 住所変更届 > 2.4 処理手順",
    "dependent_trigger": "DOC-004::3. 扶養親族変更届 > 3.1 提出が必要な場合",
    "dependent_deadline": "DOC-004::3. 扶養親族変更届 > 3.2 提出期限",
    "dependent_docs": "DOC-004::3. 扶養親族変更届 > 3.3 必要書類",
    "dependent_process": "DOC-004::3. 扶養親族変更届 > 3.4 処理手順",
    "commute_trigger": "DOC-004::4. 通勤経路変更届 > 4.1 提出が必要な場合",
    "commute_deadline": "DOC-004::4. 通勤経路変更届 > 4.2 提出期限",
    "commute_docs": "DOC-004::4. 通勤経路変更届 > 4.3 必要書類",
    "commute_process": "DOC-004::4. 通勤経路変更届 > 4.4 処理手順",
    "housing_trigger": "DOC-004::5. 住居届 > 5.1 提出が必要な場合",
    "housing_deadline": "DOC-004::5. 住居届 > 5.2 提出期限",
    "procedure_housing_docs": "DOC-004::5. 住居届 > 5.3 必要書類",
    "housing_process": "DOC-004::5. 住居届 > 5.4 処理手順",
    "account_trigger": "DOC-004::6. 給与口座変更届 > 6.1 提出が必要な場合",
    "procedure_account_deadline": "DOC-004::6. 給与口座変更届 > 6.2 提出期限",
    "account_docs": "DOC-004::6. 給与口座変更届 > 6.3 必要書類",
    "account_process": "DOC-004::6. 給与口座変更届 > 6.4 処理手順",
    "common_note": "DOC-004::7. 共通注意事項",
    "system_check": "DOC-004::8. システム入力時の確認事項",
    "revision_date": "DOC-005::制度改正通知 > 2. 適用開始日",
    "commute_old": "DOC-005::3. 通勤手当の改正 > 改正前",
    "commute_new": "DOC-005::3. 通勤手当の改正 > 改正後",
    "commute_transition": "DOC-005::3. 通勤手当の改正 > 経過措置",
    "housing_old": "DOC-005::4. 住居手当の改正 > 改正前",
    "housing_new": "DOC-005::4. 住居手当の改正 > 改正後",
    "housing_transition": "DOC-005::4. 住居手当の改正 > 経過措置",
    "dependent_old": "DOC-005::5. 扶養手当の改正 > 改正前",
    "dependent_new": "DOC-005::5. 扶養手当の改正 > 改正後",
    "dependent_transition": "DOC-005::5. 扶養手当の改正 > 経過措置",
    "revision_priority": "DOC-005::6. 旧通知の取扱い",
}


def evidence(*keys: str) -> str:
    return "|".join(E[key] for key in keys)


def docs_for(value: str) -> str:
    return "|".join(dict.fromkeys(item.split("::", 1)[0] for item in value.split("|")))


def scenario(topic, question, answer_type, difficulty, heading, answer_key, *keys):
    expected_evidence = evidence(*keys) if keys else ""
    return {
        "topic": topic,
        "question": question,
        "expected_answer_type": answer_type,
        "difficulty": difficulty,
        "expected_heading": heading,
        "expected_answer_key": answer_key,
        "expected_evidence": expected_evidence,
        "expected_document_ids": docs_for(expected_evidence) if expected_evidence else "",
    }


SCENARIOS = [
    scenario("適用対象", "給与制度規程は常勤職員に適用されますか？", "根拠十分", "direct", "適用対象", "架空市の常勤職員に適用される。", "scope"),
    scenario("適用対象", "会計年度任用職員の給料日をこの規程だけで確定できますか？", "文書不足", "near_miss", "適用対象", "別規程によるため、この文書だけでは確定できない。"),
    scenario("給与支給日", "通常の給与支給日は毎月何日ですか？", "根拠十分", "direct", "給与支給日", "毎月21日。", "payday"),
    scenario("給与支給日", "21日が土曜日の場合はいつ給与を支給しますか？", "根拠十分", "boundary", "休日の給与支給日", "前日の金曜日。", "payday", "payday_example"),
    scenario("給与支給日", "21日が祝日の場合はいつ振り込みますか？", "根拠十分", "boundary", "休日の給与支給日", "直前の営業日。", "payday"),
    scenario("給与計算", "給与計算の対象期間は毎月いつからいつまでですか？", "根拠十分", "direct", "給与計算期間", "毎月1日から末日まで。", "period"),
    scenario("給与明細", "給与明細に記載する項目を教えてください。", "根拠十分", "practical", "給与明細の記載事項", "基本給、諸手当、控除額、支給総額、差引支給額。", "payslip"),
    scenario("給与明細", "給与明細は紙で渡すのが原則ですか？", "根拠十分", "near_miss", "給与明細の交付方法", "電子交付が原則。", "payslip"),
    scenario("控除", "給与から控除される主な項目は何ですか？", "根拠十分", "direct", "給与からの控除", "所得税、住民税、共済組合掛金、対象者の雇用保険料、法令等に基づく控除。", "deduction"),
    scenario("控除", "控除額が正しいか判断できない場合はどこへ確認しますか？", "判断要", "judgment", "控除額の疑義", "人事給与課へ確認する。", "deduction"),
    scenario("給与口座", "給与は家族名義の口座へ振り込めますか？", "根拠十分", "near_miss", "給与振込口座の名義", "職員本人名義の金融機関口座へ振り込む。", "account"),
    scenario("給与口座", "給与の振込先を変更するときは何の届出が必要ですか？", "根拠十分", "direct", "給与口座変更届", "給与口座変更届を提出する。", "account", "account_trigger"),
    scenario("給与口座", "来月から給与口座を変える場合、いつまでに届け出ますか？", "根拠十分", "practical", "給与口座変更届の提出期限", "変更希望月の前月15日まで。", "account_deadline", "procedure_account_deadline"),
    scenario("給与口座", "給与口座変更届が前月15日に間に合わない場合、いつ反映されますか？", "判断要", "judgment", "期限後の口座変更", "翌月以降の反映となる場合があるため個別確認が必要。", "account_deadline"),
    scenario("給与停止", "給与の全部または一部を停止する可能性があるのはどのような場合ですか？", "根拠十分", "direct", "給与の支給停止", "休職、停職、長期欠勤、法令に基づく場合。", "salary_stop"),
    scenario("給与停止", "休職者の給与を何割停止するか、この規程だけで判断できますか？", "文書不足", "unanswerable", "支給停止の詳細", "個別の制度規程によるため割合は確定できない。"),
    scenario("過払返納", "給与を払い過ぎた場合の返納方法には何がありますか？", "根拠十分", "direct", "過払給与の返納方法", "一括返納または分割返納。", "repayment"),
    scenario("過払返納", "過払給与を必ず一括返納させる必要がありますか？", "判断要", "judgment", "返納方法の決定", "職員の事情を考慮して一括または分割を決定する。", "repayment"),
    scenario("届出義務", "給与計算に影響する主な届出をまとめて教えてください。", "根拠十分", "direct", "主な届出", "扶養親族、住所、通勤経路、住居、給与口座の各変更届。", "reporting"),
    scenario("所管部署", "給与制度規程の問い合わせ先はどこですか？", "根拠十分", "direct", "制度所管部署", "人事給与課。", "salary_contact"),
    scenario("通勤手当", "通勤手当はどのような通勤手段を対象としますか？", "根拠十分", "direct", "通勤手当の支給対象", "公共交通機関または交通用具を利用した通勤。", "commute_target"),
    scenario("通勤手当", "改正前の通勤手当の支給要件を教えてください。", "根拠十分", "direct", "通勤手当の支給要件", "実通勤、2km以上、届出提出のすべて。", "commute_req", "commute_old"),
    scenario("通勤手当", "2025年10月以降の通勤距離基準は何km以上ですか？", "根拠十分", "revision", "改正後の通勤距離基準", "1.5km以上。", "commute_new", "revision_date"),
    scenario("通勤手当", "2025年9月30日以前に認定した通勤手当は新基準になりますか？", "根拠十分", "boundary", "通勤手当の経過措置", "旧基準を適用する。", "commute_transition"),
    scenario("通勤手当", "2025年10月に通勤距離がちょうど1.5kmなら距離要件を満たしますか？", "根拠十分", "boundary", "改正後の通勤距離境界", "1.5km以上なので距離要件を満たす。", "commute_new", "revision_date"),
    scenario("通勤手当", "2025年10月に通勤距離1.4kmで車通勤する職員は距離要件を満たしますか？", "根拠十分", "boundary", "改正後の通勤距離境界", "1.5km未満なので距離要件を満たさない。", "commute_new", "revision_date"),
    scenario("通勤手当", "2025年10月に通勤経路が変わり、1.8kmを車通勤する職員の要件と届出期限を教えてください。", "根拠十分", "multi_document", "改正後の通勤要件と届出期限", "1.5km以上、実通勤、届出が必要で、経路変更届は変更日から10日以内。", "commute_req", "commute_new", "commute_deadline"),
    scenario("通勤手当", "通勤経路が変わった場合はどの届出を出しますか？", "根拠十分", "direct", "通勤経路変更", "通勤経路変更届を提出する。", "commute_change", "commute_trigger"),
    scenario("通勤手当", "通勤経路変更届は変更日から何日以内ですか？", "根拠十分", "near_miss", "通勤経路変更届の提出期限", "10日以内。", "commute_deadline"),
    scenario("通勤手当", "通勤経路変更届に添付する書類を教えてください。", "根拠十分", "practical", "通勤経路変更届の必要書類", "届出、経路図、該当者は定期券写し。", "commute_docs"),
    scenario("通勤手当", "通勤経路変更届を受け付けた後の処理順序は？", "根拠十分", "practical", "通勤経路変更届の処理手順", "受付、経路確認、支給額確認、システム登録。", "commute_process"),
    scenario("通勤手当", "転居後に通勤しなくなった職員の通勤手当はどうしますか？", "根拠十分", "multi_document", "通勤実態消失時の支給停止", "通勤実態がなくなったため支給停止。住所変更届も必要。", "commute_stop", "address_trigger"),
    scenario("通勤手当", "長期休職になった職員の通勤手当は継続しますか？", "根拠十分", "direct", "通勤手当の支給停止", "長期休職の場合は支給停止。", "commute_stop"),
    scenario("通勤手当", "複数の通勤ルートがある場合、所属だけで認定経路を決められますか？", "判断要", "judgment", "複数経路の認定", "合理的・経済的な経路を基準とし、個別事情は確認が必要。", "faq_routes"),
    scenario("通勤手当", "一時的な勤務地変更でも通勤経路変更届が必須ですか？", "判断要", "judgment", "一時的勤務地変更", "異動の内容や期間で異なるため確認が必要。", "faq_temp_workplace"),
    scenario("通勤手当", "自転車通勤なら必ず通勤手当を支給できますか？", "判断要", "judgment", "自転車通勤", "交通用具利用者に該当し得るが詳細な認定条件の確認が必要。", "faq_bicycle", "commute_target"),
    scenario("住居手当", "住居手当はどのような職員を対象としますか？", "根拠十分", "direct", "住居手当の支給対象", "本人が賃貸契約し家賃を負担する職員。", "housing_target"),
    scenario("住居手当", "2025年10月以降の住居手当の家賃要件はいくらを超える場合ですか？", "根拠十分", "revision", "改正後の家賃要件", "月額15,000円を超える場合。", "housing_new", "housing_transition"),
    scenario("住居手当", "2025年10月以降、家賃がちょうど15,000円なら住居手当の対象ですか？", "根拠十分", "boundary", "改正後の家賃境界", "15,000円を超えていないため家賃要件を満たさない。", "housing_new"),
    scenario("住居手当", "2025年10月以降、本人名義で家賃15,001円なら家賃要件を満たしますか？", "根拠十分", "boundary", "改正後の家賃境界", "15,000円を超えるため家賃要件を満たす。", "housing_new", "housing_req"),
    scenario("住居手当", "2025年9月に認定する家賃16,000円の住宅は家賃要件を満たしますか？", "根拠十分", "boundary", "改正前の家賃境界", "16,000円を超えていないため旧家賃要件を満たさない。", "housing_old", "housing_transition"),
    scenario("住居手当", "家族名義の賃貸住宅に住む職員へ住居手当を支給できますか？", "判断要", "judgment", "家族名義住宅", "本人名義が原則だが個別事情の確認が必要。", "faq_family_house", "housing_req"),
    scenario("住居手当", "夫婦で家賃を折半している場合の住居手当を一律に判断できますか？", "判断要", "judgment", "家賃折半", "負担状況の確認が必要で一律判断できない。", "faq_split_rent"),
    scenario("住居手当", "住居手当の認定時に必要な書類は何ですか？", "根拠十分", "direct", "住居手当の必要書類", "住居届、賃貸借契約書写し、家賃支払確認書類。", "housing_docs", "procedure_housing_docs"),
    scenario("住居手当", "賃貸住宅へ入居した職員は何の届出が必要ですか？", "根拠十分", "practical", "住居届が必要な場合", "住居届を提出する。", "housing_trigger"),
    scenario("住居手当", "住居届は入居日から何日以内に提出しますか？", "根拠十分", "near_miss", "住居届の提出期限", "30日以内。", "housing_deadline"),
    scenario("住居手当", "住居届を受け付けてからシステム登録までの流れは？", "根拠十分", "practical", "住居届の処理手順", "受付、契約書確認、家賃額確認、認定審査、システム登録。", "housing_process"),
    scenario("住居手当", "職員が賃貸住宅を退去した場合、住居手当はどうしますか？", "根拠十分", "direct", "住居手当の支給停止", "住宅退去時は支給停止。", "housing_stop"),
    scenario("扶養手当", "扶養手当はどのような職員に支給しますか？", "根拠十分", "direct", "扶養手当の支給対象", "扶養親族を有する職員。", "dependent_target"),
    scenario("扶養手当", "扶養親族として認定できる続柄を教えてください。", "根拠十分", "direct", "扶養親族の範囲", "配偶者、子、父母、その他人事給与課が認める者。", "dependent_relatives"),
    scenario("扶養手当", "扶養親族の認定で確認する生計要件は何ですか？", "根拠十分", "direct", "扶養認定要件", "主として職員の収入で生計を維持していること。", "dependent_req"),
    scenario("扶養手当", "子どもが生まれたときは扶養親族変更届が必要ですか？", "根拠十分", "practical", "出生時の届出", "出生は届出が必要な場合に該当する。", "dependent_trigger", "dependent_change"),
    scenario("扶養手当", "扶養親族が就職して要件を失った場合は届出が必要ですか？", "根拠十分", "practical", "扶養要件喪失時の届出", "扶養親族変更届を提出する。", "dependent_trigger", "dependent_change"),
    scenario("扶養手当", "扶養親族変更届は事由発生日から何日以内ですか？", "根拠十分", "near_miss", "扶養親族変更届の提出期限", "15日以内。", "dependent_deadline"),
    scenario("扶養手当", "扶養親族変更届の必要書類を教えてください。", "根拠十分", "practical", "扶養親族変更届の必要書類", "届出、戸籍関係書類、必要に応じて所得証明書。", "dependent_docs"),
    scenario("扶養手当", "扶養親族変更届の受付後はどの順に処理しますか？", "根拠十分", "practical", "扶養親族変更届の処理手順", "受付、書類審査、認定確認、システム登録、結果通知。", "dependent_process"),
    scenario("扶養手当", "2025年9月に子どもが生まれ、扶養認定された場合、扶養手当はいつからですか？", "根拠十分", "boundary", "改正前の支給開始", "旧基準により認定事由発生日の翌月から。", "dependent_old", "dependent_transition"),
    scenario("扶養手当", "2025年10月に子どもが生まれ認定された場合、扶養手当はいつからですか？", "根拠十分", "boundary", "改正後の支給開始", "認定事由が確認され認定された月から。", "dependent_new", "dependent_transition"),
    scenario("扶養手当", "2025年10月の出生について支給開始時期と届出期限をまとめてください。", "根拠十分", "multi_document", "改正後の支給開始と届出期限", "認定月から支給し、扶養親族変更届は事由発生日から15日以内。", "dependent_new", "dependent_transition", "dependent_deadline"),
    scenario("扶養手当", "扶養要件を失った場合、いつから手当を停止しますか？", "根拠十分", "direct", "扶養手当の支給停止時期", "事由発生日の翌月から。", "dependent_stop"),
    scenario("扶養手当", "別居している父母を扶養に入れられるか所属で即決できますか？", "判断要", "judgment", "別居父母の扶養認定", "扶養実態と生計維持関係を総合確認するため一律判断できない。", "faq_separate_parent", "dependent_req"),
    scenario("扶養手当", "内縁関係の相手を扶養手当の対象にできますか？", "判断要", "judgment", "内縁関係の扶養認定", "FAQでは判断できず個別確認が必要。", "faq_common_law"),
    scenario("扶養手当", "海外に住む親族を扶養認定してよいですか？", "判断要", "judgment", "海外居住親族", "制度所管部署の判断が必要。", "faq_judgment"),
    scenario("扶養手当", "扶養親族変更届が期限を過ぎた場合も受け付けられますか？", "判断要", "judgment", "期限後の扶養届", "受付は可能だが認定や支給時期への影響は個別確認。", "faq_late_dependent", "faq_late_form"),
    scenario("時間外勤務手当", "時間外勤務手当は誰の命令で勤務した場合に支給しますか？", "根拠十分", "direct", "時間外勤務手当の支給対象", "所属長の命令による時間外勤務。", "overtime_target"),
    scenario("時間外勤務手当", "時間外勤務は事前承認がないと必ず支給対象外ですか？", "根拠十分", "near_miss", "時間外勤務の承認", "事前または事後に承認されれば対象となり得る。", "overtime_req"),
    scenario("時間外勤務手当", "事後承認された残業は手当の対象になりますか？", "根拠十分", "paraphrase", "事後承認", "事後承認された勤務時間は支給対象となり得る。", "overtime_req"),
    scenario("時間外勤務手当", "承認のない残業に時間外勤務手当を支給できますか？", "根拠十分", "direct", "支給対象外", "承認がないため支給対象外。", "overtime_excluded"),
    scenario("時間外勤務手当", "職員が自主的に残った時間は残業手当の対象ですか？", "根拠十分", "practical", "自主的残業", "自主的な残業は支給対象外。", "overtime_excluded"),
    scenario("時間外勤務手当", "勤務実績を確認できない残業は支給できますか？", "根拠十分", "direct", "勤務実績未確認", "勤務実績を確認できない場合は支給対象外。", "overtime_excluded"),
    scenario("住所変更", "転居した職員は住所変更届を出す必要がありますか？", "根拠十分", "direct", "住所変更届が必要な場合", "転居時は住所変更届が必要。", "address_trigger"),
    scenario("住所変更", "住居表示だけが変わった場合も住所変更届は必要ですか？", "根拠十分", "near_miss", "住居表示変更", "住居表示変更も提出対象。", "address_trigger"),
    scenario("住所変更", "住所変更届は住所変更日から何日以内ですか？", "根拠十分", "near_miss", "住所変更届の提出期限", "14日以内。", "address_deadline"),
    scenario("住所変更", "住所変更届に必要な添付書類は何ですか？", "根拠十分", "practical", "住所変更届の必要書類", "住所変更届と住民票の写し。", "address_docs"),
    scenario("住所変更", "住所変更届の受付後の処理手順を教えてください。", "根拠十分", "practical", "住所変更届の処理手順", "受付、添付確認、システム登録、登録結果確認。", "address_process"),
    scenario("給与口座", "給与口座変更届に必要な確認書類は何ですか？", "根拠十分", "practical", "給与口座変更届の必要書類", "届出と通帳または口座情報確認書類。", "account_docs"),
    scenario("給与口座", "給与口座変更届を受け付けた後の処理順序は？", "根拠十分", "practical", "給与口座変更届の処理手順", "受付、口座情報確認、システム登録、テスト確認。", "account_process"),
    scenario("届出共通", "提出期限を過ぎた届出は一切受け付けられませんか？", "判断要", "near_miss", "期限後の届出", "届出は受け付けるが反映時期等は個別確認。", "faq_late_form", "common_note"),
    scenario("届出共通", "添付書類が足りない届出を受け付けられますか？", "判断要", "judgment", "書類不備", "FAQは認定未完了と不足書類の提出を示す一方、手続きマニュアルは受付不可としているため、受付可否は人事給与課へ確認する。", "faq_missing_docs", "common_note"),
    scenario("届出共通", "届出書を電子メールで受け付けてよいですか？", "判断要", "judgment", "メール提出", "所属や手続きで運用が異なるため確認が必要。", "faq_email"),
    scenario("システム入力", "人事給与システムへ登録する前に何を確認しますか？", "根拠十分", "practical", "システム登録前の確認", "添付有無、期限、認定要件、既存登録との整合性。", "system_check"),
    scenario("システム入力", "人事給与システムへ入力した後に再確認は必要ですか？", "根拠十分", "direct", "入力後の確認", "入力後は必ず登録内容を再確認する。", "system_check"),
    scenario("制度改正", "手当制度の改正はいつから適用されますか？", "根拠十分", "direct", "制度改正の適用開始日", "2025年10月1日。", "revision_date"),
    scenario("制度改正", "2025年10月以降に旧通知と改正通知の内容が違う場合はどちらを優先しますか？", "根拠十分", "near_miss", "旧通知の取扱い", "改正通知を優先する。", "revision_priority", "revision_date"),
    scenario("制度改正", "通勤手当の距離基準は改正前後でどう変わりましたか？", "根拠十分", "multi_document", "通勤手当の改正前後", "2km以上から1.5km以上へ変更。", "commute_old", "commute_new"),
    scenario("制度改正", "住居手当の家賃基準は改正前後でどう変わりましたか？", "根拠十分", "multi_document", "住居手当の改正前後", "16,000円超から15,000円超へ変更。", "housing_old", "housing_new"),
    scenario("制度改正", "扶養手当の支給開始時期は改正前後でどう変わりましたか？", "根拠十分", "multi_document", "扶養手当の改正前後", "事由発生日の翌月から、認定された月からへ変更。", "dependent_old", "dependent_new"),
    scenario("複合手続き", "転居で通勤しなくなった場合、通勤手当と住所変更届をどう処理しますか？", "根拠十分", "multi_document", "通勤手当停止と住所変更", "通勤実態消失で手当停止、住所変更届は14日以内。", "commute_stop", "address_deadline"),
    scenario("複合手続き", "過払給与の返納方法と給与口座変更に必要な書類をまとめてください。", "根拠十分", "multi_document", "過払返納と口座変更", "一括または分割返納。口座変更届と口座情報確認書類が必要。", "repayment", "account_docs"),
    scenario("複合手続き", "2025年10月に本人名義で契約し、家賃15,500円を負担する住宅へ入居した場合の要件・書類・期限は？", "根拠十分", "multi_document", "改正後の住居手当と住居届", "本人名義で家賃15,000円超を負担する要件を満たし、住居届・契約書写し・支払確認書類を入居日から30日以内に提出。", "housing_req", "housing_new", "procedure_housing_docs", "housing_deadline"),
    scenario("文書不足", "退職手当の具体的な計算式を教えてください。", "文書不足", "unanswerable", "退職手当", "対象文書に記載がない。"),
    scenario("文書不足", "育児休業中の給与は通常の何割支給されますか？", "文書不足", "unanswerable", "育児休業中の給与", "対象文書に記載がない。"),
    scenario("文書不足", "テレワーク手当の月額上限はいくらですか？", "文書不足", "unanswerable", "テレワーク手当", "対象文書に記載がない。"),
    scenario("文書不足", "副業許可申請は何日前までにどの部署へ出しますか？", "文書不足", "unanswerable", "副業許可", "対象文書に記載がない。"),
    scenario("文書不足", "賞与の支給月と算定期間を教えてください。", "文書不足", "unanswerable", "賞与", "対象文書に記載がない。"),
    scenario("文書不足", "共済組合の扶養認定に必要な収入基準はいくらですか？", "文書不足", "unanswerable", "共済扶養", "対象文書に具体的基準の記載がない。"),
    scenario("文書不足", "年末調整の申告書はいつまでに提出しますか？", "文書不足", "unanswerable", "年末調整", "対象文書に記載がない。"),
    scenario("文書不足", "産前産後休暇中の給与の取扱いを教えてください。", "文書不足", "unanswerable", "産前産後休暇", "対象文書に記載がない。"),
    scenario("文書不足", "管理職手当の月額はいくらですか？", "文書不足", "unanswerable", "管理職手当", "対象文書に記載がない。"),
    scenario("文書不足", "単身赴任手当の距離要件を教えてください。", "文書不足", "unanswerable", "単身赴任手当", "対象文書に記載がない。"),
]


def colloquial(text: str) -> str:
    replacements = (
        ("給与振込口座", "給料の振込先"),
        ("給与口座変更届", "給料の口座変更届"),
        ("通勤経路変更届", "通勤ルート変更届"),
        ("扶養親族変更届", "扶養の変更届"),
        ("住居届", "住宅の届"),
        ("給与", "給料"),
        ("提出", "出す"),
        ("支給", "出る"),
        ("何日以内", "いつまで"),
    )
    for old, new in replacements:
        if old in text:
            return text.replace(old, new, 1)
    changed = text.replace("ですか", "でしょうか", 1)
    return changed if changed != text else f"これって、{text}"


def noisy(text: str) -> str:
    replacements = (
        ("承認", "しょうにん"),
        ("家賃", "家ちん"),
        ("扶養", "扶用"),
        ("通勤", "つうきん"),
        ("振込", "振りこみ"),
        ("提出", "てい出"),
        ("給与", "給料"),
    )
    for old, new in replacements:
        if old in text:
            return f"すみません、{text.replace(old, new, 1)}"
    return f"すみません、{text}"


def question_variant(base: str, variant_type: str) -> str:
    if variant_type == "formal":
        return base
    if variant_type == "staff_consultation":
        return f"職員から相談を受けました。{base}"
    if variant_type == "concise":
        return f"給与事務担当です。{base}"
    if variant_type == "colloquial":
        return colloquial(base)
    return noisy(base)


def generate_records() -> list[dict]:
    if len(SCENARIOS) != 100:
        raise ValueError(f"シナリオ数は100件である必要があります: {len(SCENARIOS)}")

    records = []
    for scenario_index, item in enumerate(SCENARIOS, start=1):
        scenario_id = f"S{scenario_index:03d}"
        for variant_index, variant_type in enumerate(VARIANT_TYPES, start=1):
            records.append(
                {
                    "question_id": f"Q{len(records) + 1:03d}",
                    "scenario_id": scenario_id,
                    "question": question_variant(item["question"], variant_type),
                    "topic": item["topic"],
                    "variant_type": variant_type,
                    "expected_document_ids": item["expected_document_ids"],
                    "expected_heading": item["expected_heading"],
                    "expected_answer_type": item["expected_answer_type"],
                    "difficulty": item["difficulty"],
                    "expected_evidence": item["expected_evidence"],
                    "expected_answer_key": item["expected_answer_key"],
                    "review_status": "assistant_reviewed",
                }
            )
    return records


def save_records(records: list[dict], output_path: Path = OUTPUT_FILE) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", encoding="utf-8-sig", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=FIELDS, lineterminator="\n")
        writer.writeheader()
        writer.writerows(records)


def main() -> None:
    records = generate_records()
    save_records(records)
    print(f"生成件数: {len(records)}")
    print(f"出力: {OUTPUT_FILE}")


if __name__ == "__main__":
    main()
