"""Explicit chat commands, quantities in cartloads and sale price per cartload."""
from live_trade import RESOURCES,TRADE_CATALOG
from coordinator import sha
import base64,os
from city_labels import city_name

def command(client,text,key):
 parts=text.split()
 if not parts:return False
 verb=parts[0]
 if verb in ('/수락','/거절'):
  if len(parts)!=1:raise ValueError('인수 없음')
  t=client.call('live_status')
  if not t:raise ValueError('제안 없음')
  client.call('live_accept' if verb=='/수락' else 'live_reject',id=t['id']);return True
 if verb not in ('/판매','/선물'):return False
 if len(parts)==3 and verb=='/선물' and parts[1]=='돈':res=0;qty=0;money=int(parts[2])
 elif len(parts)==(4 if verb=='/판매' else 3) and parts[1] in RESOURCES:
  res=RESOURCES[parts[1]];qty=int(parts[2]);money=qty*int(parts[3]) if verb=='/판매' else 0
  if verb=='/판매' and int(parts[3])<=0:raise ValueError('가격')
 else:raise ValueError('거래 명령 형식')
 client.call('live_offer',request_id=key,kind='sale' if verb=='/판매' else 'gift',resource=res,quantity=qty,money=money);return True

def poll(bridge):
 from fleet_bridge import poll as fleet_poll
 return fleet_poll(bridge)

def legacy_poll(bridge):
 t=bridge.client.call('live_status')
 from empire_transport import publish
 publish(bridge,t)
 if t and t.get('suspended') and not t.get('install'):
  bridge.transfer_busy=False;bridge.incoming_trade=0
  bridge.write_changed('transport.txt','0 0 0 0')
  bridge.write_changed('trade-alert.txt','')
  mask=2 if t['state']=='offered' else 0
  bridge.write_changed('trade-view.txt',f"{t['id']} {mask}\n참가자가 나가 이 거래는 대기 중입니다."+(' 수락 전 제안은 취소할 수 있습니다.' if mask else ' 저장된 재고·대금은 유지됩니다.'))
  bridge.write_changed('trade-hint.txt','참가자가 나가 교역할 수 없습니다.')
  return ['교역 대기: 참가자 퇴장']
 if t and t['state']=='preflight':
  source=t['sender']==bridge.client.city
  bridge.write_changed('transport.txt',f"{t['id']} {t['resource']} {t['quantity']} {6 if source else 7} 1")
  marker=bridge.root/'transport-state.txt'
  try:values=list(map(int,marker.read_text().split()))
  except (OSError,ValueError):values=[]
  if len(values)==7 and values[0]==t['id'] and values[1] in (6,7):
   bridge.client.call('live_preflight',id=t['id'],available=values[1]==6)
  bridge.transfer_busy=False;bridge.incoming_trade=0
  bridge.write_changed('trade-view.txt',f"{t['id']} 2\n양쪽 도시의 선창과 수로를 확인하고 있습니다.")
  return []
 if t and t.get('source_route') and t['sender']==bridge.client.city:
  stage=4 if t['state']=='collecting' else 5 if t['state']=='departing' else 2 if t['state'] in ('saving','committed') and t.get('phase') in ('load','depart') else 2 if t.get('goods_live') and t['state']=='deferred' else 3
  bridge.write_changed('transport.txt',f"{t['id']} {t['resource']} {t['quantity']} {stage} {int(t.get('source_route',0)==3)}")
  marker=bridge.root/'transport-state.txt'
  if t['state']=='collecting' and marker.exists():
   try:contract,status,building=map(int,marker.read_text().split()[:3])
   except (OSError,ValueError):contract=status=building=0
   if contract==t['id'] and status in (3,4):
    t=bridge.client.call('live_collected',id=t['id'],building=building) if status==3 else bridge.client.call('live_collection_failed',id=t['id'])
  if t['state']=='departing' and marker.exists():
   proof={}
   try:
    values=list(map(int,marker.read_text().split()));contract,status,building=values[:3]
    if len(values)==7 and values[6]==1 and values[3:6]==[t['resource'],t['quantity'],t['source_route']]:
     proof={'departure':values[3:6]}
   except (OSError,ValueError):contract=status=building=0
   if contract==t['id'] and status in (5,4) and (status==4 or proof or not t.get('goods_live')):
    t=bridge.client.call('live_departed' if status==5 else 'live_departure_failed',id=t['id'],**proof)
 if t and not t.get('cash_live') and t['receiver']==bridge.client.city:
  stage=1 if t['state']=='travelling' else 2 if t['state'] in ('saving','committed') else 2 if t.get('goods_live') and t['state']=='deferred' else 3
  bridge.write_changed('transport.txt',f"{t['id']} {t['resource']} {t['quantity']} {stage} {int(t.get('source_route',0)==3)}")
  marker=bridge.root/'transport-state.txt'
  if t['state']=='travelling' and not t.get('cargo_delivered') and marker.exists():
   try:
    transport_id,status,building=map(int,marker.read_text().split()[:3])
   except (OSError,ValueError):transport_id=status=building=0
   if transport_id==t['id'] and status in (3,4):
    t=bridge.client.call('live_arrived',id=t['id'],building=building) if status==3 else bridge.client.call('live_transport_failed',id=t['id'])
 if not t or t.get('cash_live'):bridge.write_changed('transport.txt','0 0 0 0')
 bridge.transfer_busy=bool(t and t['state'] in ('saving','committed'))
 bridge.incoming_trade=t['id'] if t and t['state']=='offered' and t['receiver']==bridge.client.city else 0
 if bridge.incoming_trade:
  slots=bridge.client.call('lobby_status')['slots'];sender=next((x['name'] for x in slots if x['city']==t['sender']),t['sender'])
  city=city_name(t['sender'],getattr(bridge,'city_names',None))
  resource=next((k for k,v in RESOURCES.items() if v==t['resource']),'돈')
  amount=f"{t['quantity']}포대 {resource}" if t['quantity'] else f"{t['money']:,}데나리"
  bridge.write_changed('trade-alert.txt',f"{sender}({city}): {amount} {'선물' if t['kind']=='gift' else '판매'} 제안")
 else:bridge.write_changed('trade-alert.txt','')
 signature=(t['id'],t['state'],t.get('error')) if t else None
 if not getattr(bridge,'history_loaded',False) or getattr(bridge,'history_signature',None)!=signature:
  records=bridge.client.call('live_history')
  published=bridge.write_changed('trade-history.txt','\n'.join(history_line(row,getattr(bridge,'city_names',None)) for row in records) or '아직 거래 이력이 없습니다.')
  if published is not False:bridge.history_signature=signature;bridge.history_loaded=True
 if not t:
  bridge.write_changed('trade-view.txt','0 0\n아직 거래 제안이 없습니다.');bridge.write_changed('trade-hint.txt','');return []
 install=t.get('install')
 if install:
  sid=install.get('serial',t['id']);data=base64.b64decode(install['save'],validate=True)
  if sha(data)!=install['hash']:raise ValueError('거래 저장 해시 불일치')
  ack=bridge.root/'trade-installed.txt'
  if ack.exists() and ack.read_text().strip()==str(sid):bridge.client.call('live_ack',id=t['id'],hash=install['hash'],**({'result':t['result']} if 'serial' in install else {}))
  else:
   target=bridge.root/('trade-install-'+str(sid)+'.sav')
   if not target.exists():
    tmp=target.with_suffix('.tmp');tmp.write_bytes(data);os.replace(tmp,target)
   marker=bridge.root/'trade-install.txt';value=f"{sid} {install['ticks']}"
   if not marker.exists() or marker.read_text()!=value:
    tmp=marker.with_suffix('.tmp');tmp.write_text(value);os.replace(tmp,marker)
 names=getattr(bridge,'city_names',None)
 resource=next((k for k,v in RESOURCES.items() if v==t['resource']),'돈')
 desc=(f"{t['quantity']}포대 {resource}" if t['quantity'] else f"{t['money']}데나리")
 if t['kind']=='sale':desc+=f" / 합계 {t['money']}데나리"
 if t.get('error')=='거래 취소 (도시 재고·자금 변경 없음)':t=dict(t,error='거래를 취소했습니다.')
 elif t.get('error'):t=dict(t,error=t['error'].replace('·',', ').replace('→',' -> ').replace('—','-'))
 states={'offered':'수락 대기 (아래 버튼 사용)','travelling':'육상 상단 이동, 하역 중 (취소 가능)','saving':'도착 정산, 저장 중 (확정 전 취소 가능)','committed':'확정됨 / 양쪽 반영 대기','finished':'양쪽 반영 완료','rejected':t.get('error') or '거절됨'}
 if t.get('cash_live'):states['travelling']='돈을 전달하고 있습니다.'
 states['queued']='교역소 상단 귀환 대기'
 states['preflight']='양쪽 도시의 선창과 수로 검사 중'
 states['deferred']='전달 확인 대기'
 if t.get('phase')=='preflight':states['saving']='출발 전 재고, 대금, 공간 검사 중 (취소 가능)'
 states['returning']=f"화물 {t.get('cargo_remaining',0)}포대 반환 대기 ,  저장 공간 확보 후 반환 재시도"
 states['collecting']='출발 상단이 저장소 방문, 수집 중 (취소 가능)'
 states['departing']='선적 상단이 도시 출구로 이동 중 (취소 가능)'
 if t.get('phase')=='load':states['saving']='출발 검사, 선적 중';states['committed']='선적 저장을 양쪽에 적용 중'
 if t.get('phase')=='refund':states['saving']='화물 반환, 저장 중';states['committed']='반환 저장을 양쪽에 적용 중'
 if t.get('phase')=='depart':states['saving']='도시 출구 도착 확인 중';states['committed']='출발 확인을 양쪽에 적용 중'
 if t.get('source_route')==3:
  states['collecting']='무역선 입항 및 부두 노동자 선적 준비 중'
  states['departing']='선적 무역선이 수로 출구로 이동 중'
  states['travelling']='도착 무역선 입항 및 부두 노동자 하역 중'
 lines=[f"거래 #{t['id']}: {city_name(t['sender'],names)}  ->  {city_name(t['receiver'],names)}",desc+' / '+states[t['state']]]
 mask=(3 if bridge.client.city==t['receiver'] else 2) if t['state']=='offered' else (2 if t['state'] in ('collecting','departing','travelling','saving','returning') else 0)
 if t['state']=='returning':mask|=4
 if bridge.client.city==t['sender']:mask|=8
 hint='' if t['state'] in ('finished','rejected') else ('상대가 제안을 확인하고 있습니다.' if t['state']=='offered' and bridge.client.city==t['sender'] else '물품과 금액을 확인한 뒤 수락하거나 거절하세요.' if t['state']=='offered' else '돈을 전달하고 있습니다.' if not t['resource'] else '상인이 물품을 운반하고 있습니다.')
 bridge.write_changed('trade-hint.txt',hint)
 bridge.write_changed('trade-view.txt',f"{t['id']} {mask}\n"+'\n'.join(lines))
 return lines


def ui_command(client,text,key):
 parts=text.split()
 from route_bridge import command as route_command
 if route_command(client,parts,key):return
 from agreement_bridge import command as agreement_command
 if agreement_command(client,parts,key):return
 if parts==['inbox']:
  client.fleet_focus=getattr(client,'fleet_inbox',0)
  return
 if parts==['next']:
  ids=[r['id'] for r in getattr(client,'fleet_rows',[])]
  if ids:client.fleet_focus=ids[(ids.index(client.fleet_focus)+1)%len(ids)] if getattr(client,'fleet_focus',0) in ids else ids[0]
  return
 if len(parts)==2 and parts[0] in ('accept','reject'):
  client.call('live_accept' if parts[0]=='accept' else 'live_reject',id=int(parts[1]));return
 if len(parts) not in (5,6,8) or parts[0]!='offer':raise ValueError('trade form')
 mode,index,quantity,price=map(int,parts[1:5])
 resources=[item['resource'] for item in TRADE_CATALOG]
 if mode not in (0,1) or not 0<=index<len(resources):raise ValueError('trade selection')
 if index==8:
  if mode!=1:raise ValueError('money gift only')
  qty=0;money=quantity
 else:
  if mode==0 and price<=0:raise ValueError('price')
  qty=quantity;money=quantity*price if mode==0 else 0
 client.call('live_offer',request_id=key,kind='sale' if mode==0 else 'gift',resource=resources[index],quantity=qty,money=money,**({'receiver':parts[5]} if len(parts)>=6 else {}),**({'post':list(map(int,parts[6:8]))} if len(parts)==8 else {}))


def history_line(t,names=None):
 resource=next((k for k,v in RESOURCES.items() if v==t['resource']),'돈')
 amount=f"{resource} {t['quantity']}포대" if t['quantity'] else f"{t['money']}데나리"
 if t['kind']=='sale':amount+=f" / {t['money']}데나리"
 states={'offered':'수락 대기','collecting':'출발지 수집 중','departing':'출구로 이동 중','travelling':'운송 중','saving':'저장 중','committed':'반영 중','finished':'완료','rejected':'거절/실패','returning':'반환 대기'}
 states['queued']='교역소 상단 귀환 대기'
 states['preflight']='양쪽 도시의 선창과 수로 검사 중'
 states['deferred']='전달 확인 대기'
 return f"#{t['id']} [{states[t['state']]}] {city_name(t['sender'],names)} -> {city_name(t['receiver'],names)} / {amount}"
