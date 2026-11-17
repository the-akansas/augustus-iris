"""Saves are found and opened whatever characters their folder's path has (user 2026-11-17: an earlier change made the
sqlite address of a save differ for special characters, and the 이어하기 list came up empty).

A save is opened read-only through a sqlite URI (windows_paths.sqlite_readonly_uri): '#', '?' and '%' mean something in a
URI, so the path is escaped in one place only, and no reader builds the address by hand. Checked here with real
folders: the address itself, the LAN 이어하기 list (save_catalog, start_catalog) and that the address stays read-only.
The game hall's list is checked in test_game_hall.py (Korean edition)."""
import json,re,sqlite3,sys,tempfile,unittest
from contextlib import closing
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];A=ROOT/'Augustus';sys.path.insert(0,str(A))
from windows_paths import sqlite_readonly_uri

# what a player's folder can be called on Windows ('?' cannot, and is added where the system allows it)
NAMES=['plain','한글 사용자','새 폴더 (2)','a#b','100%','50%41x','a&b=c',"it's",'a+b','semi;colon','sp  ace','[brackets]','~tilde',
       'comma,dot.','at@sign','excl!','dollar$','caret^','back`tick','brace{}','Augustus-MP-261117-rc7 (1)','#첫글자','끝글자%']

def folders(base):
    made=[]
    for name in NAMES+['q?x']:
        try:(base/name).mkdir();made.append(base/name)
        except OSError:
            if name in NAMES:raise          # only '?' may be refused (Windows)
    return made

def room(folder,binding):
    """A room with one complete joint save, as save_catalog reads it."""
    folder.mkdir(parents=True)
    with closing(sqlite3.connect(folder/'room.sqlite')) as db:
        db.execute('CREATE TABLE scenario_binding(value TEXT)');db.execute('INSERT INTO scenario_binding VALUES(?)',(json.dumps(binding),))
        db.execute('CREATE TABLE joint_save(id INTEGER PRIMARY KEY,request TEXT,ticks INTEGER,state TEXT,speed INTEGER)')
        db.execute("INSERT INTO joint_save VALUES(3,'r',1200,'complete',50)")
        db.execute('CREATE TABLE joint_part(id INTEGER,city TEXT,save BLOB,hash TEXT)')
        for city in binding['cities']:db.execute('INSERT INTO joint_part VALUES(3,?,?,?)',(city,b'x','h'))
        db.commit()
    return folder/'room.sqlite'

class Address(unittest.TestCase):
    def test_every_folder_name_opens_and_stays_read_only(self):
        with tempfile.TemporaryDirectory() as tmp:
            for folder in folders(Path(tmp)):
                with self.subTest(folder=folder.name):
                    path=folder/'room.sqlite'
                    with closing(sqlite3.connect(path)) as db:db.execute('CREATE TABLE t(x)');db.execute('INSERT INTO t VALUES(7)');db.commit()
                    with closing(sqlite3.connect(sqlite_readonly_uri(path),uri=True)) as db:
                        self.assertEqual(db.execute('SELECT x FROM t').fetchone()[0],7)
                        with self.assertRaises(sqlite3.OperationalError):db.execute('INSERT INTO t VALUES(8)')   # mode=ro kept
                    before=sorted(p.name for p in folder.parent.iterdir())
                    with self.assertRaises(sqlite3.OperationalError):                                          # a missing save is never made
                        with closing(sqlite3.connect(sqlite_readonly_uri(folder/'none.sqlite'),uri=True)) as db:db.execute('SELECT 1')
                    self.assertFalse((folder/'none.sqlite').exists())
                    self.assertEqual(sorted(p.name for p in folder.parent.iterdir()),before)                   # nor a stray file beside it

    def test_no_reader_builds_the_address_by_hand(self):
        # game_hall.py did until rc7: 'file:'+path+'?mode=ro' lost the save (and mode=ro) for '#', '?' and '%41'
        for path in sorted(A.glob('*.py')):
            if path.name=='windows_paths.py':continue
            text=path.read_text(encoding='utf-8-sig')
            self.assertIsNone(re.search(r"""['"]file:['"]\s*\+|mode=ro""",text),path.name)
            if 'uri=True' in text:self.assertIn('sqlite_readonly_uri',text,path.name)

class LanList(unittest.TestCase):
    def test_the_list_finds_the_save_in_every_folder(self):
        import save_catalog,start_catalog,maker_room
        binding=dict(cities=['player1','player2'])
        self.assertTrue(save_catalog.compatible_binding(binding,binding))
        with tempfile.TemporaryDirectory() as tmp:
            for folder in folders(Path(tmp)):
                with self.subTest(folder=folder.name):
                    rooms=folder/'rooms'
                    first=room(rooms/'game-20261117-010101-1',binding)
                    second=room(rooms/'network-play-0a1b'/'host-1',binding)
                    (second.parent/maker_room.MARK).write_text('1\n',encoding='ascii')
                    result=save_catalog.catalog(rooms,binding)
                    self.assertEqual(result['warnings'],[])
                    self.assertEqual(sorted(e['database'] for e in result['entries']),sorted(str(p.resolve()) for p in (first,second)))
                    self.assertTrue(all(e['available'] and e['id']==3 for e in result['entries']),result['entries'])
                    choices=start_catalog.save_choices(result['entries'],'project')
                    self.assertEqual(len(choices),2)
                    self.assertEqual(sorted(' · 제작자 방' in c['label'] for c in choices),[False,True])
                    for c in choices:   # what the list hands to the restore opens again
                        with closing(sqlite3.connect(sqlite_readonly_uri(c['restore']),uri=True)) as db:
                            self.assertEqual(db.execute("SELECT id FROM joint_save WHERE state='complete'").fetchone()[0],c['save_id'])

if __name__=='__main__':unittest.main()
