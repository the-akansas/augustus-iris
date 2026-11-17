from windows_paths import sqlite_readonly_uri
"""Host-authoritative reconciliation for the experimental post ledger.

Transport must supply authenticated city and ordered room roster. A report is a
fresh, checksum-validated native book, NOT a stale auto-save selected by date.
This module never edits city money/stock, triggers a game save or alters clocks.
Not wired to the legacy online trade bridge yet.
"""
import hashlib
import os
from pathlib import Path
import re
import sqlite3
import struct
import zlib
from contextlib import closing

STEPS = ('export', 'escrow', 'receive', 'pay', 'refund_goods', 'refund_money')


def native_receipts(piece, roster_hash, slot, cities):
    """Read review91's exact native SAV piece; reject any ambiguous evidence."""
    if not isinstance(piece, bytes) or len(piece) != 64000:
        raise ValueError('receipt length')
    if not 0 <= slot < len(cities) <= 8 or not re.fullmatch('[0-9a-f]{64}', roster_hash):
        raise ValueError('room identity')
    if zlib.crc32(piece[:-4]) != struct.unpack_from('<I', piece, 63996)[0]:
        raise ValueError('receipt checksum')
    magic, version, active, owner, length = struct.unpack_from('<4sIIII', piece)
    if (magic, active, owner) != (b'MPCS', 1, slot) or version not in (1,2) or not 2188 <= length <= 63976:
        raise ValueError('city identity or format')
    if any(piece[20+length+(4 if version==2 else 0):-4]):
        raise ValueError('receipt padding')
    book = piece[20:20+length]
    if book[:4] != b'MPT1' or book[4:68] != roster_hash.encode():
        raise ValueError('roster mismatch')
    count, = struct.unpack_from('<I', book, 68)
    if count > 512 or length != 2188 + count * 116 or zlib.crc32(book[:-4]) != struct.unpack_from('<I', book, length-4)[0]:
        raise ValueError('book checksum or size')
    result = {}
    for i in range(count):
        raw, peer, step, resource, amount, applied = struct.unpack_from('<96siiiii', book, 2184+i*116)
        key = raw.split(b'\0', 1)[0]
        # peer == owner: a one-sided money step (throne debit or its refund, trade_post_ledger.stage_debit), never goods
        if b'\0' not in raw or not re.fullmatch(rb'[a-z0-9:_]+', key) or not 0 <= peer < len(cities) or (peer == owner and (resource or step not in (1, 4))):
            raise ValueError('command identity')
        if not 1 <= step <= 6 or not 0 <= resource < 22 or not 1 <= amount <= 1000000 or applied not in (0, 1):
            raise ValueError('command payload')
        if resource and (amount > 32 or step in (2,4,6)):
            raise ValueError('goods payload')
        key = key.decode()
        if key in result:
            raise ValueError('duplicate receipt')
        result[key] = dict(peer=cities[peer], step=STEPS[step-1], asset=resource, amount=amount, applied=bool(applied))
    return result


def reconcile(ledger, city, receipts, online):
    """Resolve lost ACKs. Missing evidence never means an effect was undone.

    Caller serializes this operation with normal commands on the room's lock.
    Conflicting contracts are isolated; unrelated contracts can still complete.
    """
    ledger._city(city)
    rows = {r['id']: dict(r) for r in ledger.db.execute('SELECT * FROM post_command WHERE city=?', (city,))}
    unknown = sorted(set(receipts)-set(rows))
    if unknown:
        with ledger.db:
            ledger.db.execute("INSERT OR REPLACE INTO post_recovery_hold VALUES(?,'*','host_record_behind')", (city,))
        return dict(state='host_record_behind', unknown=unknown, applied_acks=[], resend=[], blocked=[])
    blocked = set()
    # A city that came back from an older checkpoint never saw these outcomes (it had left).
    forgiven = {r[0] for r in ledger.db.execute('SELECT command FROM post_forgiven WHERE city=?', (city,))}
    for key, row in rows.items():
        proof = receipts.get(key)
        t = ledger._contract(city, row['contract'])
        peer = t['receiver'] if city == t['sender'] else t['sender']
        if proof is None:
            if row['state'] != 'pending' and key not in forgiven:
                blocked.add(row['contract'])
            continue
        if any(proof.get(k) != v for k,v in dict(peer=peer, step=row['step'], asset=row['asset'], amount=row['amount']).items()) or type(proof.get('applied')) is not bool:
            blocked.add(row['contract'])
        elif row['state'] != 'pending' and proof['applied'] != (row['state']=='applied') and key not in forgiven:
            blocked.add(row['contract'])
    with ledger.db:
        ledger.db.execute('DELETE FROM post_recovery_hold WHERE city=?',(city,))
        for tid in blocked:
            ledger.db.execute('INSERT INTO post_recovery_hold VALUES(?,?,?)',(city,tid,'city_receipt_conflict'))
    confirmed=[]
    for key,row in rows.items():
        if row['contract'] not in blocked and row['state']=='pending' and key in receipts:
            if ledger.recovery_held(ledger._contract(city,row['contract'])):
                continue
            ledger.ack(city,key,row['digest'],receipts[key]['applied'])
            confirmed.append(key)
    resend=[r for r in ledger.commands(city,online) if r['contract'] not in blocked]
    return dict(state='needs_city_recovery' if blocked else 'reconciled', applied_acks=confirmed, resend=resend, blocked=sorted(blocked), unknown=[])


def restore_host_copy(candidates, destination, expected_sha256, cities):
    """Recover an exact host checkpoint from local/participant replica files.

    expected_sha256 MUST come from the trusted matching room checkpoint manifest,
    never from the candidate itself. Priority order is host copy then replicas.
    Does not merge stale checkpoints with current cities or infer missing effects.
    """
    destination=Path(destination).resolve()
    if destination.exists() or not re.fullmatch('[0-9a-f]{64}', expected_sha256):
        raise ValueError('new recovery destination and trusted checksum required')
    for candidate in candidates:
        candidate=Path(candidate)
        try:
            data=candidate.read_bytes()
        except OSError:
            continue
        if hashlib.sha256(data).hexdigest()!=expected_sha256:
            continue
        # Stage exact bytes, validate before publishing; don't modify evidence.
        import uuid
        stage=destination.with_name(destination.name+'.'+uuid.uuid4().hex+'.staging')
        created=False
        try:
            with stage.open('xb') as f:
                created=True
                f.write(data);f.flush();os.fsync(f.fileno())
            with closing(sqlite3.connect(sqlite_readonly_uri(stage),uri=True)) as db:
                if db.execute('PRAGMA integrity_check').fetchone()[0]!='ok':
                    raise ValueError('database corruption')
                import json
                version, roster=db.execute('SELECT version,cities FROM post_meta').fetchone()
                if version!=1 or json.loads(roster)!=list(cities):
                    raise ValueError('checkpoint roster')
            # Exclusive destination creation: never overwrite a live host DB.
            if os.name == 'nt':
                os.rename(stage,destination)  # Windows refuses an existing target.
            else:
                os.link(stage,destination)
            return str(candidate)
        finally:
            if created and stage.exists(): stage.unlink()
    raise ValueError('no matching healthy host replica')


def receipt_epoch(piece):
    version,=struct.unpack_from('<I',piece,4)
    length,=struct.unpack_from('<I',piece,16)
    return struct.unpack_from('<I',piece,20+length)[0] if version==2 else 0

def forgive(db,cities):
    """Cities restored from an older (retained) checkpoint lack the receipts of steps
    settled after it. Those steps stay settled for everyone else; the city is not held."""
    if not cities or not db.execute("SELECT 1 FROM sqlite_master WHERE name='post_forgiven'").fetchone():return
    db.executemany("INSERT OR IGNORE INTO post_forgiven SELECT id,city FROM post_command WHERE city=? AND state!='pending'",[(c,) for c in cities])

def archived_receipts(db,city,piece,proof):
    """Old outcomes remain in the host checkpoint; native epoch rejects replay.
    A city may advance ONLY through a previously persisted exact-book archive.
    An older city save is still reconciled against its own epoch and held if stale.
    """
    import json
    epoch=receipt_epoch(piece)
    rows=db.execute('SELECT * FROM cash_archive WHERE city=? AND epoch<? ORDER BY epoch',(city,epoch)).fetchall()
    if len(rows)!=epoch or any(r['epoch']!=i for i,r in enumerate(rows)):raise ValueError('unknown receipt epoch')
    merged={}
    for row in rows:
        for key,value in json.loads(row['payload']).items():
            if key in merged:raise ValueError('duplicate archived command')
            merged[key]=value
    if set(merged)&set(proof):raise ValueError('archived command replay')
    return dict(merged,**proof),epoch

def archive_request(db,city,piece,proof,epoch):
    import json
    if len(proof)<400:return None
    rows={r['id']:r for r in db.execute('SELECT id,state FROM post_command WHERE city=?',(city,))}
    forgiven={r[0] for r in db.execute('SELECT command FROM post_forgiven WHERE city=?',(city,))}
    if any(k not in rows or rows[k]['state']=='pending' or ((rows[k]['state']=='applied')!=v['applied'] and k not in forgiven) for k,v in proof.items()):return None
    payload=json.dumps(proof,sort_keys=True,separators=(',',':'))
    digest=hashlib.sha256(piece).hexdigest()
    old=db.execute('SELECT * FROM cash_archive WHERE city=? AND epoch=?',(city,epoch)).fetchone()
    if old and old['payload']!=payload and not forgiven:raise ValueError('archive snapshot conflict')
    # A city back from an older checkpoint archives its own book again from that point.
    with db:db.execute('INSERT OR REPLACE INTO cash_archive VALUES(?,?,?,?)',(city,epoch,payload,digest))
    return dict(compact=True,epoch=epoch,hash=digest)
