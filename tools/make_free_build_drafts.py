"""2·4·6-player free-build drafts from the shipped, already played default (scenarios/unified-sandbox).

Nothing new is invented: the empire map (template 25), the neutral cities and their trade, the starting funds (10,000),
the allowed buildings and the player transport are copied from unified-sandbox. Only the set of player cities differs:
  2  Capua + Tarentum                    (the first two slots of the default; the original two-city pair)
  4  the default's four slots unchanged  (Capua, Tarentum, Mediolanum, Syracusae)
  6  the four + Carthago + Tarraco       (the two extra slots of scenarios/visual-eight-six, the 6-player check)
A city that stops being a player city goes back to the neutral row the editor's own presets give it
(creator_presets.merged_empire), switched off, as the editor does. A neutral city that becomes a player city keeps its
neutral trade in parked_trade, again as the editor does on a role change, so nothing is lost.
Output: Augustus/scenario-drafts/free-build-<n>/scenario.json (never scenarios/, so the lobby's default and its
automatic choice do not change; a draft is played by pointing AUGUSTUS_MP_PROJECT at it).
"""
import copy,json,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'Augustus'))
import creator_presets,scenario_project

# Carthago uses the official free-build map (101, Carthago.map): the campaign mission (9) starts with a town of 534 people
# already built, which a free-build seat must not have (user 2026-11-15).
SIX=dict(name_id=6,campaign_scenario=101),dict(name_id=7,campaign_scenario=4)    # visual-eight-six player5, player6 (Carthago: free-build map)
TITLES={2:'자유 건설 초안 · 2인 (카푸아·타렌툼)',4:'자유 건설 초안 · 4인 (기본 구성)',6:'자유 건설 초안 · 6인 (기본 + 카르타고·타라코)'}

def draft(base,count):
    d=copy.deepcopy(base);d.update(id=f'free-build-{count}',title=TITLES[count],revision=1)
    cities={c['name_id']:c for c in d['empire']['cities']}
    neutral={c['name_id']:creator_presets.city_fields(c) for c in creator_presets.merged_empire()['cities']}
    allowed=d['slots'][0]['allowed_buildings']
    if count==2:
        for slot in d['slots'][2:]:
            row=dict(neutral[slot['name_id']],role='npc',enabled=False);row.update(x=cities[slot['name_id']]['x'],y=cities[slot['name_id']]['y'])
            cities[slot['name_id']].clear();cities[slot['name_id']].update(row)
        d['slots']=d['slots'][:2]
    if count==6:
        for i,extra in enumerate(SIX):
            c=cities[extra['name_id']]
            c['parked_trade']={k:copy.deepcopy(c[k]) for k in ('sea','cost','sells','buys')}
            if 'trade_players' in c:c['parked_trade']['trade_players']=c.pop('trade_players')
            c.update(role='player',enabled=True,sea=0,cost=0,sells={},buys={})
            d['slots'].append(dict(id=f'player{5+i}',name_id=extra['name_id'],campaign_scenario=extra['campaign_scenario'],allowed_buildings=list(allowed),terrain_edits=[]))
    d['empire']['cities']=[c for c in d['empire']['cities']]
    scenario_project.validate(d);scenario_project.require_runtime(d)
    return d

def main():
    base=json.loads((ROOT/'Augustus/scenarios/unified-sandbox/scenario.json').read_text(encoding='utf-8-sig'))
    out=ROOT/'Augustus/scenario-drafts'
    for n in (2,4,6):
        target=out/f'free-build-{n}'/'scenario.json';target.parent.mkdir(parents=True,exist_ok=True)
        target.write_text(json.dumps(draft(base,n),ensure_ascii=False,indent=1)+'\n',encoding='utf8');print(target)

if __name__=='__main__':main()
