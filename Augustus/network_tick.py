"""Piggyback live engine progress on authenticated RPCs, without a second RTT.

The existing clock authority validates monotonic ticks and all save/trade/army
barriers. No client may extend a grant locally. A failed optional clock update
must not turn an already completed primary operation into a failed operation.
"""
from pathlib import Path
from network_diagnostics import record,ident

def attach(room,request,response):
 if not response.get('ok') or '_engine_ticks' not in request or request.get('op')=='clock' or not getattr(room,'started',False):return response
 try:
  clock_request={k:request.get(k) for k in ('protocol','build','session','scenario','city','token')}
  clock_request.update(op='clock',ticks=request['_engine_ticks'])
  with room.lock:
   ticks=request['_engine_ticks'];prior=room.progress.get(request.get('city'),(0,0))[0]
   if type(ticks)==int and ticks<prior:return response
   response['engine_clock']=room.request(clock_request)
 except Exception as error:
  # The primary RPC may already have committed. Preserve its response; lack of
  # a clock reply makes the engine exhaust its bounded grant and wait safely.
  record(Path(room.coordinator.path).parent,'piggyback_clock_rejected',session=ident(room.coordinator.session),peer=ident(request.get('city')),outcome='failed',reason=type(error).__name__)
 return response
