"""Bounded host-controlled victory barrier. Restored completed saves never replay it."""
import json
from coordinator import sha

def initialize(db):
 db.execute('CREATE TABLE IF NOT EXISTS victory_ceremony(id INTEGER PRIMARY KEY,run TEXT,tick INTEGER,participants TEXT,done TEXT,finished INTEGER)')

def begin(room,db,data,tick):
 if data['rules'].get('celebration','notice')!='video':return
 db.execute('INSERT OR IGNORE INTO victory_ceremony VALUES(1,?,?,?,?,0)',(data['run_id'],tick,json.dumps(room.active_cities(db)),'[]'))
 room.ceremony_deadline=room.clock()+180

def state(room,db):
 row=db.execute('SELECT * FROM victory_ceremony WHERE id=1').fetchone()
 if not row or row['finished']:return None
 active=set(room.active_cities(db));participants=set(json.loads(row['participants']));done=set(json.loads(row['done']))
 waiting=sorted((participants&active)-done)
 if not hasattr(room,'ceremony_deadline'):room.ceremony_deadline=room.clock()+180
 if not waiting or room.clock()>=room.ceremony_deadline:
  db.execute('UPDATE victory_ceremony SET finished=1 WHERE id=1');db.commit()
  room.system_chat(db,'승리 연출을 마쳤습니다. 도시 건설을 계속합니다.' if not waiting else '승리 연출 대기 시간이 끝나 도시 건설을 계속합니다.',key='victory-resume:'+row['run'])
  return None
 return dict(run=row['run'],tick=row['tick'],waiting=waiting,participants=sorted(participants))

def finish(room,db,city,run):
 current=state(room,db)
 if not current:return dict(finished=True)
 if run!=current['run'] or city not in current['participants']:raise ValueError('invalid victory acknowledgement')
 if room.progress.get(city,(-1,0))[0]!=current['tick']:raise ValueError('victory tick not reached')
 row=db.execute('SELECT done FROM victory_ceremony WHERE id=1').fetchone();done=set(json.loads(row[0]));done.add(city)
 db.execute('UPDATE victory_ceremony SET done=? WHERE id=1',(json.dumps(sorted(done)),));db.commit()
 return dict(finished=state(room,db) is None)

def poll_bridge(bridge,clock,ticks):
 value=clock.get('ceremony');payload=''
 if value and ticks==value['tick'] and bridge.client.city in value['participants']:
  nonce=sha((bridge.config['session']+'|victory|'+value['run']+'|'+bridge.client.city).encode())
  payload=nonce+'\n'
  path=bridge.root/'victory-done.txt'
  if path.exists() and path.read_text(encoding='ascii').strip()==nonce:
   bridge.client.call('victory_done',run=value['run'])
  names=getattr(bridge,'city_names',{})
  bridge.write_changed('victory-wait.txt','다른 플레이어의 영상 종료를 기다립니다.\n'+', '.join(names.get(c,c) for c in value['waiting']))
 bridge.write_changed('victory-request.txt',payload)
