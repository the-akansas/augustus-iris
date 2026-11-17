"""City-visit permission (19차): viewer side list, instant local update."""
import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'Augustus'))
import participant_admin
class B:
    def __init__(s):s.files={};s.client=type('C',(),{'city':'player2'})()
    def write_changed(s,n,t):s.files[n]=t
def state(rows):
    slots=[dict(city=c,claimed=True,name=c,city_name=c,generation='g'+c,name_id=i,contact_age_ms=0,rtt_ms=5) for i,c in ((2,'player1'),(1,'player2'),(4,'player3'))]
    return dict(slots=slots,host_city='player1',observe_permissions=rows)
def test_viewer_sees_who_blocks_them():
    b=B();participant_admin.publish(b,state([dict(owner='player1',viewer='player2',allowed=0,revision=1)]))
    assert b.files['observe-allowed.txt'].split('\n')==['2 0','4 1']
def test_owner_change_shows_at_once():
    b=B();participant_admin.publish(b,state([]))
    participant_admin.apply_local(b,'player3',False,1)
    row=[l for l in b.files['observe-permissions.txt'].split('\n') if l.startswith('player3')][0].split('\t')
    assert row[3:]==['0','1']
if __name__=='__main__':
    test_viewer_sees_who_blocks_them();test_owner_change_shows_at_once();print('ok')
