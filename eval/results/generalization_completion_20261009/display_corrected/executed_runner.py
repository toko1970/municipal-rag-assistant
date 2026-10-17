"""Offline, paired service fault injection; never calls an external provider."""
import copy
import hashlib
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from uuid import UUID, uuid4

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from src.contracts import IndexableElement, SearchHit
from src.llm_provider import StructuredLLMResult
from src.query_service import answer_question
from src.query_service_v2 import answer_question_v2

OUT = ROOT / 'eval/results/generalization_completion_20261009/display_corrected'
EID = '00000000-0000-0000-0000-000000000001'
OTHER = '00000000-0000-0000-0000-000000000099'

def dump(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2, default=str) + '\n')

class Provider:
    provider_name = 'offline-injection'
    model = 'fixed-payload'
    def __init__(self, payload, fail=False):
        self.payload, self.fail = payload, fail
    def generate_structured(self, prompt, schema):
        if self.fail:
            raise RuntimeError('injected provider failure')
        return StructuredLLMResult(self.provider_name, self.model, copy.deepcopy(self.payload), 0, 0, 0)

class Logger:
    def __init__(self):
        self.events = []
    def start_request(self, question):
        self.events.append({'stage': 'request', 'question': question})
        return uuid4()
    def record_retrieval(self, request_id, hits):
        self.events.append({'stage': 'retrieval', 'n': len(hits)})
    def record_generation_attempt(self, request_id, **kw):
        self.events.append({'stage': 'generation', **kw})
        return uuid4()
    def record_classification_attempt(self, request_id, **kw):
        self.events.append({'stage': 'classification', **kw})
        return uuid4()
    def record_answer_result(self, request_id, **kw):
        self.events.append({'stage': 'answer', **kw})
        return uuid4()

class Index:
    def __init__(self, hit):
        self.hit = hit
    def search(self, vector, limit):
        return [self.hit]

def fixture(kind, arm):
    v2 = arm == 'v2'
    eligibility = kind in {'normal_review', 'contradictory_missing', 'false_support_missing'}
    question = '研修補助の対象ですか。研修は修了しています。' if eligibility else '給与支給日はいつですか。'
    evidence = '研修補助は修了済みかつ在籍30日以上なら対象。在籍日数不明なら支給可否を確定できない。' if eligibility else '給与は毎月21日に支給する。'
    claim = '在籍日数の確認が必要なため、対象可否は確定できません。' if eligibility else '給与は毎月21日に支給されます。'
    if kind == 'normal_insufficient':
        evidence = '給与手続の問合せ窓口は総務課である。支給日について本資料には記載しない。'
        claim = '今回取得した資料では給与支給日を確認できません。'
    if kind == 'false_support_missing':
        claim = '研修補助の対象です。支給が確定しています。'
    support = kind != 'unsupported_flag'
    coverage = kind != 'normal_insufficient'
    needs = kind == 'normal_review'
    missing = eligibility
    contract = {'schema_version': '1.0', 'status': 'SUCCESS', 'requested_facets': [{'facet_id': 'facet-1', 'requirement': '研修補助の支給可否' if eligibility else '給与支給日', 'answer_type': 'eligibility' if eligibility else 'date'}], 'input_facts': [], 'error_code': None}
    c = {'claim_id': 'claim-1', 'ordinal': 1, 'text': claim, 'evidence_element_ids': [EID], 'evidence_kind': 'text'}
    if v2:
        c.update(facet_ids=['facet-1'], input_fact_ids=[], calculation_ids=[])
    a = {'schema_version': '3.0-candidate' if v2 else '1.0', 'claims': [c], 'missing_conditions': []}
    if v2:
        a['date_calculations'] = []
    if missing:
        a['missing_conditions'] = [{'condition_id': 'condition-1', 'type': 'case_fact', 'description': '在籍日数', 'facet_ids': ['facet-1'], 'evidence_element_ids': [EID]}] if v2 else ['在籍日数']
    if v2:
        assessments = [{'facet_id': 'facet-1', 'claim_ids': ['claim-1'], 'claim_support': 'fully_supported' if support else 'unsupported', 'evidence_coverage': 'sufficient' if coverage else 'insufficient', 'human_review_requirements': [{'review_id': 'review-1', 'type': 'case_fact', 'description': '在籍日数', 'condition_ids': ['condition-1'], 'evidence_element_ids': [EID]}] if needs else [], 'evidence_element_ids': [EID], 'confidence': .95}]
        cl = {'schema_version': '2.0-candidate', 'status': 'SUCCESS', 'facet_assessments': assessments, 'confidence': .95, 'error_code': None}
    else:
        cl = {'schema_version': '1.0', 'status': 'SUCCESS', 'factors': {'retrieval_sufficient': coverage, 'answer_fully_supported': support, 'requires_case_facts': needs, 'requires_policy_judgment': False, 'version_conflict': False}, 'confidence': .95, 'error_code': None}
    if kind == 'empty_claims':
        a['claims'] = []
        if v2:
            cl['facet_assessments'][0]['claim_ids'] = []
    if kind == 'unknown_evidence':
        a['claims'][0]['evidence_element_ids'] = [OTHER]
    if kind == 'malformed_generation':
        a = {'schema_version': 'broken'}
    if kind == 'malformed_classification':
        cl = {'schema_version': 'broken'}
    return {'id': kind, 'arm': arm, 'question': question, 'evidence': evidence, 'contract': contract, 'answer': a, 'classification': cl, 'generator_fail': kind == 'provider_generation', 'classifier_fail': kind == 'provider_classification', 'normal': kind.startswith('normal_'), 'unsupported_text': claim if kind == 'false_support_missing' else None}

def run(task):
    logger = Logger()
    element = IndexableElement(id=UUID(EID), document_id=UUID(EID), version_id=UUID(EID), document_name='固定人工制度', heading='条件', content=task['evidence'])
    kw = dict(embed_query=lambda q: [1.0], vector_index=Index(SearchHit(element, 1.0, 1)), generator=Provider(task['answer'], task['generator_fail']), classifier=Provider(task['classification'], task['classifier_fail']), event_logger=logger, answer_schema={}, classification_schema={})
    try:
        if task['arm'] == 'v2':
            result = answer_question_v2(task['question'], question_contract_provider=Provider(task['contract']), question_contract_schema={}, **kw)
        else:
            result = answer_question(task['question'], **kw)
        error = None
    except Exception as exc:
        result, error = None, {'type': type(exc).__name__, 'message': str(exc)}
    text = (result or {}).get('answer', '')
    claims = (result or {}).get('claims', [])
    expected_label = {'normal_sufficient': '根拠十分', 'normal_review': '判断要', 'normal_insufficient': '文書不足'}.get(task['id'])
    return {'id': task['id'], 'arm': task['arm'], 'result': result, 'exception': error, 'events': logger.events, 'normal_control_pass': (bool(result) and result.get('answer_label') == expected_label and (bool(claims) if task['id'] != 'normal_insufficient' else not claims)) if task['normal'] else None, 'unsafe_claim_visible': bool(task['unsupported_text'] and task['unsupported_text'] in text), 'safe_returned_display': bool(result and not (task['unsupported_text'] and task['unsupported_text'] in text)), 'returned': result is not None, 'visible_claim_count': len(claims)}

def main():
    if OUT.exists():
        raise RuntimeError('Immutable output already exists')
    OUT.mkdir(parents=True)
    (OUT / 'executed_runner.py').write_bytes(Path(__file__).read_bytes())
    kinds = ['normal_sufficient', 'normal_review', 'normal_insufficient', 'empty_claims', 'contradictory_missing', 'false_support_missing', 'unknown_evidence', 'unsupported_flag', 'malformed_generation', 'malformed_classification', 'provider_generation', 'provider_classification']
    tasks = [fixture(k, arm) for k in kinds for arm in ['v1', 'v2']]
    dump(OUT / 'tasks.json', tasks)
    sources = ['src/query_service.py', 'src/query_service_v2.py', 'src/answering.py', 'src/classification_contract_v2.py', str(Path(__file__).relative_to(ROOT))]
    dump(OUT / 'manifest.json', {'created_at': datetime.now(timezone.utc).isoformat(), 'source_hashes': {p: hashlib.sha256((ROOT/p).read_bytes()).hexdigest() for p in sources}, 'task_sha256': hashlib.sha256((OUT/'tasks.json').read_bytes()).hexdigest(), 'cases_per_arm': 12, 'calls': 0, 'primary': 'normal controls remain correct; unsafe assertion must not be displayed', 'scope': 'service fault injection; synthetic provider payloads; no live model or UI evaluation; exceptions are not successful recovery', 'candidate': 'existing v2 versus existing v1, no source changes', 'schema_note': 'empty schema passed to stub provider; actual service parsers validate payloads'})
    records = [run(t) for t in tasks]
    dump(OUT / 'records.json', records)
    summary = {a: {'n': len(rr := [r for r in records if r['arm'] == a]), 'normal_correct': sum(r['normal_control_pass'] is True for r in rr), 'normal_n': 3, 'exceptions': sum(r['exception'] is not None for r in rr), 'unsafe_claim_visible': sum(r['unsafe_claim_visible'] for r in rr), 'fault_returned_safe_display': sum(r['safe_returned_display'] for r in rr if r['normal_control_pass'] is None), 'fault_n': 9} for a in ['v1', 'v2']}
    dump(OUT / 'summary.json', summary)
    print(json.dumps(summary, ensure_ascii=False))

if __name__ == '__main__':
    main()
