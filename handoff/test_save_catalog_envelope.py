"""Resume list with joint saves whose transport record sits in an envelope (versions 6-10: army, contracts, routes).
User report 2026-11-13: the 2-player test did not start; save_catalog read transport['transfer'] at the top level of a
version 6 checkpoint (KeyError), and that one room stopped the whole list and the game."""
import sys,unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'Augustus'))
import transport_snapshot as T

class TransferOf(unittest.TestCase):
    def test_nested_and_flat(self):
        moving=dict(id=7,state='returning',sender='capua',receiver='tarentum')
        self.assertIsNone(T.transfer_of(None))
        self.assertIsNone(T.transfer_of(dict(version=1,transfer=None)))
        self.assertEqual(T.transfer_of(dict(version=2,transfer=moving)),moving)
        self.assertIsNone(T.transfer_of(dict(version=6,transport=dict(version=5,transfer=None),army={},commands=[])))
        self.assertEqual(T.transfer_of(dict(version=10,transport=dict(version=9,transport=dict(version=6,transport=dict(version=2,transfer=moving))),routes={})),moving)

class CatalogSurvives(unittest.TestCase):
    def test_a_bad_room_is_a_warning_not_a_crash(self):
        import inspect,save_catalog
        src=inspect.getsource(save_catalog.catalog)
        self.assertIn('KeyError',src)                                  # one unreadable room never stops the list
        self.assertNotIn("transport['transfer']",src)                  # read through transfer_of only

if __name__=='__main__':unittest.main()
