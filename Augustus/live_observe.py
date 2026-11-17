"""Authenticated latest-state relay. Bounded history, epochs, watch leases and deltas.

Authentication, permissions and leases are checked under the room lock; the
multi-megabyte decode/encode work then runs after the room lock is released
(Deferred), under a lock of its own. Before, every observation upload held the
room lock and delayed every other city's clock and status requests.
"""
import time,threading
from observe_codec import encode,decode,digest
LEASE=10.0
HISTORY=4
class Deferred:
 def __init__(self,fn):self.fn=fn
 def __call__(self):return self.fn()
def _heavy_lock(room):
 lock=getattr(room,'observe_lock',None)
 if lock is None:room.observe_lock=lock=threading.Lock()
 return lock
def _put(room,lock,city,ticks,seq,epoch,packet,watchers,now):
 with lock:
  old=room.observations.get(city)
  if old and (epoch<old['epoch'] or (epoch==old['epoch'] and seq<old['sequence'])):return dict(accepted=False,obsolete=True)
  if old and epoch==old['epoch'] and seq==old['sequence']:
   return dict(accepted=bool(isinstance(packet,dict) and packet.get('hash')==old['hash']),sequence=seq)
  same=old is not None and epoch==old['epoch']
  if same and ticks<old['ticks']:raise ValueError('observation rollback')
  before=old['data'] if same else None
 try:data=decode(before,packet)
 except ValueError:return dict(accepted=False,resync=True)
 with lock:
  current=room.observations.get(city)
  if current is not old:return dict(accepted=False,obsolete=True)
  # Keep enough bases that a viewer one round trip behind still gets a small delta.
  history=([old]+old.get('history',[])[:HISTORY-1]) if same else []
  # No recursive histories retained.
  history=[{k:v for k,v in row.items() if k not in ('history','encoded')} for row in history]
  room.observations[city]=dict(epoch=epoch,sequence=seq,ticks=ticks,data=data,hash=digest(data),received=now,history=history)
 return dict(accepted=True,sequence=seq,watchers=watchers)
def _get(room,lock,target,r,now):
 with lock:
  row=room.observations.get(target)
  if not row:return dict(available=False)
  base=None
  if r.get('epoch')==row['epoch']:
   for item in [row]+row['history']:
    if item['sequence']==r.get('after') and item['hash']==r.get('hash'):base=item['data'];break
  # A row has at most current + two history bases + a full-state response.
  key=digest(base) if base is not None else ''
  cache=row.setdefault('encoded',{});delta=cache.get(key)
 if delta is None:
  delta=encode(base,row['data'])
  with lock:
   if len(cache)>=4:cache.clear()
   cache[key]=delta
 age=time.monotonic()-row['received']
 return dict(available=True,epoch=row['epoch'],sequence=row['sequence'],ticks=row['ticks'],stale=age>3,age_seconds=age,delta=delta)
def request(room,db,city,r):
 if not room.started or city not in room.active_cities(db):raise ValueError('observer unavailable')
 if not hasattr(room,'observations'):room.observations={}
 if not hasattr(room,'observers'):room.observers={}
 now=time.monotonic();room.observers={c:v for c,v in room.observers.items() if now-v['seen']<LEASE}
 op=r['op']
 if op=='observe_status':return dict(watchers=sum(v['target']==city for v in room.observers.values()))
 if op=='observe_leave':
  old=room.observers.get(city)
  if old and old['watch']==r.get('watch',0):room.observers.pop(city,None)
  return dict(left=True)
 if op=='observe_put':
  ticks,seq,epoch=r.get('ticks'),r.get('sequence'),r.get('epoch');packet=r.get('delta')
  if any(type(v)is not int for v in (ticks,seq,epoch)) or not 0<=ticks<=room.grant or not 0<seq<2**53 or not 0<epoch<2**63:raise ValueError('observation position')
  watchers=sum(v['target']==city for v in room.observers.values());lock=_heavy_lock(room)
  return Deferred(lambda:_put(room,lock,city,ticks,seq,epoch,packet,watchers,now))
 target=r.get('target');watch=r.get('watch',0)
 if target==city or target not in room.active_cities(db) or type(watch)is not int or not 0<=watch<2**63:raise ValueError('observation target')
 from observe_permissions import allowed
 if not allowed(db,target,city):
  room.observers.pop(city,None)
  return dict(available=False,denied=True)
 old=room.observers.get(city)
 if old and watch<old['watch']:return dict(available=False,superseded=True)
 room.observers[city]=dict(target=target,watch=watch,seen=now)
 lock=_heavy_lock(room)
 # Permission and lease checks above run even when the immutable delta is cached.
 return Deferred(lambda:_get(room,lock,target,r,now))
def spectator_request(room,db,viewer,r):
 """A spectator (spectate.py, Korean edition) watching a city: like a player's observe_get / observe_leave, with
 `viewer` ('spectator:...') as its lease key and the owner's permission for spectators (observe_permissions,
 viewer spectate.SPECTATOR). Its lease counts as a watcher, so the city sends its state as for a player."""
 if not room.started:raise ValueError('observer unavailable')
 if not hasattr(room,'observations'):room.observations={}
 if not hasattr(room,'observers'):room.observers={}
 now=time.monotonic();room.observers={c:v for c,v in room.observers.items() if now-v['seen']<LEASE}
 op=r['op']
 if op=='observe_leave':
  old=room.observers.get(viewer)
  if old and old['watch']==r.get('watch',0):room.observers.pop(viewer,None)
  return dict(left=True)
 target=r.get('target');watch=r.get('watch',0)
 if target not in room.active_cities(db) or type(watch)is not int or not 0<=watch<2**63:raise ValueError('observation target')
 from observe_permissions import allowed
 if not allowed(db,target,'~spectator'):   # spectate.SPECTATOR
  room.observers.pop(viewer,None)
  return dict(available=False,denied=True)
 old=room.observers.get(viewer)
 if old and watch<old['watch']:return dict(available=False,superseded=True)
 room.observers[viewer]=dict(target=target,watch=watch,seen=now)
 lock=_heavy_lock(room)
 return Deferred(lambda:_get(room,lock,target,r,now))
