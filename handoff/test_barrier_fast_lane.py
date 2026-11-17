"""Barrier fast lane (20차): a joint-save capture is uploaded from the clock pump
as soon as the engine stops on the barrier tick, not on the next slow bridge pass."""
import sys,tempfile,threading,time,types
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'Augustus'))

def bridge(root):
    c=types.SimpleNamespace(session='s',city='capua',token='t',address=('127.0.0.1',1),scenario='x')
    return types.SimpleNamespace(root=Path(root),client=c,departed=False,uploaded=set(),layout_version=None)

def fake_upload(monkey_calls):
    import save_upload
    class Client:
        def __init__(self,*a):pass
        def call(self,op,**k):monkey_calls.append((op,k['id'],k['ticks']));time.sleep(.2)
    save_upload.Client=Client
    return save_upload.Upload()

def test_fast_lane_uploads_on_barrier_tick_only():
    import clock_pump
    calls=[];root=tempfile.mkdtemp();b=bridge(root);b.upload=fake_upload(calls)
    (Path(root)/'capture.txt').write_text('7 700');(Path(root)/'capture-7.sav').write_bytes(b'x'*64)
    clock_pump.fast_save(b,dict(save_id=7,save_ticks=700),690)   # still running toward the barrier
    clock_pump.fast_save(b,dict(save_id=0,save_ticks=0),700)     # no save pending
    time.sleep(.05);assert calls==[]
    clock_pump.fast_save(b,dict(save_id=7,save_ticks=700),700)
    time.sleep(.05);assert calls==[('save_part',7,700)]
    # A bridge pass holding an older save_status (no pending save) must not cancel it.
    b.upload.poll(b,None,700);assert b.upload.job and not b.upload.job.cancel.is_set()
    time.sleep(.3);b.upload.poll(b,dict(id=7,ticks=700),700)
    assert 7 in b.uploaded
    clock_pump.fast_save(b,dict(save_id=7,save_ticks=700),700)   # already uploaded: no repeat
    time.sleep(.05);assert len(calls)==1

def test_clock_reply_carries_barrier_tick():
    src=(Path(__file__).resolve().parents[1]/'Augustus'/'lobby.py').read_text(encoding='utf8')
    assert "save_ticks=saving['ticks'] if saving else 0" in src
    # 21차: cities approach the barrier at the host's speed (no forced 80%).
    assert "speed=((speed or 80) if ticks<self.grant else 0) if saving" in src

if __name__=='__main__':
    for name,f in list(globals().items()):
        if name.startswith('test_'):f();print('ok',name)
