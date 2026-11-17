"""Chat before choosing a city, authenticated by the existing room invitation."""
import unicodedata

def initialize(db):
    db.execute('CREATE TABLE IF NOT EXISTS lobby_display_name(invite TEXT PRIMARY KEY,name TEXT NOT NULL)')
    db.execute('CREATE TABLE IF NOT EXISTS lobby_color(invite TEXT PRIMARY KEY,color INTEGER NOT NULL)')

COLOR_TAKEN='다른 플레이어가 쓰고 있는 색입니다.'
COLOR_LOCKED='게임 시작 준비 중이거나 시작한 뒤에는 색을 바꿀 수 없습니다.'

def colors(db):
    """Player colour (0..7) of every participant. Participants with a city never share a colour (at most eight seats):
    they are served first, so invitations of people who came and left, or who have not chosen a city, can never use
    up the colours (with more than eight invitations two players' trade posts used to get the same colour).
    A colour a player picked is kept; the others get their joining order's colour, or the next free one when that
    is taken. Only participants without a city may share a colour, and only when all eight are in use."""
    rows=[(row[0],row[1]) for row in db.execute('SELECT token,city FROM lobby_invite ORDER BY rowid')]
    joined={key:i for i,(key,_) in enumerate(rows)}
    order=[key for key,city in rows if city]+[key for key,city in rows if not city]
    try:picked={row[0]:row[1] for row in db.execute('SELECT invite,color FROM lobby_color') if row[0] in order and type(row[1])==int and 0<=row[1]<8}
    except Exception:picked={}   # a room record from before colours could be picked
    result={};used=set()
    for key in order:
        if key in picked and picked[key] not in used:result[key]=picked[key];used.add(picked[key])
    for key in order:
        if key in result:continue
        i=joined[key];c=next((c%8 for c in range(i,i+8) if c%8 not in used),i%8);result[key]=c;used.add(c)
    return result

def color(db,key):
    return colors(db).get(key,-1)

def choose(room,db,key,request):
    """A participant with a city picks its colour (trade post flag and roof, legion flag, map mark, chat mark)."""
    wanted=request.get('color')
    if type(wanted)!=int or not 0<=wanted<8:raise ValueError('colour')
    if getattr(room,'started',False) or getattr(room,'roster_job',None) or getattr(room,'start_at',None) is not None:raise ValueError(COLOR_LOCKED)
    seat=db.execute('SELECT city FROM lobby_invite WHERE token=?',(key,)).fetchone()
    if not seat or not seat[0]:raise ValueError('먼저 도시를 선택하세요.')
    current=colors(db);seated={row[0] for row in db.execute('SELECT token FROM lobby_invite WHERE city IS NOT NULL')}
    if any(k!=key and k in seated and c==wanted for k,c in current.items()):raise ValueError(COLOR_TAKEN)
    db.execute('INSERT INTO lobby_color(invite,color) VALUES(?,?) ON CONFLICT(invite) DO UPDATE SET color=excluded.color',(key,wanted))
    # an unseated participant's own earlier pick of this colour gives way
    db.execute('DELETE FROM lobby_color WHERE color=? AND invite!=?',(wanted,key))
    db.commit()
    return dict(color=wanted)

def send(db,key,request):
    mid,text=request.get('message_id'),request.get('text')
    if not isinstance(mid,str) or len(mid)!=32 or any(c not in '0123456789abcdef' for c in mid):raise ValueError('message id')
    if not isinstance(text,str) or not text.strip() or len(text)>500 or len(text.encode('utf8'))>2000:raise ValueError('message length')
    if any(unicodedata.category(c) in ('Cc','Cf','Cs') for c in text):raise ValueError('control character')
    name=db.execute('SELECT name FROM lobby_display_name WHERE invite=?',(key,)).fetchone()
    if not name:raise ValueError('아이디를 먼저 입력해 주세요.')
    owner='invite:'+key
    old=db.execute('SELECT id,text FROM chat WHERE city=? AND message_id=?',(owner,mid)).fetchone()
    if old:
        if old['text']!=text:raise ValueError('message id reused')
        return dict(id=old['id'])
    # A participant without a city has no player colour on the map, roofs or flags yet: no colour mark (-1).
    seat=db.execute('SELECT city FROM lobby_invite WHERE token=?',(key,)).fetchone()
    result=db.execute('INSERT INTO chat(city,message_id,text,sender,player_color) VALUES(?,?,?,?,?)',(owner,mid,text,name[0],color(db,key) if seat and seat[0] else -1))
    db.commit()
    return dict(id=result.lastrowid)
