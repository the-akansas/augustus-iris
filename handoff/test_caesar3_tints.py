"""Flag cloth and post office roof made on the player's PC from the player's own Caesar III (Augustus/caesar3_tints.py,
user 2026-11-16). With the game data (AUGUSTUS_C3_DATA) the pictures are made into a temporary folder and compared with
the ones the Korean edition ships (Augustus/assets/Graphics, when present and Pillow is installed): the same pixels,
except the golden eagle of the empire map (group 174), whose shipped outline brightness came from a step nobody wrote
down; there the coloured area is the same up to one pixel. Without the game data: the PNG writer and the list only."""
import os,struct,sys,tempfile,unittest,zlib
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'Augustus'))
import caesar3_tints as T
DATA=os.environ.get('AUGUSTUS_C3_DATA')
SHIPPED=ROOT/'Augustus'/'assets'/'Graphics'

def read_png(path):
    """Our own PNGs only (8-bit RGBA, filter 0)."""
    data=Path(path).read_bytes();assert data[:8]==b'\x89PNG\r\n\x1a\n'
    pos=8;idat=b'';w=h=0
    while pos<len(data):
        n,kind=struct.unpack('>I4s',data[pos:pos+8]);body=data[pos+8:pos+8+n];pos+=12+n
        if kind==b'IHDR':w,h,depth,ctype=struct.unpack('>IIBB',body[:10]);assert (depth,ctype)==(8,6)
        elif kind==b'IDAT':idat+=body
    raw=zlib.decompress(idat);rows=[]
    for y in range(h):
        line=raw[y*(4*w+1):(y+1)*(4*w+1)];assert line[0]==0
        rows.append([tuple(line[1+4*x:5+4*x]) for x in range(w)])
    return rows

class Writer(unittest.TestCase):
    def test_png_round_trip_and_list(self):
        rows=[[(0,0,0,0),(10,20,30,255)],[(255,255,255,128),(1,2,3,4)]]
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/'a.png';T.png(rows,p);self.assertEqual(read_png(p),rows)
        names=[n for n,_ in T.pictures()]
        self.assertEqual(len(names),52);self.assertEqual(len(set(names)),52)
        self.assertIn('Admin_Logistics/Player_Trade_Roof_Shade.png',names)
    def test_without_game_data_nothing_breaks(self):
        with tempfile.TemporaryDirectory() as d:
            self.assertEqual(T.ensure(Path(d)/'none',Path(d)/'assets'),0)
            self.assertFalse((Path(d)/'assets').exists())

@unittest.skipUnless(DATA and (Path(DATA)/'C3.sg2').is_file() or DATA and (Path(DATA)/'c3.sg2').is_file(),'Caesar III data (AUGUSTUS_C3_DATA) needed')
class FromTheGame(unittest.TestCase):
    def test_made_and_kept(self):
        with tempfile.TemporaryDirectory() as d:
            assets=Path(d)/'assets'
            self.assertEqual(T.ensure(DATA,assets),52)
            self.assertEqual(T.ensure(DATA,assets),0)                          # already there: kept
            (assets/'Graphics/MP_Flags/S_3.png').unlink();self.assertEqual(T.ensure(DATA,assets),1)
            for rel,_ in T.pictures():
                rows=read_png(assets/'Graphics'/rel);self.assertTrue(any(px[3] for row in rows for px in row) ,rel)
            try:from PIL import Image
            except ImportError:self.skipTest('Pillow not installed: the comparison with the shipped pictures needs it')
            if not (SHIPPED/'MP_Flags/E175_1.png').is_file():self.skipTest('no shipped pictures in this copy (Global edition)')
            for rel,_ in T.pictures():
                made=read_png(assets/'Graphics'/rel)
                ref=Image.open(SHIPPED/rel).convert('RGBA');w,h=ref.size;r=ref.load()
                self.assertEqual((len(made[0]),len(made)),(w,h),rel)
                area=sum(1 for y in range(h) for x in range(w) if (r[x,y][3]>0)!=(made[y][x][3]>0))
                if '/E174_' in rel:self.assertLessEqual(area,1,rel);continue
                diff=sum(1 for y in range(h) for x in range(w) if (r[x,y][3] or made[y][x][3]) and r[x,y]!=made[y][x])
                self.assertEqual((area,diff),(0,0),rel)

if __name__=='__main__':unittest.main()
