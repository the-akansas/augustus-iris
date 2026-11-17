"""Game menu mailbox for authenticated army orders."""
import json,time

def eta(bridge,row):
 ticks=row.get('remaining_ticks')
 if ticks is None:return ''
 months=(ticks+799)//800
 text=f'{months}개월 이내 도착' if months else '도착 처리 중'
 try:
  year,month,day,tick=map(int,(bridge.root/'calendar.txt').read_text().split())
  total=((month*16+day)*50+tick)+ticks
  year+=total//9600;month=(total%9600)//800;day=(total%800)//50
  text+=f" / 예정 {'기원전 ' if year<0 else ''}{abs(year)}년 {month+1}월 {day+1}일"
 except (OSError,ValueError):pass
 return text

def command(bridge,text,action):
 parts=text.split()
 if not parts:raise ValueError('군단을 선택하세요.')
 op=parts[0]
 if op=='cancel' and len(parts)==2:
  bridge.client.call('army_order_cancel',action_id=parts[1]);return
 if op=='dismiss' and len(parts)==2:
  # The legion command panel's "send back" on a visiting support legion (token as the game knows it).
  row=next((r for r in bridge.client.call('army_overview') if r.get('incoming') and str(r.get('token'))==parts[1] and r['role']==1),None)
  if row is None:raise ValueError('돌려보낼 지원군을 찾지 못했습니다.')
  bridge.client.call('army_send_home',expedition=row['id']);return
 if op=='recall' and len(parts)==2:
  # The army tab's "return" on an own legion that is away (formation number as the game knows it).
  row=next((r for r in bridge.client.call('army_overview') if not r.get('incoming') and str(r.get('formation'))==parts[1] and r['phase'] not in ('returned','failed')),None)
  if row is None:raise ValueError('불러들일 군단을 찾지 못했습니다.')
  if row.get('returning') or row['phase'] in ('recalling','returning'):raise ValueError('이미 돌아오고 있습니다.')
  if row['phase']=='stationed':bridge.client.call('army_order',action_id=action,destination=row['destination'],role=row['role'],expedition=row['id'])
  else:bridge.client.call('army_order_cancel',action_id=row['action'])
  return
 if op=='depart' and len(parts)>=7:
  _,destination,role,formation,fort,unit,*identities=parts
  expected=dict(fort=int(fort),unit=int(unit),identities=[list(map(int,x.split(':'))) for x in identities])
  bridge.client.call('army_order',action_id=action,destination=destination,role=int(role),formation=int(formation),expected=expected)
 elif op=='return' and len(parts)==4:
  _,destination,role,expedition=parts
  bridge.client.call('army_order',action_id=action,destination=destination,role=int(role),expedition=expedition)
 else:raise ValueError('파견 요청 형식이 올바르지 않습니다.')
 bridge.write_changed('army-order.txt',action+'\npreparing\n군단을 이동하고 있습니다.\n')

def poll(bridge):
 now=time.monotonic()
 if now<getattr(bridge,'army_poll_next',0):return
 bridge.army_poll_next=now+1
 # Army dispatch is sealed (army_seal.SEALED): the room answers these with nothing, so they are not asked - two
 # round trips less in such rounds at a high ping (2026-11-15).
 import army_seal
 status=[] if army_seal.SEALED else bridge.client.call('army_order_status')
 if status:
  s=status[0];text={'saving':'도시 저장을 준비하고 있습니다.','preparing':'군단을 이동하고 있습니다.','moving':'군단이 이동하고 있습니다. 다른 군단도 보낼 수 있습니다.','complete':'이동을 마쳤습니다. 두 도시에 적용하고 있습니다.','cancelled':'요청을 취소했습니다.','failed':'요청을 처리하지 못했습니다.'}[s['state']]
  if s['result'] and 'message' in s['result']:text=s['result']['message']
  order=[s['id'],s['state'],text]
 else:order=None
 rows=[] if army_seal.SEALED else bridge.client.call('army_overview');lines=[];alerts=[]
 try:
  visitors=bridge.root/'army-visitors.txt'
  alive={int(p[0]):int(p[2]) for p in (line.split() for line in visitors.read_text().splitlines()) if len(p)==3}
  fresh=time.time()-visitors.stat().st_mtime<5   # the game is running and has just counted its visitors
  for r in rows:
   if not r.get('incoming') or r['phase']!='stationed':continue
   # support with nobody left goes home empty; an attack force that retreated (gone from the map) or was wiped out
   # goes home with those last seen alive (user 2026-11-13: it stayed 'stationed' on the sender's side)
   if (r['role']==1 and alive.get(r['token'])==0) or (r['role']==2 and fresh and alive.get(r['token'],0)==0):
    bridge.client.call('army_wiped',expedition=r['id'])
 except (OSError,ValueError):pass
 try:
  import city_notices
  city_notices.army(bridge,rows)
 except (OSError,ValueError):pass
 for r in rows:
  if r['phase']=='travelling':
   other=r['origin'] if r.get('incoming') else r['destination'];name=getattr(bridge,'city_names',{}).get(other,other)
   # The banner over the city view stays for the whole two-month march: only for an attack on its way. A support
   # legion on its way is told once (city_notices.army) and listed in the army tab (user, 2026-11-13: the banner
   # for support was in the way of playing).
   # 'id<TAB>text': the game hides a banner the player clicked, by this id, until that march ends (user 2026-11-13)
   if r.get('incoming') and not r.get('returning') and r['role']==2:alerts.append(str(r['id'])+'\t'+name+' 공격군 / '+eta(bridge,r)+' / 눌러서 닫기')
   elif not r.get('incoming') and status and r.get('action')==status[0]['id']:
    # the newest order's line; several legions may be on the road at once, each is listed in the army tab
    if order[1]=='moving':order[2]=('귀환 중 / ' if r.get('returning') else '파견 중 / ')+eta(bridge,r)
  if r.get('incoming'):continue
  if r['phase']!='stationed':continue
  current=json.loads(r['current']);destination=r['destination'];name=getattr(bridge,'city_names',{}).get(destination,destination)
  lines.append('\t'.join([r['id'],destination,str(r['role']),name+' / '+('지원군' if r['role']==1 else '공격군')]))
 if order:bridge.write_changed('army-order.txt','\n'.join(order)+'\n')
 bridge.write_changed('army-visits.txt','\n'.join(lines))
 # Visiting legions carry their owner's colour (token -> player colour index).
 colors=getattr(bridge,'route_player_colors',{})
 marks=[f"{r['token']} {colors.get(r['origin'],-1)}" for r in rows if type(r.get('token'))==int and r['token']>0 and colors.get(r['origin'],-1) in range(8)]
 bridge.write_changed('army-colors.txt','\n'.join(marks[:32])+'\n')
 bridge.write_changed('army-alert.txt','\n'.join(alerts[:3]))
 # Left side panel (army tab): kind (0 mine, 1 coming to us), owner colour, title, detail.
 side=[];names=getattr(bridge,'city_names',{})
 for r in rows:
  role='공격군' if r['role']==2 else '지원군'
  if r.get('incoming'):
   if r['phase']!='travelling' or r.get('returning'):continue
   side.append(f"1\t{colors.get(r['origin'],-1)}\t{names.get(r['origin'],r['origin'])} {role}\t{eta(bridge,r) or '이동 중'}")
  elif r['phase'] in ('travelling','stationed'):
   where=names.get(r['destination'],r['destination'])
   detail=('귀환 중 · ' if r.get('returning') else '파견 중 · ')+(eta(bridge,r) or '') if r['phase']=='travelling' else '주둔 중'
   side.append(f"0\t-1\t{where} {role}\t{detail.rstrip(' ·')}")
 bridge.write_changed('side-army.txt','\n'.join(side[:12])+('\n' if side else ''))
