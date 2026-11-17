"""Texts shown outside the game window (a console tool, a file in a report) in the player's language (2026-11-14).

The game and the scenario creator translate what they show at the moment they show it (src/core/mp_i18n.c,
creator-src/CreatorLang.cs). A console tool prints straight to the console, so it looks its texts up here, the same
way and in the same catalogs (i18n/<code>.tsv, built from i18n/review.csv): line by line an exact text, else a
template with {0} {1} / %d %s slots, and a slot that is itself a known text (or a text that fits a template, or a
list of known texts) is shown translated too. Anything unknown stays Korean. The code keeps writing Korean.

Language: AUGUSTUS_TEXT_LANG=ko|en|ru|de|es|fr, else the game's own setting (mp_language in augustus.ini, read the
way the creator reads it), else the Windows display language, else Korean.

  from ui_text import T;print(T('가져온 것: '+names))"""
import os,re
from pathlib import Path

HERE=Path(__file__).resolve().parent
CODES=['ko','en','ru','de','es','fr']
_SLOT=re.compile(r'\{(\d+)\}|%[-+ #0]*\d*(?:\.\d+)?(?:hh|h|ll|l|z)?[diuxXsScfgeEp]')
_state={}
_HANGUL=re.compile('['+chr(0xAC00)+'-'+chr(0xD7A3)+']')   # spelled as numbers so the text inventory does not list it


def _ini_language(root):
    folders=[]
    profile=Path(root)/'user-profile'
    try:
        marker=profile/'user_dir.txt'
        if marker.is_file():
            text=marker.read_text(encoding='utf-8',errors='replace').strip().strip('\0')
            folders.append(Path(text) if text else Path(root))
    except OSError:pass
    folders+=[profile,Path(root)]
    for folder in folders:
        for ini in (folder/'config'/'augustus.ini',folder/'augustus.ini'):
            try:
                if not ini.is_file():continue
                for line in ini.read_text(encoding='utf-8',errors='replace').splitlines():
                    key,eq,value=line.partition('=')
                    if eq and key.strip()=='mp_language':
                        value=value.strip()
                        return CODES[int(value)-1] if value.isdigit() and 1<=int(value)<=len(CODES) else 'ko'
            except OSError:continue
    return None


def _windows_language():
    if os.name!='nt':return None
    try:
        import ctypes
        primary=ctypes.windll.kernel32.GetUserDefaultUILanguage()&0x3ff
    except (AttributeError,OSError):
        return None
    return {0x12:'ko',0x09:'en',0x19:'ru',0x07:'de',0x0a:'es',0x0c:'fr'}.get(primary,'en')


def language(root=HERE):
    forced=os.environ.get('AUGUSTUS_TEXT_LANG','').strip()
    if forced in CODES:return forced
    return _ini_language(root) or _windows_language() or 'ko'


def _unescape(text):
    out=[];i=0
    while i<len(text):
        c=text[i]
        if c=='\\' and i+1<len(text):
            i+=1;n=text[i];out.append('\n' if n=='n' else '\t' if n=='t' else n)
        else:out.append(c)
        i+=1
    return ''.join(out)


def _load(code,root):
    exact={};templates=[]
    try:lines=(Path(root)/'i18n'/(code+'.tsv')).read_text(encoding='utf-8').splitlines()
    except OSError:return exact,templates
    for line in lines:
        if not line or line.startswith('#') or '\t' not in line:continue
        key,value=line.split('\t',1)
        if not value:continue
        key=_unescape(key);value=_unescape(value)
        found=list(_SLOT.finditer(key))
        if not found:exact[key]=value;continue
        pieces=[];order=[];start=0;printf=0
        for m in found:
            pieces.append(key[start:m.start()].replace('%%','%'))
            if m.group(1) is not None:order.append(int(m.group(1)))
            else:order.append(printf);printf+=1
            start=m.end()
        pieces.append(key[start:].replace('%%','%'))
        templates.append((pieces,order,value,sum(map(len,pieces))))
    templates.sort(key=lambda t:-t[3])
    return exact,templates


def _slot(word,table,depth):
    exact,templates=table
    if word in exact:return exact[word]
    if depth>=4 or word.isascii():return word
    done=_line(word,table,depth+1)   # a sentence of its own first ("A · B" may be one), a list of items after it
    if done is not None:return done
    if ', ' in word or '·' in word:
        parts=re.split('(, )' if ', ' in word else '(·)',word);out=[];changed=False
        for i,part in enumerate(parts):
            core=part.strip(' ')
            if i%2 or not core:out.append(part);continue
            done=_slot(core,table,depth+1);changed|=done!=core
            at=part.index(core);out.append(part[:at]+done+part[at+len(core):])
        return ''.join(out) if changed else word
    return word


def _line(line,table,depth=0):
    exact,templates=table
    if line in exact:return exact[line]
    for pieces,order,value,_ in templates:
        if not line.startswith(pieces[0]):continue
        p=len(pieces[0]);slots=[];ok=True
        for k in range(len(order)):
            after=pieces[k+1]
            if k+1==len(order):
                end=len(line)-len(after) if line.endswith(after) else -1
                if end<=p:ok=False;break
            else:
                end=line.find(after,p+1) if after else -1
                if end<=p:ok=False;break
            slots.append(line[p:end]);p=end+len(after)
        if not ok or p!=len(line):continue
        def fill(m):
            n=int(m.group(1))
            return _slot(slots[order.index(n)],table,depth) if n in order else m.group(0)
        return re.sub(r'\{(\d+)\}',fill,value)
    return None


def T(text,root=HERE):
    """text in the player's language (unknown parts stay Korean)."""
    if not text or not _HANGUL.search(text):return text
    key=str(Path(root))
    if key not in _state:
        code=language(root)
        _state[key]=(code,_load(code,root) if code!='ko' else ({},[]))
    code,table=_state[key]
    if code=='ko' or not (table[0] or table[1]):return text
    out=[]
    for line in text.split('\n'):
        done=_line(line,table)
        out.append(line if done is None else done)
    return '\n'.join(out)
