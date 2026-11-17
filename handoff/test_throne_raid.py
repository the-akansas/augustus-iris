"""Race for the Throne: the emperor's punitive expedition (confirmed plan 2026-11-14, docs/황위-쟁탈전-확정안-20261114.md).

  * Paranoia 100 -> the legions LEAVE ROME at once (no preparation) and march for 3 months. Only on the march can the
    withdrawal tribute be paid: they turn back and paranoia drops by 80. The amount is that of the stage held at
    departure (3,000 / 5,000 / 8,000 / 12,000 / 18,000 Dn) and does not follow a stage won on the way.
  * On arrival they attack at once. No tribute any more. Beating them: -25. Not within 2 months: they sack the city
    and withdraw, paranoia -50. Never below the stage floor. No elimination.
  * Then 2 months without a new expedition. Each one against the same player is larger: 32, 48, 64, 80 (cap).
  * A gift on the march does not call it off; a coup can still be funded. Private: only the player concerned sees it.
Runs the real host code (throne_rules, throne_state, throne_play, the debit ledger) and the real bridge code
(throne_client: the box, the march card, the tribute dialog, the order file for the engine, the report to the room,
the player's own notices). Stand-ins: the city's money engine (test_throne_trial.Cities) and the battle itself: the
file the game's engine writes (emperor-raid.txt) is written by the test. Fixture values (paranoia, stage, treasury)
are TEST INPUTS."""
import json,sys,unittest,uuid
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parent))
from test_throne_trial import B,CITIES,MONTH,RULES,Base,Cities,FakeClient,SimpleBridge,save,set_secret,restore_own,restore_replica,activate,req
import throne_rules as tr,throne_state as ts,throne_events as te,throne_play as tp

X=RULES['expedition']
MARCH,SIEGE,COOL=X['march_months']*MONTH,X['siege_months']*MONTH,X['cooldown_months']*MONTH

class RaidBase(Base):
    def raid(self,city='player1',host=None):return (host or self.host).state()['players'][city]['secret']['expedition']
    def paranoia(self,city='player1',host=None):return (host or self.host).state()['players'][city]['secret']['paranoia']
    def report(self,city,count,seen,tick,host=None):
        h=host or self.host;h.settle(tick);out=tp.raid_report(h.db,B,city,count,seen,tick);h.db.commit();return out
    def to_march(self,city='player1',stage=None,tick=0):
        """Wake the emperor and put `city` at the maximum (test input): its first expedition leaves Rome."""
        activate(self.host,'player3',cities=self.cities)
        set_secret(self.host,city,stage=stage,paranoia=100);self.host.settle(tick)
        self.assertEqual(self.raid(city)['phase'],'preparing');return tick
    def to_fighting(self,city='player1',stage=None,tick=0):
        """...and walk it to the city: arrival after the march, then the engine's 'they attack'."""
        self.to_march(city,stage,tick)
        self.host.settle(tick+MARCH);self.assertEqual(self.raid(city)['phase'],'arrived')
        self.assertTrue(self.report(city,1,tp.RAID_ATTACKING,tick+MARCH));self.assertEqual(self.raid(city)['phase'],'fighting')
        return tick+MARCH

class Rules(unittest.TestCase):
    def test_numbers(self):
        self.assertEqual((X['march_months'],X['siege_months'],X['cooldown_months'],X['tribute_reduction'],X['victory_reduction'],X['sack_reduction']),(3,2,2,80,25,50))
        self.assertNotIn('preparation_months',X)
        self.assertEqual([tr.raid_tribute(RULES,s) for s in range(6)],[3000,5000,8000,12000,18000,18000])
        self.assertEqual([tr.raid_size(RULES,n) for n in range(1,7)],[32,48,64,80,80,80])
        self.assertEqual([tr.raid_relief(RULES,s,100,80) for s in range(5)],[20,20,30,40,50])   # stage floors 10,20,30,40,50
        self.assertEqual(tr.raid_relief(RULES,0,100,25),75);self.assertEqual(tr.raid_relief(RULES,4,60,25),50)
        self.assertEqual(tr.raid_relief(RULES,0,100,50),50);self.assertEqual(tr.raid_relief(RULES,4,100,50),50)
        self.assertEqual(tr.raid_relief(RULES,0,5,80),5)                                       # below the floor already (gifts): never raised
        ts.validate_rules(dict(RULES,expedition=dict(X,army_cap=96)))                          # the editor may change it...
        with self.assertRaises(ValueError):ts.validate_rules(dict(RULES,expedition=dict(X,army_cap=16)))   # ...but not below the first size
        scenario=json.loads((Path(__file__).resolve().parents[1]/'Augustus'/'scenarios'/'throne-test-v1'/'scenario.json').read_text(encoding='utf-8'))
        self.assertEqual(scenario['rules']['throne'],RULES)

class March(RaidBase):
    def test_peace_and_below_the_maximum_nothing_starts(self):
        self.host.settle(50*MONTH);self.assertEqual(self.raid()['phase'],'idle')      # peace: paranoia 0, no emperor
        activate(self.host,'player3',tick=50*MONTH,cities=self.cities);set_secret(self.host,'player1',paranoia=99)
        self.host.settle(50*MONTH);self.assertEqual(self.raid(),dict(phase='idle',id=0,count=0,deadline_tick=None,tribute_paid=False,result=None))
        self.assertEqual(self.host.own('player1')['raid']['order'],'')
    def test_they_leave_at_once_and_arrive_after_the_march(self):
        activate(self.host,'player3',cities=self.cities);set_secret(self.host,'player1',paranoia=100)
        self.host.settle(10);e=self.raid()
        self.assertEqual((e['phase'],e['count'],e['deadline_tick'],e['result']),('preparing',1,10+MARCH,None))   # 'preparing' = on the march
        self.assertEqual(self.raid('player2')['phase'],'idle')                        # only the player at the maximum
        own=self.host.own('player1')['raid'];self.assertEqual((own['order'],own['size'],own['tribute'],own['wait']),('',32,3000,'3개월'))
        for _ in range(3):self.host.settle(10+MARCH-1)
        self.assertEqual(self.raid(),e)                                               # polls never move it
        self.host.settle(10+MARCH);self.assertEqual(self.raid()['phase'],'arrived')
        self.assertEqual(self.host.own('player1')['raid']['order'],'attack')          # they attack at once: the engine is told to let them in
        self.host.settle(10+MARCH+20*MONTH);self.assertEqual(self.raid()['phase'],'arrived')   # the city has not answered: nothing is decided for it
        self.assertFalse(self.report('player1',2,tp.RAID_ATTACKING,10+MARCH+20*MONTH))  # another expedition's number
        self.assertFalse(self.report('player2',1,tp.RAID_ATTACKING,10+MARCH+20*MONTH))  # another player's city
        t=10+MARCH+20*MONTH;self.assertTrue(self.report('player1',1,tp.RAID_ATTACKING,t))
        self.assertEqual((self.raid()['phase'],self.raid()['deadline_tick']),('fighting',t+SIEGE))   # the 2 months run from the arrival in the city
        self.assertFalse(self.report('player1',1,tp.RAID_ATTACKING,t+5));self.assertEqual(self.raid()['deadline_tick'],t+SIEGE)
    def test_tribute_on_the_march_turns_them_back(self):
        t=self.to_march();before=self.cities.treasury['player1']
        q=self.host.quote('player1','tribute',3000,funds=before,tick=t+MONTH)
        self.assertEqual((q['ok'],q['charge'],q['before'],q['after'],q['points']),(True,3000,100,20,80))
        self.assertFalse(self.host.quote('player1','tribute',2999,tick=t)['ok'])      # the fixed amount, nothing else
        self.assertFalse(self.host.quote('player1','tribute',3000,funds=2999,tick=t)['ok'])
        self.assertFalse(self.host.quote('player2','tribute',3000,tick=t)['ok'])      # nobody is marching on that city
        out=self.host.spend('player1','tribute',3000,funds=before,tick=t+MONTH);self.assertEqual(out['state'],'charging')
        self.assertEqual((self.raid()['phase'],self.paranoia()),('preparing',100))    # nothing until the money is taken
        self.cities.run(self.host,'player1');self.host.settle(t+MONTH)
        e=self.raid();self.assertEqual((e['phase'],e['result'],e['tribute_paid'],e['deadline_tick']),('cooldown','tribute',True,t+MONTH+COOL))
        self.assertEqual(self.paranoia(),20);self.assertEqual(self.cities.treasury['player1'],before-3000)
        own=self.host.own('player1');self.assertEqual((own['last']['kind'],own['last']['result'],own['last']['points']),('tribute','withdrawn',80))
        self.assertEqual(own['raid']['order'],'withdraw')                             # they never entered; the number stays called back
        again=self.host.spend('player1','tribute',3000,tick=t+MONTH,request=out['request']);self.assertTrue(again['duplicate'])
        self.cities.run(self.host,'player1');self.host.settle(t+MONTH);self.assertEqual(self.cities.treasury['player1'],before-3000)   # never twice
        self.host.settle(t+MARCH);self.assertEqual(self.raid()['phase'],'cooldown' if t+MARCH<t+MONTH+COOL else 'idle')   # they do not arrive
    def test_tribute_is_the_one_of_the_stage_held_at_departure(self):
        t=self.to_march(stage=1)                                                      # floor 20, tribute 5,000
        self.assertEqual(self.host.own('player1')['raid']['tribute'],5000)
        self.coup('player1',10000,0,tick=t+MONTH)                                     # a coup can be funded on the march: stage 2 now
        self.assertEqual(self.host.state()['players']['player1']['stage'],2);self.assertEqual(self.raid()['phase'],'preparing')
        self.assertEqual(self.host.own('player1')['raid']['tribute'],5000)            # not 8,000: fixed when they left
        self.assertFalse(self.host.quote('player1','tribute',8000,tick=t+MONTH)['ok'])
        self.host.spend('player1','tribute',5000,tick=t+MONTH);self.cities.run(self.host,'player1');self.host.settle(t+MONTH)
        self.assertEqual((self.paranoia(),self.raid()['result']),(30,'tribute'))      # the reduction stops at the floor of the stage held NOW (30)
    def test_tribute_respects_the_stage_floor_and_costs_more_later(self):
        t=self.to_march(stage=3)                                                      # floor 40
        self.assertEqual(self.host.own('player1')['raid']['tribute'],12000)
        self.host.spend('player1','tribute',12000,tick=t);self.cities.run(self.host,'player1');self.host.settle(t)
        self.assertEqual((self.paranoia(),self.raid()['result']),(40,'tribute'))
    def test_a_gift_on_the_march_does_not_call_it_off(self):
        t=self.to_march()
        self.host.spend('player1','gift',10000,tick=5);self.cities.run(self.host,'player1');self.host.settle(5)
        self.assertEqual(self.paranoia(),50);self.assertEqual(self.raid()['phase'],'preparing')
        self.host.settle(MARCH);self.assertEqual(self.raid()['phase'],'arrived')      # only the tribute turns them back
    def test_no_tribute_once_they_have_arrived(self):
        t=self.to_march();self.host.settle(t+MARCH)                                   # arrived
        q=self.host.quote('player1','tribute',3000,tick=t+MARCH);self.assertFalse(q['ok']);self.assertIn('이제 공물은 받지 않습니다',q['reason'])
        self.assertEqual(self.host.spend('player1','tribute',3000,tick=t+MARCH)['state'],'refused');self.assertEqual(len(self.host.debits()),1)   # only the activating coup
        self.report('player1',1,tp.RAID_ATTACKING,t+MARCH)
        self.assertFalse(self.host.quote('player1','tribute',3000,tick=t+MARCH)['ok'])   # fighting: neither
    def test_tribute_not_taken_changes_nothing_and_the_march_goes_on(self):
        self.cities.treasury['player1']=6000                                          # the activating coup of player3 does not touch it
        t=self.to_march();self.cities.treasury['player1']=100
        self.host.spend('player1','tribute',3000,tick=t);self.cities.run(self.host,'player1');self.host.settle(t)
        self.assertEqual(self.host.own('player1')['last']['state'],'void')
        self.assertEqual((self.raid()['phase'],self.paranoia(),self.cities.treasury['player1']),('preparing',100,100))
        self.host.settle(t+MARCH);self.assertEqual(self.raid()['phase'],'arrived')
    def test_a_tribute_under_way_holds_the_arrival_until_it_is_settled(self):
        t=self.to_march();before=self.cities.treasury['player1']
        self.host.spend('player1','tribute',3000,tick=t+MARCH-1)                      # charging: the city has not answered
        self.host.settle(t+MARCH+5);self.assertEqual(self.raid()['phase'],'preparing')   # they do not arrive while the payment is open
        self.assertTrue(self.host.own('player1')['raid']['paying']);self.assertEqual(self.host.own('player1')['raid']['order'],'')
        self.cities.run(self.host,'player1');self.host.settle(t+MARCH+5)              # taken: it counts, they turn back
        self.assertEqual((self.raid()['result'],self.paranoia(),self.cities.treasury['player1']),('tribute',20,before-3000))

class Outcomes(RaidBase):
    def test_beating_the_legions(self):
        t=self.to_fighting()
        self.assertTrue(self.report('player1',1,tp.RAID_BEATEN,t+100))
        e=self.raid();self.assertEqual((e['phase'],e['result'],e['tribute_paid'],e['deadline_tick']),('cooldown','defeated',False,t+100+COOL))
        self.assertEqual(self.paranoia(),75)
        for _ in range(3):self.assertFalse(self.report('player1',1,tp.RAID_BEATEN,t+100))   # the same report again
        self.assertEqual(self.paranoia(),75);self.assertEqual(self.host.state()['players']['player1']['stage'],0)   # no coup effect
    def test_beaten_before_the_room_heard_of_the_arrival(self):
        t=self.to_march();self.host.settle(MARCH)
        self.assertTrue(self.report('player1',1,tp.RAID_BEATEN,MARCH+3));self.assertEqual((self.raid()['result'],self.paranoia()),('defeated',75))
    def test_not_beaten_in_time_sacked_minus_fifty_and_stronger_next_time(self):
        t=self.to_fighting()
        self.host.settle(t+SIEGE-1);self.assertEqual((self.raid()['phase'],self.paranoia()),('fighting',100))
        self.host.settle(t+SIEGE);e=self.raid()
        self.assertEqual((e['phase'],e['result'],e['deadline_tick']),('cooldown','sacked',t+SIEGE+COOL));self.assertEqual(self.paranoia(),50)   # 2026-11-14: -50, not unchanged
        for _ in range(3):self.host.settle(t+SIEGE)
        self.assertEqual(self.paranoia(),50)                                          # once
        self.assertFalse(self.host.state()['players']['player1']['eliminated'])
        self.assertEqual(self.host.own('player1')['raid']['order'],'withdraw')
        self.assertFalse(self.report('player1',1,tp.RAID_BEATEN,t+SIEGE+1));self.assertEqual(self.paranoia(),50)   # too late
        self.host.settle(t+SIEGE+COOL);e=self.raid()                                  # 50 + 2 months x2 = 54: no new one
        self.assertEqual((e['phase'],e['count'],self.paranoia()),('idle',1,54))
        set_secret(self.host,'player1',paranoia=100);self.host.settle(t+SIEGE+COOL);e=self.raid()   # at the maximum again (test input): the next one, larger
        self.assertEqual((e['phase'],e['count'],e['result']),('preparing',2,None));self.assertEqual(self.host.own('player1')['raid']['size'],48)
    def test_sack_stops_at_the_stage_floor(self):
        t=self.to_fighting(stage=4);self.host.settle(t+SIEGE)                         # floor 50: 100-50 = 50
        self.assertEqual((self.raid()['result'],self.paranoia()),('sacked',50))
    def test_the_maximum_during_the_cooldown_waits_for_its_end(self):
        t=self.to_fighting();self.report('player1',1,tp.RAID_BEATEN,t)                # 75, cooldown until t+COOL
        set_secret(self.host,'player1',paranoia=100);self.host.settle(t+COOL-1)
        self.assertEqual((self.raid()['phase'],self.raid()['count']),('cooldown',1))
        self.host.settle(t+COOL);self.assertEqual((self.raid()['phase'],self.raid()['count'],self.raid()['deadline_tick']),('preparing',2,t+COOL+MARCH))
    def test_size_grows_to_the_cap(self):
        t=self.to_fighting();sizes=[32]
        for n in range(2,7):
            self.report('player1',n-1,tp.RAID_BEATEN,t);t=self.raid()['deadline_tick']        # beaten; cooldown ends at t
            set_secret(self.host,'player1',paranoia=100);self.host.settle(t);self.assertEqual(self.raid()['count'],n)
            t=self.raid()['deadline_tick'];self.host.settle(t);self.report('player1',n,tp.RAID_ATTACKING,t)
            sizes.append(self.host.own('player1')['raid']['size'])
        self.assertEqual(sizes,[32,48,64,80,80,80])
    def test_cooldown_ends_quietly_below_the_maximum(self):
        t=self.to_fighting();self.report('player1',1,tp.RAID_BEATEN,t)                # 75
        self.host.settle(t+COOL);e=self.raid()
        self.assertEqual((e['phase'],e['count'],e['result'],e['deadline_tick']),('idle',1,None,None))
        self.assertEqual(self.host.own('player1')['raid']['order'],'withdraw')        # the old number stays called back
        self.host.settle(t+COOL+12*MONTH);self.assertEqual((self.paranoia(),self.raid()['phase'],self.raid()['count']),(100,'preparing',2))

class EndAndPrivacy(RaidBase):
    def test_the_end_calls_it_off_and_refunds_a_tribute_under_way(self):
        t=self.to_march();before=self.cities.treasury['player1']
        self.host.spend('player1','tribute',3000,tick=t);self.cities.run(self.host,'player1',ack=False)   # taken, the room does not know yet
        set_secret(self.host,'player2',stage=4,paranoia=50)
        self.coup('player2',80000,0,tick=t)                                            # player2 takes the throne
        self.assertTrue(self.host.state()['ended'])
        self.cities.report(self.host,'player1');self.host.settle(t)
        e=self.raid();self.assertEqual((e['phase'],e['result'],e['tribute_paid']),('resolved','called_off',False));self.assertEqual(self.paranoia(),100)
        self.cities.run(self.host,'player1');self.host.settle(t)
        self.assertEqual(self.host.own('player1')['last']['state'],'refunded');self.assertEqual(self.cities.treasury['player1'],before)
        self.host.settle(t+50*MONTH);self.assertEqual(self.raid()['phase'],'resolved')  # nothing starts after the end
    def test_the_end_calls_back_legions_in_the_city(self):
        t=self.to_fighting();set_secret(self.host,'player2',stage=4,paranoia=50);self.coup('player2',80000,0,tick=t)
        self.host.settle(t);self.assertEqual((self.raid()['phase'],self.raid()['result']),('resolved','called_off'))
        self.assertEqual(self.host.own('player1')['raid']['order'],'withdraw')
    def test_only_the_player_concerned_sees_it(self):
        t=self.to_fighting()
        public=json.dumps(te.public_status(self.host.db,B),ensure_ascii=False)
        for word in ('expedition','raid','fighting','tribute','원정','공물'):self.assertNotIn(word,public)
        other=self.host.own('player2');self.assertEqual((other['raid']['phase'],other['raid']['count'],other['raid']['order']),('idle',0,''))
        self.assertEqual(self.host.own('player2')['paranoia'],21)                     # its own value: 15 and three months x2
    def test_scoreboard_only_at_the_end_shows_everything(self):
        t=self.to_march();self.host.spend('player1','tribute',3000,tick=t);self.cities.run(self.host,'player1');self.host.settle(t)
        self.assertIsNone(te.public_status(self.host.db,B)['scoreboard'])
        set_secret(self.host,'player2',stage=4,paranoia=50);self.coup('player2',80000,0,tick=t+MONTH)
        status=te.public_status(self.host.db,B);rows=status['scoreboard']
        self.assertEqual((status['ended'],status['leading']),(True,5));self.assertEqual([r['city'] for r in rows][0],'player2')
        first=rows[0];self.assertEqual((first['winner'],first['stage'],first['successes'],first['coup_total'],first['known']),(True,5,1,80000,True))
        mine=next(r for r in rows if r['city']=='player1');self.assertEqual((mine['raids'],mine['tributes'],mine['paranoia'],mine['stage']),(1,1,22,0))
        third=next(r for r in rows if r['city']=='player3');self.assertEqual((third['failures'],third['coup_total']),(1,5000))   # the activating coup that failed
    def test_save_and_restore_keep_the_expedition(self):
        t=self.to_fighting();saved=save(self.host,1,t+10,self.cities);e=self.raid()
        own=restore_own(self.tmp.name,saved,self.host);self.addCleanup(own.db.close)
        self.assertEqual(self.raid(host=own),e)
        self.assertTrue(self.report('player1',1,tp.RAID_BEATEN,t+20,host=own));self.assertEqual(self.paranoia(host=own),75)
    def test_new_host_from_a_backup_waits_for_the_record_and_protects_its_deadline(self):
        t=self.to_fighting();saved=save(self.host,1,t+10,self.cities)
        new=restore_replica(self.tmp.name,saved,self.host);self.addCleanup(new.db.close)
        self.assertIn('pending',new.state()['players']['player1'])
        new.settle(t+10+30*MONTH)                                                     # the record is not there: nothing is decided
        self.assertFalse(self.report('player1',1,tp.RAID_BEATEN,t+10+30*MONTH,host=new))
        o=saved['openings']['player1'];te.hand_in(new.db,B,'player1',o['secret'],o['nonce'],t+10+30*MONTH);new.db.commit()
        e=self.raid(host=new);self.assertEqual((e['phase'],e['deadline_tick']),('fighting',t+SIEGE+30*MONTH))   # moved by the waiting time, once
        self.assertTrue(self.report('player1',1,tp.RAID_BEATEN,t+10+30*MONTH,host=new));self.assertEqual(self.raid(host=new)['result'],'defeated')
    def test_validation(self):
        t=self.to_fighting();state=self.host.state();e=state['players']['player1']['secret']['expedition']
        for bad in (dict(deadline_tick=None),dict(result='sacked'),dict(phase='cooldown'),dict(count=0),dict(result='plundered')):
            broken=json.loads(json.dumps(state));broken['players']['player1']['secret']['expedition'].update(bad)
            with self.assertRaises(ValueError):ts.validate(broken,B)
        ts.validate(state,B)

class RaidClient(FakeClient):
    def call(s,op,**r):
        if op!='throne_raid':return super().call(op,**r)
        s.calls.append(op);h=s.host;tick=h.state()['last_tick'];h.settle(tick)
        tp.raid_report(h.db,B,s.city,r['count'],r['seen'],tick);h.db.commit();return dict(own=tp.view(h.state(),s.city,tick))

class Player(RaidBase):
    """The player's PC: the box and the march card, the tribute dialog, the order for the game's engine, the report,
    the player's own notices."""
    def bridge(self,city='player1'):
        import throne_client
        folder=Path(self.tmp.name)/('pc-'+city);folder.mkdir(exist_ok=True)
        b=SimpleBridge(folder,RaidClient(self.host,city));b.joined=True;b.config=dict(session='s1')
        (folder/'post-identity.txt').write_text('ab'*32+' 0');return b,throne_client
    def sync(self,b,tc):
        own=tc.raid_sync(b,b.client.call('throne_mine'));tc.publish_panel(b,own);return own
    def box(self,b):return [l.split('\t') for l in b.files['throne-box.txt'].splitlines()]
    def dialog(self,b):return [l.split('\t') for l in b.files['throne-dialog.txt'].splitlines()]
    def test_the_whole_course_on_the_players_pc(self):
        import city_notices
        activate(self.host,'player3',cities=self.cities);b,tc=self.bridge()
        self.sync(b,tc);self.assertEqual(b.files['emperor-raid-request.txt'],'');self.assertEqual(b.throne_private_events,'')
        self.assertFalse(any(l[0]=='march' for l in self.box(b)))
        set_secret(self.host,'player1',paranoia=100);self.host.settle(0);self.sync(b,tc)
        self.assertIn(['march','황제군이 오고 있습니다','도착까지 3개월','1'],self.box(b))   # the card, with its button
        self.assertEqual(b.files['emperor-raid-request.txt'],'')                     # nothing for the engine yet
        warning=b.throne_private_events;self.assertEqual(len(warning.split('\t')[0]),32);self.assertIn('\t황제의 징벌 원정\t',warning)
        self.assertIn('이미 출발했습니다',warning);self.assertIn('철수 공물 3,000 Dn',warning)
        self.sync(b,tc);self.assertEqual(b.throne_private_events.split('\t')[0],warning.split('\t')[0])   # the same id every time: shown once by the game
        tc.command(b,'tribute\n200000',req());d=self.dialog(b)
        self.assertIn(['kind','tribute'],d);self.assertIn(['row','공물','3,000 Dn'],d);self.assertIn(['row','보유 자금','200,000 Dn'],d)
        self.assertIn(['row','공물 후 편집증','20 (지금 100)'],d);self.assertIn(['row','황제군 도착까지','3개월'],d);self.assertIn(['go','공물 바치기','1'],d)
        self.assertFalse(any(l[0]=='amount' for l in d))                             # a fixed amount: nothing to adjust
        tc.command(b,'add1000\n200000',req());self.assertIn(['row','공물','3,000 Dn'],self.dialog(b))
        tc.command(b,'go\n200000',req());self.cities.run(self.host,'player1');self.sync(b,tc)
        self.assertEqual(self.raid()['result'],'tribute');self.assertEqual(self.paranoia(),20)
        self.assertEqual(b.files['emperor-raid-request.txt'],'ab'*32+' 0 1 32 2\n')  # that number is called back (they never entered)
        self.assertFalse(any(l[0]=='march' for l in self.box(b)));self.assertEqual(b.files['throne-dialog.txt'],'')
        lines=[e for e in city_notices.state(b)['log'] if e[1]==7];self.assertEqual([e[3] for e in lines],['황제군 철수: 공물을 바쳐 황제의 의심을 달랬습니다.'])
        self.sync(b,tc);self.assertEqual(len([e for e in city_notices.state(b)['log'] if e[1]==7]),1)   # once
    def test_arrival_orders_the_attack_and_takes_the_card_away(self):
        t=self.to_march();b,tc=self.bridge();self.host.settle(t+MARCH);self.sync(b,tc)
        self.assertEqual(b.files['emperor-raid-request.txt'],'ab'*32+' 0 1 32 1\n');self.assertEqual(b.throne_private_events,'')
        self.assertFalse(any(l[0]=='march' for l in self.box(b)))                     # no tribute any more: no card
        self.assertNotIn('throne_raid',b.client.calls)                               # the engine has said nothing yet
        (b.root/'emperor-raid.txt').write_text('1 1 32 0 32\n');self.sync(b,tc)      # the legions are in the city
        self.assertEqual(self.raid()['phase'],'fighting')
        calls=b.client.calls.count('throne_raid');self.sync(b,tc);self.assertEqual(b.client.calls.count('throne_raid'),calls)   # reported once
        tc.command(b,'tribute\n200000',req())                                         # a late click (the card was still on screen)
        self.assertEqual(b.files['throne-dialog.txt'],'');self.assertTrue(any(l[0]=='note' and '이제 공물은 받지 않습니다' in l[1] for l in self.box(b)))
    def test_beaten_in_the_city_is_passed_on(self):
        import city_notices
        t=self.to_fighting();b,tc=self.bridge()
        (b.root/'emperor-raid.txt').write_text('1 3 32 32 0\n');own=self.sync(b,tc)
        self.assertEqual((self.raid()['result'],self.paranoia()),('defeated',75));self.assertEqual(own['raid']['phase'],'cooldown')
        self.sync(b,tc);self.assertEqual([e[3] for e in city_notices.state(b)['log'] if e[1]==7],['황제군 격파: 로마의 군대를 물리쳤습니다.'])
    def test_other_numbers_and_called_back_legions_are_not_reported(self):
        t=self.to_fighting();b,tc=self.bridge()
        for text in ('2 3 48 48 0\n','1 4 32 3 0\n','1 2 32 3 9\n','garbage','1 3\n'):
            (b.root/'emperor-raid.txt').write_text(text);self.sync(b,tc)
        self.assertNotIn('throne_raid',b.client.calls);self.assertEqual(self.raid()['phase'],'fighting')
    def test_no_identity_no_order(self):
        t=self.to_fighting();b,tc=self.bridge();(b.root/'post-identity.txt').unlink()
        self.sync(b,tc);self.assertEqual(b.files['emperor-raid-request.txt'],'')
    def test_sacked_line(self):
        import city_notices
        t=self.to_fighting();self.host.settle(t+SIEGE);b,tc=self.bridge();self.sync(b,tc)
        self.assertEqual([e[3] for e in city_notices.state(b)['log'] if e[1]==7],['황제군이 도시를 약탈하고 물러났습니다. 황제의 분노가 조금 가라앉았습니다.'])
        self.assertEqual(b.files['emperor-raid-request.txt'],'ab'*32+' 0 1 32 2\n')
    def test_scoreboard_file_names_the_players(self):
        import throne_client as tc
        rows=[dict(city='player2',stage=5,winner=True,known=True,successes=5,failures=3,coup_total=412600,gift_total=18400,raids=1,tributes=1,paranoia=50,reached=9),
              dict(city='player1',stage=1,winner=False,known=False)]
        text=tc.score_file(dict(scoreboard=rows),dict(player1='Kim',player2='Lee'),'player1').splitlines()
        self.assertEqual(text[0],'title\t황위 쟁탈전 종료');self.assertIn('Lee 총독이',text[1])
        self.assertEqual(text[2].split('\t'),['row','1','Lee','5/5','5 / 3','412,600','18,400','1 / 1','50','1','0'])
        self.assertEqual(text[3].split('\t'),['row','2','Kim','1/5','-','-','-','-','-','0','1'])
        self.assertEqual(tc.score_file(dict(scoreboard=None),{},'player1'),'')

import test_throne_room_flow as flow

@unittest.skipUnless(flow.DATA and flow.PROJECT.is_file() and flow.native_library(1),'needs AUGUSTUS_C3_DATA and the real post_* C library: '+flow._why)
class ThroughTheRoom(flow.RoomFlow):
    """The same course through the real room server (TCP), the real bridges (game_bridge.Bridge.step) and the real C
    money mailbox, as in test_throne_room_flow. Stand-ins: the engine process (its expedition file is written here),
    the clock reports, the draw of the activating coup, and paranoia 100 (test input)."""
    test_spend_end_refund_save_reload_and_handover=None;test_refund_after_end_continues_across_handover_and_lost_ack=None
    def raid(self,room,city):
        _,st=self.spend_states(room);return st['players'][city]['secret']['expedition'],st['players'][city]['secret']['paranoia']
    def test_arrival_report_tribute_and_withdrawal(self):
        flow.os.environ['AUGUSTUS_C3_DATA']=flow.DATA
        a=self.make_room('room-raid');names=['player1','player2','player3','player4']
        bridges={c:self.bridge(a,i,c) for i,c in enumerate(names)}
        self.start(a,bridges);self.clock(a,bridges,50)
        p3=bridges['player3'];self.draws+=[9999];self.command(p3,'coup');self.command(p3,'go');self.pump(bridges)   # wakes the emperor (fails)
        p1=bridges['player1'];self.fixture(a,'player1',paranoia=100)
        self.pump(bridges,rounds=2)
        e,_=self.raid(a,'player1');self.assertEqual((e['phase'],e['count']),('preparing',1))       # on the march
        box=lambda b:(b.root/'throne-box.txt').read_text(encoding='utf8')
        self.assertIn('march\t황제군이 오고 있습니다',box(p1));self.assertNotIn('march\t',box(bridges['player2']))
        self.assertEqual((p1.root/'emperor-raid-request.txt').read_text(),'')
        self.pump({'player1':p1},rounds=1)
        self.assertIn('\t황제의 징벌 원정\t',(p1.root/'throne-events.txt').read_text(encoding='utf8'))          # this player's own warning
        self.assertNotIn('징벌 원정',(bridges['player2'].root/'throne-events.txt').read_text(encoding='utf8'))
        before=self.cities['player1'].treasury                                                                       # on the march: the tribute turns them back
        self.command(p1,'tribute');self.assertIn('row\t공물\t3,000 Dn',(p1.root/'throne-dialog.txt').read_text(encoding='utf8'))
        self.command(p1,'go');self.pump(bridges)
        e,paranoia=self.raid(a,'player1')
        self.assertEqual((e['phase'],e['result'],paranoia),('cooldown','tribute',20));self.assertEqual(self.cities['player1'].treasury,before-3000)
        self.assertEqual((p1.root/'emperor-raid-request.txt').read_text().split()[2:],['1','32','2'])               # that number is called back
        self.assertEqual((p1.root/'emperor-raid-request.txt').read_text().split()[:2],(p1.root/'post-identity.txt').read_text().split())
        self.clock(a,bridges,e['deadline_tick']);self.fixture(a,'player1',paranoia=100);self.pump(bridges,rounds=2)   # after the cooldown, at the maximum again (test input)
        e,_=self.raid(a,'player1');self.assertEqual((e['phase'],e['count']),('preparing',2))
        self.clock(a,bridges,e['deadline_tick']);self.pump(bridges,rounds=2)                                         # not paid this time: they arrive and attack
        e,_=self.raid(a,'player1');self.assertEqual(e['phase'],'arrived')
        self.assertEqual((p1.root/'emperor-raid-request.txt').read_text().split()[2:],['2','48','1'])               # count size attack
        (p1.root/'emperor-raid.txt').write_text('2 1 48 0 40\n');self.pump({'player1':p1},rounds=2)                 # the engine: they are here
        e,_=self.raid(a,'player1');self.assertEqual(e['phase'],'fighting');self.assertNotIn('march\t',box(p1))
        (p1.root/'emperor-raid.txt').write_text('2 3 48 48 0\n');self.pump({'player1':p1},rounds=2)                 # beaten
        e,paranoia=self.raid(a,'player1');self.assertEqual((e['result'],paranoia),('defeated',75))
        _,st=self.spend_states(a);self.assertTrue(all(p['secret']['expedition']['count']==0 for c,p in st['players'].items() if c!='player1'))

if __name__=='__main__':unittest.main()
