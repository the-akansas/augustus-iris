"""28차: one silent guest leaves the game; the host stops itself only when no guest answers."""
import sqlite3,sys,unittest
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'Augustus'))
import lobby,migration,recovery_group
class Fake:
 started=True
 def __init__(self,seen):self.now=1000.0;self.presence={c:(t,True) for c,t in seen.items()};self.progress={};self.left=[]
 def clock(self):return self.now
 def depart(self,db,token,city,timed_out=False,removed=False):self.left.append(city);db.execute('INSERT INTO departed_invite VALUES(?)',(token,))
class SilentGuest(unittest.TestCase):
 def room(self,cities,seen):
  db=sqlite3.connect(':memory:');db.row_factory=sqlite3.Row;self.addCleanup(db.close)
  db.executescript('CREATE TABLE lobby_invite(token TEXT,city TEXT);CREATE TABLE departed_invite(token TEXT);CREATE TABLE succession(city TEXT PRIMARY KEY,save_id INTEGER);CREATE TABLE authority_fenced(value INTEGER);CREATE TABLE joint_save(id INTEGER,state TEXT)')
  for c in cities:db.execute('INSERT INTO lobby_invite VALUES(?,?)',('t'+c,c))
  for c in cities[1:]:db.execute('INSERT INTO succession VALUES(?,1)',(c,))
  return db,Fake(seen)
 def run_check(self,db,room):
  with patch.object(recovery_group,'plan',lambda *a,**k:{'candidate':'b'}),patch.object(migration,'fence',lambda r,d:d.execute('INSERT INTO authority_fenced VALUES(1)')):
   try:lobby.Lobby.expire_guests(room,db);return 'playing'
   except ValueError as e:return str(e)
 def test_one_guest_gone_others_answer(self):
  db,room=self.room(['a','b','c','d'],{'b':960,'c':999,'d':999.5})
  self.assertEqual(self.run_check(db,room),'playing');self.assertEqual(room.left,['b'])
  self.assertIsNone(db.execute('SELECT 1 FROM authority_fenced').fetchone())
 def test_nobody_answers_host_is_cut_off(self):
  db,room=self.room(['a','b','c','d'],{'b':960,'c':961,'d':962})
  self.assertEqual(self.run_check(db,room),'host fenced');self.assertEqual(room.left,[])
 def test_two_players_keep_the_old_rule(self):
  db,room=self.room(['a','b'],{'b':960})
  self.assertEqual(self.run_check(db,room),'host fenced')
 def test_answer_of_a_player_who_already_left_does_not_count(self):
  db,room=self.room(['a','b','c'],{'b':960,'c':999})
  db.execute("INSERT INTO departed_invite VALUES('tc')")
  self.assertEqual(self.run_check(db,room),'host fenced')
if __name__=='__main__':unittest.main()
