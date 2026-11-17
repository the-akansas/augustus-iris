"""Cash gifts on native receipt commands; never request a shared save."""
import base64,hashlib,secrets,json
from trade_post_ledger import Ledger
from post_recovery import native_receipts,reconcile
import joint_save

def initialize(db):
    import player_fleet
    player_fleet.initialize(db)
    import goods_live
    goods_live.initialize(db)
    db.execute('CREATE TABLE IF NOT EXISTS cash_transfer(id INTEGER PRIMARY KEY,contract TEXT UNIQUE)')
    db.execute('CREATE TABLE IF NOT EXISTS cash_scope(value TEXT NOT NULL)')
    db.execute('CREATE TABLE IF NOT EXISTS cash_attempt(command TEXT PRIMARY KEY,attempts INTEGER NOT NULL)')
    db.execute('CREATE TABLE IF NOT EXISTS cash_retry(command TEXT PRIMARY KEY,next_time REAL NOT NULL)')
    db.execute('CREATE TABLE IF NOT EXISTS cash_archive(city TEXT,epoch INTEGER,payload TEXT NOT NULL,hash TEXT NOT NULL,PRIMARY KEY(city,epoch))')

def scope(room,db):
    row=db.execute('SELECT value FROM cash_scope').fetchone()
    if row:return row[0]
    value=hashlib.sha256(json.dumps([room.coordinator.session,room.coordinator.scenario],sort_keys=True).encode()).hexdigest()
    db.execute('INSERT INTO cash_scope VALUES(?)',(value,));db.commit();return value

FAILED_TEXT={'escrow':'구매자의 자금이 모자라 거래가 취소되었습니다.','export':'판매자 교역소에 물품이 모자라 거래가 취소되었습니다.'}
def sync(db,ledger,transfer_id=None):
    for row in db.execute("SELECT c.id,c.contract FROM cash_transfer c JOIN live_transfer t ON t.id=c.id WHERE t.state NOT IN ('finished','rejected') AND (? IS NULL OR c.id=?)",(transfer_id,transfer_id)).fetchall():
        t=ledger.db.execute('SELECT * FROM post_contract WHERE id=?',(row['contract'],)).fetchone()
        if not t:continue
        phase=t['phase'];state='finished' if phase=='complete' else 'rejected' if phase=='cancelled' else 'offered' if phase=='offered' else 'travelling'
        transfer=db.execute('SELECT * FROM live_transfer WHERE id=?',(row['id'],)).fetchone()
        if transfer['resource']:
            import goods_live
            state=goods_live.state(db,transfer,t)
        if state not in ('finished','rejected','offered') and ledger.db.execute("SELECT 1 FROM post_command c JOIN cash_attempt a ON c.id=a.command WHERE c.contract=? AND c.state='pending' AND (SELECT COALESCE(SUM(a2.attempts),0) FROM post_command c2 JOIN cash_attempt a2 ON c2.id=a2.command WHERE c2.contract=c.contract AND c2.step=c.step)>=6",(row['contract'],)).fetchone():state='deferred'
        if transfer['resource'] and t['received'] and not db.execute('SELECT counted FROM goods_motion WHERE id=?',(row['id'],)).fetchone()[0]:
            import delivery_goals
            delivery_goals.delivered(db,transfer,exact_once=True)
            db.execute('UPDATE goods_motion SET counted=1 WHERE id=?',(row['id'],))
        if state=='deferred' and transfer['state']!='deferred':
            from pathlib import Path
            from network_diagnostics import record
            record(Path(ledger.db.execute('PRAGMA database_list').fetchone()[2]).parent,'trade_confirmation_pending',transfer_id=row['id'],phase=phase)
        db.execute('UPDATE live_transfer SET state=? WHERE id=?',(state,row['id']))
        if state=='rejected' and transfer['state']!='rejected' and not transfer['error']:
            # Say why an accepted deal fell through: the city could not hand over what it owed.
            failed=ledger.db.execute("SELECT step FROM post_command WHERE contract=? AND state='unapplied' AND step IN ('export','escrow') AND id NOT IN (SELECT command FROM post_forgiven) ORDER BY attempt LIMIT 1",(row['contract'],)).fetchone()
            if failed:db.execute('UPDATE live_transfer SET error=? WHERE id=?',(FAILED_TEXT[failed[0]],row['id']))
    db.commit()

def mapped(db,t):return t and db.execute('SELECT 1 FROM cash_transfer WHERE id=?',(t['id'],)).fetchone()

def ready(room,cities):
    entries=getattr(room,'cash_ready',{})
    return all(c in entries and room.clock()-entries[c]<30 for c in cities)

def trade(room,db,city,r,t):
    if r['op']!='live_status' and r.get('id')!=t['id']:raise ValueError('stale offer')
    if city not in (t['sender'],t['receiver']):raise ValueError('not a transfer participant')
    ledger=Ledger(room.coordinator.path,room.coordinator.scenario['cities'],transport=True)
    try:
        ledger.offer(t['sender'],t['request'],t['receiver'],t['resource'],t['quantity'],t['money'],route='sea' if t['resource'] and db.execute('SELECT route FROM goods_motion WHERE id=?',(t['id'],)).fetchone()[0]==3 else 'land')
        if t['resource']:
            import goods_live
            return goods_live.trade(room,db,city,r,t,ledger)
        if r['op']=='live_accept':
            if not ready(room,(t['sender'],t['receiver'])):raise ValueError('both engines required')
            if joint_save.pending(db):raise ValueError('save in progress')
            ledger.accept(city,t['request'],room.active_cities(db))
        elif r['op']=='live_reject':ledger.cancel(city,t['request'])
        elif r['op']!='live_status':raise ValueError('unsupported cash operation')
        sync(db,ledger,t['id']);out=dict(db.execute('SELECT * FROM live_transfer WHERE id=?',(t['id'],)).fetchone());out['cash_live']=True
        return out
    finally:ledger.close()

def settle_throne(room,db,city):
    """A city's receipts may have settled a throne spend (one-sided debit): apply its effect once (throne_play)."""
    import throne_play
    if not throne_play.is_test(room.coordinator.scenario):return
    tick=max(getattr(room,'progress',{}).get(city,(0,0))[0],0)
    try:
        if throne_play.settle(db,room.coordinator.scenario,tick):db.commit()
    except ValueError:db.rollback()   # retried on the next report or throne poll; never blocks the city's cash

def materialize(room,db):
    ledger=Ledger(room.coordinator.path,room.coordinator.scenario['cities'],transport=True)
    try:
        for t in db.execute("SELECT * FROM live_transfer WHERE id IN (SELECT id FROM cash_transfer) AND state NOT IN ('finished','rejected')").fetchall():
            ledger.offer(t['sender'],t['request'],t['receiver'],t['resource'],t['quantity'],t['money'],route='sea' if t['resource'] and db.execute('SELECT route FROM goods_motion WHERE id=?',(t['id'],)).fetchone()[0]==3 else 'land')
    finally:ledger.close()

def request(room,db,city,credential,r):
    if not room.started or not db.execute('SELECT 1 FROM play_session WHERE city=?',(city,)).fetchone():raise ValueError('game not running')
    if not hasattr(room,'cash_exchange'):room.cash_exchange={};room.cash_epoch=secrets.token_hex(16);room.cash_ready={}
    value=scope(room,db);cities=room.coordinator.scenario['cities'];old=room.cash_exchange.get(city)
    if old and old['credential']!=credential:old=None;room.cash_ready.pop(city,None)
    if r['op']=='cash_challenge':
        if not old or room.clock()-old['created']>30 or 'result' in old:
            old=dict(credential=credential,created=room.clock(),nonce=secrets.token_hex(16));room.cash_exchange[city]=old
        return dict(epoch=room.cash_epoch,nonce=old['nonce'],roster=value,slot=cities.index(city),cities=cities)
    if r['op']!='cash_report' or not old or r.get('epoch')!=room.cash_epoch or r.get('nonce')!=old['nonce'] or room.clock()-old['created']>30:raise ValueError('stale cash report')
    if joint_save.pending(db):return dict(state='saving',resend=[])
    text=r.get('piece')
    if not isinstance(text,str) or len(text)!=85336:raise ValueError('cash frame size')
    piece=base64.b64decode(text,validate=True);fingerprint=hashlib.sha256(piece).hexdigest()
    if 'result' in old:
        if old['hash']!=fingerprint:raise ValueError('conflicting cash report')
        return old['result']
    # One city alone (2026-11-15): the ledger takes a roster of one; it only ever holds that city's own throne debits.
    # (2026-11-14 this returned at once: the ledger then refused a roster of one and every report was refused.)
    ledger=Ledger(room.coordinator.path,cities,transport=True)
    try:
        try:
            from post_recovery import archived_receipts,archive_request
            current_proof=native_receipts(piece,value,cities.index(city),cities)
            proof,receipt_epoch=archived_receipts(ledger.db,city,piece,current_proof)
        except ValueError:
            room.cash_ready.pop(city,None)
            with ledger.db:ledger.db.execute("INSERT OR REPLACE INTO post_recovery_hold VALUES(?,'*','invalid_native_book')",(city,))
            result=dict(state='needs_city_recovery',resend=[])
        else:
            result=reconcile(ledger,city,proof,set(room.active_cities(db)))
            import goods_live
            goods_live.retry_confirmed_failures(ledger,city)
            result['resend']=ledger.commands(city,set(room.active_cities(db))) if result['state']=='reconciled' else result.get('resend',[])
            # Six deliveries without a native receipt isolate this transaction.
            # Late valid proof still settles it; no inferred debit, refund or room rollback.
            resend=[]
            with ledger.db:
                for command in result.get('resend',[]):
                    import goods_live
                    command=goods_live.decorate(db,command)
                    if command is None:continue
                    row=ledger.db.execute('SELECT attempts FROM cash_attempt WHERE command=?',(command['id'],)).fetchone()
                    attempts=row[0] if row else 0
                    delivered=ledger.db.execute('SELECT COALESCE(SUM(a.attempts),0) FROM post_command c JOIN cash_attempt a ON c.id=a.command WHERE c.contract=? AND c.step=?',(command['contract'],command['step'])).fetchone()[0]
                    import time
                    now=time.time()
                    due=ledger.db.execute('SELECT next_time FROM cash_retry WHERE command=?',(command['id'],)).fetchone()
                    if due and now<due[0]:continue
                    if attempts>=6:attempts=0
                    ledger.db.execute('INSERT OR REPLACE INTO cash_retry VALUES(?,?)',(command['id'],now+min(30,2**attempts)))
                    ledger.db.execute('INSERT OR REPLACE INTO cash_attempt VALUES(?,?)',(command['id'],attempts+1))
                    resend.append(dict(command,epoch=receipt_epoch))
                    break # Native mailbox consumes exactly one command per proof exchange.
            if result['state']=='reconciled':
                compact=archive_request(ledger.db,city,piece,current_proof,receipt_epoch)
                if compact:resend=[compact]
            result['resend']=resend
            if result['state']=='reconciled':room.cash_ready[city]=room.clock()
            else:room.cash_ready.pop(city,None)
        sync(db,ledger)
        settle_throne(room,db,city)
        old.update(hash=fingerprint,result=result);return result
    finally:ledger.close()
