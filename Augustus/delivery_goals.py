"""Cumulative deliveries committed with both native city snapshots, never on offer/ACK.
Transfers are serialized by live_trade. Persisting their monotonic ID prevents
retries from counting twice; transport_snapshot reserves these IDs after restore.
"""
import json,re
from pathlib import Path
CATALOG={x['resource']:x['name'] for x in json.loads(Path(__file__).with_name('trade-catalog.json').read_text(encoding='utf8')) if x['resource']}

def validate(goals,cities):
 if not isinstance(goals,list) or len(goals)>16:raise ValueError('납품 과제는 최대 16개입니다.')
 ids=set()
 for g in goals:
  if not isinstance(g,dict) or set(g)!={'id','sender','receiver','resource','quantity','kind'}:raise ValueError('납품 과제 형식 오류')
  if not isinstance(g['id'],str) or not re.fullmatch('[a-z0-9-]{1,40}',g['id']) or g['id'] in ids:raise ValueError('납품 과제 식별자 오류')
  ids.add(g['id'])
  if not isinstance(g['sender'],str) or not isinstance(g['receiver'],str) or g['sender'] not in cities or g['receiver'] not in cities or g['sender']==g['receiver']:raise ValueError('납품 과제의 보내는 도시와 받는 도시를 확인하세요.')
  if type(g['resource'])!=int or g['resource'] not in CATALOG:raise ValueError('납품 물품 오류: 돈은 물품 납품에 포함되지 않습니다.')
  if type(g['quantity'])!=int or not 1<=g['quantity']<=1000000:raise ValueError('납품 수량은 1~1,000,000포대입니다.')
  if g['kind'] not in ('gift','sale','either'):raise ValueError('납품 거래 방식 오류')

def initialize(db):
 db.execute('CREATE TABLE IF NOT EXISTS objective_delivery(id INTEGER PRIMARY KEY,counts TEXT,last_id INTEGER)')

def initial(goals):return dict(counts={g['id']:0 for g in goals},last_id=0)

def snapshot(db,goals):
 row=db.execute('SELECT counts,last_id FROM objective_delivery WHERE id=1').fetchone()
 return dict(counts=json.loads(row[0]),last_id=row[1]) if row else initial(goals)

def validate_snapshot(value,goals):
 if not isinstance(value,dict) or set(value)!={'counts','last_id'} or type(value['last_id'])!=int or not 0<=value['last_id']<2**32:raise ValueError('납품 저장 정보 오류')
 if not isinstance(value['counts'],dict) or set(value['counts'])!={g['id'] for g in goals}:raise ValueError('납품 진행 정보 누락')
 for g in goals:
  n=value['counts'][g['id']]
  if type(n)!=int or not 0<=n<=g['quantity']:raise ValueError('납품 진행 수량 오류')
 if value['last_id']==0 and any(value['counts'].values()):raise ValueError('납품 거래 기록 누락')

def restore(db,value,goals):
 validate_snapshot(value,goals)
 db.execute('INSERT OR REPLACE INTO objective_delivery VALUES(1,?,?)',(json.dumps(value['counts'],sort_keys=True),value['last_id']))

def matches(g,t):
 return g['sender']==t['sender'] and g['receiver']==t['receiver'] and g['resource']==t['resource'] and (g['kind']=='either' or g['kind']==t['kind'])

def delivered(db,t,exact_once=False):
 row=db.execute('SELECT rules,completed_tick FROM objective_state WHERE id=1').fetchone()
 if not row or row['completed_tick'] is not None:return
 goals=json.loads(row['rules']).get('deliveries',[])
 if not goals:return
 value=snapshot(db,goals)
 if not exact_once and t['id']<=value['last_id']:return
 for g in goals:
  if matches(g,t):value['counts'][g['id']]=min(g['quantity'],value['counts'][g['id']]+t['quantity'])
 value['last_id']=max(value['last_id'],t['id']);restore(db,value,goals)

def met(value,goals):return all(value['counts'][g['id']]>=g['quantity'] for g in goals)

def in_transit(db,goals):
 result={g['id']:0 for g in goals}
 if not db.execute("SELECT 1 FROM sqlite_master WHERE name='live_transfer'").fetchone():return result
 t=db.execute('SELECT * FROM live_transfer ORDER BY id DESC LIMIT 1').fetchone()
 if not t:return result
 c=db.execute('SELECT phase FROM live_cargo WHERE id=?',(t['id'],)).fetchone()
 if not c:return result
 active=t['state'] in ('departing','travelling') or t['state']=='saving' and c['phase'] in ('depart','deliver') or t['state']=='committed' and c['phase'] in ('load','depart')
 if active:
  for g in goals:
   if matches(g,t):result[g['id']]=t['quantity']
 return result

def lines(value,names,own,view):
 goals=value['rules'].get('deliveries',[])
 if not goals:return []
 result=[];counts=value['deliveries']['counts'];missing=set(value.get('missing',[]))
 for g in goals:
  involved=own in (g['sender'],g['receiver'])
  if view=='mine' and not involved or view=='others' and involved:continue
  if not result:result=['','[물품 납품 과제]']
  done=counts[g['id']]>=g['quantity'];waiting=not done and bool({g['sender'],g['receiver']}&missing)
  result.append('['+('납품 완료' if done else '담당자 대기' if waiting else '진행 중')+'] '+'보내는 도시: '+names.get(g['sender'],g['sender'])+' / 받는 도시: '+names.get(g['receiver'],g['receiver']))
  kind={'gift':'선물만','sale':'판매만','either':'선물 또는 판매'}[g['kind']]
  result.append(CATALOG[g['resource']]+' 배송 완료: '+format(counts[g['id']],',')+' / '+format(g['quantity'],',')+'포대 ('+kind+')')
  transit=value.get('delivery_in_transit',{}).get(g['id'],0)
  if waiting:result.append('담당자 필요: '+', '.join(names.get(c,c) for c in (g['sender'],g['receiver']) if c in missing)+'. 다음 이어하기에서 담당자를 배정하세요.')
  if own==g['sender']:result.append('내 역할: 이 도시로 물품을 보냅니다.')
  elif own==g['receiver']:result.append('내 역할: 받은 제안을 수락하고 물품 도착을 기다립니다.')
  if transit and not done:result.append('운송 중: '+str(transit)+'포대. 도착 후 양쪽 도시 반영이 확정되면 집계합니다.')
 if result:result.append('납품은 누적 수량입니다. 완료된 물품을 소비해도 진행량은 줄지 않습니다.')
 return result
