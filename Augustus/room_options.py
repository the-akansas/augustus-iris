"""Versioned room rules. Personal options and hotkeys never enter this payload."""
import json
from pathlib import Path
from coordinator import sha
SCHEMA=json.loads(Path(__file__).with_name('room_options_schema.json').read_text(encoding='utf8'))

def values(value):
    if not isinstance(value,list) or len(value)!=len(SCHEMA):raise ValueError('방 옵션 개수가 다릅니다.')
    if any(type(v)!=int or not 0<=v<=s['maximum'] for v,s in zip(value,SCHEMA)):raise ValueError('방 옵션 값이 잘못되었습니다.')
    return list(value)

def legacy_values(value):
    """Older rooms/saves: 41 values (before cheats) or 42 (before weather)."""
    if not isinstance(value,list) or len(value) not in (41,42):raise ValueError('이전 방 옵션 개수가 다릅니다.')
    tail=[s['default'] for s in SCHEMA[len(value):]]
    return values(value+tail)

def encode(value):return json.dumps(values(value),separators=(',',':'))

def initialize(db):
    db.execute('CREATE TABLE IF NOT EXISTS room_options(id INTEGER PRIMARY KEY,revision INTEGER,locked INTEGER,initialized INTEGER,payload TEXT,hash TEXT)')
    db.execute('CREATE TABLE IF NOT EXISTS joint_options(id INTEGER PRIMARY KEY,payload TEXT,hash TEXT)')
    row=db.execute('SELECT payload,hash FROM room_options WHERE id=1').fetchone()
    if row:
        if sha(row[0].encode())!=row[1]:raise ValueError('방 옵션 무결성 오류')
        prior=json.loads(row[0])
        if isinstance(prior,list) and len(prior) in (41,42):
            payload=encode(legacy_values(prior))
            db.execute('UPDATE room_options SET payload=?,hash=? WHERE id=1',(payload,sha(payload.encode())))
    if not row:
        payload=encode([s['default'] for s in SCHEMA])
        db.execute('INSERT INTO room_options VALUES(1,0,0,0,?,?)',(payload,sha(payload.encode())))

def state(db):
    row=db.execute('SELECT revision,locked,initialized,payload,hash FROM room_options WHERE id=1').fetchone()
    if sha(row[3].encode())!=row[4]:raise ValueError('방 옵션 무결성 오류')
    return dict(version=2,revision=row[0],locked=bool(row[1]),initialized=bool(row[2]),values=values(json.loads(row[3])))

def request(room,db,key,r):
    current=state(db)
    if r['op']=='room_options_ack':
        if not current['initialized'] or type(r.get('revision'))!=int or r['revision']!=current['revision']:raise ValueError('이전 방 옵션 확인입니다.')
        if not hasattr(room,'options_acks'):room.options_acks={}
        room.options_acks[key]=current['revision'];return current
    host=db.execute('SELECT token FROM lobby_invite ORDER BY rowid LIMIT 1').fetchone()[0]
    if key!=host:raise ValueError('방장만 방 옵션을 변경할 수 있습니다.')
    if current['locked'] or room.started or room.start_at is not None or getattr(room,'roster_job',None):raise ValueError('게임 시작 후에는 방 옵션을 변경할 수 없습니다.')
    proposed=values(r.get('values'))
    # 날씨 효과 표시 is no longer offered (user 2026-11-15): a room sets it off, whatever an older profile carries.
    proposed=[0 if row['key']=='CONFIG_UI_DRAW_WEATHER' else v for v,row in zip(proposed,SCHEMA)]
    revision=r.get('revision')
    if type(revision)!=int or revision<0:raise ValueError('방 옵션 변경 번호 오류')
    if current['initialized'] and proposed==current['values']:return current
    if revision!=current['revision']:raise ValueError('방 옵션이 변경되었습니다. 다시 열어 주세요.')
    payload=encode(proposed)
    db.execute('UPDATE room_options SET revision=revision+1,initialized=1,payload=?,hash=? WHERE id=1',(payload,sha(payload.encode())))
    db.commit();room.options_acks={}
    from mailbox_io import publish_text
    publish_text(Path(room.coordinator.path).parent/'room-options-worker.txt',' '.join(map(str,proposed)))
    room.presence={city:(seen,False) for city,(seen,ready) in room.presence.items()}
    room.system_chat(db,'방 옵션이 변경되었습니다. 적용 확인 후 다시 준비해 주세요.')
    return state(db)

def require_ack(room,db,city):
    current=state(db)
    invite=db.execute('SELECT token FROM lobby_invite WHERE city=?',(city,)).fetchone()
    if not current['initialized'] or not invite or getattr(room,'options_acks',{}).get(invite[0])!=current['revision']:
        raise ValueError('방 옵션 적용을 기다리고 있습니다.')

def lock(db):
    if not state(db)['initialized']:raise ValueError('방 옵션을 먼저 확정해 주세요.')
    db.execute('UPDATE room_options SET locked=1 WHERE id=1');db.commit()

def capture(db,sid):
    current=state(db)
    if not current['initialized'] or not current['locked']:raise ValueError('확정된 방 옵션이 없습니다.')
    payload=json.dumps(current,sort_keys=True,separators=(',',':'))
    db.execute('INSERT INTO joint_options VALUES(?,?,?)',(sid,payload,sha(payload.encode())))

def read(db,sid):
    row=db.execute('SELECT payload,hash FROM joint_options WHERE id=?',(sid,)).fetchone()
    if not row or sha(row[0].encode())!=row[1]:raise ValueError('공동 저장의 방 옵션이 없거나 손상되었습니다.')
    return validate_snapshot(json.loads(row[0]))

def validate_snapshot(value):
    if not isinstance(value,dict) or set(value)!={'version','revision','locked','initialized','values'} or type(value['version'])!=int or value['version'] not in (1,2) or type(value['revision'])!=int or value['revision']<1 or value['locked'] is not True or value['initialized'] is not True:raise ValueError('저장된 방 옵션 형식 오류')
    if value['version']==1 or (isinstance(value['values'],list) and len(value['values'])==42):return dict(value,version=2,values=legacy_values(value['values']))
    values(value['values']);return value

def restore(db,snapshot):
    v=validate_snapshot(snapshot);payload=encode(v['values'])
    db.execute('UPDATE room_options SET revision=?,locked=1,initialized=1,payload=?,hash=? WHERE id=1',(v['revision'],payload,sha(payload.encode())))

def put(db,sid,snapshot):
    v=validate_snapshot(snapshot);payload=json.dumps(v,sort_keys=True,separators=(',',':'))
    db.execute('INSERT INTO joint_options VALUES(?,?,?)',(sid,payload,sha(payload.encode())))
