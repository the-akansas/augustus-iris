"""Acceptance order survives partial private-record restoration. Model + actual C when configured."""
import copy,sys,unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parent))
import test_throne_trial as T
import test_throne_end_refund as E
import cash_snapshot

class SequenceCases:
    backend=E.ModelCities
    def setUp(self):
        super().setUp();self.cities=self.backend({c:200000 for c in T.CITIES})
        T.activate(self.host,cities=self.cities)
        for city in ('player1','player2'):T.set_secret(self.host,city,stage=4,paranoia=50)
    def partial(self,legacy=False):
        self.draws.queue=[0]
        earlier=self.host.spend('player2','coup',80000,tick=1600,request='f'*32)
        saved=T.save(self.host,1,1600,self.cities)
        if legacy:saved['cash']['tables'].pop('post_sequence')
        host=T.restore_replica(self.tmp.name,saved,self.host);self.addCleanup(host.db.close)
        opening=saved['openings']['player1'];T.te.hand_in(host.db,T.B,'player1',opening['secret'],opening['nonce'],1600);host.db.commit()
        self.draws.queue=[0]
        later=host.spend('player1','coup',80000,tick=1600,request='1'*32)
        self.assertGreater(later['seq'],earlier['seq'])
        opening=saved['openings']['player2'];T.te.hand_in(host.db,T.B,'player2',opening['secret'],opening['nonce'],1600);host.db.commit()
        self.cities.run(host,'player1');self.cities.run(host,'player2');host.settle(1600)
        self.assertEqual(host.state()['winner'],'player2')
        self.cities.run(host,'player1');host.settle(1600)
        self.assertEqual(self.cities.treasury['player1'],200000)
        self.assertEqual(self.cities.treasury['player2'],120000)
        return host,later
    def test_partial_restore_keeps_prior_acceptance(self):
        host,later=self.partial()
        self.assertEqual(host.db.execute('SELECT value FROM post_sequence').fetchone()[0],later['seq'])
    def test_legacy_checkpoint_without_counter_allocates_after_hidden_records(self):
        host,later=self.partial(legacy=True)
        self.assertGreater(later['seq'],T.ts.MAX_TICK*1000+999)
        checkpoint=cash_snapshot.current(host.db);cash_snapshot.validate(copy.deepcopy(checkpoint),T.CITIES)
        for bad in [-1,2**63,True,'1']:
            broken=copy.deepcopy(checkpoint);broken['tables']['post_sequence'][0]['value']=bad
            with self.assertRaises(ValueError):cash_snapshot.validate(broken,T.CITIES)

class SequenceModel(SequenceCases,T.Base):pass
@unittest.skipUnless(E.native(),E._why or 'native library unavailable')
class SequenceNative(SequenceCases,T.Base):backend=E.NativeCities

if __name__=='__main__':unittest.main()
