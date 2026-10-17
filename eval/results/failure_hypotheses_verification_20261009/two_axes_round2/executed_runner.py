"""Final reviewer-requested exploratory two-axis probe, four fixed historical inputs."""
import hashlib,json,sys,time
from pathlib import Path
from datetime import datetime,timezone
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
P=ROOT/'eval/results/failure_hypotheses_verification_20261009';OUT=P/'two_axes_round2'
def write(n,x):(OUT/n).write_text(json.dumps(x,ensure_ascii=False,indent=2)+'\n')
def read(p):return json.loads(p.read_text())
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def main():
 OUT.mkdir(exist_ok=True)
 source=read(P/'tasks.json');tasks=[]
 prompt='以下を2軸で独立判定してください。最終ラベルは導出しません。\n軸1 answer_supported: 提示された固定回答の全重要主張が取得根拠で支持されるか。support_evidence_idsに判断に用いたelement_idを列挙してください。\n軸2 requested_value_determinable: 入力decision_targetで指定する行政判断の対象自体（個別の支給可否・金額・期限等）の値を、提示された事実だけで確定できるか。「可否を今確定できない」という根拠付き説明を作れることと、その支給可否自体の確定とは区別します。支給可否が保留ならfalse、条件を規則へ当てはめ額や期限が決まるならtrueです。範囲外の実務条件は追加しないでください。\n各軸の理由を短く記載してください。\n入力: '
 schema={'type':'object','properties':{'answer_supported':{'type':'boolean'},'support_evidence_ids':{'type':'array','items':{'type':'string'}},'support_reason':{'type':'string'},'requested_value_determinable':{'type':'boolean'},'determinability_reason':{'type':'string'}},'required':['answer_supported','support_evidence_ids','support_reason','requested_value_determinable','determinability_reason'],'additionalProperties':False}
 for t in source:
  if t['origin'].startswith('historical_visible') and t['arm']=='baseline':
   payload={k:t[k] for k in ['question','evidence','answer']};payload['decision_target']='期限' if t['id'].startswith('TH022') else '金額' if t['id'].startswith('TH047') else '給付可否';tasks.append({'id':t['id'],'prompt':prompt+json.dumps(payload,ensure_ascii=False),'input':payload,'expected':{'answer_supported':True,'requested_value_determinable':t['id'].startswith(('TH022','TH047'))},'expectation_reason':'TH025/031は照合未了のため支給可否保留、TH022/047は提示条件から期限/額が決まる。全4固定回答の主張自体は支持される。'})
 write('tasks.json',tasks);write('schema.json',schema)
 write('manifest.json',{'review_revalidation_round':2,'started_at':datetime.now(timezone.utc).isoformat(),'model':'gemini-3.1-flash-lite','temperature':0,'max_calls':4,'max_campaign_calls':39,'max_campaign_estimated_cost_usd':.10,'max_output_tokens':1536,'http_attempts':1,'tasks_sha256':sha(OUT/'tasks.json'),'schema_sha256':sha(OUT/'schema.json'),'script_sha256':sha(Path(__file__)),'purpose':'Independent axes under explicitly prescribed definitions; exploratory feasibility probe, not causal diagnosis or quality improvement measure.'})
 if '--run' not in sys.argv:return
 if (OUT/'records.jsonl').exists():raise RuntimeError('Refuse overwrite')
 from google import genai
 from google.genai import types as gt
 import config
 prior=[json.loads(l) for l in (P/'api_records.jsonl').read_text().splitlines()]+[json.loads(l) for l in (P/'invalidated_round0/api_records.jsonl').read_text().splitlines()]
 assert len(prior)==35
 spent=sum(r.get('estimated_cost_usd',0) for r in prior);records=[]
 client=genai.Client(api_key=config.GOOGLE_API_KEY,http_options=gt.HttpOptions(timeout=45000,retry_options=gt.HttpRetryOptions(attempts=1)))
 for t in tasks:
  reserve=(len(t['prompt'].encode())+len(json.dumps(schema).encode())+3000)*.25/1e6+1536*1.5/1e6
  if spent+reserve>.10:break
  r={'id':t['id'],'prompt_sha256':hashlib.sha256(t['prompt'].encode()).hexdigest(),'expected':t['expected']}
  try:
   v=client.models.generate_content(model='gemini-3.1-flash-lite',contents=t['prompt'],config=gt.GenerateContentConfig(temperature=0,max_output_tokens=1536,response_mime_type='application/json',response_json_schema=schema));r['raw_text']=v.text;r['data']=json.loads(v.text);r['usage']=v.usage_metadata.model_dump();r['model_version']=v.model_version
   u=v.usage_metadata;r['estimated_cost_usd']=((u.prompt_token_count or 0)*.25+((u.candidates_token_count or 0)+(u.thoughts_token_count or 0))*1.5)/1e6;spent+=r['estimated_cost_usd'];r['error']=None
   assert set(r['data'])==set(schema['required'])
   ids={e['element_id'] for e in t['input']['evidence']};assert r['data']['support_evidence_ids'] and set(r['data']['support_evidence_ids'])<=ids
   r['correct']=all(type(r['data'][k]) is bool and r['data'][k]==v for k,v in t['expected'].items())
  except Exception as ex:r['error']=type(ex).__name__
  records.append(r)
  with (OUT/'records.jsonl').open('a') as f:f.write(json.dumps(r,ensure_ascii=False)+'\n')
  print(t['id'],r.get('correct'),r['error'],flush=True)
  if r['error']:break
  time.sleep(5.1)
 write('summary.json',{'completed':len(records),'correct':sum(r.get('correct',False) for r in records),'errors':sum(r['error'] is not None for r in records),'campaign_calls':len(prior)+len(records),'round_estimated_cost_usd':sum(r.get('estimated_cost_usd',0) for r in records),'campaign_estimated_cost_usd':spent})
if __name__=='__main__':main()
