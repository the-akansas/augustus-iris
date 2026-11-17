"""Receipt exchange behind the real Lobby credential check and room lock.

Internal protocol gate is server-owned, never enabled by a network request.
Current native playable engine is not capable; no legacy effects are replayed.
This is a recovery RPC, not a new trade UI or city-state repair mechanism.
"""
import base64,hashlib,json,secrets
from trade_post_ledger import Ledger
from post_recovery import native_receipts,reconcile

TTL=30.0

def identity(room):
    co=room.coordinator
    return hashlib.sha256(json.dumps([co.session,co.scenario['sha256'],co.scenario['cities']],separators=(',',':')).encode()).hexdigest()

def request(room,db,city,credential,r):
    if getattr(room.coordinator,'post_protocol',0)!=1:
        return dict(state='unsupported',protocol=0)
    if not room.started or not db.execute('SELECT 1 FROM play_session WHERE city=?',(city,)).fetchone():
        raise ValueError('game not running')
    if db.execute('SELECT 1 FROM live_transfer LIMIT 1').fetchone():
        raise ValueError('legacy room cannot switch trade protocols')
    if r.get('schema')!=1 or type(r.get('schema')) is not int:
        raise ValueError('receipt schema')
    if not hasattr(room,'post_exchange'):
        room.post_exchange={};room.post_epoch=secrets.token_hex(16)
    scope=identity(room);cities=room.coordinator.scenario['cities'];slot=cities.index(city)
    old=room.post_exchange.get(city)
    if old and old['credential']!=credential:
        old=None;room.post_exchange.pop(city,None)
    op=r['op']
    if op=='post_challenge':
        # Repeated polls reuse an unconsumed challenge; bounded one/city memory.
        if not old or room.clock()-old['created']>TTL or old.get('result') is not None:
            old=dict(nonce=secrets.token_hex(16),created=room.clock(),credential=credential)
            room.post_exchange[city]=old
        return dict(state='report_required',protocol=1,epoch=room.post_epoch,nonce=old['nonce'],roster=scope,slot=slot)
    if op!='post_report':raise ValueError('unknown receipt operation')
    if not old or r.get('epoch')!=room.post_epoch or r.get('nonce')!=old['nonce'] or room.clock()-old['created']>TTL:
        raise ValueError('stale receipt challenge')
    text=r.get('piece')
    if not isinstance(text,str) or len(text)!=85336:
        raise ValueError('receipt frame size')
    try:piece=base64.b64decode(text,validate=True)
    except Exception:raise ValueError('receipt encoding') from None
    digest=hashlib.sha256(piece).hexdigest()
    if old.get('result') is not None:
        if digest!=old['digest']:raise ValueError('conflicting receipt retransmission')
        return old['result']
    ledger=Ledger(room.coordinator.path,cities)
    try:
        try:
            proofs=native_receipts(piece,scope,slot,cities)
        except ValueError:
            # Do not erase or manufacture a receipt, or touch game balances.
            with ledger.db:
                ledger.db.execute("INSERT OR REPLACE INTO post_recovery_hold VALUES(?,'*','invalid_native_book')",(city,))
            result=dict(state='needs_city_recovery',applied_acks=[],resend=[],blocked=[],reason='invalid_native_book')
        else:
            result=reconcile(ledger,city,proofs,set(room.active_cities(db)))
        result=dict(result,protocol=1,epoch=room.post_epoch,nonce=old['nonce'])
        old.update(digest=digest,result=result)
        return result
    finally:ledger.close()
