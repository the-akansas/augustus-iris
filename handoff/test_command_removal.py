"""The game window can hold command.txt open for a moment (it checks the file every frame); Windows then refuses a
plain delete. User report 2026-11-13: '방 만들기' stayed 'processing' because network_play crashed on command.unlink()
(WinError 32). Every command removal goes through mailbox_io.remove_file, which waits for the short lock."""
import sys,unittest
from pathlib import Path
from unittest.mock import patch
ROOT=Path(__file__).resolve().parents[1];A=ROOT/'Augustus';sys.path.insert(0,str(A))

class CommandRemoval(unittest.TestCase):
    def test_no_plain_unlink_of_the_command_file(self):
        for name in ('network_play.py','game_bridge.py'):
            text=(A/name).read_text(encoding='utf-8')
            self.assertNotIn('command.unlink()',text,name)
            self.assertIn('remove_file(command)',text,name)
    def test_remove_file_waits_for_a_short_lock(self):
        import mailbox_io,tempfile,shutil
        d=Path(tempfile.mkdtemp());self.addCleanup(shutil.rmtree,d,True);f=d/'command.txt';f.write_text('x')
        real=Path.unlink;calls=[]
        def locked(self,missing_ok=False):
            calls.append(1)
            if len(calls)<3:e=PermissionError(13,'in use');e.winerror=32;raise e
            return real(self,missing_ok=missing_ok)
        with patch.object(Path,'unlink',locked):mailbox_io.remove_file(f)
        self.assertFalse(f.exists());self.assertEqual(len(calls),3)

if __name__=='__main__':unittest.main()
