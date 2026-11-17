"""Who a player trade post is bound to and whom a soldier belongs to (hover text only).

Everything comes from identifiers the room already authenticated:
  * a player trade post is bound to its partner by its route slot (building orientation = index in the sorted
    scenario city list, route_bridge/trade_partner_bridge use the same numbering);
  * a visiting legion carries its expedition token; the server's army overview names the token's origin city;
  * a city's player is the room slot's claimed player name and connection state.
No colour, screen position or display text is used to decide an owner. Nothing private is read: no Race for the
Throne value, no attempt, no gift or expedition content beyond the public origin city of a visiting legion.

Files (UTF-8, rewritten whenever the room status or the army overview changes):
  post-partners.txt  AUGPOST1, then  slot<TAB>city name<TAB>player
  army-owners.txt    AUGARMY1, then  own<TAB>city name<TAB>player  and  token<TAB>city name<TAB>player
"""
NO_PLAYER='담당자 없음'
NO_NAME='아이디 미확인'
LIMIT=40

def clean(value,limit=LIMIT):
    text=' '.join(str(value).replace('\t',' ').replace('\r',' ').replace('\n',' ').split())
    return text if len(text)<=limit else text[:limit-1]+'…'

def player_label(slot):
    """The city's player as the room knows it now: name, plus why they are not playing when that is the case."""
    if not slot or not slot.get('claimed'):return NO_PLAYER
    name=slot.get('player_name')
    if not isinstance(name,str) or not name.strip():return NO_NAME
    name=clean(name,24)
    if slot.get('departed'):return name+' (퇴장)'
    if not slot.get('online'):return name+' (연결 끊김)'
    return name

def table(slots,city_names):
    return {s['city']:(clean(city_names.get(s['city'],s['city'])),player_label(s)) for s in slots}

def post_partners(slots,city_names,own):
    """Route slot -> partner. Slot numbers are the positions in the sorted city list, as for the trade posts."""
    known=table(slots,city_names)
    lines=[f'{index}\t{known[city][0]}\t{known[city][1]}' for index,city in enumerate(sorted(known),1) if city!=own]
    return 'AUGPOST1\n'+''.join(line+'\n' for line in lines)

def army_owners(slots,city_names,own,rows):
    """Visiting legions in this city (incoming expeditions) by token, and this city's own legions."""
    known=table(slots,city_names);lines=[]
    if own in known:lines.append(f'own\t{known[own][0]}\t{known[own][1]}')
    for r in rows or ():
        token=r.get('token')
        if not r.get('incoming') or type(token)!=int or token<=0 or r.get('phase') in ('returned','failed'):continue
        if r.get('destination',own)!=own:continue
        origin=r.get('origin')
        if origin==own or origin not in known:continue   # unknown origin: the game shows "소속 정보 미확인"
        lines.append(f'{token}\t{known[origin][0]}\t{known[origin][1]}')
    return 'AUGARMY1\n'+''.join(line+'\n' for line in lines[:65])

def publish(bridge,state=None,rows=None):
    identity=(getattr(bridge.client,'session',None),bridge.client.city,bool(getattr(bridge,'joined',False)))
    if getattr(bridge,'affiliation_identity',None)!=identity:
        bridge.affiliation_identity=identity
        bridge.affiliation_slots=[];bridge.affiliation_rows=[]
    if state is not None:bridge.affiliation_slots=state.get('slots',[])
    if rows is not None:bridge.affiliation_rows=rows
    slots=getattr(bridge,'affiliation_slots',[]);names=getattr(bridge,'city_names',{})
    own=bridge.client.city if getattr(bridge,'joined',False) else None
    if own is None:
        bridge.write_changed('post-partners.txt','AUGPOST1\n');bridge.write_changed('army-owners.txt','AUGARMY1\n');return
    bridge.write_changed('post-partners.txt',post_partners(slots,names,own))
    bridge.write_changed('army-owners.txt',army_owners(slots,names,own,getattr(bridge,'affiliation_rows',[])))

class Recorder:
    """Keeps the army overview that army_bridge.poll already requests (no extra request, army code unchanged).
    Every attribute and call goes to the real client."""
    def __init__(self,client):
        self.__dict__['client']=client;self.__dict__['army_rows']=None
    def __getattr__(self,name):return getattr(self.client,name)
    def __setattr__(self,name,value):setattr(self.client,name,value)
    def call(self,op,**request):
        result=self.client.call(op,**request)
        if op=='army_overview' and isinstance(result,list):self.__dict__['army_rows']=result
        return result
