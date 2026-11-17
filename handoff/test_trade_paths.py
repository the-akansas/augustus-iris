"""Natural trade paths on the empire map (empire_paths.py: display_routes for the in-game map, empire.route_paths).

What the paths must keep, checked here:
  * land paths over land cells, sea paths over sea cells of the PASSAGE DATA (every segment, after straightening and
    rounding), checked by an independent fine sampler, not by the module's own grid walk. The passage data itself is
    an estimate (picture colour confirmed by the original routes), so this proves the paths keep to that data, not
    that the data matches the real map everywhere;
  * no path -> None / path_state 'none', never a straight line in its place;
  * same input -> same output (also after reloading the data);
  * stored paths stay until the endpoints move or the user regenerates; saving and reloading keeps them; projects
    without paths and older schemas keep working; schema 3 cannot carry them;
  * trade rules are untouched: the editor's links (scenario_check) and the engine layout are the same with or
    without stored paths and even when the passage data cannot be read.
Synthetic grids test the rules; the shipped empire-passage.json is tested on the real default projects.
"""
import copy,json,math,sys,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
ROOT=Path(__file__).resolve().parents[1]/'Augustus'
sys.path.insert(0,str(ROOT))
import empire_paths as ep,scenario_check as sc,scenario_project as sp,creator_presets

PATH_FIELDS={'path','path_state','path_note','path_key','path_record'}

def synthetic(rows,lanes=None):
    """A passage file of 10 px cells from strings ('L','S','B'); returns its path (kept for the test run)."""
    f=tempfile.NamedTemporaryFile('w',suffix='.json',delete=False,encoding='utf8')
    json.dump(dict(schema=1,cell=10,width=len(rows[0])*10,height=len(rows)*10,image_sha256='0'*64,rows=rows,
                   lanes=lanes or dict(land=[],sea=[]),validation={}),f);f.close();return Path(f.name)

def kind_at(d,x,y):
    c=d['cell'];return d['rows'][min(d['_h']-1,int(y)//c)][min(d['_w']-1,int(x)//c)]

def off_kind(path_file,points,transport,legs=True):
    """Points of the drawn line (sampled every 0.37 px) on a forbidden cell. The two city legs are left out when
    legs=False (a sea path's harbour leg may cross land; a land leg may be inside the city icon). An exact cell corner
    is skipped: the path may touch it (the search's diagonal rule needs one open side cell there)."""
    d=ep.load(path_file);want='S' if transport=='sea' else 'L';bad=[]
    segs=list(zip(points,points[1:]))
    if not legs:segs=segs[1:-1]
    for a,b in segs:
        n=max(1,int(math.dist(a,b)/0.37))
        for i in range(n+1):
            x=a[0]+(b[0]-a[0])*i/n;y=a[1]+(b[1]-a[1])*i/n
            if abs(x/10-round(x/10))<1e-9 and abs(y/10-round(y/10))<1e-9:continue   # an exact cell corner: a point, no width
            if kind_at(d,x,y) not in (want,'B'):bad.append((round(x,1),round(y,1)))
    return bad

#           0         1
#           01234567890123456789
LAKE=['LLLLLLLLLLSSSSSSSSSS',   # land on the left with a lake, sea on the right with an island
      'LLLLLLLLLLSSSSSSSSSS',
      'LLLSSSSLLLSSSSSSSSSS',
      'LLLSSSSLLLSSSLLLSSSS',
      'LLLSSSSLLLSSSLLLSSSS',
      'LLLSSSSLLLSSSSSSSSSS',
      'LLLLLLLLLLSSSSSSSSSS',
      'LLLLLLLLLLSSSSSSSSSS']

class Rules(unittest.TestCase):
    @classmethod
    def setUpClass(cls):cls.f=synthetic(LAKE)
    def test_land_path_goes_round_the_lake(self):
        p=ep.find((15,45),(85,45),'land',self.f)
        self.assertIsNotNone(p);self.assertEqual(off_kind(self.f,p,'land'),[])
        self.assertTrue(ep.check(p,'land',self.f))
        self.assertTrue(any(y<20 or y>60 for x,y in p),'the straight line crosses the lake; the path must not')
    def test_sea_path_stays_on_water_round_the_island(self):
        p=ep.find((125,35),(185,45),'sea',self.f)
        self.assertIsNotNone(p);self.assertEqual(off_kind(self.f,p,'sea',legs=False),[])
    def test_no_path(self):
        self.assertIsNone(ep.find((145,40),(15,15),'land',self.f))      # the island has no land way to the mainland
        dry=synthetic(['L'*20]*10+['L'*14+'SSSSSS'])
        self.assertIsNone(ep.find((15,15),(185,15),'sea',dry))          # no water within reach of an inland city
        rec,state,note=ep.resolve({},1,(145,40),2,(15,15),'land',path=self.f)
        self.assertEqual((rec,state),(None,'none'));self.assertIn('경로 미확정',note)
    def test_corner_slip_is_not_a_passage(self):
        big=[r.replace('L','L'*10).replace('S','S'*10) for r in ('LS','SL') for _ in range(10)]   # 10x10-cell blocks
        f=synthetic(big)                                   # land touches land only at one corner point, so does sea
        self.assertIsNone(ep.find((50,50),(150,150),'land',f))
        self.assertIsNone(ep.find((150,50),(50,150),'sea',f))
        self.assertIsNotNone(ep.find((50,50),(80,20),'land',f))
    def test_both_cells_open_either_way(self):
        f=synthetic(['LLLLL','SSBSS','LLLLL'])            # a strait the original land route crosses
        self.assertIsNotNone(ep.find((25,5),(25,45),'land',f))
        self.assertIsNotNone(ep.find((5,15),(45,15),'sea',f))
    def test_same_input_same_path(self):
        a=ep.find((15,45),(85,45),'land',self.f);ep._cache.clear();b=ep.find((15,45),(85,45),'land',self.f)
        self.assertEqual(a,b)
        self.assertEqual(ep.find((85,45),(15,45),'land',self.f),ep.find((85,45),(15,45),'land',self.f))
    def test_damaged_data_is_refused(self):
        f=synthetic(['LLX','LLL'])
        with self.assertRaises(ValueError):ep.load(f)

def every_link(n,neutrals=False):
    d=creator_presets.default_project(n)
    if neutrals:
        ids=[s['id'] for s in d['slots']]
        for c in d['empire']['cities']:
            if c['role']=='npc' and not c.get('reserved'):c['enabled']=True;c['trade_players']=ids
    return d

def routes(data):return {(r['a'],r['b'],r['transport']):r for r in ep.display_routes(data)['routes']}

class RealMap(unittest.TestCase):
    def test_data_file(self):
        d=ep.load()
        self.assertEqual((d['width'],d['height'],d['cell']),(2000,1000,10))
        v=d['validation'];self.assertLessEqual(v['sea_pieces_on_land_cells']+v['land_pieces_on_sea_cells'],0.05*(v['sea_pieces']+v['land_pieces']))
        self.assertGreater(len(d['lanes']['sea']),400);self.assertGreater(len(d['lanes']['land']),350)
    def test_every_drawn_path_keeps_to_its_terrain(self):
        data=every_link(8,neutrals=True);count=0;missing=0
        for r in routes(data).values():
            p=r['points']
            if p is None:missing+=1;continue
            count+=1
            self.assertEqual(off_kind(ep.DATA,p,r['transport'],legs=False),[],(r['a'],r['b']))
            if r['transport']=='land':   # land legs: on land outside the city icon
                for city,gate in ((p[0],p[1]),(p[-1],p[-2])):
                    t=ep.CITY_ICON/max(math.dist(city,gate),1e-9)
                    if t<1:self.assertEqual(off_kind(ep.DATA,[[city[0]+(gate[0]-city[0])*t,city[1]+(gate[1]-city[1])*t],gate],'land'),[])
        self.assertGreater(count,150);self.assertGreater(missing,0)   # some relations really have no path on this map
    def test_paths_run_from_a_to_b(self):
        data=every_link(4);pos={c['name_id']:[c['x'],c['y']] for c in data['empire']['cities']}
        for r in routes(data).values():
            if r['points']:self.assertEqual((r['points'][0],r['points'][-1]),(pos[r['a']],pos[r['b']]))
    def test_same_project_same_paths(self):
        data=every_link(6,neutrals=True);a=ep.display_routes(data);ep._cache.clear();b=ep.display_routes(copy.deepcopy(data))
        self.assertEqual(a,b)

def adopt(data):
    """Store a path for every relation (what an older editor version kept in the project)."""
    pos={c['name_id']:(c['x'],c['y']) for c in data['empire']['cities']}
    for kind,transport,a,b,_,_ in ep.relations(data):
        rec,state,_=ep.resolve({},a,pos[a],b,pos[b],transport)
        if rec:data['empire'].setdefault('route_paths',{})[ep.key_for(a,b,transport)]=rec

class Storage(unittest.TestCase):
    def test_stored_paths_survive_save_and_reload(self):
        data=every_link(4);adopt(data);self.assertTrue(data['empire']['route_paths'])
        with tempfile.TemporaryDirectory() as d:
            f=Path(d)/'p.json';f.write_text(json.dumps(data,ensure_ascii=False),encoding='utf8')
            again=sp.load(f)
        self.assertEqual(again['empire']['route_paths'],data['empire']['route_paths'])
    def test_stored_path_is_kept_not_replaced(self):
        data=every_link(2);adopt(data)
        key,rec=next(iter(data['empire']['route_paths'].items()))
        bent=[rec['from'],[(rec['from'][0]+rec['to'][0])//2,min(rec['from'][1],rec['to'][1])-40],rec['to']]
        rec['points']=bent;sp.validate(data)
        a,b,t=key.split('-');self.assertEqual(routes(data)[(int(a),int(b),t)]['points'],bent)
        self.assertEqual(ep.resolve(data['empire']['route_paths'],*self.ends(data,key),regenerate=True)[1],'auto')   # explicit regeneration
    def ends(self,data,key):
        a,b,t=key.split('-');pos={c['name_id']:(c['x'],c['y']) for c in data['empire']['cities']}
        return int(a),pos[int(a)],int(b),pos[int(b)],t
    def test_moving_a_city_makes_a_new_path(self):
        data=every_link(2);adopt(data)
        key=next(iter(data['empire']['route_paths']));a,b,t=key.split('-')
        city=next(c for c in data['empire']['cities'] if c['name_id']==int(a));city['y']+=10
        self.assertEqual(routes(data)[(int(a),int(b),t)]['points'][0],[city['x'],city['y']])
    def test_old_projects_and_bad_records(self):
        data=every_link(4);sp.validate(data)                       # no route_paths: still valid
        adopt(data);sp.validate(data)
        old=copy.deepcopy(data);old['schema']=3
        with self.assertRaises(ValueError):sp.validate(old)          # schema 3 has no place for them
        for spoil in (lambda r:r.update(points=[r['from']]),lambda r:r.update(to=[0,0]),lambda r:r.update(extra=1),
                      lambda r:r['points'].append([5000,1]),lambda r:r.update(data='zz')):
            bad=copy.deepcopy(data);spoil(next(iter(bad['empire']['route_paths'].values())))
            with self.assertRaises(ValueError):sp.validate(bad)
        bad=copy.deepcopy(data);bad['empire']['route_paths']={'9-3-land':next(iter(data['empire']['route_paths'].values()))}
        with self.assertRaises(ValueError):sp.validate(bad)

class TradeRulesUnchanged(unittest.TestCase):
    def test_links_and_layout_ignore_paths(self):
        data=every_link(6,neutrals=True);plain=sc.check(data,None,sc.evidence(data))
        with_paths=copy.deepcopy(data);adopt(with_paths)
        self.assertEqual(plain,sc.check(with_paths,None,sc.evidence(with_paths)))
        self.assertEqual(sp.layout(data),sp.layout(with_paths))   # the engine never sees the paths
        self.assertFalse(any('path' in k for g in plain['links'] for l in g['links'] for k in l))   # the editor shows kinds only
    def test_unreadable_data_keeps_every_relation(self):
        data=every_link(4,neutrals=True)
        with patch.object(ep,'load',side_effect=OSError('missing')):broken=ep.display_routes(data)
        self.assertEqual([(r['a'],r['b'],r['transport']) for r in broken['routes']],[(a,b,t) for _,t,a,b,_,_ in ep.relations(data)])
        self.assertTrue(all(r['points'] is None for r in broken['routes']))

if __name__=='__main__':unittest.main()
