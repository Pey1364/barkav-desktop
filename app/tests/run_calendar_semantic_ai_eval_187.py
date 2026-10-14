import os, sys, json, argparse

from pathlib import Path
from datetime import date,timedelta
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from calendar_semantic_report_187 import generate_semantic_report
from project_report_ai_187 import generate_project_text
from calendar_report_tables_187 import clean_report_description, normalized, report_table
parser=argparse.ArgumentParser(description='Explicit live AI evaluation using synthetic report fixtures only.')
parser.add_argument('--credentials-base',type=Path,required=True)
parser.add_argument('--output-dir',type=Path,required=True)
parser.add_argument('--case',type=int,help='Run only one numbered synthetic fixture after a transient provider failure.')
args=parser.parse_args()
out=args.output_dir;out.mkdir(parents=True,exist_ok=True)
cases=json.loads((Path(__file__).parent/'fixtures/calendar_semantic_cases_187.json').read_text(encoding='utf-8-sig'))['cases']
start=date(2026,9,19)
results=[]
for ci,case in enumerate(cases,1):
    if args.case and ci!=args.case:continue
    entries=[{'_day':start+timedelta(days=i),'activity':clean_report_description(body) or body,
        'activity_key':body,'details':'','_source_id':f'S{i+1}', 'تعداد عوامل پیمانکار':'0'} for i,body in enumerate(case['activities'])]
    raw_results=[]
    def call(prompt,**options):
        model,raw=generate_project_text(prompt,**options)
        raw_results.append({'model':model,'response':raw})
        return model,raw
    try:
        model,rows=generate_semantic_report(entries,start,start+timedelta(days=len(entries)-1),daily=case.get('daily',False),mode='کامل',engine='AUTO',
            base_dir=args.credentials_base,ui_settings={},generator=call)
        groups={f'R{i+1}':set() for i in range(len(entries))}
        for row in rows:
            for evidence in row['_semantic_evidence']: groups[evidence['record_id']].add(evidence.get('activity', row['شرح گزارش']))
        for seq in case['same']:
            assert set.intersection(*(groups[f'R{i}'] for i in seq)), ('same',seq,groups)
        for a,b in case['different']:
            assert not groups[f'R{a}'] & groups[f'R{b}'], ('different',a,b,groups)
        for ref in case['ignored']: assert not groups[f'R{ref}'], ('ignored',ref,groups)
        for ref,title in case.get('titles',{}).items():
            assert normalized(title) in {normalized(t) for t in groups[f'R{ref}']}, ('title',ref,title,groups)
        if case.get('compound'): assert len(groups[f"R{case['compound']}"])==2, ('compound',groups)
        for row in rows:
            refs={int(e['record_id'][1:])-1 for e in row['_semantic_evidence']}
            if refs:assert set(row['_dates'])=={entries[i]['_day'].isoformat() for i in refs}
        if case.get('daily'):assert len(rows)==len(entries)
        state={'case':case['name'],'passed':True,'model':model,'calls':len(raw_results),'headers':report_table(rows,periodic=True)[0], 'rows':rows}
        print(f'CASE {ci} PASS model={model} groups={len(rows)} calls={len(raw_results)}',flush=True)
    except Exception as exc:
        state={'case':case['name'],'passed':False,'error':str(exc),'calls':len(raw_results)}
        print(f'CASE {ci} FAIL {type(exc).__name__}: {exc}',flush=True)
    state['responses']=raw_results
    state['prompt_version']='v3-final'
    results.append(state)
    (out/'results.json').write_text(json.dumps(results,ensure_ascii=False,indent=2,default=str),encoding='utf-8')
print('RESULT',sum(item['passed'] for item in results),'/',len(results),out,flush=True)
sys.exit(0 if all(item['passed'] for item in results) else 1)
