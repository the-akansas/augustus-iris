"""Race for the Throne stays inside throne rooms (user request 2026-11-13: nothing that works only in the throne mode may
show up on another map).

A free-build room (scenarios/unified-sandbox, 4 players) is run end to end with the same real parts as
test_throne_room_flow (room server, TCP, game_bridge.Bridge, the C money mailbox). Checked for every player:
  * the files the game draws throne things from are empty: throne-hud.txt (the "황제 편집증" box), throne-actions.txt
    (its buttons), throne-events.txt (coup popups); no throne line (notice kind 7) in the notice cards or the log;
  * the room's public status has no throne part; the throne operations are refused; a throne command sent anyway
    changes nothing and charges nothing; a joint save has no throne record;
  * a mailbox folder left from an earlier throne game (stale box, buttons, popup, notice line) is cleared on joining.
Needs the same environment as test_throne_room_flow (AUGUSTUS_C3_DATA; a C compiler or AUGUSTUS_POST_NATIVE_DIR)."""
import json,sys,unittest
from contextlib import closing
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parent))
import test_throne_room_flow as F

FREE=F.ROOT/'Augustus/scenarios/unified-sandbox/scenario.json'
THRONE_FILES=('throne-hud.txt','throne-actions.txt','throne-events.txt','throne-box.txt','throne-dialog.txt','throne-score.txt')

@unittest.skipUnless(F.DATA and FREE.is_file() and F.native_library(1),'needs AUGUSTUS_C3_DATA and the real post_* C library: '+F._why)
class FreeBuildRoom(F.RoomFlow):
    def setUp(self):
        super().setUp()
        p=patch.object(F,'PROJECT',FREE);p.start();self.addCleanup(p.stop)
    def text(self,b,name):
        try:return (b.root/name).read_text(encoding='utf8')
        except OSError:return ''
    def no_throne(self,bridges):
        for c,b in bridges.items():
            for name in THRONE_FILES:self.assertEqual(self.text(b,name).strip(),'',f'{c} {name}')
            notices=self.text(b,'city-notices.txt').splitlines()
            kinds=[l.split()[1] for l in notices[1::2]] if notices else []
            self.assertNotIn('7',kinds,c)
            log=self.text(b,'city-notice-log.txt').splitlines()
            self.assertFalse(any(l.split()[1:2]==['7'] for l in log[1::2]),c)
            hud=''.join(self.text(b,n) for n in ('throne-hud.txt','city-notices.txt','city-notice-log.txt'))
            for word in ('편집증','쿠데타','황위','황제 폐위'):self.assertNotIn(word,hud,c)

    def test_free_build_room_shows_nothing_of_the_throne(self):
        a=self.make_room('free-a')
        names=['player1','player2','player3','player4']
        # player2's mailbox folder still holds files from an earlier throne game (not reset): box, buttons, popup, line
        stale=self.tmp/'player2'/a['root'].name;stale.mkdir(parents=True)
        (stale/'throne-hud.txt').write_text('황제 편집증\n내 편집증 40/100\n',encoding='utf8')
        (stale/'throne-actions.txt').write_text('coup\t쿠데타 지원\t1\n',encoding='utf8')
        (stale/'throne-events.txt').write_text('0'*32+'\t쿠데타 시도 발생\t누군가\n',encoding='utf8')
        (stale/'city-notice-state.json').write_text(json.dumps(dict(sequence=5,seen=['throne:'+'0'*32],events=[[5,7,1,0,0,0,'쿠데타 실패 · 모든 총독 편집증 +5']],
            read=[],pending=[],expire={},log=[[5,7,1,'쿠데타 실패 · 모든 총독 편집증 +5']]),ensure_ascii=False),encoding='utf8')
        bridges={c:self.bridge(a,i,c,again=(c=='player2')) for i,c in enumerate(names)}
        self.start(a,bridges);self.clock(a,bridges,1600);self.pump(bridges)
        self.no_throne(bridges)
        host=bridges['player1']
        self.assertIsNone(host.client.call('lobby_view',invite=host.config['invite']).get('throne'))
        for op,args in (('throne_mine',{}),('throne_quote',dict(kind='coup',amount=5000,funds=FUNDS)),
                        ('throne_spend',dict(request='1'*32,kind='coup',amount=5000,funds=FUNDS,expect=[])),
                        ('throne_hand_in',dict(secret={},nonce='0'*64))):
            with self.assertRaises(Exception,msg=op):host.client.call(op,**args)
        # a throne command sent anyway (no box exists to send it): nothing shown, nothing charged
        before={c:self.cities[c].treasury for c in names}
        try:self.command(bridges['player3'],'coup');self.command(bridges['player3'],'go')
        except Exception:pass
        self.pump(bridges);self.no_throne(bridges)
        self.assertEqual({c:self.cities[c].treasury for c in names},before)
        with closing(a['room'].coordinator.connect()) as db:
            self.assertFalse(db.execute("SELECT 1 FROM sqlite_master WHERE name='post_contract'").fetchone() and
                             db.execute("SELECT 1 FROM post_contract WHERE route='debit'").fetchone())
        # a joint save carries no throne record
        self.joint_save(a,bridges)
        with closing(a['room'].coordinator.connect()) as db:
            self.assertIsNone(db.execute('SELECT 1 FROM joint_throne').fetchone())
        self.pump(bridges);self.no_throne(bridges)

for _name in [n for n in dir(F.RoomFlow) if n.startswith('test_')]:setattr(FreeBuildRoom,_name,None)   # run those in their own file
FUNDS=F.FUNDS

if __name__=='__main__':unittest.main()
