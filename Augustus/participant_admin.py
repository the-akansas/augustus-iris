"""Host-only connection removal. No bans, forced saves or fabricated install ACKs."""
import secrets
from coordinator import sha

def request(room,db,city,r):
 host=db.execute('SELECT city FROM lobby_invite ORDER BY rowid LIMIT 1').fetchone()[0]
 if city!=host:raise ValueError('host required')
 target=r.get('target');generation=r.get('generation')
 if target==host:raise ValueError('cannot remove host')
 row=db.execute('SELECT token FROM lobby_invite WHERE city=?',(target,)).fetchone()
 if not row and isinstance(generation,str):
  # A lost removal reply is retryable even after a lobby slot was released.
  for left in db.execute('SELECT token FROM departed_invite'):
   if secrets.compare_digest(sha(left[0].encode()),generation):return {'removed':True}
 if not row or not isinstance(generation,str):raise ValueError('participant changed')
 # Confirmation is bound to one invitation, not a reusable city slot.
 if not secrets.compare_digest(sha(row[0].encode()),generation):raise ValueError('participant changed')
 if db.execute('SELECT 1 FROM departed_invite WHERE token=?',(row[0],)).fetchone():return {'removed':True}
 room.depart(db,row[0],target,removed=True)
 # Unaccepted offers never touched stock. Loaded cargo and committed results
 # stay in the existing suspended/recovery path; do not erase or fake refunds.
 import live_cargo
 for transfer in db.execute('SELECT * FROM live_transfer WHERE sender=? OR receiver=?',(target,target)).fetchall():
  import cash_live
  if cash_live.mapped(db,transfer):continue # Issued native commands may already be applied; preserve their receipt ledger.
  cargo=live_cargo.get(db,transfer['id'])
  untouched=transfer['state'] in ('offered','collecting') or (transfer['state']=='saving' and (not cargo or cargo['phase']=='load'))
  if not untouched:continue
  job=getattr(room,'live_prepare_job',None)
  if job and job['id']==transfer['id']:live_cargo.stop_job(room)
  db.execute("UPDATE live_transfer SET state='rejected',error='참가자의 연결이 해제되어 출발 전 거래를 취소했습니다.' WHERE id=?",(transfer['id'],))
 db.commit()
 if not room.started:
  room.start_at=None;room.start_step=None
  db.execute('DELETE FROM play_session');db.commit()
 return {'removed':True}

def save_blocked(room,db):
 import live_trade
 t=live_trade.busy(db)
 if not t:return False
 active=room.active_cities(db)
 if all(c in active for c in (t['sender'],t['receiver'])):return True
 if t['state']!='committed':return False
 cargo=db.execute('SELECT 1 FROM live_cargo WHERE id=?',(t['id'],)).fetchone()
 for c in (t['sender'],t['receiver']):
  if c not in active:continue
  ack=db.execute('SELECT 1 FROM live_cargo_ack WHERE result=? AND city=?',(t['result'],c)).fetchone() if cargo else db.execute('SELECT 1 FROM live_installed WHERE id=? AND city=?',(t['id'],c)).fetchone()
  if not ack:return True
 return False

def publish(bridge,state):
 def clean(s):return str(s).replace('\t',' ').replace('\n',' ').replace('\r',' ')
 rows=[];permissions=[]
 policies={(r['owner'],r['viewer']):r for r in state.get('observe_permissions',[])}
 for slot in sorted(state['slots'],key=lambda s:s['city']!=state['host_city']):
  if not slot['claimed'] or slot.get('departed'):continue
  age=slot.get('contact_age_ms');rtt=slot.get('rtt_ms')
  status='응답 확인 중' if age is None else '연결 정상' if age<3000 else f'{age//1000}초째 응답 없음'
  label=slot['name']+(' · 방장' if slot['city']==state['host_city'] else '')+' / '+slot['city_name']
  detail=('왕복 지연: 측정 중' if rtt is None else f'왕복 지연: {rtt}ms')+' / '+status
  p=policies.get((bridge.client.city,slot['city']),dict(allowed=1,revision=0))
  permissions.append('\t'.join(map(str,[slot['city'],slot.get('generation',''),int(slot['city']!=bridge.client.city),p['allowed'],p['revision']])))
  rows.append('\t'.join(map(clean,[slot['city'],slot.get('generation',''),int(slot['city']!=state['host_city']),label,detail])))
 bridge.write_changed('participants.txt','\n'.join(rows))
 bridge.permission_rows=permissions
 bridge.write_changed('observe-permissions.txt','\n'.join(permissions))
 # Which other players currently let me watch them (empire map 'city visit' button).
 me=bridge.client.city;allow=[]
 for slot in state['slots']:
  if slot['city']==me or not slot['claimed'] or slot.get('departed') or slot.get('dormant'):continue
  p=policies.get((slot['city'],me),dict(allowed=1))
  allow.append(f"{slot.get('name_id',0)} {int(bool(p['allowed']))}")
 bridge.write_changed('observe-allowed.txt','\n'.join(allow))

def apply_local(bridge,target,allowed,revision):
 """Show a confirmed change at once instead of after the next status poll."""
 rows=[]
 for line in getattr(bridge,'permission_rows',[]):
  parts=line.split('\t')
  if len(parts)==5 and parts[0]==target:parts[3]=str(int(bool(allowed)));parts[4]=str(revision)
  rows.append('\t'.join(parts))
 bridge.permission_rows=rows
 bridge.write_changed('observe-permissions.txt','\n'.join(rows))
