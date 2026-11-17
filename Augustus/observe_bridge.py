"""One asynchronous producer, one in-flight delta, latest capture; no heartbeat waits."""
import threading,time
from observe_codec import encode
from observe_channel import Channel
from mailbox_io import publish_text
PUBLISH_INTERVAL=0.5

def clone(client,root):
 c=type(client)(root,client.session,client.city,client.token,client.address,client.scenario)
 if hasattr(client,'latency'):c.latency=client.latency
 return c

def identity(b):return (b.client.session,b.client.city,b.client.token,b.client.address)
class Publisher:
 def __init__(self,b):
  self.identity=identity(b);self.stop=threading.Event();self.channel=Channel(b.root,'observe-channel');self.client=clone(b.client,b.root/'observation-network')
  path=b.root/'observe-epoch.txt'
  try:prior=int(path.read_text())
  except (OSError,ValueError):prior=0
  self.last_capture=0.0
  self.epoch=max(time.time_ns(),prior+1);publish_text(path,str(self.epoch));self.last_seen=time.monotonic();self.error=None;self.sent=0;self.bytes=0;self.full=0
  self.thread=threading.Thread(target=self.run,daemon=True,name='city-state-producer');self.thread.start()
 def close(self):self.stop.set()
 def run(self):
  before=None;seq=0;pending=None;watchers=0
  try:
   while not self.stop.is_set() and time.monotonic()-self.last_seen<30:
    try:
     if pending is None:
      if not watchers:watchers=self.client.call('observe_status')['watchers']
      if not watchers:self.stop.wait(.5);continue
      # Two states a second are plenty for a delayed spectator view; each capture
      # serialises the whole city on the observed player's game thread.
      wait=self.last_capture+PUBLISH_INTERVAL-time.monotonic()
      if wait>0:self.stop.wait(wait)
      self.last_capture=time.monotonic()
      request=self.channel.demand();deadline=time.monotonic()+3;state=None
      while not self.stop.is_set() and time.monotonic()<deadline:
       state=self.channel.read()
       if state and state[0]==request:break
       self.stop.wait(.02)
      else:continue
      if self.stop.is_set():break
      _,ticks,data=state
      seq+=1;pending=(data,dict(epoch=self.epoch,sequence=seq,ticks=ticks,delta=encode(before,data)))
     data,fields=pending;reply=self.client.call('observe_put',**fields)
     if reply.get('accepted'):
      watchers=reply.get('watchers',watchers)
      before=data;self.sent+=1;self.bytes+=len(fields['delta']['patch']);self.full+=not bool(fields['delta']['base']);pending=None;self.error=None
     elif reply.get('resync'):
      before=None;fields['delta']=encode(None,data)
     elif reply.get('obsolete'):break
     else:raise ValueError('state publication rejected')
    except (OSError,ValueError) as e:self.error=str(e);self.stop.wait(.5)
  finally:self.channel.close()

def poll(bridge):
 old=getattr(bridge,'observe_task',None)
 if getattr(bridge,'departed',False):
  if old:old.close()
  return
 if old and (old.identity!=identity(bridge) or old.stop.is_set()):
  old.close()
  if old.thread.is_alive():return
  old=None
 if not old or not old.thread.is_alive():bridge.observe_task=old=Publisher(bridge)
 old.last_seen=time.monotonic()
