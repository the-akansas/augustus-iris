"""Feeds the shared clock independently of the bridge's long poll cycle.

The bridge loop runs a dozen RPCs per pass; at a 400ms ping one pass takes
several seconds, so progress reports and grants piggybacked on it arrive in
bursts and the room clock sees cities as stale. This thread sends only the
small 'clock' RPC on its own kept-alive connection a few times per second.
"""
import threading,time
from mailbox_io import read_live_text
INTERVAL=0.25
# While a barrier (save/army/ceremony) holds the clock, poll faster so the
# fast lane sees the stop and the release a few hundred ms sooner.
BARRIER_INTERVAL=0.1

def identity(b):return (b.client.session,b.client.city,b.client.token,b.client.address)
class ClockPump:
 def __init__(self,bridge):
  from observe_bridge import clone
  self.bridge=bridge;self.identity=identity(bridge);self.stop=threading.Event()
  self.client=clone(bridge.client,bridge.root/'clock-network')
  self.thread=threading.Thread(target=self.run,daemon=True,name='clock-pump');self.thread.start()
 def close(self):self.stop.set()
 def run(self):
  engine=self.bridge.root/'engine.txt'
  while not self.stop.is_set():
   wait=INTERVAL
   try:
    if engine.exists() and time.time()-engine.stat().st_mtime<1.0:
     sample=read_live_text(engine)
     if sample is not None and sample.strip().isdigit():
      clock=self.client.call('clock',ticks=int(sample.strip()))
      if not self.stop.is_set():self.bridge.accept_clock(clock)
      if not self.stop.is_set():fast_save(self.bridge,clock,int(sample.strip()))
      if clock.get('wait_reason') in ('save','army','ceremony','trade'):wait=BARRIER_INTERVAL
   except Exception:
    # Optional fast path: the bridge loop still reports progress on every RPC.
    pass
   self.stop.wait(wait)
  self.client.disconnect()

def fast_save(bridge,clock,ticks):
 """Barrier fast lane: upload this city's joint-save capture as soon as the
 engine stops on the barrier tick, instead of waiting for the next pass of
 the slow bridge loop (several seconds at a 400ms ping). The server still
 validates id, tick and progress; Upload ignores repeats."""
 sid=clock.get('save_id') or 0;at=clock.get('save_ticks') or 0
 upload=getattr(bridge,'upload',None)
 if not sid or ticks!=at or upload is None:return
 upload.poll(bridge,dict(id=sid,ticks=at),ticks)

def poll(bridge):
 old=getattr(bridge,'clock_pump',None)
 wanted=getattr(bridge.client,'clock_enabled',False) and not getattr(bridge,'departed',False)
 if old and (not wanted or old.identity!=identity(bridge) or not old.thread.is_alive()):
  old.close();bridge.clock_pump=old=None
 if wanted and not old:bridge.clock_pump=ClockPump(bridge)
