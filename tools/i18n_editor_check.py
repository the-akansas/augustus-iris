"""List editor (creator-src/*.cs) texts that would stay Korean in another language (2026-11-14).

  python tools/i18n_editor_check.py [--lang en]

The editor translates a whole text, then line by line, then templates, then known phrases inside a line
(creator-src/CreatorLang.cs). This reads the C# sources, joins string pieces written with + into one line with
{0} {1} for the values in between, and reports every line in which Korean is left after those four steps.
It is a reading of the source, not a run of the editor: a text built in another way can be missed, and a piece that
is never shown can be listed. Exit code 1 when something is listed."""
import argparse,re,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'Augustus'))
import ui_text
HANGUL=re.compile('[\uac00-\ud7a3]')
LIT=re.compile(r'@?"((?:[^"\\\n]|\\.)*)"')
SKIP_LINE=re.compile(r'^\s*(//|\*|/\*)')

def unescape(s):
    return s.replace('\\r\\n','\n').replace('\\n','\n').replace('\\t','\t').replace('\\"','"').replace('\\\\','\\')

def built(line):
    """Templates one source line can build: literals joined by + with slots between."""
    hits=list(LIT.finditer(line));out=[];i=0
    while i<len(hits):
        text='';n=0;j=i
        before=line[:hits[i].start()].rstrip()
        if before.endswith('+') and not before.endswith('++'):text='{0}';n=1
        while True:
            text+=unescape(hits[j].group(1))
            if j+1<len(hits):
                gap=line[hits[j].end():hits[j+1].start()]
                if re.fullmatch(r'\s*\+\s*',gap):j+=1;continue
                if re.fullmatch(r'\s*\+[^";{}]*\+\s*',gap) and gap.count('(')==gap.count(')') and '?' not in gap:text+='{%d}'%n;n+=1;j+=1;continue
            break
        after=line[hits[j].end():].lstrip()
        if after.startswith('+') and not after.startswith('++'):text+='{%d}'%n
        out.append(text);i=j+1
    return out

def shown(text,table,phrases):
    exact=table[0]
    raw=text.replace('\\','\\\\').replace('\n','\\n').replace('"','\\"')
    for form in (text,raw,raw.replace('\\"','"')):
        if form in exact:return exact[form]
    lines=[]
    for line in text.split('\n'):
        done=ui_text._line(line,table)
        if done is None:done=line
        if HANGUL.search(done):          # the editor translates a slot's text the same way, phrases included
            for key in phrases:
                if key in done:done=done.replace(key,exact[key])
        lines.append(done)
    return '\n'.join(lines)

def main():
    p=argparse.ArgumentParser();p.add_argument('--lang',default='en');a=p.parse_args()
    table=ui_text._load(a.lang,ROOT/'Augustus')
    keys={k for k in table[0] if len(k.strip())>=2 and HANGUL.search(k) and '\n' not in k}
    phrases=sorted(keys,key=len,reverse=True)
    left={}
    for path in sorted((ROOT/'creator-src').glob('*.cs')):
        for no,line in enumerate(path.read_text(encoding='utf-8-sig').splitlines(),1):
            if SKIP_LINE.match(line) or not HANGUL.search(line):continue
            code=line.split(' // ')[0]
            for text in built(code):
                if not HANGUL.search(text):continue
                sample=re.sub(r'\{(\d+)\}',lambda m:str(7+int(m.group(1))),text)
                if HANGUL.search(shown(sample,table,phrases)) and HANGUL.search(shown(text,table,phrases)):left.setdefault(text,f'{path.name}:{no}')
    for text,where in left.items():print(where,'|',text.replace('\n','\\n'))
    print(len(left),'left')
    return 1 if left else 0
if __name__=='__main__':sys.exit(main())
