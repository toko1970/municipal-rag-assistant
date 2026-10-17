"""Freeze a small, explicit Rubric-v2 development challenge before model use."""
from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid5, NAMESPACE_URL

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "eval/results/generalization_completion_20261009/classification"


def uid(name: str) -> str:
    return str(uuid5(NAMESPACE_URL, "classification-generalization-20261009/" + name))


DOCS = [
    ("A1", "臨時派遣交通補助要領", "距離単価と審査", "承認された臨時派遣の往復経路について、経路距離1km当たり180円を補助し、1回の上限は3,600円とする。端数kmは切り捨てる。支給の確定には派遣命令簿と実走行記録の照合が必要であり、人事給与室が照合する。所属部署だけでは個別支給を確定できない。"),
    ("A2", "臨時派遣交通補助手続", "提出資料", "申請には派遣命令番号と実走行記録を添える。出張報告書の提出先は庶務室である。"),
    ("B1", "夜間保全当番調整休要領", "取得時間と確定", "夜間保全当番を当番表で事前承認され、当番終了の記録があるとき、1回につき調整休2時間を付与する。実際の付与時間を確定するには承認済み当番回数と終了記録を照合する。"),
    ("B2", "夜間保全当番調整休手続", "申請期限と窓口", "調整休の申請は当番を行った月の翌月3日17時までに勤怠室へ提出する。申請には当番終了票を添付する。"),
    ("C1", "貸与端末更新補填要領", "補填計算と審査", "事前承認された貸与端末の交換用電池を購入した場合、領収書に記載された電池代金の50%を補填し、上限を8,000円とする。送料は補填対象外。個別の支給は購入品が承認済みの交換用電池であることを資産台帳と領収書で照合して確定する。"),
    ("C2", "貸与端末更新補填手続", "別契約と照合担当", "交換用電池の補填は情報資産室が照合する。端末の修理時に生じる自己負担率は別の保守契約で定め、この手続には率を記載しない。"),
]


def case(cid, family, questions, oracle, label, facets, reviews=(), terms=(), forbidden=(), note=""):
    return {"scenario_id": cid, "family": family, "questions": list(questions),
            "oracle_evidence_ids": list(oracle), "gold": {
                "rubric_version": "classification-rubric-v2.0", "label": label,
                "requested_facets": list(facets), "human_review_types": list(reviews),
                "required_answer_terms": list(terms), "forbidden_answer_terms": list(forbidden),
                "review_note": note}}


CASES = [
    case("A01", "transport", ("承認済みの臨時派遣で往復経路12kmです。条件を満たす場合の交通補助の算定額はいくらですか。", "派遣の行き帰りで12km、承認も済み。補助はいくらになる？"), ("A1",), "根拠十分", ("交通補助の算定額",), terms=("2,160",)),
    case("A02", "transport", ("臨時派遣交通補助は、所属部署だけで職員ごとの支給を確定できますか。", "この派遣補助、所属だけで支給OKと決められる？"), ("A1",), "根拠十分", ("所属部署だけで個別支給を確定できるか",), terms=("所属", "できない"), note="尋ねているのは権限・可否の一般命題。個別支給の結論ではない。"),
    case("A03", "transport", ("派遣命令の承認と往復12kmは分かっていますが、実走行記録が未照合です。この職員への交通補助の支給額を確定できますか。", "命令承認済み、距離は12km。ただ走行記録はまだ照合前。この人に払う額は決まる？"), ("A1", "A2"), "判断要", ("この職員への支給額を確定できるか",), reviews=("case_fact",), terms=("実走行",), forbidden=("支給額は2,160円で確定",)),
    case("A04", "transport", ("臨時派遣交通補助の所得税上の所得区分を教えてください。", "派遣の交通補助って税金では何所得？"), ("A1", "A2"), "文書不足", ("所得税上の所得区分",), forbidden=("給与所得です", "雑所得です")),
    case("B01", "night_rota", ("事前承認され終了記録もある夜間保全当番を3回行いました。付与される調整休は何時間ですか。", "夜の保全当番を3回、承認も終了記録もOK。休み何時間つく？"), ("B1",), "根拠十分", ("調整休の付与時間",), terms=("6時間",)),
    case("B02", "night_rota", ("夜間保全当番を3回行いましたが、事前承認の記録が確認できません。本人に付与される調整休を確定できますか。", "当番3回やったけど事前承認の記録がまだ不明。実際に付く休みは決められる？"), ("B1",), "判断要", ("本人の調整休付与を確定できるか",), reviews=("case_fact",), terms=("承認",)),
    case("B03", "night_rota", ("2028年2月に事前承認と終了記録がある夜間保全当番を2回行いました。調整休の時間と申請期限・提出先を教えてください。", "2028/2の夜間当番2回は承認も終了記録も済み。休みは何時間で、いつどこに申請？"), ("B1", "B2"), "根拠十分", ("調整休の時間", "申請期限", "提出先"), terms=("4時間", "3月3日", "17時", "勤怠室")),
    case("B04", "night_rota", ("夜間保全当番調整休の未使用時間は翌年度へ繰り越せますか。", "当番の調整休、使わず残った分は次年度に回せる？"), ("B1", "B2"), "文書不足", ("未使用時間の翌年度繰越可否",)),
    case("C01", "device", ("事前承認済みの交換用電池を12,000円で購入し、資産台帳と領収書の照合も済みました。補填額はいくらですか。", "承認済みの交換電池が1万2千円、台帳と領収書も照合OK。いくら補填？"), ("C1",), "根拠十分", ("交換用電池の補填額",), terms=("6,000",)),
    case("C02", "device", ("購入額12,000円の領収書はありますが、購入品が事前承認された交換用電池か資産台帳で未照合です。この人への補填額を確定できますか。", "領収書は1万2千円。承認された電池か台帳チェック前だけど、この人に払う額は決まる？"), ("C1", "C2"), "判断要", ("本人への補填額を確定できるか",), reviews=("case_fact",), terms=("資産台帳",)),
    case("C03", "device", ("貸与端末の交換用電池について、補填対象に送料を含めますか。", "交換電池の送料も補填に入る？"), ("B2", "C1"), "根拠十分", ("送料を補填対象に含めるか",), terms=("送料", "対象外"), note="B2は無関係な先行根拠。"),
    case("C04", "device", ("貸与端末の修理にかかる実際の自己負担率は何%ですか。", "端末修理の自己負担って結局何パーセント？"), ("C2", "C1"), "文書不足", ("修理の実際の自己負担率",), forbidden=("50%です",), note="別契約の所在は分かるが、実率は取得していない。"),
]


def write(path: Path, data):
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n")


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    for name in ("corpus.json", "challenge.json", "manifest.json"):
        if (OUT / name).exists():
            raise RuntimeError(f"Refusing to overwrite {name}")
    corpus = [{"id": key, "element_id": uid(key), "document_id": uid(key + "-doc"),
               "version_id": uid(key + "-version"), "document_name": title,
               "heading": heading, "content": content} for key, title, heading, content in DOCS]
    rows = []
    for c in CASES:
        for variant, question in zip(("formal", "paraphrase"), c["questions"]):
            rows.append({k: v for k, v in c.items() if k != "questions"} |
                        {"id": c["scenario_id"] + "-" + variant, "variant": variant,
                         "question": question})
    assert len(rows) == 24 and len({r["scenario_id"] for r in rows}) == 12
    write(OUT / "corpus.json", corpus)
    write(OUT / "challenge.json", rows)
    write(OUT / "manifest.json", {
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "state": "precommitted_before_model_outputs", "candidate": "existing Question Contract v2",
        "baseline": "existing classification v1", "comparison_rubric": "classification-rubric-v2.0 for both arms",
        "source_commit": None, "source_file_hashes": {},
        "corpus_sha256": sha(OUT / "corpus.json"), "challenge_sha256": sha(OUT / "challenge.json"),
        "model_requested": "gemini-3.5-flash-lite", "model_fallback_if_unavailable": None,
        "temperature": 0, "seed": 42, "max_output_tokens": 2048,
        "api_min_interval_seconds": 12.2, "http_timeout_seconds": 60,
        "max_api_attempts": 400, "max_estimated_usd": 2.0, "max_wall_seconds": 3600,
        "retry": "at most two retries per task on 429/503; obey RetryInfo seconds plus 2s; never exceed global budgets",
        "price_assumption_usd_per_million": {"input": 0.25, "output": 1.5},
        "primary_metric": "paired scenario composite: both expressions must have correct Rubric-v2 label and all required answer facets without unsupported concrete claim",
        "gate_next_stage": "candidate scenario net improvement >= 2, zero new unsafe individual-payment assertions, zero new document-insufficient-to-grounded errors, and zero other new composite regressions",
        "repeat_scenarios": ["A02", "A03", "B03", "C04"],
        "retrieved_scenarios": ["A01", "A02", "A03", "B03", "C02", "C04"],
        "oracle_runs": "all 24 expressions once in both arms; repeat subset both arms and expressions once more",
        "retrieved_runs": "six scenarios both expressions both arms; local BM25 over frozen six-document corpus, top_k=3",
        "max_review_revalidation_rounds": 2,
        "known_limitations": "Synthetic development challenge, not representative accuracy or sealed holdout. Local BM25 is isolated and not deployed Qdrant. No code improvement in this round.",
    })


if __name__ == "__main__":
    main()
