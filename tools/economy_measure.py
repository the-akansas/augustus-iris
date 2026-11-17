"""Economy measurement and save/reload comparison on fixture cities (headless engine only, no window).

For each case (a folder holding city.sav + receipt.bin; default: handoff/review151/prepared-1..3), working on copies:
  chained     12 runs of one month each (800 ticks): every month is saved and loaded again
  continuous  one run of 12 months (9,600 ticks)
  split       6 months, save, then 6 more months
  repeat      the continuous run once more (shows run-to-run differences that have nothing to do with saving)
Each run uses the engine's measurement mode 'economy-ticks' through city_client.Engine (same exit-code and engine-log
checks as every other engine call: a log with ERROR fails the run). Nothing is built, no money is added, no setting is
changed. Output: <out>/results.json and <out>/summary.md, plus every run folder with its engine log.

    Augustus\\runtime\\python.exe -B -X utf8 tools\\economy_measure.py <out folder> [case folder ...]

Precheck (before any long run): the 0-tick audit of each case is read first. A city without population or houses,
or with neither a tax building nor any tax/export record, cannot show income, so it is not measured for throne costs
unless --allow-unsuitable is given (it can still serve as a save/reload regression case). The check alone:
    ... tools\\economy_measure.py --check <out folder> <case folder or existing audit folder> [...]
An existing audit folder (economy-audit.json + roster-audit.json) is read as it is; no engine run, nothing written there.
"""
import json,shutil,sys,time
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'Augustus'))
MONTH=800
HOUSES=range(10,30)          # BUILDING_HOUSE_SMALL_TENT .. BUILDING_HOUSE_LUXURY_PALACE (src/building/type.h)
TAX_BUILDINGS={84,85,86,87}  # BUILDING_SENATE_1_UNUSED, BUILDING_SENATE, BUILDING_FORUM, BUILDING_FORUM_2_UNUSED
FIELDS=('taxes','exports','donated','income_total','imports','wages','construction','interest','salary','sundries','tribute','levies','expenses_total')

def run(source,target,ticks):
    from city_client import Engine
    started=time.time();Engine().run('economy-ticks',source,target,qty=ticks);return time.time()-started

def state(folder):
    e=json.loads((folder/'economy-audit.json').read_text(encoding='utf8'))
    t=json.loads((folder/'trade-audit.json').read_text(encoding='utf8'))
    r=json.loads((folder/'roster-audit.json').read_text(encoding='utf8'))
    e['stock']={str(x['id']):x['stock'] for x in t['resources'] if x['stock']}
    e['buildings']=r['buildings'];return e

def precheck(audit):
    """What a 0-tick audit says about income: buildings that exist, income the city has on record, nothing measured yet."""
    e=json.loads((audit/'economy-audit.json').read_text(encoding='utf8'))
    types=[b[1] for b in json.loads((audit/'roster-audit.json').read_text(encoding='utf8'))['buildings']]
    houses=sum(1 for t in types if t in HOUSES);tax=sum(1 for t in types if t in TAX_BUILDINGS)
    records={f'{y}.{k}':e[y][k] for y in ('this_year','last_year') for k in ('taxes','exports')}
    reasons=[]
    if e['population']<=0 or not houses:reasons.append('인구 또는 주택이 없음')
    elif not tax and not any(records.values()):reasons.append('세금 징수 시설도, 세금·수출 기록도 없음 (수입원 없음)')
    return dict(audit=str(audit),population=e['population'],houses=houses,tax_buildings=tax,tax_percentage=e['tax_percentage'],
                treasury=e['treasury'],income_records=records,has_income_record=any(v>0 for v in records.values()),
                measured_income=None,suitable_for_throne_costs=not reasons,reasons=reasons,save_regression_usable=True)

def precheck_text(name,c):
    lines=[f"## {name}",f"- 시설: 인구 {c['population']}, 주택 {c['houses']}채, 세금 징수 시설 {c['tax_buildings']}개 (세율 {c['tax_percentage']}%)",
           f"- 과거 수입 기록: {'있음' if c['has_income_record'] else '없음'} ({', '.join(f'{k} {v}' for k,v in c['income_records'].items())})",
           '- 실제 측정 수입: 미측정 (12개월 측정에서만 나온다)',
           f"- 황위 비용 측정: {'적합 후보' if c['suitable_for_throne_costs'] else '부적합 - '+'; '.join(c['reasons'])}",
           '- 저장·재로드 회귀: 사용 가능 (0틱 감사가 정상적으로 읽혔다)']
    return '\n'.join(lines)

def compare(a,b):
    """Meaningful state, not file bytes: game time, money, people, work, stock and every building row."""
    keys=('year','month','day','tick','treasury','population','workers_employed','workers_needed','stock','buildings')
    return [k for k in keys if a[k]!=b[k]]

def monthly(months):
    """Month-by-month changes from the engine's own yearly records (this_year is cumulative inside a year)."""
    rows=[]
    for prev,cur in zip(months,months[1:]):
        new_year=cur['year']!=prev['year']
        row=dict(year=cur['year'],month=cur['month'],treasury=cur['treasury'],treasury_change=cur['treasury']-prev['treasury'],population=cur['population'],
                 workers_employed=cur['workers_employed'],workers_needed=cur['workers_needed'],stock=cur['stock'])
        for f in FIELDS:
            before=prev['this_year'][f]
            now=cur['last_year'][f]+cur['this_year'][f] if new_year else cur['this_year'][f]   # interval may include both sides of the year boundary
            row[f]=now-before
        rows.append(row)
    return rows

def case_name(case):return case.parent.name if case.name=='checked' else case.name

def measure(case,out,allow_unsuitable=False):
    name=case_name(case)
    base=out/name
    if base.exists():raise FileExistsError('Measurement output already exists: '+str(base))
    (base/'m00').mkdir(parents=True)
    for file in ('city.sav','receipt.bin'):shutil.copy2(case/file,base/'m00'/file)
    run(base/'m00',base/'m00-audit',0)
    check=precheck(base/'m00-audit');(base/'precheck.json').write_text(json.dumps(check,ensure_ascii=False,indent=1),encoding='utf8')
    print(precheck_text(name,check),flush=True)
    if not check['suitable_for_throne_costs'] and not allow_unsuitable:
        return dict(case=str(case),skipped='; '.join(check['reasons']),precheck=check)
    months=[state(base/'m00-audit')];seconds=0;previous=base/'m00'
    for m in range(1,13):
        print(f'{name}: month {m}/12',flush=True)
        seconds+=run(previous,base/f'm{m:02d}',MONTH);months.append(state(base/f'm{m:02d}'));previous=base/f'm{m:02d}'
    cont_seconds=run(base/'m00',base/'continuous',12*MONTH);cont=state(base/'continuous')
    run(base/'m00',base/'half',6*MONTH);run(base/'half',base/'split',6*MONTH);split=state(base/'split')
    run(base/'m00',base/'repeat',12*MONTH);repeat=state(base/'repeat')
    return dict(case=str(case),precheck=check,start=months[0],months=monthly(months),end=months[-1],
                differences=dict(chained_vs_continuous=compare(months[-1],cont),split_vs_continuous=compare(split,cont),repeat_vs_continuous=compare(repeat,cont)),
                end_values={k:dict(treasury=v['treasury'],population=v['population'],buildings=len(v['buildings'])) for k,v in (('chained',months[-1]),('continuous',cont),('split',split),('repeat',repeat))},
                seconds=dict(chained=round(seconds,1),continuous=round(cont_seconds,1)))

def summary(results):
    lines=['# 경제 측정 결과 (economy_measure.py)','','순자금 변화는 총수입이 아니다. 항목별 값은 엔진의 연간 재정 기록 차이다.','']
    for r in results:
        if r.get('skipped'):
            lines+=[f"## {r.get('case_name',Path(r['case']).name)}",'',f"측정하지 않음 (사전 점검): {r['skipped']}. 저장·재로드 회귀용으로는 --allow-unsuitable로 실행할 수 있다.",'']
            continue
        lines+=[f"## {r.get('case_name',Path(r['case']).name)}",'',f"시작: {r['start']['year']}년 {r['start']['month']+1}월, 자금 {r['start']['treasury']}, 인구 {r['start']['population']}, 세율 {r['start']['tax_percentage']}%",'',
                '| 월 | 자금 | 순변화 | 세금 | 수출 | 수입품 | 임금 | 봉급 | 기타 | 인구 | 고용 | 부족 |','| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |']
        for m in r['months']:
            lines.append(f"| {m['year']}.{m['month']+1} | {m['treasury']} | {m['treasury_change']} | {m['taxes']} | {m['exports']} | {m['imports']} | {m['wages']} | {m['salary']} | {m['sundries']+m['interest']+m['levies']+m['construction']+m['tribute']} | {m['population']} | {m['workers_employed']} | {m['workers_needed']} |")
        net=sum(m['treasury_change'] for m in r['months'])
        lines+=['',f"12개월 순자금 변화: {net}",f"저장 비교(다른 항목): 매달 저장 {r['differences']['chained_vs_continuous'] or '없음'} / 6+6 {r['differences']['split_vs_continuous'] or '없음'} / 같은 연속 실행 반복 {r['differences']['repeat_vs_continuous'] or '없음'}",
                f"끝 값: {json.dumps(r['end_values'],ensure_ascii=False)}",'']
    return '\n'.join(lines)

def check_only(out,cases):
    """Only the listed inputs; an existing audit is reused, a case gets a fresh 0-tick audit in a new folder."""
    if not cases:raise SystemExit('--check: 점검할 입력을 지정하세요.')
    out.mkdir(parents=True,exist_ok=True)
    report=[];texts=['# 경제 측정 사전 점검','']
    for case in cases:
        if (case/'economy-audit.json').is_file() and (case/'roster-audit.json').is_file():audit=case
        elif (case/'city.sav').is_file() and (case/'receipt.bin').is_file():
            audit=out/(case_name(case)+'-check')
            if audit.exists():raise FileExistsError('Check output already exists: '+str(audit))
            work=out/(case_name(case)+'-check-input');work.mkdir(parents=True)
            for file in ('city.sav','receipt.bin'):shutil.copy2(case/file,work/file)
            run(work,audit,0)
        else:raise SystemExit(f'감사 결과도, city.sav/receipt.bin도 없음: {case}')
        c=precheck(audit);report.append(dict(c,case=str(case)));texts+=[precheck_text(case_name(case),c),'']
    target=out/'precheck.json'
    if target.exists():raise FileExistsError('Check output already exists: '+str(target))
    target.write_text(json.dumps(report,ensure_ascii=False,indent=1),encoding='utf8')
    (out/'precheck.md').write_text('\n'.join(texts),encoding='utf8');print('\n'.join(texts))
    return report

def main():
    args=sys.argv[1:];check='--check' in args;allow='--allow-unsuitable' in args
    args=[a for a in args if a not in ('--check','--allow-unsuitable')]
    if not args:raise SystemExit(__doc__)
    out=Path(args[0]);out.mkdir(parents=True,exist_ok=True)
    if check:check_only(out,[Path(p) for p in args[1:]]);return
    cases=[Path(p) for p in args[1:]] or [ROOT/'handoff/review151'/f'prepared-{i}'/'checked' for i in (1,2,3)]
    results=[]
    for case in cases:
        if not ((case/'city.sav').is_file() and (case/'receipt.bin').is_file()):raise SystemExit(f'city.sav/receipt.bin 없음: {case}')
        r=measure(case,out,allow)
        r['case_name']=case_name(case);results.append(r)
    (out/'results.json').write_text(json.dumps(results,ensure_ascii=False,indent=1),encoding='utf8')
    (out/'summary.md').write_text(summary(results),encoding='utf8');print(out/'summary.md')

if __name__=='__main__':main()
