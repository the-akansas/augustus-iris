"""Contract UI adapter; identifiers come only from the authenticated room."""
from city_labels import city_name

def command(client,parts,key):
 if not parts or not parts[0].startswith('route_'):return False
 if parts[0]=='route_offer' and len(parts)==2:
  client.call('route_offer',peer=parts[1],request_id=key);return True
 if parts[0] in ('route_accept','route_reject') and len(parts)==3:
  client.call(parts[0],peer=parts[1],revision=int(parts[2]));return True
 raise ValueError('도시 계약 입력 형식 오류')

def publish(b,data,roster):
 import city_notices
 notices=city_notices.state(b)
 city=b.client.city
 links={r['b'] if r['a']==city else r['a']:r for r in data['links'] if city in (r['a'],r['b'])}
 built={p['peer'] for p in data.get('posts',[]) if p['city']==city and p['active']}
 inbox=[]
 lines=[]
 colors=[]
 for index,peer in enumerate(sorted(roster),1):
  color=getattr(b,'route_player_colors',{}).get(peer,-1)
  colors.append(f"{index} {color if type(color)==int and 0<=color<8 else -1}")
  if peer==city:continue
  r=links.get(peer)
  state=0 if not r else 1 if r['state']=='active' else 2 if r['state']=='offered' and r['proposer']!=city else 3 if r['state']=='offered' else 0
  if state==2:inbox.append(str(index))
  if state not in (1,2):city_notices.resolve(notices,3,index)
  lines.append(f"{index} {peer} {state} {r['revision'] if r else 0}")
  if state==1 and peer in built:
   city_notices.drop(notices,3,index) # Post built: the contract notices have done their job.
   continue
  if r:
   name=city_name(peer,getattr(b,'city_names',{}))
   text=(f'{name}: 교역 계약 제안이 왔습니다. 계약을 확인하세요.' if state==2 else
         f'{name}: 교역 계약이 수락되었습니다. 전용 교역소를 건설하세요.' if state==1 else
         f'{name}: 교역 계약 제안이 거절되었습니다.' if r['state']=='rejected' and r['proposer']==city else None)
   if text:
    key=f"route:{b.client.session}:{peer}:{r['revision']}:{r['state']}"
    city_notices.add(notices,key,3,index,0,0,0,text,pending=state in (1,2),replace=True)
 b.write_changed('route-inbox.txt','\n'.join(inbox)+'\n')
 b.write_changed('route-state.txt','\n'.join(lines)+'\n')
 b.write_changed('route-player-colors.txt','\n'.join(colors)+'\n')
 city_notices.publish(b,notices)
