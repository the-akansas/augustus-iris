"""Pings in the waiting room (user 2026-11-13): the host sees every guest's ping; a guest sees the other guests' pings
and its own ping to the host on the host's row, but never its own ping on its own row."""
import sys,unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'Augustus'))
import lobby_map

def slot(city,name,rtt):return dict(city=city,name=name,claimed=True,ready=False,online=True,contact_age_ms=100,rtt_ms=rtt,player_color=0)
STATE=dict(host_city='p1',slots=[slot('p1','방장',0),slot('p2','둘',401),slot('p3','셋',402)],
           empire_map=[dict(id=c,name=c,x=10*i,y=10*i) for i,c in enumerate(('p1','p2','p3'),1)])
class B:
    def __init__(self,city):self.joined=True;self.client=type('C',(),dict(city=city))()
def labels(city):
    lines=lobby_map.encode(B(city),STATE).split('\n')[2:];return {lines[i+3]:lines[i+2] for i in range(0,9,4)}

class Ping(unittest.TestCase):
    def test_host_sees_every_guest(self):
        got=labels('p1');self.assertNotIn('ms',got['p1']);self.assertIn('401ms',got['p2']);self.assertIn('402ms',got['p3'])
    def test_guest_never_sees_its_own_ping_on_its_row(self):
        got=labels('p2')
        self.assertNotIn('ms',got['p2'])                   # own row: no ping
        self.assertIn('401ms',got['p1'])                   # own ping to the host, on the host's row
        self.assertIn('402ms',got['p3'])                   # the other guest's ping
    def test_roster_uses_the_same_rule(self):
        src=(ROOT/'Augustus/game_bridge.py').read_text(encoding='utf8')
        self.assertIn("elif slot['city']!=state['host_city'] and not mine:",src)

if __name__=='__main__':unittest.main()
