"""Caches that grew without end (user 2026-11-16 "용량이 미쳤는데"):
  * private-game-data: a new private copy whenever the original game files or the Korean resources change; the copies
    made before for the same original folder go after a day (renamed first: one a running game holds stays whole), an
    unfinished or half-deleted one too; a copy of another original folder stays.
  * creator-cache/presets-*: the editor's terrain and empire catalogue, made again whenever the game files or the engine
    change; the ones presets-current.json no longer points to go after a day.
Runs without the game data."""
import json,os,sys,tempfile,time,unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]/'Augustus'
sys.path.insert(0,str(ROOT))
import prepare_network_data as pnd,creator_workspace as cw

def folder(path,days,files=None):
    path.mkdir(parents=True)
    for name,text in (files or {'x.bin':'x'}).items():(path/name).write_text(text,encoding='utf-8')
    then=time.time()-days*86400
    for p in [*path.rglob('*'),path]:os.utime(p,(then,then))
    return path

class PrivateCopies(unittest.TestCase):
    def test_old_copies_of_the_same_game_go(self):
        with tempfile.TemporaryDirectory() as t:
            root=Path(t);source=Path(t)/'C3'
            mine=lambda d:{'prepared.json':json.dumps(dict(source=str(source),private_game_data=True)),'c3.sg2':'x'}
            keep=folder(root/'current',3,mine(0))
            old=folder(root/'old1',3,mine(0));fresh=folder(root/'old2',0,mine(0))
            other=folder(root/'other',40,{'prepared.json':json.dumps(dict(source=str(Path(t)/'elsewhere'),private_game_data=True))})
            stage=folder(root/'preparing-1',2);newstage=folder(root/'preparing-2',0);half=folder(root/'removing-1',0)
            stranger=folder(root/'notes',5,{'readme.txt':'mine'})
            pnd.prune(root,keep,source)
            self.assertEqual(sorted(p.name for p in root.iterdir()),sorted([keep.name,'old2','other','preparing-2','notes']))
            self.assertTrue((keep/'c3.sg2').is_file())
    def test_a_copy_in_use_stays_whole(self):
        with tempfile.TemporaryDirectory() as t:
            root=Path(t);source=Path(t)/'C3'
            old=folder(root/'old',3,{'prepared.json':json.dumps(dict(source=str(source),private_game_data=True))})
            real=os.rename
            def busy(a,b):raise PermissionError(32,'in use')
            pnd.os.rename=busy
            try:pnd.prune(root,root/'keep',source)
            finally:pnd.os.rename=real
            self.assertTrue((old/'prepared.json').is_file())   # not renamed: not touched at all
    def test_never_fatal(self):
        pnd.prune(Path('/nonexistent/folder'),None,'x')

class EditorCatalogue(unittest.TestCase):
    def test_old_catalogues_go(self):
        with tempfile.TemporaryDirectory() as t:
            root=Path(t);cache=root/'creator-cache'
            cur=folder(cache/'presets-cur',5,{'catalog.json':'{}'})
            (cache/'presets-current.json').write_text(json.dumps(dict(metadata=str(cur/'catalog.json'))),encoding='utf-8')
            folder(cache/'presets-old',3);folder(cache/'presets-new',0);folder(cache/'removing-x',0);folder(cache/'terrain-evidence',9)
            cw.Workspace(root).tidy()
            self.assertEqual(sorted(p.name for p in cache.iterdir()),['presets-cur','presets-current.json','presets-new','terrain-evidence'])
    def test_without_a_current_one_nothing_goes(self):
        with tempfile.TemporaryDirectory() as t:
            root=Path(t);cache=root/'creator-cache';folder(cache/'presets-old',9)
            cw.Workspace(root).tidy()
            self.assertTrue((cache/'presets-old').is_dir())

if __name__=='__main__':unittest.main()
