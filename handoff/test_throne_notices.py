"""황위 시험 규칙 v1: public coup notices and the failure rise (user decision 2026-11-13).

  * The first coup ever is announced (popup, confirm-and-close), naming no one; its result is not part of it.
  * After that a success is not announced, except a stage-4 success ("황궁 내부 장악", popup). A failure is announced
    as a fanfare line in the notice tab (no popup), naming no one, and raises EVERY player's paranoia by 5 at once
    (the failing player too, so nobody can tell). The end of the trial is a fanfare line too.
  * A restore-pending record (the host cannot see it) takes the failures it missed once, when it is handed in.
Runs the real host code (throne_play, throne_state, throne_events) and the real bridge notice code (throne_client.fanfare,
city_notices). City money: the Python stand-in of test_throne_trial (the money path itself is covered elsewhere)."""
import json,sys,unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parent))
from test_throne_trial import B,CITIES,MONTH,RULES,Base,FakeClient,SimpleBridge,save,set_secret,restore_replica,activate
import throne_state as ts,throne_events as te,throne_play as tp

class Notices(Base):
    def kinds(self,host=None):return [n['kind'] for n in (host or self.host).state()['notices']]
    def paranoia(self,host=None):return {c:p['secret']['paranoia'] for c,p in (host or self.host).state()['players'].items() if 'secret' in p}

    def test_first_coup_is_announced_without_its_result(self):
        self.coup('player1',5000,0)                       # success
        self.assertEqual(self.kinds(),['coup_first'])
        self.assertEqual(self.paranoia(),dict(player1=20,player2=10,player3=10))   # floors only, no +5
        n=te.public_status(self.host.db,B)['notices'];self.assertEqual([(x['title'],x['popup']) for x in n],[('쿠데타 시도 발생',True)])
        self.assertNotIn('성공',n[0]['body'])

    def test_first_coup_failing_is_one_confirm_window(self):
        # 2026-11-14: not two windows: one notice says the coup was tried and failed
        self.coup('player1',5000,9999)
        self.assertEqual(self.kinds(),['coup_first_failed'])
        n=te.public_status(self.host.db,B)['notices'];self.assertEqual([(x['title'],x['popup']) for x in n],[('쿠데타 시도 발생',True)])
        self.assertIn('실패',n[0]['body'])
        self.assertEqual(self.paranoia(),{c:15 for c in CITIES})

    def test_later_success_is_silent_and_failure_raises_everyone(self):
        activate(self.host,'player3',cities=self.cities)  # failing first coup
        before=self.paranoia();self.assertEqual(before,{c:15 for c in CITIES})
        self.coup('player1',5000,0)                       # success: nothing public
        self.assertEqual(self.kinds(),['coup_first_failed'])
        self.assertEqual(self.paranoia(),dict(before,player1=20))   # its new floor 20 only
        self.coup('player2',5000,9999)                    # failure: everyone +5, the failing player too
        self.assertEqual(self.kinds(),['coup_first_failed','coup_failed'])
        n=te.public_status(self.host.db,B)['notices'][-1];self.assertEqual((n['title'],n['popup']),('쿠데타 실패',True))   # 2026-11-14: a confirm window, not a line
        self.assertEqual(self.paranoia(),dict(player1=25,player2=20,player3=20))
        for _ in range(3):self.host.settle(0)             # polls and resends never add it again
        self.assertEqual(self.paranoia(),dict(player1=25,player2=20,player3=20))

    def test_rise_stops_at_the_maximum(self):
        activate(self.host,'player3',cities=self.cities)
        set_secret(self.host,'player1',paranoia=98)
        self.coup('player2',5000,9999);self.assertEqual(self.paranoia()['player1'],100)

    def test_stage_four_success_popup_and_end_line(self):
        activate(self.host,'player3',cities=self.cities)
        set_secret(self.host,'player1',stage=3,paranoia=40)
        self.coup('player1',40000,0,tick=0)               # stage 4 done
        self.assertEqual(self.kinds()[-1],'final_stage')
        n=te.public_status(self.host.db,B)['notices'][-1];self.assertEqual((n['title'],n['popup']),('황궁 내부 장악',True))
        self.coup('player1',80000,0,tick=2*MONTH)         # the last stage: the end
        self.assertEqual(self.kinds()[-1],'throne_taken')
        n=te.public_status(self.host.db,B)['notices'][-1];self.assertEqual((n['popup'],n['line']),(False,'황제 폐위, 황위 쟁탈전 종료'))
        self.assertEqual(self.kinds().count('final_stage'),1)

    def test_only_the_first_stage_four_success_of_the_room_is_announced(self):
        activate(self.host,'player3',cities=self.cities)
        set_secret(self.host,'player1',stage=3,paranoia=40);set_secret(self.host,'player2',stage=3,paranoia=40)
        self.coup('player1',40000,0,tick=0);self.assertEqual(self.kinds().count('final_stage'),1)
        self.coup('player2',40000,0,tick=0);self.assertEqual(self.kinds().count('final_stage'),1)   # the second one: silent
        self.assertEqual(te.public_status(self.host.db,B)['leading'],4)

    def test_notices_name_no_one(self):
        activate(self.host,'player3',cities=self.cities)
        set_secret(self.host,'player1',stage=3,paranoia=40);self.coup('player1',40000,0)
        self.coup('player2',5000,9999)
        public=json.dumps(te.public_status(self.host.db,B)['notices'],ensure_ascii=False)
        for c in CITIES:self.assertNotIn(c,public)
        st=self.host.state();ids={n['id'] for n in st['notices']}
        for p in st['players'].values():
            for e in p['secret']['spends']:self.assertNotIn(tp.contract_id(e['request']),ids)   # not the ledger id

    def test_pending_record_takes_missed_failures_once(self):
        activate(self.host,'player3',cities=self.cities)
        saved=save(self.host,1,0,self.cities)
        new=restore_replica(self.tmp.name,saved,self.host);self.addCleanup(new.db.close)
        for c in ('player1','player3'):o=saved['openings'][c];te.hand_in(new.db,B,c,o['secret'],o['nonce'],0)
        new.db.commit();self.cities.load(saved['cities'])
        self.draws.queue.append(9999);out=new.spend('player1','coup',5000,tick=0);self.cities.run(new,'player1');new.settle(0)
        self.assertEqual(self.paranoia(new),dict(player1=20,player3=20))   # player2 pending: not visible
        o=saved['openings']['player2'];te.hand_in(new.db,B,'player2',o['secret'],o['nonce'],0);new.db.commit()
        self.assertEqual(self.paranoia(new)['player2'],20)                             # 15 at the save + the missed 5
        for _ in range(2):new.settle(0)
        self.assertEqual(self.paranoia(new),{c:20 for c in CITIES})

    def test_bridge_shows_failures_as_confirm_windows_not_lines(self):
        import throne_client,city_notices
        activate(self.host,'player3',cities=self.cities)
        b=SimpleBridge(Path(self.tmp.name)/'b1',FakeClient(self.host,'player1'));b.root.mkdir();b.joined=True;b.config=dict(session='s1')
        def feed():throne_client.fanfare(b,te.public_status(self.host.db,B));return b.files.get('city-notices.txt','')
        self.assertEqual(feed(),'0\n')                    # a new notice record: the failure already there is not replayed
        self.coup('player2',5000,9999)
        self.assertEqual(feed(),'0\n')                    # 2026-11-14: a failure is a confirm window now, never a line in the notice tab
        self.assertEqual(sum(1 for e in city_notices.state(b)['log'] if e[1]==7),0)
        popups=[n for n in te.public_status(self.host.db,B)['notices'] if n['popup']]
        self.assertEqual([n['title'] for n in popups],['쿠데타 시도 발생','쿠데타 실패'])   # these reach throne-events.txt (game_bridge)

    def test_rules_carry_the_failure_rise(self):
        self.assertEqual(RULES['failure_paranoia'],5)
        with self.assertRaises(ValueError):ts.validate_rules(dict(RULES,failure_paranoia=51))   # the editor's range is 0..50

if __name__=='__main__':unittest.main()
