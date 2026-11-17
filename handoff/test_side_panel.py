"""25차: left side panel data (trade and army tabs) published by the bridges."""
import sqlite3,sys,time,unittest,importlib.util
from pathlib import Path
H=Path(__file__).resolve().parent;sys.path.insert(0,str(H.parent/'Augustus'))
import player_fleet,fleet_bridge,army_bridge
spec=importlib.util.spec_from_file_location('grace',H/'test_shipment_grace.py');grace=importlib.util.module_from_spec(spec);spec.loader.exec_module(grace)
class Bridge:
 def __init__(s):s.files={};s.client=type('C',(),{'city':'a'})();s.city_names={'a':'카푸아','b':'타렌툼'};s.route_player_colors={'a':0,'b':1}
 def write_changed(s,name,text):s.files[name]=text
class SideTests(unittest.TestCase):
 def test_post_status_and_file(self):
  t=grace.GraceTests();t.setUp();t.order(1,5);t.order(6,6);t.at(1000,{1:5},inbound=3)
  st=player_fleet.post_status(t.db,'a')
  self.assertEqual((st[0]['loaded'],st[0]['inbound'],st[0]['away'],len(st[0]['queue'])),(5,3,0,2))
  self.assertEqual(st[0]['leave'],2400) # waiting on carts: only the 3-month cap applies
  t.at(1300,{1:5,6:6});self.assertEqual(player_fleet.post_status(t.db,'a')[0]['leave'],100) # all loaded: two days
  b=Bridge();fleet_bridge.side_trade(b,dict(post_status=player_fleet.post_status(t.db,'a'),rows=[],agreements={'agreements':[]}))
  self.assertEqual(b.files['side-trade.txt'].splitlines(),['P 11 2 11 0 100 0','Q 1 1 1 5','Q 2 1 6 6','C 0 0'])
 def test_army_lines(self):
  b=Bridge();b.root=Path('.');b.army_poll_next=0
  rows=[dict(id='x',phase='travelling',incoming=True,origin='b',destination='a',role=2,remaining_ticks=None),
        dict(id='y',phase='stationed',incoming=False,origin='a',destination='b',role=1,current='{}',token=0)]
  b.client.call=lambda op,**k:[] if op=='army_order_status' else rows
  from unittest.mock import patch
  import army_seal
  with patch.object(army_seal,'SEALED',False):army_bridge.poll(b)   # the lines for when dispatch is unsealed again; sealed, nothing is asked
  self.assertEqual(b.files['side-army.txt'].splitlines(),['1\t1\t타렌툼 공격군\t이동 중','0\t-1\t타렌툼 지원군\t주둔 중'])
  b.files={};b.army_poll_next=0;b.client.call=lambda op,**k:self.fail('asked '+op)
  army_bridge.poll(b);self.assertEqual(b.files['side-army.txt'],'')

class PlayersTabTests(unittest.TestCase):
 def test_left_reconnecting_late_and_ok(self):
  import game_bridge
  slot=lambda city,**k:dict(dict(city=city,name='id-'+city,claimed=True,online=True,departed=False,dormant=False,ticks=1000,age_ms=0,engine_state='active',player_color=0,contact_age_ms=0,rtt_ms=40),**k)
  state=dict(host_city='a',slots=[slot('a'),slot('b',ticks=1300,player_color=1),slot('c',online=False,player_color=2),slot('d',departed=True,claimed=True,player_color=3),slot('e',claimed=False)])
  rows=[r.split('\t') for r in game_bridge.side_players(state,'a',1000,{}).splitlines()]
  self.assertEqual([r[0] for r in rows],['0','1','2','3'])
  self.assertEqual(rows[0][2:5],['1','1','id-a'])
  self.assertTrue(all(len(r)==9 for r in rows));self.assertEqual(rows[1][8],'b')
 def test_room_rules_reach_the_player(self):
  import game_bridge
  self.assertEqual(game_bridge.Bridge.error_message('판매자의 보유 물품을 선택하세요.'),'판매자의 보유 물품을 선택하세요.')
  self.assertIn('잠시 후',game_bridge.Bridge.error_message('Traceback internal'))

if __name__=='__main__':unittest.main()
