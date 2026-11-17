"""Who may trade with whom between player cities. One rule set for the editor, the checks and the room server.

Stored in rules.player_trade (schema 4+, optional):
  {"exceptions": [{"between": ["player1", "player3"], "allow": false}, ...]}
Each pair is stored once (slot ids, sorted), so both directions always agree. A pair is symmetric: it covers
sales, gifts and agreements in both directions. It says nothing about which goods move which way.

Resolution order for a pair of player slots:
  1. an explicit exception for that pair
  2. a team-derived default            (not implemented yet: team_default() always answers None)
  3. the base policy: players may trade (current behaviour; files without player_trade keep it)
No rule here can make a trade possible that the map makes impossible; route checks are separate.

Ownership: exceptions name slots, like allowed buildings and governance. Swapping a slot's city keeps them;
deleting a slot deletes the exceptions that name it.
"""
import json,sys
from pathlib import Path

def _pair(a,b):return tuple(sorted((a,b)))

def validate(policy,slot_ids):
    if not isinstance(policy,dict) or set(policy)!={'exceptions'}:raise ValueError('플레이어 간 교역 설정의 필드가 올바르지 않습니다.')
    rows=policy['exceptions']
    if not isinstance(rows,list) or len(rows)>28:raise ValueError('플레이어 간 교역 예외는 28개까지입니다.')
    seen=set()
    for row in rows:
        if not isinstance(row,dict) or set(row)!={'between','allow'} or type(row['allow']) is not bool:raise ValueError('플레이어 간 교역 예외 형식이 올바르지 않습니다.')
        pair=row['between']
        if not isinstance(pair,list) or len(pair)!=2 or pair[0]==pair[1] or any(p not in slot_ids for p in pair):raise ValueError('플레이어 간 교역 예외가 없는 자리를 가리킵니다.')
        if pair!=sorted(pair):raise ValueError('플레이어 간 교역 예외의 두 자리는 이름 순으로 적습니다.')
        if tuple(pair) in seen:raise ValueError('같은 두 자리의 교역 예외가 두 번 있습니다.')
        seen.add(tuple(pair))
    return policy

def team_default(rules,a,b):
    """Extension point for team rules. No team setting exists yet, so there is never a team-derived answer."""
    return None

def decide(rules,a,b):
    """(allowed, source) for player slots a and b. source: 'exception' | 'team' | 'default'."""
    if a==b:raise ValueError('같은 도시끼리는 교역 관계가 없습니다.')
    for row in (rules or {}).get('player_trade',{}).get('exceptions',[]):
        if tuple(row['between'])==_pair(a,b):return row['allow'],'exception'
    team=team_default(rules,a,b)
    if team is not None:return team,'team'
    return True,'default'

def allowed(rules,a,b):return decide(rules,a,b)[0]

def blocked_pairs(rules,slot_ids):
    """Every pair that resolves to 'not allowed'. Used for the room binding; empty when nothing is restricted."""
    ids=sorted(slot_ids);return [[a,b] for i,a in enumerate(ids) for b in ids[i+1:] if not allowed(rules,a,b)]

def set_pair(data,a,b,allow):
    """Editor operation. Stores an exception only when it differs from what team/base rules give."""
    import copy
    data=copy.deepcopy(data);rules=data['rules'];pair=list(_pair(a,b))
    rows=[r for r in rules.get('player_trade',{}).get('exceptions',[]) if r['between']!=pair]
    base=team_default(rules,a,b);base=True if base is None else base
    if allow!=base:rows.append(dict(between=pair,allow=bool(allow)))
    rows.sort(key=lambda r:r['between'])
    if rows:rules['player_trade']=dict(exceptions=rows)
    else:rules.pop('player_trade',None)
    return data

def forget_slot(rules,slot_id):
    """A deleted slot takes its exceptions with it."""
    policy=rules.get('player_trade')
    if not policy:return
    policy['exceptions']=[r for r in policy['exceptions'] if slot_id not in r['between']]
    if not policy['exceptions']:rules.pop('player_trade',None)

def binding_allowed(binding,a,b):
    """Room server side. The binding carries the resolved blocked pairs; an old binding has none (everything allowed)."""
    return _pair(a,b) not in {tuple(p) for p in binding.get('player_trade_blocked',[])}

def require(binding,a,b):
    if not binding_allowed(binding,a,b):raise ValueError('이 시나리오에서는 두 도시 사이의 교역이 허용되지 않습니다.')
