import sys,sqlite3,unittest,tempfile,json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'Augustus'))
import live_trade,goods_live,cash_live,fleet_map,city_notices,joint_save
from fleet_bridge import receiver_visible
class TimelineTests(unittest.TestCase):
 def setUp(self):
  self.db=sqlite3.connect(':memory:');self.db.row_factory=sqlite3.Row;live_trade.initialize(self.db);joint_save.initialize(self.db)
  self.t=dict(id=1,request='a'*32,sender='a',receiver='b',resource=11,quantity=2,money=0,kind='gift',state='departing')
  self.db.execute('INSERT INTO live_transfer(id,request,sender,receiver,resource,quantity,money,kind,state) VALUES(?,?,?,?,?,?,?,?,?)',tuple(self.t.values()))
  self.db.execute('INSERT INTO goods_motion(id,route) VALUES(1,2)');self.db.commit()
  self.room=SimpleNamespace(grant=500,progress={'a':(100,0),'b':(100,0)},active_cities=lambda db:['a','b'])
  self.arrivals=[];self.ledger=SimpleNamespace(_contract=lambda city,tid:dict(phase='travel',received=False),arrived=lambda city,tid:self.arrivals.append((city,tid)))
 def tearDown(self):self.db.close()
 def request(self,city,op,**kw):
  with patch.object(cash_live,'sync'):
   return goods_live.trade(self.room,self.db,city,dict(op=op,**kw),self.t,self.ledger)
 def depart(self):return self.request('a','live_departed',departure=[11,2,2])
 def test_one_timeline_gates_spawn_notification_and_receipt(self):
  self.depart();self.t['state']='travelling'
  for tick,expected in [(100,0),(196,500),(291,994),(292,1000),(900,1000)]:
   self.room.progress={'a':(tick,0),'b':(tick,0)}
   row=dict(self.t,**goods_live.map_motion(self.room,self.db,self.t),fleet=dict(assigned=1,home=0,building=59,generation=1))
   self.assertEqual(row['map_progress'],expected)
   self.assertEqual(receiver_visible(row),tick>=292)
   before=len(self.arrivals);self.request('b','live_arrived',building=59)
   self.assertEqual(len(self.arrivals)>before,tick>=292)
   with tempfile.TemporaryDirectory(dir=Path(__file__).resolve().parent) as temp:
    root=Path(temp);(root/'empire-player-slots.txt').write_text('1\ta\tA\n2\tb\tB\n')
    written={};b=SimpleNamespace(root=root,client=SimpleNamespace(city='b',session='test'),write_changed=lambda k,v:written.update({k:v}))
    fleet_map.publish(b,[row]);self.assertEqual(int(written['empire-fleet.txt'].splitlines()[1].split()[9]),expected)
    city_notices.trade(b,[row]);events=city_notices.state(b)['events'];self.assertEqual(any('도착했습니다' in e[6] for e in events),tick>=292)
 def test_duplicate_departure_pause_and_restore(self):
  self.depart();self.room.progress={'a':(196,0),'b':(100,0)}
  self.assertEqual(goods_live.map_motion(self.room,self.db,self.t)['map_progress'],0)
  for _ in range(30):self.depart()
  self.assertEqual(tuple(self.db.execute('SELECT map_depart_tick,map_arrive_tick FROM goods_motion').fetchone()),(100,292))
  restored=sqlite3.connect(':memory:');restored.row_factory=sqlite3.Row;self.db.backup(restored)
  self.room.progress={'a':(196,0),'b':(196,0)}
  self.assertEqual(goods_live.map_motion(self.room,restored,self.t)['map_progress'],500);restored.close()
 def test_checkpoint_keeps_timeline_and_reads_legacy(self):
  import cash_snapshot,copy
  from trade_post_ledger import Ledger
  ledger=Ledger(':memory:',['a','b']);db=ledger.db;live_trade.initialize(db)
  ledger.bind('a','b',11,1);ledger.bind('b','a',22,1);ledger.offer('a','a'*32,'b',11,2,0)
  db.execute('INSERT INTO live_transfer(id,request,sender,receiver,resource,quantity,money,kind,state) VALUES(?,?,?,?,?,?,?,?,?)',tuple(self.t.values()))
  db.execute("INSERT INTO cash_scope VALUES(?)",('b'*64,));db.execute('INSERT INTO cash_transfer VALUES(1,?)',('a'*32,))
  db.execute('INSERT INTO goods_motion(id,route,departed,map_depart_tick,map_arrive_tick) VALUES(1,2,1,100,292)');db.commit()
  data=cash_snapshot.current(db);cash_snapshot.validate(data,['a','b'])
  restored=sqlite3.connect(':memory:');restored.row_factory=sqlite3.Row;live_trade.initialize(restored);cash_snapshot.restore(restored,data,['a','b'])
  self.assertEqual(tuple(restored.execute('SELECT map_depart_tick,map_arrive_tick FROM goods_motion').fetchone()),(100,292));restored.close()
  legacy=copy.deepcopy(data);legacy['tables']['goods_motion'][0].pop('map_depart_tick');legacy['tables']['goods_motion'][0].pop('map_arrive_tick');cash_snapshot.validate(legacy,['a','b'])
  self.assertEqual(legacy['tables']['goods_motion'][0]['map_arrive_tick'],0)
  bad=copy.deepcopy(data);bad['tables']['goods_motion'][0]['map_arrive_tick']=99
  with self.assertRaises(ValueError):cash_snapshot.validate(bad,['a','b'])
  ledger.close()
 def test_wrong_city_cannot_start_or_arrive(self):
  with self.assertRaises(ValueError):self.request('b','live_departed',departure=[11,2,2])
  self.assertEqual(self.db.execute('SELECT departed FROM goods_motion').fetchone()[0],0)
  self.depart()
  with self.assertRaises(ValueError):self.request('a','live_arrived',building=59)
if __name__=='__main__':unittest.main()
