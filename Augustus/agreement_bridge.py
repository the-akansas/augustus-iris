"""Presentation and input adapter; contract settlement stays on the host."""
import time
from city_labels import city_name

def stock_args(b):
 args={}
 for key,name in (('stock','trade-stock.txt'),('storage_stock','trade-storage-stock.txt')):
  try:
   p=b.root/name
   if 0<=time.time()-p.stat().st_mtime<5:args[key]=[list(map(int,line.split())) for line in p.read_text().splitlines()]
  except (OSError,ValueError):pass
 return args

def poll(b):
 now=time.monotonic()
 if now<getattr(b,'agreement_due',0):return
 b.agreement_due=now+1
 args=stock_args(b)
 data=b.client.call('agreement_poll',**args)
 b.agreements=data['agreements'];b.client.agreements=b.agreements
 try:publish(b,data)
 except OSError:pass # Presentation file contention must not delay native transport.

def publish(b,data):
 import city_notices
 notices=city_notices.state(b)
 targets=[]
 for entry in b.agreements:
  other=entry['buyer'] if b.client.city==entry['seller'] else entry['seller']
  targets.append(f"{entry['id']} {other}")
  if entry['state']!='offered' or entry['proposer']==b.client.city:city_notices.drop(notices,4,entry['id']) # Answered: nothing left to do.
  if entry['state']=='offered' and entry['proposer']!=b.client.city:
   key=f"agreement:{b.client.session}:{entry['id']}:{entry.get('revision',0)}"
   label='조건 조정 제안' if entry.get('revision',0) else '거래 제안'
   city_notices.add(notices,key,4,entry['id'],0,0,0,f'{city_name(other,getattr(b,"city_names",None))}: {label}이 왔습니다.',pending=True)
  # My proposal (or counter-proposal) was waiting on the other city: tell me its answer once.
  before=getattr(b,'agreement_previous',{}).get(entry['id'])
  if before and before[0]=='offered' and before[1]==b.client.city and entry['state']!='offered':
   name=city_name(other,getattr(b,"city_names",None))
   goods=f"{city_notices.resource_name(entry['resource'])} {entry['quantity']}포대 · {entry['money']:,} Dn"
   answer='수락했습니다' if entry['state'] in ('active','complete') else '거절했습니다'
   key=f"agreement:{b.client.session}:{entry['id']}:{before[2]}:{answer}"
   city_notices.add(notices,key,5,entry['id'],0,0,0,f'{name}: 거래 제안을 {answer}. ({goods})')
  # Delivery deadline passed: both sides hear it once (the seller could not send within three months).
  if before and before[0]=='active' and entry['state']=='stopped' and entry.get('expired'):
   name=city_name(other,getattr(b,"city_names",None))
   goods=f"{city_notices.resource_name(entry['resource'])} {entry['quantity']}포대"
   text=(f'{name}에 보낼 {goods}을 3개월 안에 보내지 못해 계약이 만료되었습니다.' if b.client.city==entry['seller']
         else f'{name}이 {goods}을 3개월 안에 보내지 않아 계약이 만료되었습니다. 대금은 나가지 않았습니다.')
   city_notices.add(notices,f"agreement:{b.client.session}:{entry['id']}:expired:{entry.get('revision',0)}",5,entry['id'],0,0,0,text)
 b.agreement_previous={e['id']:(e['state'],e['proposer'],e.get('revision',0)) for e in b.agreements}
 b.write_changed('agreement-inbox.txt','\n'.join(str(a['id']) for a in b.agreements if a['state']=='offered' and a['proposer']!=b.client.city)+'\n')
 b.write_changed('agreement-targets.txt','\n'.join(targets)+'\n')
 city_notices.publish(b,notices)
 b.write_changed('trade-peer-stock.txt',''.join(f'self {res} {qty}\n' for res,qty in data.get('stocks',{}).get(b.client.city,{}).items()))
 b.write_changed('trade-buy-catalog.txt',''.join(f'{peer} {res}\n' for peer,items in data.get('purchase_catalogs',{}).items() for res in items))
 rows=b.agreements;focus=getattr(b.client,'agreement_focus',0)
 peer=getattr(b.client,'agreement_peer',None)
 if peer:rows=[a for a in rows if peer in (a['seller'],a['buyer'])]
 a=next((a for a in rows if a['id']==focus),None)
 if a is None:a=next((a for a in rows if a['state']=='offered' and a['proposer']!=b.client.city),next((a for a in rows if a['state'] in ('active','paused')),rows[0] if rows else None))
 pending=sum(a['state']=='offered' and a['proposer']!=b.client.city for a in rows)
 b.write_changed('agreement-notify.txt',str(pending))
 if not a:b.write_changed('agreement-view.txt','0 0\n계약이 없습니다. 구매 또는 지속 거래 제안을 보내세요.');return
 from live_trade import RESOURCES
 resource=next(k for k,v in RESOURCES.items() if v==a['resource'])
 names=getattr(b,'city_names',None);seller=city_name(a['seller'],names);buyer=city_name(a['buyer'],names)
 mask=(1 if a['state']=='offered' and a['proposer']!=b.client.city else 0)|(2 if a['state'] in ('offered','active','paused') else 0)|(4 if a['state']=='paused' else 0)|(16 if a['state']=='offered' and a['proposer']!=b.client.city else 0)
 state={'offered':'상대 동의 대기','active':'반복 운송 / 재고·상단 배정 대기' if a['repeat'] else '교역소 준비 / 일회 운송 대기','paused':'운송·퇴장·교역소 확인 후 재제안','stopped':'납기 3개월을 넘겨 만료됨' if a.get('expired') else '중단됨 · 이미 출발한 회차는 정산 유지','complete':'거래 완료'}[a['state']]
 if a['state']=='offered' and a.get('revision',0)>0:state='조건 조정 제안 · 최종 동의 대기'
 lines=[f"[{'지속 계약' if a['repeat'] else '거래 제안'} #{a['id']}] {state}",f'물품: {resource} {a["quantity"]}포대 / {seller} → {buyer}',f'총액: {a["money"]:,} Dn · 단가 {a["money"]/a["quantity"]:g} Dn/포대', '일부 수량 허용: 감량 수락 시 바로 체결' if a.get('allow_partial') else '조건을 조정하면 상대가 다시 확인합니다.']
 peer=a['buyer'] if b.client.city==a['seller'] else a['seller']
 b.write_changed('agreement-view.txt',f"{a['id']} {mask} {a.get('revision',0)} {a['quantity']} {a.get('allow_partial',0)} {peer}\n"+'\n'.join(lines))

def command(client,parts,key):
 if len(parts)==3 and parts[0]=='contract_focus':
  client.agreement_peer=parts[2];client.agreement_focus=int(parts[1]);return True
 if len(parts)==2 and parts[0]=='contract_open':
  client.agreement_peer=parts[1];client.agreement_focus=0;return True
 if parts==['contract_next']:
  rows=getattr(client,'agreements',[]);peer=getattr(client,'agreement_peer',None);ids=[a['id'] for a in rows if not peer or peer in (a['seller'],a['buyer'])];current=getattr(client,'agreement_focus',0)
  if ids:client.agreement_focus=ids[(ids.index(current)+1)%len(ids)] if current in ids else ids[0]
  return True
 if len(parts)==5 and parts[0] in ('contract_accept','contract_stop','contract_resume'):
  client.call({'contract_accept':'agreement_accept','contract_stop':'agreement_stop','contract_resume':'agreement_resume'}[parts[0]],id=int(parts[1]),post=list(map(int,parts[2:4])),revision=int(parts[4]),request_id=key);return True
 if len(parts) in (6,7) and parts[0]=='contract_counter':
  # contract_counter id revision quantity post generation [unit price]
  extra=dict(money=int(parts[3])*int(parts[6])) if len(parts)==7 else {}
  client.call('agreement_counter',id=int(parts[1]),revision=int(parts[2]),quantity=int(parts[3]),post=list(map(int,parts[4:6])),request_id=key,**extra);return True
 if parts and parts[0]=='contract_offer':
  if len(parts)!=10:raise ValueError('계약 입력 형식 오류')
  from live_trade import TRADE_CATALOG
  mode,index,qty,price=map(int,parts[1:5]);repeat=int(parts[8])
  if mode not in (0,2) or not 0<=index<len(TRADE_CATALOG) or not TRADE_CATALOG[index]['resource']:raise ValueError('계약 품목 오류')
  a=client.call('agreement_offer',request_id=key,mode='buy' if mode==2 else 'sell',peer=parts[5],resource=TRADE_CATALOG[index]['resource'],quantity=qty,money=qty*price,repeat=repeat,post=list(map(int,parts[6:8])),allow_partial=int(parts[9]));client.agreement_peer=parts[5];client.agreement_focus=a['id'];return True
 return False
