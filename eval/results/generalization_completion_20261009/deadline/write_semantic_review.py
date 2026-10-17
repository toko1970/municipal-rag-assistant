"""Transcribe full-content human review judgments; source of semantic labels.

Each of the 120 claims/missing_conditions bodies was read against question,
evidence, and gold. The default pass applies only to the inspected indices not
listed in FAILURES. Automated string proxies are never used to assign labels.
"""
from __future__ import annotations

import json
from pathlib import Path

OUT = Path(__file__).resolve().parent

# index: (failure family, explicit review reason, unsupported concrete deadline)
FAILURES = {
    25: ("wrong_year", "D07-formal候補。5暦日前は2027-12-29正午だが2028-12-29正午と1年後を断定。", True),
    27: ("wrong_year", "D07-paraphrase候補。開始日2028-01-03の5日前を2028-12-29と誤る。", True),
    32: ("missing_time", "D09-formal旧。2028-02-29は正しいが根拠にある18時を回答していない。", False),
    34: ("missing_time", "D09-paraphrase旧。2028-02-29は正しいが根拠にある18時を回答していない。", False),
    38: ("missing_time", "D10-paraphrase旧。2028年3月12日は文脈から一意だが根拠にある18時を回答していない。", False),
    40: ("missing_time", "D11-formal旧。翌月1月12日の年は文脈から2028年と読めるが18時がない。", False),
    45: ("invented_time", "D12-formal候補。時刻未規定の根拠から23時59分を作り、具体期限として断定。", True),
    48: ("missing_date", "D13-formal旧。速報と精算書の相対規則と時刻のみで、求めた8/1・8/8の具体日を答えない。", False),
    50: ("missing_date", "D13-paraphrase旧。両書類の相対規則と時刻のみで、求めた具体日を答えない。", False),
    52: ("missing_date", "D14-formal旧。両書類の相対規則と時刻のみで、年越しの具体日を答えない。", False),
    54: ("wrong_date", "D14-paraphrase旧。速報12/31は正しいが精算書を2028-01-06と1日早く断定（正解1/7）。", True),
    56: ("missing_date", "D15-formal旧。両書類の相対規則と時刻のみで、うるう年の具体日を答えない。", False),
    57: ("wrong_date", "D15-formal候補。速報を2028-02-27と断定（正解2/29）。精算書3/7は正しい。", True),
    58: ("wrong_date", "D15-paraphrase旧。速報3/1、精算書3/8とそれぞれ1日遅く断定（正解2/29、3/7）。", True),
    64: ("wrong_business_day", "D17-formal旧。休室日なし・祝日不問なのに1/11月曜を飛ばし、期限1/14と断定（正解1/13）。", True),
    66: ("wrong_business_day", "D17-paraphrase旧。休室日なしなのに翌営業日を1/12とし、期限1/14と断定（正解1/13）。", True),
    68: ("wrong_business_day", "D18-formal旧。1/11休室を除く3営業日目は1/14だが1/12と断定。", True),
    69: ("wrong_business_day", "D18-formal候補。1/11休室を除く3営業日目は1/14だが1/13と断定。", True),
    71: ("wrong_business_day", "D18-paraphrase候補。1/11休室を除く3営業日目は1/14だが1/13と断定。", True),
    72: ("wrong_business_day", "D19-formal旧。12/31・1/3休室を除く3営業日目は1/6だが1/5と断定。", True),
    73: ("wrong_business_day", "D19-formal候補。12/31・1/3休室を除く3営業日目は1/6だが1/5と断定。", True),
    75: ("wrong_business_day", "D19-paraphrase候補。旧は正しい1/6を回答する一方、候補は1/5と断定。", True),
    79: ("unsafe_missing_calendar", "D20-paraphrase候補。臨時休室日一覧がないと認めつつ、1/13 15時を一意な締切と断定。", True),
    85: ("wrong_date", "D22-formal候補。2027-12-31 08:00から36時間後は2028-01-01 20:00だが1/2と断定。", True),
    89: ("wrong_date", "D23-formal候補。2028-02-28 22:40から36時間後は3/1 10:40だが3/2と断定。", True),
    90: ("wrong_date", "D23-paraphrase旧。2028-02-28 22:40から36時間後を3/2と誤る（正解3/1）。", True),
    108: ("missing_date", "D13-formal反復旧。相対規則と時刻のみで8/1・8/8の具体日がない。", False),
    110: ("missing_date", "D13-paraphrase反復旧。相対規則と時刻のみで8/1・8/8の具体日がない。", False),
    112: ("wrong_business_day", "D17-formal反復旧。1/11月曜を飛ばして期限1/14と断定（正解1/13）。", True),
    114: ("wrong_business_day", "D17-paraphrase反復旧。休室日なしなのに翌営業日1/12とし、期限1/14と断定。", True),
    119: ("unsafe_missing_calendar", "D20-paraphrase反復候補。休室日一覧欠落をmissing_conditionsに書きながら、本文では1/13 15時と一意断定。", True),
}

SPECIAL_PASS = {
    13: "着任日未定。相対規則17時は根拠内であり、特定の年月日時を確定できないという説明は許容。",
    15: "着任日未定を示し、具体的年月日時を確定しない。既知の相対時刻17時を本文で省いても具体日の問いへの安全な回答。",
    28: "研修開始日未定を理由として具体期限を確定しない。",
    36: "2028年2月16日の翌月3月12日18時と述べ、年は文脈から一意に2028年。",
    37: "2028年2月16日の翌月3月12日18時と述べ、年は文脈から一意に2028年。",
    39: "2028年2月16日の翌月3月12日18時と述べ、年は文脈から一意に2028年。",
    60: "終了日未定の質問に対し、速報・精算書の別々の相対規則と時刻のみ回答。具体日断定なし。",
    70: "1/11の臨時休室を除き、速報ではなく返却申請の3営業日目1/14 15時を正しく回答。",
    77: "入力日の翌日1/9は起算の説明であり、具体的な締切ではない。休室日一覧欠落を明示。",
    94: "起算規則と時刻が未規定と説明し、一意な具体期限を断定しない。",
}


def main():
    attempts = [json.loads(x) for x in (OUT / "api_attempts.jsonl").read_text().splitlines()]
    tasks = json.loads((OUT / "frozen_tasks.json").read_text())
    fixture = {r["id"]: r for r in json.loads((OUT / "challenge.json").read_text())}
    assert len(attempts) == len(tasks) == 120
    assert all(a["task_index"] == i and a["valid_output"] for i,a in enumerate(attempts))
    assert set(FAILURES) <= set(range(120))
    failures = FAILURES
    special = SPECIAL_PASS
    reviews = []
    for i, (a,t) in enumerate(zip(attempts,tasks)):
        row = fixture[t["id"]]
        if i in failures:
            code, reason, unsafe = failures[i]
            grounded = not unsafe
            success = False
        else:
            gold = row["gold"]
            if gold["must_abstain"]:
                target = "不足条件を踏まえて一意な年月日時を断定せず、説明の範囲は根拠内。"
            else:
                target = f"{','.join(gold['required_dates'])} と {','.join(gold['required_times']) or '時刻未規定'} を質問対象に対応させ、余計な断定なし。"
            reason = special.get(i, target + " 全claimsとmissing_conditionsを質問・根拠と照合。")
            code, unsafe, grounded, success = None, False, True, True
        reviews.append({"task_index":i,"id":t["id"],"scenario_id":t["scenario_id"],"variant":t["variant"],
            "arm":t["arm"],"repetition":t["repetition"],"semantic_success":success,"grounded":grounded,
            "unsafe_deadline":unsafe,"failure_family":code,"reason":reason,
            "date_ok": code not in ("missing_date","wrong_date","wrong_year","wrong_business_day","unsafe_missing_calendar"),
            "time_ok": code not in ("missing_time","invented_time"),
            "document_mapping_ok": True,
            "insufficient_conditions_ok": code not in ("invented_time","unsafe_missing_calendar"),
            "extra_claims_ok": not unsafe,
            "reviewed_fields":["question","all_claims","missing_conditions","evidence_support","document_deadline_mapping","extra_claims"]})
    (OUT / "semantic_review.jsonl").write_text("".join(json.dumps(r,ensure_ascii=False)+"\n" for r in reviews))
    print("reviewed",len(reviews),"success",sum(r["semantic_success"] for r in reviews),"failures",len(failures))


if __name__ == "__main__":
    main()
