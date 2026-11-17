"""Readiness-time warning only. Existing compatibility gates are unchanged."""
def warn(room,db,city):
    host=db.execute('SELECT city FROM lobby_invite ORDER BY rowid LIMIT 1').fetchone()
    if not host or not host[0] or host[0]==city:return
    versions=getattr(room,'client_versions',{})
    def info(owner):
        token=db.execute('SELECT token FROM city WHERE id=?',(owner,)).fetchone()
        return versions.get(token[0]) if token else None
    ours,theirs=info(city),info(host[0])
    if ours and theirs and ours==theirs:return
    row=db.execute('SELECT name FROM player_name WHERE city=?',(city,)).fetchone()
    name=row[0] if row else city
    reason='방장과 버전이 다릅니다.' if ours and theirs else '방장과 버전을 확인할 수 없습니다.'
    room.system_chat(db,'버전 경고: '+name+' / '+reason)
