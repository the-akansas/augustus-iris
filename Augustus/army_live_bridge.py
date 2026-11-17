"""One outstanding native army command; lost ACK replays identical ID."""
import time

def poll(bridge):
 import army_seal
 if army_seal.SEALED:return   # the room has no army command for a game while dispatch is sealed (army_live.request)
 state=getattr(bridge,'army_live_exchange',None)
 if state:
  if time.monotonic()-getattr(bridge,'army_live_started',0)>12:
   bridge.client.call('army_live_poll',command=state['id'])
   bridge.army_live_started=time.monotonic()
   # Keep the original exchange to accept a late proof after delivery cap.
  try:
   text=(bridge.root/'army-live-response.txt').read_text();line,_,payload=text.partition('\n');key,applied=line.split()
  except (OSError,ValueError):return
  if key!=state['id']:return
  bridge.client.call('army_live_report',command=key,applied=applied=='1',payload=payload)
  bridge.army_live_exchange=None
  return
 if time.monotonic()<getattr(bridge,'army_live_next',0):return
 bridge.army_live_next=time.monotonic()+1
 command=bridge.client.call('army_live_poll')['command']
 if not command:return
 try:scope,owner=(bridge.root/'post-identity.txt').read_text().split()
 except (OSError,ValueError):return
 text=f"{scope} {owner} {command['id']} {command['token']} {command['step']} {command['role']} {command['formation']}\n{command['payload']}"
 bridge.write_changed('army-live-request.txt',text);bridge.army_live_exchange=command;bridge.army_live_started=time.monotonic()
