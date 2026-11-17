"""A struggle for the throne played alone (user 2026-11-15): the money of a coup, a gift or a tribute is a one-sided
debit of the player's own city. Nobody receives it, so its contract and its native receipt name the city itself;
goods still always name another city."""
import json,sqlite3,struct,sys,tempfile,unittest,zlib
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'Augustus'))
import trade_post_ledger as tpl,post_recovery,cash_snapshot

ROSTER='a'*64
def piece(owner,receipts):
    """A native receipt book as the city's engine writes it (src/multiplayer/post_book.c, post_city.c)."""
    count=len(receipts);length=2188+count*116;book=bytearray(length)
    book[0:4]=b'MPT1';book[4:68]=ROSTER.encode();struct.pack_into('<I',book,68,count)
    for i,(key,peer,step,resource,amount,applied) in enumerate(receipts):
        struct.pack_into('<96siiiii',book,2184+i*116,key.encode(),peer,step,resource,amount,applied)
    struct.pack_into('<I',book,length-4,zlib.crc32(bytes(book[:-4])))
    out=bytearray(64000);struct.pack_into('<4sIIII',out,0,b'MPCS',1,1,owner,length);out[20:20+length]=book
    struct.pack_into('<I',out,63996,zlib.crc32(bytes(out[:-4])));return bytes(out)

class Solo(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.path=str(Path(self.tmp.name)/'room.db')
    def tearDown(self):self.tmp.cleanup()
    def test_a_ledger_of_one_city_takes_its_own_debit(self):
        ledger=tpl.Ledger(self.path,['p1'],transport=True)
        with ledger.db:tpl.stage_debit(ledger.db,['p1'],'p1','0'*32,5000)
        t=ledger.db.execute('SELECT sender,receiver,route,money FROM post_contract').fetchone()
        self.assertEqual(tuple(t),('p1','p1','debit',5000))
        with ledger.db:tpl.stage_debit(ledger.db,['p1'],'p1','0'*32,5000)                   # a resend changes nothing
        self.assertEqual(ledger.db.execute('SELECT count(*) FROM post_command').fetchone()[0],1)
        self.assertEqual(ledger.commands('p1',['p1'])[0]['peer'],'p1')                       # the receipt will name the city itself
        ledger.close()
    def test_an_earlier_debit_naming_another_city_is_still_the_same_debit(self):
        ledger=tpl.Ledger(self.path,['p1','p2'],transport=True)
        with ledger.db:ledger.db.execute("INSERT INTO post_contract(id,sender,receiver,resource,quantity,money,route,phase) VALUES(?,?,?,0,0,?,'debit','export')",('1'*32,'p1','p2',800))
        with ledger.db:tpl.stage_debit(ledger.db,['p1','p2'],'p1','1'*32,800)               # no conflict
        with self.assertRaises(ValueError):tpl.stage_debit(ledger.db,['p1','p2'],'p1','1'*32,900)
        ledger.close()
    def test_receipts_name_the_own_city_for_money_only(self):
        got=post_recovery.native_receipts(piece(0,[('t:export:1',0,1,0,5000,1),('t:pay:1',0,4,0,5000,1)]),ROSTER,0,['p1'])
        self.assertEqual({k:v['peer'] for k,v in got.items()},{'t:export:1':'p1','t:pay:1':'p1'})
        for bad in [('g:export:1',0,1,3,10,1),('m:escrow:1',0,2,0,500,1)]:                   # goods, or a step of a trade
            with self.assertRaises(ValueError):post_recovery.native_receipts(piece(0,[bad]),ROSTER,0,['p1'])
        got=post_recovery.native_receipts(piece(1,[('x:export:1',0,1,3,10,1)]),ROSTER,1,['p1','p2'])   # goods to another city as before
        self.assertEqual(got['x:export:1']['peer'],'p1')
    def test_the_joint_save_keeps_an_own_city_debit_and_still_refuses_a_trade_with_itself(self):
        def data(row):
            tables={n:[] for n in cash_snapshot.TABLES};tables['post_meta']=[dict(version=1,cities=json.dumps(['p1']))];tables['cash_scope']=[dict(value='b'*64)]
            tables['post_contract']=[row];return dict(tables=tables,transfers=[])
        base=dict(id='0'*32,sender='p1',receiver='p1',resource=0,quantity=0,money=5000,route='debit',phase='export')
        cash_snapshot.validate(data(base),['p1'])
        with self.assertRaises(ValueError):cash_snapshot.validate(data(dict(base,route='land')),['p1'])

if __name__=='__main__':unittest.main()
