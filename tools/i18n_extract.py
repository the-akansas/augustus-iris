"""List every Korean user-facing text in the multiplayer code, the game screens we added and the scenario editor
(multilingual work, user 2026-11-13). The Korean text is the key of every translation (see docs/다국어-설계-20261113.md).

  python tools/i18n_extract.py [--root .] [--out i18n/source.json] [--csv i18n/review.csv]

Each entry: text (the Korean source exactly as written in the code), kind, places (file:line), args.
  kind  plain   a fixed text
        format  a C printf text (%d, %s ...) or a Python str.format / % text: args lists the slots
        fstring a Python f-string: args lists the expressions; it has to become tr('... {name} ...', name=...) first
Comments, log-only texts and the translation tables of the original game (src/translation) are not listed."""
import argparse,csv,hashlib,json,re,sys
from pathlib import Path

HANGUL=re.compile('[가-힣]')
C_STR=re.compile(r'"((?:[^"\\\n]|\\.)*)"')
CS_STR=re.compile(r'@?"((?:[^"\\\n]|\\.)*)"')
PRINTF=re.compile(r'%[-+ #0]*\d*(?:\.\d+)?(?:hh|h|ll|l|z)?[diuxXsScfgeEp%]')
SKIP_DIRS={'translation','__pycache__','test-work','creator-cache','creator-probes'}
# Shown in every language at once on purpose (the language picker): not translated.
SKIP_FILES={'mp_language.c','language_select.c'}

def unescape_c(s):
    try:return bytes(s,'utf-8').decode('unicode_escape').encode('latin-1').decode('utf-8')
    except (UnicodeDecodeError,UnicodeEncodeError):return s

def strip_c_comments(text):
    # keep line numbers: blank out comments character by character
    out=[];i=0;n=len(text);state=None
    while i<n:
        c=text[i]
        if state is None:
            if text.startswith('//',i):state='line';out.append('  ');i+=2;continue
            if text.startswith('/*',i):state='block';out.append('  ');i+=2;continue
            if c=='"':
                j=i+1
                while j<n and text[j]!='"' and text[j]!='\n':
                    j+=2 if text[j]=='\\' else 1
                out.append(text[i:j+1]);i=j+1;continue
            if c=="'":
                j=i+1
                while j<n and text[j]!="'" and text[j]!='\n':
                    j+=2 if text[j]=='\\' else 1
                out.append(text[i:j+1]);i=j+1;continue
            out.append(c);i+=1
        elif state=='line':
            if c=='\n':state=None;out.append('\n')
            else:out.append(' ')
            i+=1
        else:
            if text.startswith('*/',i):state=None;out.append('  ');i+=2;continue
            out.append('\n' if c=='\n' else ' ');i+=1
    return ''.join(out)

LOG_CALL=re.compile(r'\b(?:log_info|log_error|log_warn|errlog|SDL_Log|printf|fprintf\s*\(\s*stderr\s*,)')
def blank_logs(line):
    """Log and console texts are for developers: blank the whole call (strings included) so they are not listed."""
    out=line
    for m in reversed(list(LOG_CALL.finditer(line))):
        i=line.find('(',m.start())
        if i<0:continue
        depth=0;j=i;n=len(line)
        while j<n:
            c=line[j]
            if c=='"':
                j+=1
                while j<n and line[j]!='"':j+=2 if line[j]=='\\' else 1
            elif c=='(':depth+=1
            elif c==')':
                depth-=1
                if depth==0:break
            j+=1
        out=out[:m.start()]+' '*(j+1-m.start())+out[j+1:]
    return out

def c_texts(path,rel,cs=False):
    raw=path.read_text(encoding='utf-8-sig',errors='replace')
    text=strip_c_comments(raw)
    for no,line in enumerate(text.split('\n'),1):
        if not HANGUL.search(line):continue
        line=blank_logs(line)
        for m in (CS_STR if cs else C_STR).finditer(line):
            s=m.group(1)
            if not HANGUL.search(s):continue
            s=s.replace('\\"','"').replace('\\\\','\\') if cs else unescape_c(s)
            yield s,f'{rel}:{no}',PRINTF.findall(s)

def py_texts(path,rel):
    import ast,tokenize,io
    src=path.read_text(encoding='utf-8-sig',errors='replace')
    try:tree=ast.parse(src)
    except SyntaxError:return
    docs=set()
    for node in ast.walk(tree):
        if isinstance(node,(ast.Module,ast.FunctionDef,ast.ClassDef,ast.AsyncFunctionDef)) and node.body and isinstance(node.body[0],ast.Expr) and isinstance(node.body[0].value,ast.Constant):
            docs.add(id(node.body[0].value))
    for node in ast.walk(tree):
        if isinstance(node,ast.Constant) and isinstance(node.value,str) and id(node) not in docs and HANGUL.search(node.value):
            if getattr(node,'_in_f',False):continue
            yield node.value,f'{rel}:{node.lineno}',re.findall(r'\{[^{}]*\}',node.value)+PRINTF.findall(node.value),'plain'
        elif isinstance(node,ast.JoinedStr):
            parts=[];args=[]
            for v in node.values:
                if isinstance(v,ast.Constant):parts.append(v.value);v._in_f=True
                else:
                    expr=ast.get_source_segment(src,v.value) or '?';args.append(expr);parts.append('{'+str(len(args)-1)+'}')
            s=''.join(parts)
            if HANGUL.search(s):yield s,f'{rel}:{node.lineno}',args,'fstring'

def collect(root):
    entries={}
    def add(text,place,args,kind):
        e=entries.setdefault(text,dict(text=text,kind=kind,args=args,places=[]))
        if kind=='fstring' or (args and e['kind']=='plain'):e['kind']=kind if kind=='fstring' else 'format';e['args']=args
        e['places'].append(place)
    for p in sorted((root/'Augustus').glob('*.py')):
        if p.name.startswith('test_'):continue
        for s,place,args,kind in py_texts(p,p.relative_to(root).as_posix()):add(s,place,args,kind if kind=='fstring' else ('format' if args else 'plain'))
    for p in sorted((root/'src').rglob('*')):
        if p.suffix not in ('.c','.inc','.h') or SKIP_DIRS & set(p.parts) or p.name in SKIP_FILES:continue
        for s,place,args in c_texts(p,p.relative_to(root).as_posix()):add(s,place,args,'format' if args else 'plain')
    for p in sorted((root/'creator-src').glob('*.cs')):
        for s,place,args in c_texts(p,p.relative_to(root).as_posix(),cs=True):add(s,place,args,'format' if args else 'plain')
    for e in entries.values():
        e['id']=hashlib.sha1(e['text'].encode('utf-8')).hexdigest()[:10]
        e['area']='editor' if all(x.startswith('creator-src/') for x in e['places']) else 'game' if all(x.startswith('src/') for x in e['places']) else 'room' if all(x.startswith('Augustus/') for x in e['places']) else 'mixed'
    return sorted(entries.values(),key=lambda e:(e['area'],e['places'][0]))

def main(argv):
    ap=argparse.ArgumentParser();ap.add_argument('--root',type=Path,default=Path(__file__).resolve().parents[1])
    ap.add_argument('--out',type=Path);ap.add_argument('--csv',type=Path);a=ap.parse_args(argv)
    entries=collect(a.root.resolve())
    out=a.out or a.root/'i18n/source.json';out.parent.mkdir(parents=True,exist_ok=True)
    out.write_text(json.dumps(dict(schema=1,languages=['ko','en','ru','de','es','fr'],entries=entries),ensure_ascii=False,indent=1),encoding='utf-8')
    if a.csv:
        # Keep the translations already in the sheet (matched by the Korean text) and the hand-written
        # 'composed' rows (sentences built at run time), so re-running the inventory never loses work.
        old={}
        if a.csv.exists():
            for r in csv.DictReader(a.csv.open(encoding='utf-8-sig',newline='')):old[r['ko']]=r
        L=['en','ru','de','es','fr']
        with a.csv.open('w',encoding='utf-8-sig',newline='') as f:
            w=csv.writer(f);w.writerow(['id','area','kind','ko']+L+['args','places'])
            for e in entries:
                prev=old.get(e['text'],{})
                w.writerow([e['id'],e['area'],e['kind'],e['text']]+[prev.get(l,'') for l in L]+[' | '.join(e['args']),' '.join(e['places'][:5])+(' …' if len(e['places'])>5 else '')])
            for r in old.values():
                if r.get('area')=='composed':w.writerow([r['id'],r['area'],r['kind'],r['ko']]+[r.get(l,'') for l in L]+[r.get('args',''),r.get('places','')])
    from collections import Counter
    print(len(entries),'texts',dict(Counter(e['area'] for e in entries)),dict(Counter(e['kind'] for e in entries)))
    return 0

if __name__=='__main__':sys.exit(main(sys.argv[1:]))
