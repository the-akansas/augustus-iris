"""400ms-ping work (18차): kept-alive RPC, time-based clock credit, observation off the room lock."""
import sys,threading,tempfile,time
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'Augustus'))

def test_credit_is_six_seconds_of_play():
    from clock_policy import credit_for_speed,TICK_MS,MAX_CREDIT_TICKS
    for speed in range(60,101,10):
        ticks=credit_for_speed(speed);secs=ticks*TICK_MS[speed//10]/1000
        assert 6.0<=secs<6.2 and ticks<=MAX_CREDIT_TICKS,(speed,ticks,secs)
    assert credit_for_speed(0)==64 and credit_for_speed(100)==375

def test_keep_alive_reuses_and_recovers():
    import coordinator,city_client
    class Room:
        n=0
        def request(self,r):Room.n+=1;return {'op':r['op']}
    srv=coordinator.Server(Room(),'127.0.0.1',0);threading.Thread(target=srv.serve_forever,daemon=True).start()
    c=city_client.Client(tempfile.mkdtemp(),'s','capua','t',srv.server_address,'x')
    assert c.call('a')=={'op':'a'};first=c.pool().sock
    assert c.call('b')=={'op':'b'} and c.pool().sock is first
    first.shutdown(2)                       # server-side close of an idle socket
    assert c.call('c')=={'op':'c'} and Room.n==3   # retried once, executed once
    c.pool().last-=100                      # idle past the limit: fresh connection
    assert c.call('d')=={'op':'d'} and c.pool().sock is not first
    srv.shutdown();srv.server_close()

def test_observation_runs_outside_room_lock():
    import live_observe
    from observe_codec import encode
    class Room:
        started=True;grant=1000;lock=threading.RLock()
        def active_cities(self,db):return ['a','b']
    import observe_permissions
    observe_permissions.allowed=lambda db,t,c:True
    room=Room();state=bytes(range(256))*64
    put=live_observe.request(room,None,'a',dict(op='observe_put',ticks=5,sequence=1,epoch=7,delta=encode(None,state)))
    assert isinstance(put,live_observe.Deferred)
    assert put()['accepted'] and room.observations['a']['data']==state
    get=live_observe.request(room,None,'b',dict(op='observe_get',target='a',watch=1,epoch=0,after=0,hash=''))
    assert isinstance(get,live_observe.Deferred)
    reply=get();assert reply['available'] and reply['sequence']==1
    # a viewer a few states behind still gets a delta against its base
    for seq in range(2,5):
        changed=bytearray(state);changed[seq]=0;prev=room.observations['a']['data']
        assert live_observe.request(room,None,'a',dict(op='observe_put',ticks=5+seq,sequence=seq,epoch=7,delta=encode(prev,bytes(changed))))()['accepted']
    from observe_codec import digest
    reply=live_observe.request(room,None,'b',dict(op='observe_get',target='a',watch=1,epoch=7,after=1,hash=digest(state)))()
    assert reply['delta']['base']==digest(state)

if __name__=='__main__':
    for name,fn in list(globals().items()):
        if name.startswith('test_'):fn();print('ok',name)
