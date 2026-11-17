"""Player trade rules (23차): offers use the clock's freshness, server reasons read in Korean."""
import sys
from pathlib import Path
A=Path(__file__).resolve().parents[1]/'Augustus'
sys.path.insert(0,str(A))

def test_offer_freshness_matches_clock():
    src=(A/'live_trade.py').read_text(encoding='utf8')
    assert '>=1.5 for c in cities' not in src and 'FRESH_SECONDS' in src

def test_trade_errors_are_korean():
    from game_bridge import Bridge
    for code in ('both engines required','amount','invalid recipient','stale offer','already committed','participant unavailable','both trading posts required'):
        text=Bridge.error_message(code)
        assert text!=Bridge.error_message('__unknown__') and any('가'<=c<='힣' for c in text),code

if __name__=='__main__':
    for n,f in list(globals().items()):
        if n.startswith('test_'):f();print('ok',n)
