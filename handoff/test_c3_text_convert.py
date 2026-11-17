"""Augustus/c3_text_convert.py: a player's own Russian / western Caesar III texts in the Korean letter encoding.
Synthetic files only (the real texts are never part of the project)."""
import re,struct,sys,tempfile,unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'Augustus'))
import c3_text_convert as C

def text_file(groups,codepage):
    """groups: {group: [strings]} -> c3.eng image (28-byte header, 1000 x (offset, in_use), blob)."""
    blob=bytearray(b'\0');index=[(0,0)]*1000
    for g,strings in sorted(groups.items()):
        index[g]=(len(blob),1)
        for s in strings:blob+=s.encode(codepage)+b'\0'
    head=b'C3 textfile.'+bytes(16)
    return head+b''.join(struct.pack('<ii',*e) for e in index)+bytes(blob)

def message_file(texts,codepage):
    blob=bytearray(b'\0');entries=bytearray(32000)
    for i,(title,content) in enumerate(texts):
        struct.pack_into('<i',entries,i*80+68,len(blob));blob+=title.encode(codepage)+b'\0'
        struct.pack_into('<i',entries,i*80+76,len(blob));blob+=content.encode(codepage)+b'\0'
    return bytes(24)+bytes(entries)+bytes(blob)

class Convert(unittest.TestCase):
    def setUp(self):self.enc=C.encoder()
    def check(self,new_game,codepage,code,strings,messages):
        with tempfile.TemporaryDirectory() as d:
            src=Path(d)/'src';out=Path(d)/'out';src.mkdir();out.mkdir()
            (src/'C3.ENG').write_bytes(text_file({1:['File',new_game,'Load'],5:strings},codepage))
            (src/'c3_mm.eng').write_bytes(message_file(messages,codepage))
            self.assertEqual(C.convert_folder(src,out),code)
            text=(out/C.OWN_TEXT).read_bytes();mm=(out/C.OWN_MESSAGES).read_bytes()
            for i,s in enumerate(strings):self.assertEqual(C.text_string(text,5,i),self.enc(s))
            self.assertEqual(C.text_string(text,1,2),b'Load')
            blob=mm[32024:]
            for i,(title,content) in enumerate(messages):
                for f,want in ((68,title),(76,content)):
                    off=struct.unpack_from('<i',mm,24+i*80+f)[0];self.assertEqual(blob[off:blob.index(b'\0',off)],self.enc(want))
            return text
    def test_russian(self):
        text=self.check('Новая игра','cp1251','ru',['Сенат','Ёлка и ёж','Рим 100 Дн'],[('Цезарь','Он доволен вами.')])
        self.assertIn(bytes([0xc9,0xa1]),text)   # Ё is the first letter of the user-defined area
    def test_german(self):
        self.check('Neues Spiel','cp1252','de',['Präfekt','Straße','Öl – „gut“…'],[('Cäsar','Er ist zufrieden.')])
    def test_korean_or_unknown_left_alone(self):
        with tempfile.TemporaryDirectory() as d:
            src=Path(d);(src/'c3.eng').write_bytes(text_file({1:['x','Nowa gra']},'cp1250'));(src/'c3_mm.eng').write_bytes(message_file([],'cp1250'))
            self.assertIsNone(C.convert_folder(src,src));self.assertFalse((src/C.OWN_TEXT).exists())
    def test_letter_list_matches_engine(self):
        engine=re.findall(r'0x[0-9a-fA-F]+',re.search(r'korean_extra_chars\[[^\]]*\]\s*=\s*\{([^}]*)\}',(ROOT/'src/graphics/korean_extra_chars.h').read_text(encoding='utf-8')).group(1))
        shipped=re.findall(r'0x[0-9a-fA-F]+',(ROOT/'Augustus/i18n/extra-letters.txt').read_text(encoding='utf-8').split('{',1)[1])
        self.assertEqual(engine,shipped)

if __name__=='__main__':unittest.main()
