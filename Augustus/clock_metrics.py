"""Read bounded native counters. Diagnostic failure never affects progression."""
import time
from network_diagnostics import record,ident

FIELDS=('native_ms','ticks','grant','run_ms','credit_wait_ms','stale_wait_ms',
        'pause_wait_ms','barrier_wait_ms','pace_ms','simulation_us')
SPACING_FIELDS=('tick_gap_max_ms','tick_gap_over100','tick_gap_over250')

def poll(bridge):
 now=time.monotonic()
 if now-getattr(bridge,'metrics_polled',-10)<2:return
 bridge.metrics_polled=now
 try:
  p=bridge.root/'clock-metrics.txt'
  if not 0<=time.time()-p.stat().st_mtime<5:return
  # Fixed size and integer-only schema; never export arbitrary file contents.
  with p.open('rb') as f:raw=f.read(513)
  if len(raw)>512:return
  values=tuple(int(x) for x in raw.split())
  if len(values) not in (len(FIELDS),len(FIELDS)+len(SPACING_FIELDS)) or any(v<0 or v>=2**63 for v in values):return
  if values==getattr(bridge,'metrics_previous',None):return
  bridge.metrics_previous=values
  record(bridge.root,'clock_metrics',session=ident(bridge.client.session),**dict(zip(FIELDS+SPACING_FIELDS,values)))
 except (OSError,ValueError):return
