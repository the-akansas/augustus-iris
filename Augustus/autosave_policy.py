"""Host-only recovery checkpoints. Manual/transaction saves are separate.
Default (no setting stored yet): on, every 5 minutes (user 2026-11-13). Switching it off is stored as 0 and kept."""
DEFAULT_SECONDS=300
import json,time,uuid
import os
from pathlib import Path

def set_interval(root, value, enabled=True):
    if type(value) is not int or (value!=0 and not 30<=value<=7200):
        raise ValueError('invalid joint save interval')
    path=Path(root)/'multiplayer-settings.json'
    try:data=json.loads(path.read_text(encoding='utf-8-sig'))
    except FileNotFoundError:data={}
    if not isinstance(data,dict):raise ValueError('invalid multiplayer settings')
    if type(enabled) is not bool:raise ValueError('invalid joint save toggle')
    data['autosave_seconds']=value if enabled else 0
    if value:data['joint_save_interval_seconds']=value
    temp=path.with_name(path.name+'.'+uuid.uuid4().hex+'.tmp')
    try:
        with temp.open('w',encoding='utf-8') as f:
            json.dump(data,f,ensure_ascii=False,indent=2);f.flush();os.fsync(f.fileno())
        os.replace(temp,path)
    finally:temp.unlink(missing_ok=True)

def read_preferences(root):
    active=read_interval(root)
    try:data=json.loads((Path(root)/'multiplayer-settings.json').read_text(encoding='utf-8-sig'))
    except (OSError,ValueError):data={}
    remembered=data.get('joint_save_interval_seconds',active or 300) if isinstance(data,dict) else 300
    if type(remembered) is not int or not 30<=remembered<=7200:remembered=300
    return bool(active),active or remembered

def read_interval(root):
    try:
        with (Path(root)/'multiplayer-settings.json').open('rb') as f:
            raw=f.read(4097)
    except FileNotFoundError:return DEFAULT_SECONDS
    except OSError:return 0
    try:
        if len(raw)>4096:return 0
        data=json.loads(raw.decode('utf-8-sig'))
        if not isinstance(data,dict):return 0
        value=data.get('autosave_seconds',DEFAULT_SECONDS)
        return value if type(value) is int and (value==0 or 30<=value<=7200) else 0
    except (OSError,ValueError):return 0

RETRY_SECONDS=10

def poll(bridge,root,role,phase,ticks,pending,now=None,complete=None):
    """Host recovery save every `interval` real seconds, counted from the last finished joint save of any kind
    (trade, cargo, army, manual or this one), so a trade save is not followed by another one at once (user 2026-11-13).
    A refused request (an engine briefly late, another save running) is tried again after RETRY_SECONDS instead of
    waiting a whole interval."""
    now=time.monotonic() if now is None else now
    done=complete.get('id') if isinstance(complete,dict) else None
    seen=getattr(bridge,'autosave_seen_complete','unseen')   # the first look only records what is there
    if done!=seen:
        if seen!='unseen' and done is not None:bridge.last_autosave=now
        bridge.autosave_seen_complete=done
    if now-getattr(bridge,'autosave_settings_checked',float('-inf'))>=2:
        interval=read_interval(root)
        if interval!=getattr(bridge,'autosave_interval',None):
            bridge.last_autosave=now
        bridge.autosave_interval=interval
        bridge.autosave_settings_checked=now
    interval=bridge.autosave_interval
    if role!='1' or phase!='started' or ticks is None or pending or not interval:
        return False
    if now-bridge.last_autosave<interval:return False
    bridge.last_autosave=now
    try:
        bridge.client.call('save_begin',request_id=uuid.uuid4().hex)
        return True
    except ValueError:
        # Not now (an engine briefly late, a save already running): one quiet retry later, never a request loop.
        bridge.last_autosave=now-interval+RETRY_SECONDS
        return False
