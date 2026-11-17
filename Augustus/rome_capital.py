"""Rome on the empire map: a fixed capital, apart from P1..P8 and from neutral trade cities.

It has no city map, cannot be moved, deleted or given to a player slot, is never a trade partner and never counts as a
player city. It is shown in every mode; showing it does not turn on the throne mode.

Position: a schema-5 file keeps its own empire.rome (existing format, never rewritten here). Every other file uses the
shared position in rome-capital.json (evidence in that file). The editor, the checks and the lobby all read it from here
or from that file, so no screen has its own coordinates.

keep_clear: a city whose centre is closer than this (empire map pixels) sits on the Rome icon. Only such cities are
reported; nothing is moved or deleted.
"""
import json
from pathlib import Path

HERE=Path(__file__).resolve().parent
_spec=[]
def spec():
    if not _spec:_spec.append(json.loads((HERE/'rome-capital.json').read_text(encoding='utf-8')))
    return _spec[0]
def texts():
    """The one source of every Rome text (editor, lobby, scenario windows): title, description, facts."""
    s=spec();return {k:s[k] for k in ('title','description','facts','facts_detail') if k in s}
def position(data):
    """(x, y, source) for this scenario. source: 'scenario' (schema-5 empire.rome) or 'shared' (rome-capital.json)."""
    rome=data.get('empire',{}).get('rome') if isinstance(data,dict) else None
    if isinstance(rome,dict) and type(rome.get('x'))==int and type(rome.get('y'))==int:return rome['x'],rome['y'],'scenario'
    s=spec();return s['x'],s['y'],'shared'
def too_close(x,y,rx,ry):
    r=spec()['keep_clear'];return (x-rx)**2+(y-ry)**2<r*r
def conflicts(data):
    """Cities of this scenario that sit on Rome: [(city dict, distance)]. Read-only."""
    rx,ry,_=position(data);out=[]
    for c in data['empire']['cities']:
        if type(c.get('x'))==int and type(c.get('y'))==int and too_close(c['x'],c['y'],rx,ry):
            out.append((c,round(((c['x']-rx)**2+(c['y']-ry)**2)**.5)))
    return out
