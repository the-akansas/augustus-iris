"""No Korean left on a foreign player's screen (user 2026-11-14).

The game translates a whole line at a time (src/core/mp_i18n.c), so a sentence the Python code builds from pieces
('관전 연결 실패: '+reason) needs a template row in i18n/review.csv ('관전 연결 실패: {0}'); the pieces alone are not
enough. These tests build every such sentence the room code can make (string pieces joined with +, f-strings, +=,
with each branch of an 'a if c else b' written out), fill the values with numbers, and check that the catalogs of all
five languages leave no Korean in them. The built-in scenarios' texts are checked the same way, and the C matcher is
compared with Augustus/ui_text.py (the same rules in Python, used by the console tools) on those sentences.
The throne box is also checked with real values (ThronePanelWithRealValues): a value can be a sentence of its own.

When a test here fails after a code change: add the sentence it names to i18n/review.csv (area composed, the values
as {0} {1} ...), translate it, and run tools/i18n_build.py."""
import ast,glob,itertools,json,re,shutil,subprocess,sys,tempfile,unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
APP=ROOT/'Augustus'
sys.path.insert(0,str(APP))
import ui_text

LANGS=['en','ru','de','es','fr']
HANGUL=re.compile('[가-힣]')
SLOT=object()
# Never shown to players: developer tools and tests.
SKIP_FILES={'diag_collect.py','update_check.py'}   # update_check.py: a Korean-edition console tool, never on the game screen
# Built from a value the test cannot see; the catalog has each whole sentence (checked in test_known_variants).
KNOWN={'보낸 사람이 {0}을 취소했습니다.':['보낸 사람이 선물을 취소했습니다.','보낸 사람이 판매 제안을 취소했습니다.'],
       '받는 사람이 {0}을 거절했습니다.':['받는 사람이 선물을 거절했습니다.','받는 사람이 판매 제안을 거절했습니다.'],
       '----- 한국어 원문 -----':[]}   # marks the Korean original kept under a translated report text: stays Korean on purpose
# Lines that are not sentences of their own (a unit or a separator added to a value elsewhere).
def fragment(line):
    text=re.sub(r'\{\d+\}','',line).strip()
    return len(HANGUL.findall(text))<2

def expand(node):
    if isinstance(node,ast.Constant):return [[node.value]] if isinstance(node.value,str) else [[SLOT]]
    if isinstance(node,ast.JoinedStr):
        parts=[]
        for v in node.values:
            if isinstance(v,ast.Constant):parts.append([[v.value]])
            elif isinstance(v,ast.FormattedValue) and v.format_spec is None:parts.append(expand(v.value))
            else:parts.append([[SLOT]])
        return product(parts)
    if isinstance(node,ast.BinOp) and isinstance(node.op,ast.Add):return product([expand(node.left),expand(node.right)])
    if isinstance(node,ast.IfExp):return expand(node.body)+expand(node.orelse)
    if isinstance(node,ast.BoolOp) and isinstance(node.op,ast.Or):
        return [[SLOT]]+[[v.value] for v in node.values[1:] if isinstance(v,ast.Constant) and isinstance(v.value,str)]
    return [[SLOT]]

def product(lists,limit=32):
    out=[[]]
    for options in lists:out=[a+b for a in out for b in options][:limit]
    return out

def template(seq):
    text='';count=0;last_slot=False
    for x in seq:
        if x is SLOT:
            if not last_slot:text+='{%d}'%count;count+=1
            last_slot=True
        elif x:text+=x;last_slot=False
    return text

def sentences(path):
    """Every line (and tab field) the file can build from pieces, with {0} {1} ... for the values."""
    src=path.read_text(encoding='utf-8-sig');tree=ast.parse(src);inner=set()
    for node in ast.walk(tree):
        if isinstance(node,(ast.BinOp,ast.JoinedStr,ast.IfExp,ast.AugAssign)):
            for child in ast.iter_child_nodes(node):
                for d in ast.walk(child):inner.add(id(d))
    for node in ast.walk(tree):
        if id(node) in inner:continue
        if isinstance(node,ast.AugAssign) and isinstance(node.op,ast.Add):
            if HANGUL.search(ast.get_source_segment(src,node.value) or ''):
                for seq in expand(node.value):yield node.lineno,template([SLOT]+seq)
        elif isinstance(node,(ast.BinOp,ast.JoinedStr,ast.IfExp)) and HANGUL.search(ast.get_source_segment(src,node) or ''):
            for seq in expand(node):yield node.lineno,template(seq)

def lines_of(text):
    for line in text.replace('\r\n','\n').split('\n'):
        for field in line.split('\t'):
            number=itertools.count()
            yield re.sub(r'\{\d+\}',lambda m:'{%d}'%next(number),field)

def sample(line):return re.sub(r'\{(\d+)\}',lambda m:str(7+int(m.group(1))),line)

def tables():
    return {code:ui_text._load(code,APP) for code in LANGS}

def shown(text,table):
    out=[]
    for line in text.split('\n'):
        done=ui_text._line(line,table)
        out.append(line if done is None else done)
    return '\n'.join(out)

def korean_left(text,catalogs):
    return [code for code,table in catalogs.items() if HANGUL.search(shown(text,table))]


class ComposedSentences(unittest.TestCase):
    def test_every_built_sentence_has_a_template(self):
        catalogs=tables();missing={}
        for path in sorted(APP.glob('*.py')):
            if path.name in SKIP_FILES or path.name.startswith('test_'):continue
            for lineno,text in sentences(path):
                for line in lines_of(text):
                    if fragment(line) or line in KNOWN:continue
                    left=korean_left(sample(line),catalogs)
                    if left:missing.setdefault(line,f'{path.name}:{lineno} ({",".join(left)})')
        self.assertEqual(missing,{},'sentences that stay Korean:\n'+'\n'.join(f'{v}  {k}' for k,v in missing.items()))

    def test_known_variants(self):
        catalogs=tables()
        for variants in KNOWN.values():
            for text in variants:self.assertEqual(korean_left(text,catalogs),[],text)

    def test_built_in_scenarios(self):
        catalogs=tables();missing=[]
        def walk(value,where):
            if isinstance(value,dict):[walk(v,where) for v in value.values()]
            elif isinstance(value,list):[walk(v,where) for v in value]
            elif isinstance(value,str) and HANGUL.search(value):
                left=korean_left(value,catalogs)
                if left:missing.append(f'{where} ({",".join(left)}): {value[:60]}')
        for path in sorted(glob.glob(str(APP/'scenarios'/'*'/'scenario.json'))+glob.glob(str(APP/'scenario-drafts'/'*'/'scenario.json'))):
            walk(json.loads(Path(path).read_text(encoding='utf-8-sig')),Path(path).parent.name)
        self.assertEqual(missing,[])

    def test_console_text_follows_the_language(self):
        catalogs=tables()
        self.assertEqual(shown('가져올 것: 게임 설정·단축키, 내 시나리오',catalogs['de']),'Wird übernommen: Spieleinstellungen und Tastenkürzel, Meine Szenarien')
        self.assertEqual(shown('목표 판정 대기: 로마, 카푸아',catalogs['en']),'Goal check pending: Rome, Capua')
        self.assertEqual(shown('Kim · 귓속말 (카푸아에게)',catalogs['fr']),'Kim · chuchotement (à Capoue)')


def throne_panel_samples():
    """Every text of the throne box, the march card, the dialogs and the scoreboard as the bridge writes them
    (throne_client box_file / dialog_file / score_file), with real values: waiting times, refusal reasons, results.
    The game shows each field of a line in the reader's language, so each field is one sample."""
    import throne_client as tc,throne_events as te
    own=dict(test=True,rules='황위 쟁탈전 규칙',active=True,ended=False,stage=1,stages=5,paranoia=100,floor=20,gift_floor=10,failures=2,
             next_cost=15700,stage_name='원로원 매수',wait='1개월 12일',restoring=False,charging=[],last=None,gift_price=200,gift_price_below=600,max_spend=1000000)
    def raid(**k):return dict(dict(phase='idle',id=5,count=2,result=None,size=48,tribute=5000,wait='',order='',after_tribute=20,after_victory=75,paying=False),**k)
    def spend(kind,state,result,**k):return dict(dict(request='x',kind=kind,amount=5000,state=state,result=result,points=80,seq=1,chance_text='71.81%'),**k)
    files=[]
    for mood in te.MOODS:files.append(tc.box_file(own,dict(leading=2,mood=mood),{},0))
    files.append(tc.box_file(dict(own,active=False,stage=0,paranoia=0),dict(leading=0,mood='평온'),{},0))
    files.append(tc.box_file(dict(own,restoring=True),{},{},0))
    for wait in ('2개월 12일','3개월','12일',''):files.append(tc.box_file(dict(own,raid=raid(phase='preparing',wait=wait)),{},{},0))
    files.append(tc.box_file(dict(own,charging=[spend('coup','charging',None)]),{},{},0));files.append(tc.box_file(dict(own,limit_reached=True),{},{},0))
    files.append(tc.box_file(dict(own,last=spend('gift','void','void')),{},{},0))
    for extra in (dict(charging=[spend('coup','charging',None)]),dict(charging=[spend('gift','refunding','ended')]),dict(charging=[spend('gift','refunding','ended',refund_blocked=True)]),
                  dict(last=spend('coup','refunded','ended')),dict(last=spend('coup','cancelled','ended'))):
        files.append(tc.box_file(dict(own,ended=True,**extra),{},{},0))
    quotes=[dict(kind='coup',ok=True,amount=15700,stage=2,stage_name='원로원 매수',minimum=15700,chance_text='41.00%',base_chance=4100,cap=6300,fail_next=19700),
            dict(kind='gift',ok=True,amount=4000,limit=4000,before=100,after=80,points=20,charge=4000,rest=0,floor=20,bottom=10),
            dict(kind='tribute',ok=True,amount=5000,before=100,after=20,points=80)]
    reasons=['금액을 정해 주세요.','황위 쟁탈전 시험이 끝났습니다.','앞선 황위 지출을 처리하는 중입니다.','보유 자금(1,200 Dn)보다 큰 금액입니다.','최소 지원금은 15,700 Dn입니다.',
             '다음 쿠데타 지원까지 1개월 12일 남았습니다.','편집증이 이미 선물로 낮출 수 있는 최저치입니다.','1점을 낮추려면 600 Dn이 필요합니다.','한 번에 1,000,000 Dn까지 낼 수 있습니다.',
             '황제군이 오고 있을 때만 공물을 바칠 수 있습니다.','황제군이 도시에 도착했습니다. 이제 공물은 받지 않습니다.','철수 공물은 5,000 Dn입니다.','보유 자금(1,200 Dn)이 철수 공물 5,000 Dn보다 적습니다.',
             '평화의 시대: 황제는 아직 총독들의 충성을 의심하지 않습니다. 선물은 받지 않습니다.','이미 마지막 단계까지 성공했습니다.']
    for q in quotes:
        for active in (True,False):
            files.append(tc.dialog_file(dict(own,active=active,raid=raid(phase='preparing',wait='1개월 20일')),dict(mode=q['kind'],quote=q,amount=q['amount'],funds=13555)))
        for reason in reasons:
            files.append(tc.dialog_file(own,dict(mode=q['kind'],quote=dict(q,ok=False,reason=reason),amount=q['amount'],funds=1200)))
            files.append(tc.dialog_file(own,dict(mode=q['kind'],quote=dict(q,ok=False,reason=reason),amount=q['amount'],message='실행하지 않았습니다. '+reason)))
            files.append(tc.box_file(own,{},dict(note=reason,note_until=1),0))
        files.append(tc.dialog_file(own,dict(mode=q['kind'],quote=q,amount=q['amount'],message='상태가 바뀌어 내용이 달라졌습니다. 다시 확인하고 눌러 주세요.')))
    for note in ('요청을 받았습니다. 도시 자금 차감이 확인되면 결과가 나옵니다.','이미 처리한 요청입니다.'):files.append(tc.box_file(own,{},dict(note=note,note_until=1),0))
    rows=[dict(city='a',stage=5,winner=True,known=True,successes=5,failures=3,coup_total=412600,gift_total=18400,raids=1,tributes=1,paranoia=50),dict(city='b',stage=1,winner=False,known=False)]
    files.append(tc.score_file(dict(scoreboard=rows),dict(a='Kim',b='Lee'),'a'))
    skip=('state','stages','leading','paranoia','mine','coup','gift','kind')
    out=[]
    for text in files:
        for line in text.splitlines():
            f=line.split('\t')
            if f[0] in skip:continue
            if f[0]=='row' and len(f)>4:continue                      # a scoreboard row: names and numbers only
            out+=[v for v in f[1:] if v and not v.lstrip('-').replace(',','').isdigit()]
    # drawn by the game itself (window/multiplayer_throne.inc, empire_rome.inc)
    out+=['평화','편집증','제국은 평화롭습니다','황제는 아직 총독들을 의심하지 않습니다','끌어내리기','내 쿠데타','가장 앞선 모의','쿠데타 지원','충성선물','공물 바치기','초기화','취소',
          '순위','총독','단계','쿠데타','지원금','선물','원정','성공 / 실패','합계','횟수 / 공물','최종','도시로 돌아가기']
    out+=list(tc.RAID_RESULT.values())+['황제의 징벌 원정','황제께서 그대의 충성심을 의심하여 징벌 원정군을 보내셨습니다. 로마의 군대가 이미 출발했습니다. 황제군 48명, 도착까지 2개월 12일, 철수 공물 5,000 Dn. '
         '도착하기 전에 공물을 바치면 군대가 돌아갑니다. 도착하면 곧바로 공격하며, 그 뒤에는 공물을 받지 않습니다. 화면의 "황제군이 오고 있습니다" 알림에서 공물을 바칠 수 있습니다.']
    return sorted(set(out))

class ThronePanelWithRealValues(unittest.TestCase):
    """Every text the throne box, the march card, the dialogs and the scoreboard can show, with real values."""
    def test_no_korean_left(self):
        catalogs=tables();left=[f'{",".join(korean_left(s,catalogs))}: {s}' for s in throne_panel_samples() if korean_left(s,catalogs)]
        self.assertEqual(left,[])
    # The examples that stood here were sentences of the old text box ("지난 지출: ..."); the box of 2026-11-14 has no
    # such lines. New examples belong here once the new texts are translated (the user: translation later).

class SameRulesAsTheGame(unittest.TestCase):
    def probe(self):
        cc=shutil.which('gcc') or shutil.which('clang')
        if not cc:self.skipTest('no C compiler')
        tmp=Path(tempfile.mkdtemp());self.addCleanup(shutil.rmtree,tmp,True)
        probe=tmp/'probe.c'
        probe.write_text('#include <stdio.h>\n#include <string.h>\n#include "core/mp_i18n.h"\n'
            'int main(int c,char**v){if(mp_i18n_load(v[1])<=0)return 2;char line[8192];while(fgets(line,sizeof line,stdin)){'
            'line[strcspn(line,"\\n")]=0;puts(mp_i18n_translate(line));}return 0;}\n',encoding='utf-8')
        exe=tmp/'probe'
        r=subprocess.run([cc,'-std=gnu99','-Wall','-Werror','-I',str(ROOT/'src'),str(probe),str(ROOT/'src/core/mp_i18n.c'),'-o',str(exe)],capture_output=True,text=True)
        self.assertEqual(r.returncode,0,r.stderr);return exe
    def compare(self,exe,samples):
        catalogs=tables();differ=[]
        for code in LANGS:
            r=subprocess.run([str(exe),str(APP/'i18n'/(code+'.tsv'))],input='\n'.join(samples)+'\n',capture_output=True,text=True,encoding='utf-8')
            self.assertEqual(r.returncode,0,r.stderr)
            for text,got in zip(samples,r.stdout.split('\n')):
                want=shown(text,catalogs[code])
                if got!=want:differ.append(f'{code}: {text} -> C {got!r} / Python {want!r}')
        self.assertEqual(differ,[])
    def test_c_matcher_agrees(self):
        exe=self.probe()
        values=['로마','밀, 보리','Kim','12','카푸아 [방장]','3','4','5','6','7']
        samples=[]
        for path in sorted(APP.glob('*.py')):
            if path.name in SKIP_FILES:continue
            for _,text in sentences(path):
                for line in lines_of(text):
                    if not fragment(line):samples.append(re.sub(r'\{(\d+)\}',lambda m:values[int(m.group(1))%len(values)],line))
        self.compare(exe,sorted(set(samples)))
    def test_c_matcher_agrees_on_the_throne_panel(self):
        self.compare(self.probe(),throne_panel_samples())


if __name__=='__main__':unittest.main()
