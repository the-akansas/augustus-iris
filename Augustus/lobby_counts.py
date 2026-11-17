"""Waiting-room head count (user 2026-11-13): '참가 6 · 도시 선택 5 · 준비 3' next to the roster title. Display only.

The three numbers follow the start rule (lobby.py room_start), so the host can start exactly when all three are equal:
  joined  seated players who have not left, plus admitted players without a city seen within 30 s
  chosen  seated players who have not left
  ready   seated, online and ready (the host counts as ready: the host does not press ready, the host starts)
Spectators hold no invitation and are not counted."""
import time


def counts(room, db, slots):
    host = db.execute('SELECT city FROM lobby_invite ORDER BY rowid LIMIT 1').fetchone()
    host = host[0] if host else None
    seated = [s for s in slots if s['claimed'] and not s.get('departed')]
    now = time.monotonic()
    waiting = sum(1 for (key,) in db.execute('SELECT token FROM lobby_invite WHERE city IS NULL AND token NOT IN (SELECT token FROM departed_invite)')
                  if now - room.last_seen(key) <= 30)
    ready = sum(1 for s in seated if s['online'] and (s['city'] == host or s['ready']))
    return dict(joined=len(seated) + waiting, chosen=len(seated), ready=ready)


def lines(state):
    """Two forms for the game to choose from: the full one, and a shorter one when the title leaves too little room."""
    c = state.get('lobby_counts') if isinstance(state, dict) else None
    if not isinstance(c, dict) or not all(type(c.get(k)) == int and 0 <= c[k] < 1000 for k in ('joined', 'chosen', 'ready')):
        return ''   # a host without this feature: show nothing
    return (f"참가 {c['joined']} · 도시 선택 {c['chosen']} · 준비 {c['ready']}\n"
            f"참가 {c['joined']} · 선택 {c['chosen']} · 준비 {c['ready']}\n")
