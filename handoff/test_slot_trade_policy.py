"""Slot starting funds, role hints, player-to-player trade policy and the shared trade-link judgement.
Engine checks run only where the rig engine and game data exist (AUGUSTUS_C3_DATA)."""
import copy,json,os,sqlite3,sys,tempfile,unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]/'Augustus'
sys.path.insert(0,str(ROOT));sys.path.insert(0,str(Path(__file__).resolve().parent))
import scenario_project as sp,scenario_check as sc,scenario_cities as cities,trade_policy as tp,creator_presets
from test_scenario_check import RICH,LAKE,OLD,everywhere,isolate,sea_port,land_port,no_marble_seller,of,MARBLE,DOCK

def base(n=4):return creator_presets.default_project(n)
def links_of(r,slot):return next(x['links'] for x in r['links'] if x['slot']==slot)

class Funds(unittest.TestCase):
    def test_slot_amounts_and_inheritance(self):
        d=base();d['rules']['starting_funds']=7000;d['slots'][0]['starting_funds']=0;d['slots'][1]['starting_funds']=1000000;sp.validate(d)
        for bad in (-1,1000001,1.5,True,'5'):
            x=copy.deepcopy(d);x['slots'][2]['starting_funds']=bad
            with self.assertRaises(ValueError):sp.validate(x)
        rows=sp.layout(d).splitlines();i=rows.index('FUNDS 2')
        self.assertEqual(rows[i+1:i+3],['player1 0','player2 1000000']);self.assertIn('START 7000',rows)
        for tag in ('GOVERNANCE','EVENTS','INVASIONS'):self.assertTrue(any(r.startswith(tag+' ') for r in rows[:i]),tag)   # positional sections filled
        model={c['slot']:c['funds'] for c in sc.city_model(d) if c['kind']=='player'}
        self.assertEqual(model['player1'],dict(amount=0,source='slot'));self.assertEqual(model['player3'],dict(amount=7000,source='common'))
        plain=base();self.assertNotIn('FUNDS',sp.layout(plain))                      # files without slot amounts: layout unchanged
        old=copy.deepcopy(d);old['schema']=3
        with self.assertRaises(ValueError):sp.validate(old)                           # older formats refuse the field
    def test_funds_and_hint_stay_with_the_slot(self):
        d=base();s=d['slots'][0];s.update(starting_funds=0,role_hint='식량 공급을 맡기 좋은 도시');sp.validate(d)
        n=next(c['name_id'] for c in d['empire']['cities'] if c['role']=='npc' and cities.preset_terrains(c['name_id']) and not c.get('reserved'))
        moved=next(x for x in sp.validate(cities.swap_city(d,s['id'],n))['slots'] if x['id']==s['id'])
        self.assertEqual((moved['starting_funds'],moved['role_hint']),(0,'식량 공급을 맡기 좋은 도시'))
        gone=sp.validate(cities.to_neutral(d,s['name_id']));self.assertNotIn('starting_funds',json.dumps(cities.find(gone,s['name_id'])))   # deleted with the slot
        fresh=sp.validate(cities.to_player(gone,s['name_id']))['slots'][-1];self.assertNotIn('starting_funds',fresh)                      # a new slot inherits
        x=copy.deepcopy(d);x['slots'][1]['role_hint']='a\nb'
        with self.assertRaises(ValueError):sp.validate(x)

    @unittest.skipUnless(os.environ.get('AUGUSTUS_C3_DATA') and (ROOT/'engine-city-test.exe').is_file(),'engine and game data required')
    def test_engine_gives_each_city_its_amount_and_reload_keeps_it(self):
        from city_client import Engine
        d=base();d['rules']['starting_funds']=7000;d['slots'][0]['starting_funds']=0;d['slots'][1]['starting_funds']=25000;sp.validate(d)
        with tempfile.TemporaryDirectory() as t:
            root=Path(t);sp.write_layout(d,root)
            for s in d['slots'][:3]:
                try:Engine().run('start-'+s['id'],root,root/s['id'])
                except RuntimeError as e:
                    if 'engine validation log failed' not in str(e):raise   # rig data lacks some UI pictures; the engine itself ran
                audit=json.loads((root/s['id']/'rules-audit.json').read_text());want=s.get('starting_funds',7000)
                self.assertEqual((audit['initial_funds'],audit['treasury']),(want,want),s['id'])
                try:Engine().run('inspect',root/s['id'],root/('re-'+s['id']))
                except RuntimeError as e:
                    if 'engine validation log failed' not in str(e):raise
                again=json.loads((root/('re-'+s['id'])/'rules-audit.json').read_text())
                self.assertEqual(again['treasury'],want)                                # loading a save does not pay the start amount again

class Policy(unittest.TestCase):
    def test_rule_order_and_storage(self):
        d=base();ids=[s['id'] for s in d['slots']]
        self.assertEqual(tp.decide(d['rules'],'player1','player2'),(True,'default'))
        x=tp.set_pair(d,'player3','player1',False);sp.validate(x)
        self.assertEqual(x['rules']['player_trade'],dict(exceptions=[dict(between=['player1','player3'],allow=False)]))   # one record for both directions
        self.assertEqual((tp.allowed(x['rules'],'player1','player3'),tp.allowed(x['rules'],'player3','player1')),(False,False))
        self.assertEqual(tp.blocked_pairs(x['rules'],ids),[['player1','player3']])
        self.assertNotIn('player_trade',tp.set_pair(x,'player1','player3',True)['rules'])    # back to the default: nothing stored
        for bad in ([dict(between=['player3','player1'],allow=False)],[dict(between=['player1','ghost'],allow=False)],
                    [dict(between=['player1','player2'],allow=False)]*2,[dict(between=['player1','player2'],allow=0)]):
            y=copy.deepcopy(d);y['rules']['player_trade']=dict(exceptions=bad)
            with self.assertRaises(ValueError):sp.validate(y)
        keep=tp.team_default
        try:
            tp.team_default=lambda rules,a,b:False                                   # a future team rule that forbids everything
            self.assertEqual(tp.decide(d['rules'],'player1','player2'),(False,'team'))
            y=tp.set_pair(d,'player1','player2',True)                               # an explicit exception beats the team default
            self.assertEqual(tp.decide(y['rules'],'player1','player2'),(True,'exception'))
        finally:tp.team_default=keep
    def test_slots_own_the_exceptions(self):
        d=tp.set_pair(base(),'player1','player3',False);sp.validate(d)
        n=next(c['name_id'] for c in d['empire']['cities'] if c['role']=='npc' and cities.preset_terrains(c['name_id']) and not c.get('reserved'))
        self.assertIn('player_trade',sp.validate(cities.swap_city(d,'player1',n))['rules'])   # city swap: slot keeps it
        gone=sp.validate(cities.to_neutral(d,d['slots'][2]['name_id']));self.assertNotIn('player_trade',gone['rules'])   # slot deleted: exception goes too
    def test_server_refuses_forbidden_pairs(self):
        import live_trade,trade_agreements
        class Room:
            started=True
            def __init__(self,blocked):self.coordinator=type('C',(),{'scenario':{'cities':['a','b','c'],'player_trade_blocked':blocked}})()
        db=sqlite3.connect(':memory:');db.row_factory=sqlite3.Row;live_trade.initialize(db)
        for op,body in (('live_offer',dict(receiver='b',kind='gift',resource=0,quantity=0,money=100)),):
            with self.assertRaises(ValueError) as e:live_trade.request(Room([['a','b']]),db,'a',dict(op=op,request_id='0'*32,**body))
            self.assertIn('허용되지 않습니다',str(e.exception))
            with self.assertRaises(ValueError) as e:live_trade.request(Room([['a','b']]),db,'b',dict(op=op,request_id='1'*32,**dict(body,receiver='a')))
            self.assertIn('허용되지 않습니다',str(e.exception))                      # symmetric
            try:live_trade.request(Room([]),db,'a',dict(op=op,request_id='2'*32,**body))
            except Exception as other:self.assertNotIn('허용되지 않습니다',str(other))   # an allowed pair gets past the rule (and stops later on the bare test database)
        try:trade_agreements.initialize(db)
        except AttributeError:pass
        with self.assertRaises(ValueError) as e:trade_agreements.request(Room([['a','c']]),db,'c',dict(op='agreement_offer',request_id='3'*32,peer='a',mode='sell',resource=15,quantity=4,money=100,repeat=0))
        self.assertIn('허용되지 않습니다',str(e.exception))
        self.assertTrue(tp.binding_allowed({'cities':['a','b']},'a','b'))           # older binding without the list: everything allowed
    def test_partner_window_hides_forbidden_peers(self):
        import trade_partner_bridge as tpb
        routes=dict(links=[],posts=[]);rows=tpb.partners('a',['a','b','c'],routes,[],[['a','b']])
        self.assertEqual([r[1] for r in rows],['c']);self.assertEqual(rows[0][0],3)  # slot numbers (colours) unchanged

class Links(unittest.TestCase):
    def test_states(self):
        d=base();isolate(d);port=sea_port(d,[MARBLE]);road=land_port(d,[1]);off=next(c for c in d['empire']['cities'] if c['role']=='npc' and not c['enabled'])
        d=tp.set_pair(d,'player1','player2',False);sp.validate(d)
        t=everywhere(d,RICH);t['player1']=LAKE;t['player3']=OLD
        r=sc.check(d,t);p1={(x['kind'],x['slot'] or x['name_id']):x for x in links_of(r,'player1')}
        self.assertEqual((p1[('player','player2')]['allowed'],p1[('player','player2')]['state']),(False,'off'))
        self.assertEqual(p1[('player','player3')]['state'],'ok')                    # players trade by land even when the city has no sea access
        self.assertEqual((p1[('neutral',port['name_id'])]['state'],p1[('neutral',road['name_id'])]['state']),('broken','ok'))
        self.assertIn('해상 교역 불가',p1[('neutral',port['name_id'])]['reason'])
        self.assertNotIn(('neutral',off['name_id']),p1)                             # unused neutral cities are not partners
        p2={x['name_id']:x for x in links_of(r,'player2') if x['kind']=='neutral'};self.assertEqual(p2[port['name_id']]['state'],'candidate')   # not "possible"
        p3={x['name_id']:x for x in links_of(r,'player3') if x['kind']=='neutral'};self.assertEqual(p3[port['name_id']]['state'],'unknown')
        self.assertEqual(p2[port['name_id']]['sells'],[MARBLE])
        allowed_but_lake=copy.deepcopy(d);cities.find(allowed_but_lake,port['name_id'])['trade_players']=['player1']
        r2=sc.check(sp.validate(allowed_but_lake),t)
        self.assertEqual({x['name_id']:x for x in links_of(r2,'player1') if x['kind']=='neutral'}[port['name_id']]['state'],'broken')   # allowing it does not make it possible
    def test_policy_blocks_supply_chains(self):
        d=base();no_marble_seller(d);d['slots'][0]['allowed_buildings'].append(106);sp.validate(d)   # only player1 can quarry marble
        free=sc.check(d,everywhere(d,RICH));self.assertFalse([f for f in of(free,'resource') if '대리석' in f['reason']])
        cut=d
        for other in ('player2','player3','player4'):cut=tp.set_pair(cut,'player1',other,False)
        r=sc.check(sp.validate(cut),everywhere(cut,RICH))
        self.assertEqual(len([f for f in of(r,'resource') if '대리석' in f['reason'] and f['severity']=='warn']),3)
        self.assertFalse(r['blocked'])
    def test_updates_follow_edits(self):
        d=base();isolate(d);port=sea_port(d,[MARBLE]);sp.validate(d);t=everywhere(d,RICH)
        before={x['name_id'] for x in links_of(sc.check(d,t),'player1') if x['allowed']}
        cities.find(d,port['name_id'])['trade_players']=['player2'];after={x['name_id'] for x in links_of(sc.check(sp.validate(d),t),'player1') if x['allowed']}
        self.assertIn(port['name_id'],before);self.assertNotIn(port['name_id'],after)
        n=d['slots'][3]['name_id'];gone=sp.validate(cities.to_neutral(d,n))
        self.assertNotIn('player4',[x['slot'] for x in sc.check(gone,t)['links']])

class Overview(unittest.TestCase):
    def test_lobby_text_uses_the_same_links(self):
        import scenario_overview as so
        catalog=json.loads((ROOT/'preset-catalog.json').read_text(encoding='utf-8-sig'))
        d=base();d['slots'][0].update(starting_funds=0,role_hint='식량 공급을 맡기 좋은 도시');d=tp.set_pair(d,'player1','player2',False);sp.validate(d)
        view=so.overview(d,catalog);p1=next(c for c in view['cities'] if c['player'] and any('제작자 추천' in l for l in c['detail']))
        text=''.join(p1['detail']);self.assertIn('시작 자금: 0',text);self.assertIn('제작자 추천(규칙 아님)',text)
        self.assertIn('교역 상대 플레이어:',text)
        self.assertIn('W\t교역 금지: ',''.join(view['briefing']))   # the pairs named (2026-11-16)

class LobbyLines(unittest.TestCase):
    def view(self,data):
        import scenario_overview as so
        return so.overview(data,json.loads((ROOT/'preset-catalog.json').read_text(encoding='utf-8-sig')))
    def test_tagged_lines_follow_the_shared_judgement(self):
        d=base();isolate(d);port=sea_port(d,[MARBLE]);road=land_port(d,[1]);d=tp.set_pair(d,'player1','player2',False);sp.validate(d)
        keep=sc.EVIDENCE
        with tempfile.TemporaryDirectory() as t:
            sc.EVIDENCE=Path(t)
            try:
                for s in d['slots']:sc.store_evidence(s,LAKE if s['id']=='player1' else RICH)
                v=self.view(d)
            finally:sc.EVIDENCE=keep
        names=[c['name'] for c in v['cities']];p1=next(c for c in v['cities'] if c['detail'] and c['detail'][0]=='H\t플레이 도시 P1')
        kinds={l.split('\t',1)[0] for c in v['cities'] for l in c['detail']}|{l.split('\t',1)[0] for l in v['briefing']}
        self.assertTrue(kinds<=set('HFRWTL'),kinds)                                    # every line is tagged
        links=[l.split('\t') for l in p1['detail'] if l[0] in 'TL']
        for kind,state,how,target,*text in links:
            self.assertIn(state,('ok','candidate','unknown','broken'));self.assertIn(how,('land','sea'));self.assertTrue(0<=int(target)<len(names))
        shown={names[int(t)]:(k,st,h) for k,st,h,t,*_ in links}
        result=sc.check(d,dict((s['id'],LAKE if s['id']=='player1' else RICH) for s in d['slots']))
        judged={x['name_id']:x for x in next(r for r in result['links'] if r['slot']=='player1')['links']}
        broken=[n for n,(k,st,h) in shown.items() if st=='broken']
        self.assertEqual(len(broken),1);self.assertEqual(shown[broken[0]][2],'sea')            # the sea-only neutral city, from the shared judgement
        self.assertEqual(judged[port['name_id']]['state'],'broken')
        self.assertTrue(any(k=='L' and st=='ok' for k,st,h in shown.values()) or any(k=='T' and st=='ok' for k,st,h in shown.values()))
        text=' '.join(p1['detail']);self.assertIn('교역 금지(시나리오 설정)',text);self.assertNotIn('—',text+' '.join(v['briefing']))
    def test_too_many_players_is_explained(self):
        d=base(8);sp.validate(d);v=self.view(d)
        # 8 seats, at most 6 play (2026-11-15): told, not refused
        self.assertIn('8자리 중 최대 6명',v['subtitle']);self.assertTrue(any(l.startswith('F\t') and '골라서 플레이합니다' in l for l in v['briefing']))
        self.assertFalse(any('시작할 수 없습니다' in l for l in v['briefing']))
        self.assertNotIn('자리 중 최대',self.view(base(6))['subtitle'])
    def test_room_file_round_trip(self):
        import scenario_overview as so
        body=so.encode('ROOM',self.view(base()));rows=body.split('\n')
        self.assertEqual(rows[:2],['AUGSCENARIO1','ROOM']);self.assertTrue(all(len(r.encode('utf-8'))<1024 for r in rows))

if __name__=='__main__':unittest.main()
