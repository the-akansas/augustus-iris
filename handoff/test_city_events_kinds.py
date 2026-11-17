"""City event kinds added 2026-11-15 (building, god, goods, health, migration, revolt, message): validation, the
layout rows and the EVENTTEXT section the engine reads (shared_empire.h, creator_city_events.h).
What the engine does with them was run by hand on the Linux test rig (events-step); not repeated here."""
import copy,json,sys,unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]/'Augustus'
sys.path.insert(0,str(ROOT))
import city_events,scenario_project as sp

def project():
    data=json.loads((ROOT/'scenarios'/'freebuild-2p'/'scenario.json').read_text(encoding='utf-8-sig'))
    for s in data['slots']:s.pop('governance',None);s['events']=[]
    return data
ALL=[dict(kind='building',month=1,amount=2,resource=92,deadline=0),dict(kind='god',month=2,amount=3,resource=2,deadline=0),
     dict(kind='goods',month=3,amount=-20,resource=1,deadline=0),dict(kind='health',month=4,amount=15,resource=0,deadline=0),
     dict(kind='migration',month=5,amount=200,resource=0,deadline=6),dict(kind='revolt',month=6,amount=1,resource=0,deadline=0),
     dict(kind='message',month=7,amount=1,resource=0,deadline=0,text='로마에서 온 편지\n총독님, 안녕하십니까?')]

class Kinds(unittest.TestCase):
    def test_all_kinds_validate_and_lay_out(self):
        data=project();data['slots'][0]['events']=copy.deepcopy(ALL);sp.validate(data)
        rows=sp.layout(data).splitlines();i=rows.index('EVENTS 7')
        self.assertEqual(rows[i+1:i+8],[f"{data['slots'][0]['id']} {city_events.KINDS.index(e['kind'])} {e['month']} {e['amount']} {e['resource']} {e['deadline']}" for e in ALL])
        t=rows.index(next(r for r in rows if r.startswith('EVENTTEXT ')))
        self.assertEqual(t,len(rows)-1-int(rows[t].split()[1]))   # the last section
        texts={int(r.split()[1]):bytes.fromhex(r.split()[2]).decode('utf-8') for r in rows[t+1:]}
        self.assertEqual(sorted(texts),[0,2,3,4,6])                 # god and revolt use the game's own messages
        self.assertEqual(texts[6],'로마에서 온 편지\n총독님, 안녕하십니까?')     # title, then the body (the editor's two boxes)
        self.assertIn('우물',texts[0]);self.assertIn('밀 20포대',texts[2])
    def test_message_without_title_gets_the_default_one(self):
        e=dict(kind='message',month=1,amount=1,resource=0,deadline=0,text='본문 한 줄')
        self.assertEqual(city_events.message_text(e),'도시 소식\n본문 한 줄')
    def test_conditions_and_repeats(self):
        data=project();sid=data['slots'][0]['id']
        data['slots'][0]['events']=[dict(kind='health',month=2,amount=5,resource=0,deadline=0,when=dict(stat='population',at_least=3000)),
                                    dict(kind='grant',month=1,amount=100,resource=0,deadline=0,repeat=dict(every=12,times=3),when=dict(stat='prosperity',at_least=40))]
        sp.validate(data);rows=sp.layout(data).splitlines();i=rows.index('EVENTS 2')
        self.assertEqual([r.split()[2] for r in rows[i+1:i+3]],['1','2'])                       # in month order; the waiting repeat is one event
        c=rows.index('EVENTCOND 2');self.assertEqual(rows[c+1:c+3],[f'{sid} 0 2 40',f'{sid} 1 1 3000'])
        self.assertEqual(rows[c+3:],['EVENTREPEAT 1',f'{sid} 0 12 3'])                         # the game repeats it: the last section
        data['slots'][0]['events'][1].pop('when');sp.validate(data);rows=sp.layout(data).splitlines();i=rows.index('EVENTS 4')
        self.assertEqual([r.split()[2] for r in rows[i+1:i+5]],['1','2','13','25'])            # a repeat without a condition: each its own event
        self.assertFalse(any(r.startswith('EVENTREPEAT') for r in rows))
        for bad in (dict(when=dict(stat='population',at_least=0)),dict(when=dict(stat='rome',at_least=5)),dict(repeat=dict(every=12,times=1)),
                    dict(repeat=dict(every=600,times=3)),dict(kind='migration',amount=200,deadline=3,when=dict(stat='money',at_least=5))):
            data['slots'][0]['events']=[dict(dict(kind='health',month=1,amount=5,resource=0,deadline=0),**bad)]
            with self.assertRaises(ValueError,msg=str(bad)):sp.validate(data)
        data['slots'][0]['events']=[dict(kind='grant',month=1,amount=1,resource=0,deadline=0,repeat=dict(every=1,times=24))]*3
        with self.assertRaises(ValueError):sp.validate(data)                                   # 72 events after repeats: more than 64
    def test_immigration_changes_do_not_overlap(self):
        # 2026-11-15: the end of one change (back to 100%) would cut a later overlapping one short in the game
        data=project();m=dict(kind='migration',amount=200,resource=0,deadline=12)
        for events in ([dict(m,month=1,repeat=dict(every=6,times=2))],[dict(m,month=10),dict(m,month=1)]):
            data['slots'][0]['events']=events
            with self.assertRaisesRegex(ValueError,'겹칩니다'):sp.validate(data)
        data['slots'][0]['events']=[dict(m,month=13),dict(m,month=1,repeat=dict(every=24,times=2))]    # 1-13, 13-25, 25-37
        sp.validate(data);rows=sp.layout(data).splitlines();i=rows.index('EVENTS 3')
        self.assertEqual([r.split()[2] for r in rows[i+1:i+4]],['1','13','25'])                 # the end of one comes before the next start
    def test_old_kinds_keep_their_layout(self):
        data=project();data['slots'][0]['events']=[dict(kind='grant',month=6,amount=1000,resource=0,deadline=0)];sp.validate(data)
        self.assertFalse(any(r.startswith('EVENTTEXT') for r in sp.layout(data).splitlines()))
    def test_refusals(self):
        bad=[dict(kind='building',month=1,amount=3,resource=92,deadline=0),dict(kind='building',month=1,amount=1,resource=299,deadline=0),
             dict(kind='god',month=1,amount=1,resource=6,deadline=0),dict(kind='goods',month=1,amount=0,resource=1,deadline=0),
             dict(kind='health',month=1,amount=0,resource=0,deadline=0),dict(kind='migration',month=1,amount=100,resource=0,deadline=3),
             dict(kind='migration',month=1,amount=200,resource=0,deadline=0),dict(kind='message',month=1,amount=1,resource=0,deadline=0,text='  '),
             dict(kind='message',month=1,amount=1,resource=0,deadline=0,text='가'*400),dict(kind='revolt',month=1,amount=1,resource=1,deadline=0),
             dict(kind='health',month=1,amount=5,resource=0,deadline=0,text='x')]
        for e in bad:
            data=project();data['slots'][0]['events']=[e]
            with self.assertRaises(ValueError,msg=str(e)):sp.validate(data)
    def test_fixed_favour_only_limits_favour_kinds(self):
        data=project();data['slots'][0]['governance']=dict(rank=0,salary_rank=-1,savings=0,favor=50,policy='fixed')
        data['slots'][0]['events']=copy.deepcopy(ALL);sp.validate(data)
        data['slots'][0]['events']=[dict(kind='favor',month=1,amount=5,resource=0,deadline=0)]
        with self.assertRaises(ValueError):sp.validate(data)

if __name__=='__main__':unittest.main()
