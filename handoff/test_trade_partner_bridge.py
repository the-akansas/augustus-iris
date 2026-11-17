import sys,unittest
from pathlib import Path
from types import SimpleNamespace
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'Augustus'))
import trade_partner_bridge as tp

def T(id,s,r,res,qty,money,state,**k):return dict(id=id,sender=s,receiver=r,resource=res,quantity=qty,money=money,kind='sale' if money and res else 'gift',state=state,**k)
def A(id,proposer,seller,buyer,state,transfer=None,qty=5,money=50,repeat=1,revision=0,cycle=0):
    return dict(id=id,proposer=proposer,seller=seller,buyer=buyer,resource=15,quantity=qty,money=money,repeat=repeat,state=state,post=11,generation=1,cycle=cycle,transfer=transfer,revision=revision,allow_partial=0)
FLEET=dict(building=11,generation=1,assigned=1,home=0)

class DealTests(unittest.TestCase):
    def test_incoming_offer_needs_answer_and_outgoing_can_cancel(self):
        d=tp.deals('a',[T(1,'b','a',19,8,320,'offered'),T(2,'a','b',1,10,120,'offered')],[])
        got={x[3]:x for x in d}
        self.assertEqual((got[1][1],got[1][9],got[1][7]),(0,3,0))
        self.assertEqual((got[2][1],got[2][9],got[2][7]),(2,2,1))
    def test_phases_follow_the_caravan(self):
        rows=[T(1,'a','b',15,5,50,'collecting',fleet=FLEET),T(2,'a','b',15,5,50,'departing',fleet=FLEET),
              T(3,'a','b',15,5,50,'travelling',fleet=FLEET,map_arrived=False),T(4,'b','a',11,4,120,'travelling',fleet=FLEET,map_arrived=True),
              T(5,'b','a',11,4,120,'finished',fleet=FLEET)]
        self.assertEqual([x[8] for x in sorted(tp.deals('a',rows,[]),key=lambda x:x[3])],[0,1,2,3,4])
    def test_terminal_rows_leave_after_caravan_is_home(self):
        home=dict(FLEET,home=1)
        self.assertEqual(tp.deals('a',[T(1,'a','b',15,5,50,'finished',fleet=home),T(2,'a','b',0,0,100,'finished')],[]),[])
    def test_linked_transfer_is_shown_once_under_its_contract(self):
        a=A(7,'a','a','b','active',transfer=3,cycle=4)
        d=tp.deals('a',[T(3,'a','b',15,5,50,'travelling',fleet=FLEET)],[a])
        self.assertEqual(len(d),1);self.assertEqual((d[0][2],d[0][3],d[0][9],d[0][11],d[0][8]),(1,7,2,4,2))
    def test_agreement_states(self):
        d=tp.deals('a',[], [A(1,'b','a','b','offered',qty=8,money=320),A(2,'a','a','b','offered'),A(3,'a','a','b','paused'),A(4,'a','a','b','active'),A(5,'a','a','b','stopped'),A(6,'c','c','d','active')])
        got={x[3]:(x[1],x[9]) for x in d}
        self.assertEqual(got,{1:(0,7),2:(2,2),3:(3,10),4:(1,2)})
    def test_cash_gift_has_no_caravan_phase(self):
        d=tp.deals('a',[T(1,'b','a',0,0,500,'offered')],[])
        self.assertEqual((d[0][1],d[0][8],d[0][9]),(0,-1,3))
    def test_status_text_is_single_line(self):
        self.assertNotIn('\n',tp.clean('a\nb\tc'))

class PartnerTests(unittest.TestCase):
    def test_partner_rows(self):
        routes=dict(links=[dict(a='a',b='b',proposer='a',state='active',request='x',revision=2),dict(a='a',b='c',proposer='c',state='offered',request='y',revision=1)],
                    posts=[dict(city='a',peer='b',building=11,generation=1,active=1),dict(city='b',peer='a',building=5,generation=1,active=0)])
        table=tp.deals('a',[T(1,'b','a',19,8,320,'offered'),T(2,'a','b',15,5,50,'travelling',fleet=FLEET)],[A(9,'a','a','b','active')])
        p=tp.partners('a',['c','a','b','d'],routes,table)
        self.assertEqual(p,[[2,'b',1,1,0,1,1,1,2],[3,'c',2,0,0,0,0,1,1],[4,'d',0,0,0,0,0,0,0]])
    def test_money_gift_is_not_a_partner_chore(self):
        table=tp.deals('a',[T(1,'b','a',0,0,500,'offered')],[])
        self.assertEqual(tp.partners('a',['a','b'],dict(links=[],posts=[]),table)[0][7],0)
    def test_publish_writes_both_files(self):
        written={};b=SimpleNamespace(client=SimpleNamespace(city='a'),write_changed=lambda k,v:written.update({k:v}))
        tp.publish(b,dict(rows=[T(1,'b','a',19,8,320,'offered')],agreements=dict(agreements=[]),routes=dict(links=[],posts=[]),route_roster=['a','b']))
        lines=written['trade-deals.txt'].splitlines()
        self.assertEqual(lines[0].split()[0::2],['1','1']);self.assertEqual(lines[1].split()[:4],['b','0','0','1']);self.assertEqual(len(lines),3)
        self.assertEqual(written['trade-partners.txt'].splitlines()[1].split(),['2','b','0','0','0','0','0','1','0'])
import city_notices,route_bridge
class NoticeCleanupTests(unittest.TestCase):
    def bridge(self):
        written={};b=SimpleNamespace(client=SimpleNamespace(city='a',session='s'),root=Path('/nonexistent'),write_changed=lambda k,v:written.update({k:v}))
        return b,written
    def test_contract_notice_leaves_once_post_is_built(self):
        b,w=self.bridge();link=dict(a='a',b='b',proposer='b',state='offered',request='x',revision=1)
        route_bridge.publish(b,dict(links=[link],posts=[]),['a','b'])
        self.assertEqual(len(b.city_notice_state['events']),1)
        route_bridge.publish(b,dict(links=[dict(link,state='active')],posts=[]),['a','b'])
        events=b.city_notice_state['events'];self.assertEqual(len(events),1);self.assertIn('건설',events[0][6])
        route_bridge.publish(b,dict(links=[dict(link,state='active')],posts=[dict(city='a',peer='b',building=9,generation=1,active=1)]),['a','b'])
        self.assertEqual(b.city_notice_state['events'],[])
    def test_trade_keeps_one_line_with_latest_stage(self):
        b,w=self.bridge();f=dict(building=11,generation=1,assigned=1,home=0)
        city_notices.trade(b,[]) # first poll is silent
        city_notices.trade(b,[dict(id=4,sender='a',receiver='b',resource=15,state='collecting',fleet=f)])
        city_notices.trade(b,[dict(id=4,sender='a',receiver='b',resource=15,state='finished',fleet=dict(f,home=1))])
        events=[e for e in b.city_notice_state['events'] if e[1]==1];self.assertEqual(len(events),1);self.assertIn('종료',events[0][6])
        self.assertEqual([e[1] for e in b.city_notice_state['events'] if e[1]==5],[5]) # plus the settlement result
class TransientNoticeTests(unittest.TestCase):
    def test_results_expire_but_stay_in_log(self):
        written={};b=SimpleNamespace(client=SimpleNamespace(city='a',session='s'),root=Path('/nonexistent'),write_changed=lambda k,v:written.update({k:v}))
        city_notices.trade(b,[])
        city_notices.trade(b,[dict(id=8,sender='a',receiver='b',resource=0,state='finished')])
        s=b.city_notice_state;self.assertEqual(len(s['events']),1)
        import time as _t
        real=_t.time
        try:
            city_notices.time.time=lambda:real()+city_notices.TRANSIENT_SECONDS+1
            city_notices.publish(b,s)
        finally:city_notices.time.time=real
        self.assertEqual(s['events'],[])
        log=written['city-notice-log.txt'].splitlines();self.assertEqual(log[0],'1');self.assertIn('송금',log[2])
class SettlementNoticeTests(unittest.TestCase):
    def run_trade(self,city,rows):
        b=SimpleNamespace(client=SimpleNamespace(city=city,session='s'),root=Path('/nonexistent'),city_names={'a':'카푸아','b':'타렌툼'},write_changed=lambda k,v:None)
        city_notices.trade(b,[])
        for r in rows:city_notices.trade(b,[r])
        return [e[6] for e in b.city_notice_state['events'] if e[1]==5]
    def test_sale_settlement_both_sides_once(self):
        t=dict(id=5,sender='a',receiver='b',resource=11,quantity=13,money=240,state='finished')
        self.assertEqual(self.run_trade('a',[t,t]),['정산 완료: 타렌툼에 대리석 13포대 판매 · 240 Dn 받음'])
        self.assertEqual(self.run_trade('b',[t]),['정산 완료: 카푸아에서 대리석 13포대 구매 · 240 Dn 지급'])
    def test_goods_gift_and_unfinished(self):
        t=dict(id=6,sender='a',receiver='b',resource=11,quantity=2,money=0,state='finished')
        self.assertEqual(self.run_trade('b',[dict(t,state='travelling'),t]),['선물 입고 완료: 카푸아에서 대리석 2포대'])
class PostFullNoticeTests(unittest.TestCase):
    def test_warning_stays_until_goods_can_leave(self):
        import tempfile
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);b=SimpleNamespace(client=SimpleNamespace(city='a',session='s'),root=root,write_changed=lambda k,v:None)
            city_notices.post_storage(b);self.assertFalse(hasattr(b,'city_notice_state') and b.city_notice_state['events'])
            (root/'post-blocked.txt').write_text('59 58 11 13\n59 58 19 2\n')
            for _ in range(3):city_notices.post_storage(b)
            s=b.city_notice_state;self.assertEqual(len(s['events']),1);e=s['events'][0]
            self.assertEqual(e[1:6],[6,59,59,58,1]);self.assertIn('빈 저장소가 없습니다',e[6]);self.assertIn(e[0],s['pending'])
            (root/'post-blocked.txt').write_text('garbage\n');city_notices.post_storage(b);self.assertEqual(len(s['events']),1)
            (root/'post-blocked.txt').write_text('');city_notices.post_storage(b);self.assertEqual(s['events'],[])
            (root/'post-blocked.txt').write_text('59 58 11 13\n');city_notices.post_storage(b);self.assertEqual(len(s['events']),1)
class DeclinedNoticeTests(unittest.TestCase):
    def test_declined_offer_tells_sender_once(self):
        b=SimpleNamespace(client=SimpleNamespace(city='a',session='s'),root=Path('/nonexistent'),city_names={'b':'타렌툼'},write_changed=lambda k,v:None)
        f=dict(building=11,generation=1,assigned=0,home=0);t=dict(id=7,sender='a',receiver='b',resource=11,quantity=2,money=240,state='rejected',fleet=f)
        city_notices.trade(b,[]);city_notices.trade(b,[t]);city_notices.trade(b,[t])
        texts=[e[6] for e in b.city_notice_state['events'] if e[1]==5];self.assertEqual(texts,['제안이 거절되었습니다: 타렌툼에 대리석 2포대'])
import agreement_bridge
class AgreementAnswerNoticeTests(unittest.TestCase):
    def publish(self,b,rows):
        b.agreements=rows;agreement_bridge.publish(b,dict(agreements=rows,stocks={},purchase_catalogs={}))
    def test_counter_proposer_hears_acceptance_once(self):
        b=SimpleNamespace(client=SimpleNamespace(city='a',session='s',agreement_focus=0),root=Path('/nonexistent'),city_names={'b':'타렌툼'},write_changed=lambda k,v:None)
        countered=A(3,'a','a','b','offered',qty=6,money=240,repeat=0,revision=1)
        self.publish(b,[countered]);self.publish(b,[countered])
        accepted=dict(countered,state='active');self.publish(b,[accepted]);self.publish(b,[accepted])
        texts=[e[6] for e in b.city_notice_state['events'] if e[1]==5]
        self.assertEqual(texts,['타렌툼: 거래 제안을 수락했습니다. (도자기 6포대 · 240 Dn)'])
    def test_partial_counter_does_not_notify_myself(self):
        b=SimpleNamespace(client=SimpleNamespace(city='a',session='s',agreement_focus=0),root=Path('/nonexistent'),write_changed=lambda k,v:None)
        received=A(4,'b','a','b','offered',qty=8,money=320,repeat=0)
        self.publish(b,[received]);self.publish(b,[dict(received,proposer='a',state='active',quantity=6,money=240,revision=1)])
        self.assertEqual([e for e in b.city_notice_state['events'] if e[1]==5],[])
if __name__=='__main__':unittest.main()
