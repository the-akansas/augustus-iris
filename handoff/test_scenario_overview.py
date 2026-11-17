"""The scenario window's text (Augustus/scenario_overview.py), checked against the scenario editor (user 2026-11-16).
What it says is where the scenario is going, enough to choose a room ("이 시나리오의 방향성만 알면 되는거지 세부 규칙은
게임내에서 알수 있잖아"): the mode and its goals, the delivery goals, how long a progress or throne game is (number of
progresses, the throne preset), the forbidden player trades, the common start message (a city's own message is that
player's), and the editor's words (황제 지지도, 기본 시작 자금, a city kept for a player). The detailed rules (throne stages
and prices, bids, governance, building lists, event contents) are not listed: the game shows them where they apply.
Runs without the game data."""
import copy,json,sys,unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]/'Augustus'
sys.path.insert(0,str(ROOT))
import scenario_project as sp,scenario_overview as so,throne_rules

def catalog():return json.loads((ROOT/'preset-catalog.json').read_text(encoding='utf-8-sig'))
def scenario(name):return json.loads((ROOT/'scenarios'/name/'scenario.json').read_text(encoding='utf-8-sig'))
def city(view,name):return next(c for c in view['cities'] if c['name']==name)
def text(lines):return '\n'.join(l.split('\t')[-1] for l in lines)
def generated(view):   # the lines this module words (the author's own text left out)
    out=[];skip=False
    for l in view['briefing']:
        if l.startswith('H\t'):skip=l in ('H\t소개 (제작자 글)','H\t게임 시작 메시지 (모두에게)')
        if not skip:out.append(l)
    return text(out)

class Whole(unittest.TestCase):
    def test_the_feature_example(self):
        v=so.overview(sp.validate(scenario('feature-trade-goals')),catalog());b=generated(v)
        self.assertIn('납품 목표: 카푸아에서 타렌툼(으)로 도자기 20포대',b);self.assertIn('납품 목표: 메디올라눔에서 시라쿠세(으)로 목재 20포대',b)
        self.assertIn('교역 금지: 카푸아 - 시라쿠세',b);self.assertIn('기본 시작 자금: 10,000 데나리',b)
        for detail in ('통치자','건설 제한','허용 건물','선물 또는 판매','도시 지원금'):self.assertNotIn(detail,b+text(sum((c['detail'] for c in v['cities']),[])))
        self.assertIn('침공 일정: 1개',text(city(v,'타렌툼')['detail']));self.assertIn('예정 이벤트: 1개',text(city(v,'메디올라눔')['detail']))
    def test_progress_and_start_message(self):
        d=sp.validate(scenario('progress-6p'));d['start_message']=dict(common='모두 보는 글\n둘째 줄',per_city={d['slots'][0]['id']:'나만 보는 비밀'})
        v=so.overview(sp.validate(d),catalog());b=text(v['briefing'])
        self.assertIn('순행 6회 · 첫 순행 24개월 뒤',b)
        for detail in ('최저 입찰가','요구량','준비 기간','부족분'):self.assertNotIn(detail,b)
        self.assertIn('게임 시작 메시지 (모두에게)\n모두 보는 글\n둘째 줄',b);self.assertNotIn('나만 보는 비밀',json.dumps(v,ensure_ascii=False))
    def test_throne_preset_only(self):
        d=sp.validate(scenario('throne-test-v1'))
        for name,label in (('standard','표준'),('short','짧은 판'),('long','긴 판')):
            d['rules']['throne']=throne_rules.preset(name);b=generated(so.overview(sp.validate(copy.deepcopy(d)),catalog()))
            self.assertIn('황위 쟁탈전 프리셋: '+label,b)
            for detail in ('최소 지원금','성공률','편집증','철수 공물','황제군'):self.assertNotIn(detail,b)
        self.assertIn('황위 쟁탈전 프리셋: 사용자 설정',text(so.overview(sp.validate(scenario('throne-6p')),catalog())['briefing']))
        self.assertNotIn('아직 게임에서 실행할 수 없습니다',json.dumps(so.MODES,ensure_ascii=False))
    def test_fewer_players(self):
        b=text(so.overview(sp.validate(scenario('coop-6p')),catalog())['briefing'])
        self.assertIn('적은 인원으로 시작하면 공동 목표가 줄어듭니다.',b);self.assertNotIn('명으로 시작하면',b)
    def test_every_shipped_scenario(self):
        for path in sorted((ROOT/'scenarios').glob('*/scenario.json')):
            v=so.overview(sp.load(path),catalog());body=so.encode('X',v)
            self.assertTrue(all(len(r.encode('utf-8'))<1024 for r in body.split('\n')),path)
            self.assertNotIn('황제 호감',body);self.assertNotIn('도시별 시작 자금',body)

class KeptSeat(unittest.TestCase):
    def test_a_city_kept_for_a_player(self):
        d=sp.validate(scenario('freebuild-4p'))
        c=next(c for c in d['empire']['cities'] if c['role']=='npc' and c['enabled'])
        c.update(reserved=True,cost=0,sells={},buys={},trade_players=[]);c.pop('sea_auto',None)
        v=so.overview(sp.validate(d),catalog())
        kept=[x for x in v['cities'] if x['detail'] and x['detail'][0]=='H\t플레이어 자리로 비워 둔 도시']
        self.assertEqual(len(kept),1);self.assertNotIn('판매 품목',text(kept[0]['detail']))

if __name__=='__main__':unittest.main()
