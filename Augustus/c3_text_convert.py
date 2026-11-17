"""Convert a player's own Caesar III text files (c3.eng, c3_mm.eng) into the game's Korean letter encoding
(CP949 plus the multilingual letters kept in its user-defined area), so a Russian, German, French, Spanish or
English Caesar III shows its own original texts in this Korean-based build (user 2026-11-13: multilingual).

We never ship those texts (copyright): each player's own files are converted on their own PC, into the private
game data copy. The original install is only read.

File layout (src/core/lang.c):
  c3.eng     28-byte header, 1000 x (offset i32, in_use i32), text blob (NUL-terminated strings)
  c3_mm.eng  24-byte header, 400 x 80-byte message entry (text offsets at 60 video, 68 title, 72 subtitle,
             76 content), message blob
Offsets point into the blob, so the converted blob is rebuilt string by string and every offset is remapped."""
import re,struct
from pathlib import Path

HERE=Path(__file__).resolve().parent

def _extra_letters():
    """Letters the game keeps in the CP949 user-defined area: slot k = 0xC9A1+k (k<94) or 0xFEA1+k-94.
    The list lives in the engine (src/graphics/korean_extra_chars.h); a copy ships as i18n/extra-letters.txt."""
    for p in (HERE/'i18n'/'extra-letters.txt',HERE.parent/'src'/'graphics'/'korean_extra_chars.h'):
        try:text=p.read_text(encoding='utf-8')
        except OSError:continue
        m=re.search(r'korean_extra_chars\[[^\]]*\]\s*=\s*\{([^}]*)\}',text)
        codes=[int(x,16) for x in re.findall(r'0x([0-9a-fA-F]+)',m.group(1) if m else text)]
        if codes:return {chr(c):(0xC9A1+k if k<94 else 0xFEA1+k-94) for k,c in enumerate(codes)}
    raise FileNotFoundError('multilingual letter list missing (i18n/extra-letters.txt)')

def encoder():
    extra=_extra_letters()
    cache={}
    def one(ch):
        if ch in cache:return cache[ch]
        o=ord(ch)
        if o<0x80:b=bytes([o])
        elif ch=='·':b=b'\xa1\xa4'                       # the engine's centred dot
        elif ch in extra:c=extra[ch];b=bytes([c>>8,c&0xff])
        elif o>=0x800:                                        # KS X 1001 letters and symbols (3-byte UTF-8)
            try:b=ch.encode('cp949')
            except UnicodeEncodeError:b=b'?'
            if len(b)!=2 or not (0xa1<=b[0]<=0xfe and 0xa1<=b[1]<=0xfe):b=b'?'
        else:b=b'?'                                           # what the engine also does for unknown letters
        cache[ch]=b;return b
    return lambda text:b''.join(one(c) for c in text)

def guess_codepage(blob):
    """Russian Caesar III uses Windows-1251; the western releases use Windows-1252. Russian text is mostly
    letters in 0xC0-0xFF; western text has only occasional accented letters."""
    high=sum(1 for b in blob if b>=0xc0);letters=sum(1 for b in blob if 0x41<=(b|0x20)<=0x7a or b>=0xc0)
    return 'cp1251' if letters and high/letters>0.3 else 'cp1252'

def _convert_strings(blob,offsets,codepage,enc):
    """Rebuild a blob: every referenced string decoded from the original code page and re-encoded."""
    out=bytearray();moved={}
    for off in sorted(set(o for o in offsets if 0<=o<len(blob))):
        end=blob.find(b'\0',off);end=len(blob) if end<0 else end
        moved[off]=len(out);out+=enc(blob[off:end].decode(codepage,errors='replace').replace('�','?'))+b'\0'
    return bytes(out),moved

TEXT_ENTRIES,MESSAGE_ENTRIES=1000,400

def convert_text(data,codepage=None,enc=None):
    enc=enc or encoder();header,index,blob=data[:28],data[28:28+TEXT_ENTRIES*8],data[28+TEXT_ENTRIES*8:]
    pairs=[struct.unpack_from('<ii',index,8*i) for i in range(TEXT_ENTRIES)]
    codepage=codepage or guess_codepage(blob)
    # A group's strings follow each other in the blob: lang.c walks from the group offset over NUL ends.
    # So every string start (not just the group starts) is kept, in order.
    starts=[0]+[i+1 for i,b in enumerate(blob) if b==0 and i+1<len(blob)]
    new,moved=_convert_strings(blob,starts,codepage,enc)
    out=bytearray(header)
    for off,used in pairs:out+=struct.pack('<ii',moved.get(off,off if not used else 0),used)
    return bytes(out+new),codepage

def convert_messages(data,codepage=None,enc=None):
    """c3_mm.eng: 24-byte header, 400 entries of 80 bytes, then the blob (layout read by lang.c parse_message).
    Offsets of 0 mean 'no text'."""
    enc=enc or encoder();ENTRY=80;head=24;FIELDS=(60,68,72,76)
    header,index,blob=data[:head],data[head:head+MESSAGE_ENTRIES*ENTRY],data[head+MESSAGE_ENTRIES*ENTRY:]
    codepage=codepage or guess_codepage(blob)
    texts=[]
    for i in range(MESSAGE_ENTRIES):texts+=[struct.unpack_from('<i',index,i*ENTRY+f)[0] for f in FIELDS]
    new,moved=_convert_strings(blob,[t for t in texts if t>0],codepage,enc)
    out=bytearray(header)
    for i in range(MESSAGE_ENTRIES):
        e=bytearray(index[i*ENTRY:(i+1)*ENTRY])
        for f in FIELDS:
            x=struct.unpack_from('<i',e,f)[0]
            if x>0:struct.pack_into('<i',e,f,moved.get(x,0))
        out+=e
    return bytes(out+new),codepage

NEW_GAME={b'New Game':('en','cp1252'),b'Nouvelle partie':('fr','cp1252'),b'Neues Spiel':('de','cp1252'),
 b'Nueva partida':('es','cp1252'),b'Nuova partita':('it','cp1252'),b'Novo jogo':('pt','cp1252'),b'Nytt spel':('sv','cp1252'),
 bytes([0xcd,0xee,0xe2,0xe0,0xff,0x20,0xe8,0xe3,0xf0,0xe0]):('ru','cp1251'),bytes([0xcd,0xee,0xe2,0xe0,0x20,0xe3,0xf0,0xe0]):('uk','cp1251'),
 bytes([0xbb,0xf5,0x20,0xb0,0xd4,0xc0,0xd3]):('ko',None)}   # same check as the engine (src/core/locale.c)

def text_string(data,group,index):
    """lang_get_string() of the engine on a c3.eng image."""
    off=struct.unpack_from('<i',data,28+group*8)[0];blob=data[28+TEXT_ENTRIES*8:];i=off;prev=0
    while index>0 and i<len(blob):
        if blob[i]==0 and (prev>=32 or prev==0):index-=1
        prev=blob[i];i+=1
    while i<len(blob) and 0<blob[i]<32:i+=1
    end=blob.find(b'\0',i);return blob[i:end if end>=0 else len(blob)]

def original_language(data):
    """(code, code page) of a player's c3.eng, or (None, None) when it is not one we can convert."""
    if len(data)<28+TEXT_ENTRIES*8 or not data.startswith(b'C3 textfile.'):return None,None
    return NEW_GAME.get(text_string(data,1,1),(None,None))

OWN_TEXT,OWN_MESSAGES='c3-own.eng','c3_mm-own.eng'   # read by src/core/lang.c when a non-Korean language is chosen

def convert_folder(source,target):
    """Write the player's own Caesar III texts, converted, as c3-own.eng / c3_mm-own.eng into target.
    Korean or unsupported originals (Polish, Czech, Greek, Asian) are left out: the Korean texts stay.
    Returns the original language code or None."""
    files={p.name.lower():p for p in Path(source).iterdir() if p.is_file()}
    text,mm=files.get('c3.eng'),files.get('c3_mm.eng')
    if not text or not mm:return None
    data=text.read_bytes();code,codepage=original_language(data)
    if not codepage:return None
    enc=encoder()
    try:
        converted,_=convert_text(data,codepage,enc);messages,_=convert_messages(mm.read_bytes(),codepage,enc)
    except (struct.error,ValueError):return None
    (Path(target)/OWN_TEXT).write_bytes(converted);(Path(target)/OWN_MESSAGES).write_bytes(messages)
    return code
