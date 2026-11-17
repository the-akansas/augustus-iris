"""Isolated replacement protocol for city-bound player trading posts.

NOT wired into the live game yet. The engine adapter must persist an immutable
command receipt in the SAME city snapshot as its inventory/cash change. An ACK
means that operation actually happened, not merely that it was requested.
Caller supplies authenticated city identity and online roster. No socket, timer,
joint-save request, simulation grant, or ordinary-warehouse reservation lives here.
"""
import hashlib
import json
import sqlite3
from contextlib import closing


def encode(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'), ensure_ascii=False)


def integer(value, low, high):
    return type(value) is int and low <= value <= high


class Ledger:
    def __init__(self, path, cities, transport=False):
        self.transport=transport
        # One city alone is a valid roster (2026-11-15): it only ever has one-sided throne debits (stage_debit).
        if not 1 <= len(cities) <= 8 or len(set(cities)) != len(cities):
            raise ValueError('city roster')
        if any(not isinstance(c, str) or not 1 <= len(c) <= 64 for c in cities):
            raise ValueError('city identifier')
        self.cities = tuple(cities)
        self.db = sqlite3.connect(path, timeout=10)
        self.db.row_factory = sqlite3.Row
        self.db.execute('PRAGMA foreign_keys=ON')
        self.db.executescript('''
        CREATE TABLE IF NOT EXISTS post_meta(version INTEGER NOT NULL, cities TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS post_sequence(id INTEGER PRIMARY KEY CHECK(id=1), value INTEGER NOT NULL);
        CREATE TABLE IF NOT EXISTS post_recovery_hold(city TEXT NOT NULL,contract TEXT NOT NULL,reason TEXT NOT NULL,PRIMARY KEY(city,contract));
        CREATE TABLE IF NOT EXISTS post_binding(
          city TEXT,peer TEXT,building INTEGER, generation INTEGER,active INTEGER,
          PRIMARY KEY(city,peer));
        CREATE UNIQUE INDEX IF NOT EXISTS post_site ON post_binding(city,building)
          WHERE active=1;
        CREATE TABLE IF NOT EXISTS post_contract(
          id TEXT PRIMARY KEY,sender TEXT NOT NULL,receiver TEXT NOT NULL,
          resource INTEGER NOT NULL,quantity INTEGER NOT NULL,money INTEGER NOT NULL,
          route TEXT NOT NULL,phase TEXT NOT NULL,cancel INTEGER NOT NULL DEFAULT 0,
          exported INTEGER NOT NULL DEFAULT 0,escrow INTEGER NOT NULL DEFAULT 0,
          received INTEGER NOT NULL DEFAULT 0,paid INTEGER NOT NULL DEFAULT 0,
          refunded_goods INTEGER NOT NULL DEFAULT 0,refunded_money INTEGER NOT NULL DEFAULT 0);
        CREATE TABLE IF NOT EXISTS post_command(
          id TEXT PRIMARY KEY,contract TEXT NOT NULL REFERENCES post_contract(id),
          city TEXT NOT NULL,step TEXT NOT NULL,asset INTEGER NOT NULL,amount INTEGER NOT NULL,
          attempt INTEGER NOT NULL,state TEXT NOT NULL,digest TEXT NOT NULL,
          UNIQUE(contract,step,attempt));
        CREATE UNIQUE INDEX IF NOT EXISTS post_pending ON post_command(contract) WHERE state='pending';
        CREATE TABLE IF NOT EXISTS post_forgiven(command TEXT PRIMARY KEY REFERENCES post_command(id),city TEXT NOT NULL);
        ''')
        row = self.db.execute('SELECT * FROM post_meta').fetchone()
        if row and (row['version'] != 1 or json.loads(row['cities']) != list(cities)):
            self.db.close()
            raise ValueError('ledger version or roster changed')
        if not row:
            with self.db:
                self.db.execute('INSERT INTO post_meta VALUES(1,?)', (encode(cities),))

    def close(self):
        self.db.close()

    def _city(self, city):
        if city not in self.cities:
            raise ValueError('unknown city')

    def _contract(self, city, tid):
        self._city(city)
        t = self.db.execute('SELECT * FROM post_contract WHERE id=?', (tid,)).fetchone()
        if not t or city not in (t['sender'], t['receiver']):
            raise ValueError('not a transaction participant')
        return dict(t)

    def bind(self, city, peer, building, generation):
        self._city(city); self._city(peer)
        if city == peer or not integer(building, 1, 100000) or not integer(generation, 1, 2**31-1):
            raise ValueError('post identity')
        with self.db:
            self.db.execute('INSERT INTO post_binding VALUES(?,?,?,?,1) '
                            'ON CONFLICT(city,peer) DO UPDATE SET building=excluded.building, '
                            'generation=excluded.generation,active=1',
                            (city, peer, building, generation))

    def demolish(self, city, building, generation):
        self._city(city)
        with self.db:
            self.db.execute('UPDATE post_binding SET active=0 WHERE city=? AND building=? AND generation=?',
                            (city, building, generation))
        # Deliberately do not delete contracts, receipts, cargo, or payments.

    def has_post(self, city, peer):
        return bool(self.db.execute('SELECT 1 FROM post_binding WHERE city=? AND peer=? AND active=1',
                                    (city, peer)).fetchone())

    def offer(self, city, tid, receiver, resource, quantity, money, route='land'):
        with self.db:
            stage_offer(self.db,self.cities,city,tid,receiver,resource,quantity,money,route)
        return self.status(city,tid)

    def _queue(self, t, step):
        receiver_step = step in ('escrow', 'receive', 'refund_money')
        city = t['receiver'] if receiver_step else t['sender']
        goods_step = step in ('export', 'receive', 'refund_goods')
        asset = t['resource'] if goods_step else 0
        amount = t['quantity'] if goods_step and asset else t['money']
        attempt = self.db.execute('SELECT count(*) FROM post_command WHERE contract=? AND step=?',
                                  (t['id'], step)).fetchone()[0] + 1
        key = t['id'] + ':' + step + ':' + str(attempt)
        digest = hashlib.sha256(encode([key, city, step, asset, amount]).encode()).hexdigest()
        self.db.execute("INSERT INTO post_command VALUES(?,?,?,?,?,?,?,'pending',?)",
                        (key, t['id'], city, step, asset, amount, attempt, digest))
        self.db.execute('UPDATE post_contract SET phase=? WHERE id=?', (step, t['id']))

    def accept(self, city, tid, online):
        with self.db:
            self.db.execute('BEGIN IMMEDIATE')
            t = self._contract(city, tid)
            if city != t['receiver']:
                raise ValueError('recipient consent required')
            if t['phase'] == 'cancelled':
                raise ValueError('cancelled offer')
            if t['phase'] == 'offered':
                if not {t['sender'], t['receiver']} <= set(online):
                    raise ValueError('participant unavailable')
                if t['resource'] and not self.transport and not (self.has_post(city, t['sender']) and self.has_post(t['sender'], city)):
                    raise ValueError('both trading posts required')
                self._queue(t, 'export')
        return self.status(city, tid)

    def recovery_held(self, t):
        return bool(self.db.execute("SELECT 1 FROM post_recovery_hold WHERE contract=? OR (contract='*' AND city IN (?,?))", (t['id'],t['sender'],t['receiver'])).fetchone())

    def commands(self, city, online):
        self._city(city)
        if city not in online:
            return []
        result = []
        for row in self.db.execute("SELECT * FROM post_command WHERE city=? AND state='pending' ORDER BY rowid", (city,)):
            t = self._contract(city, row['contract'])
            if self.recovery_held(t):
                continue
            peer = t['receiver'] if city == t['sender'] else t['sender']
            if not self.transport and row['asset'] and row['step'] in ('export','receive') and not self.has_post(city, peer):
                continue
            result.append(dict(row,peer=peer))
            if len(result) == 16:
                break
        return result

    def _refund(self, t):
        if t['received']:
            raise ValueError('received cargo cannot be refunded')
        if t['exported'] and not t['refunded_goods']:
            self._queue(t, 'refund_goods')
        elif t['escrow'] and not t['refunded_money']:
            self._queue(t, 'refund_money')
        else:
            self.db.execute("UPDATE post_contract SET phase='cancelled' WHERE id=?", (t['id'],))

    def cancel(self, city, tid):
        with self.db:
            self.db.execute('BEGIN IMMEDIATE')
            t = self._contract(city, tid)
            if t['received'] or t['phase'] == 'complete':
                raise ValueError('already received; settlement must finish')
            self.db.execute('UPDATE post_contract SET cancel=1 WHERE id=?', (tid,))
            # An issued instruction may already be applied. Resolve its receipt
            # before refunding, even if a cancel request wins the network race.
            if not self.db.execute("SELECT 1 FROM post_command WHERE contract=? AND state='pending'", (tid,)).fetchone():
                self._refund(t)
        return self.status(city, tid)

    def arrived(self, city, tid):
        with self.db:
            self.db.execute('BEGIN IMMEDIATE')
            t = self._contract(city, tid)
            if city != t['receiver']:
                raise ValueError('recipient arrival report required')
            if t['phase'] == 'travel':
                self._queue(t, 'receive')
        return self.status(city, tid)

    def retry(self, city, tid):
        with self.db:
            self.db.execute('BEGIN IMMEDIATE')
            t = self._contract(city, tid)
            if not t['phase'].startswith('blocked:'):
                raise ValueError('not blocked')
            if t['cancel'] and not t['received']:
                self._refund(t)
            else:
                self._queue(t, t['phase'].split(':',1)[1])

    def ack(self, city, command, digest, applied):
        if type(applied) is not bool:
            raise ValueError('receipt must confirm applied or unapplied')
        with self.db:
            self.db.execute('BEGIN IMMEDIATE')
            row = self.db.execute('SELECT * FROM post_command WHERE id=?', (command,)).fetchone()
            if not row or row['city'] != city or row['digest'] != digest:
                raise ValueError('receipt identity mismatch')
            t = self._contract(city, row['contract'])
            if self.recovery_held(t):
                raise ValueError('transaction awaiting record reconciliation')
            state = 'applied' if applied else 'unapplied'
            if row['state'] != 'pending':
                if row['state'] != state:
                    raise ValueError('conflicting receipt')
                return self.status(city, t['id'])
            self._settle(t, row, applied)
        return self.status(city, t['id'])

    def _settle(self, t, row, applied):
        """One command's outcome moves its contract on. Caller holds the transaction."""
        self.db.execute('UPDATE post_command SET state=? WHERE id=?', ('applied' if applied else 'unapplied',row['id']))
        step = row['step']
        if applied:
            flag = dict(export='exported',escrow='escrow',receive='received',pay='paid',
                        refund_goods='refunded_goods',refund_money='refunded_money')[step]
            self.db.execute('UPDATE post_contract SET '+flag+'=1 WHERE id=?', (t['id'],))
            t[flag] = 1
        if t['cancel'] and not t['received']:
            if not applied and step.startswith('refund_'):
                self.db.execute('UPDATE post_contract SET phase=? WHERE id=?', ('blocked:'+step,t['id']))
            else:
                self._refund(t)
        elif not applied:
            if step in ('export','escrow'):
                self.db.execute('UPDATE post_contract SET cancel=1 WHERE id=?', (t['id'],))
                self._refund(t)
            else:
                self.db.execute('UPDATE post_contract SET phase=? WHERE id=?', ('blocked:'+step,t['id']))
        elif step == 'export':
            if not t['resource'] and t['route'] == 'debit':
                # One-sided debit (throne spending, debit_stage): the money only leaves the city; nobody receives it.
                self.db.execute("UPDATE post_contract SET phase='complete' WHERE id=?", (t['id'],))
            elif not t['resource']:
                self._queue(t, 'receive')
            elif t['money']:
                self._queue(t, 'escrow')
            else:
                self.db.execute("UPDATE post_contract SET phase='travel' WHERE id=?", (t['id'],))
        elif step == 'escrow':
            self.db.execute("UPDATE post_contract SET phase='travel' WHERE id=?", (t['id'],))
        elif step == 'receive':
            if t['resource'] and t['money']:
                self._queue(t, 'pay')
            else:
                self.db.execute("UPDATE post_contract SET phase='complete' WHERE id=?", (t['id'],))
        elif step == 'pay':
            self.db.execute("UPDATE post_contract SET phase='complete' WHERE id=?", (t['id'],))
        else:
            self._refund(t)

    def abandon(self, gone):
        """Cities whose players left this session stay at their last retained checkpoint.
        Their outstanding steps never run: what they owe is waived, what they would
        hand over is not taken, and goods heading to them go back to the sender.
        Goods they already sent keep travelling to a remaining receiver.
        Returns True when anything changed."""
        gone = set(gone) & set(self.cities)
        if not gone:
            return False
        changed = False
        with self.db:
            self.db.execute('BEGIN IMMEDIATE')
            for _ in range(256):
                step_done = False
                for row in self.db.execute('SELECT * FROM post_command WHERE state=? ORDER BY rowid', ('pending',)).fetchall():
                    if row['city'] not in gone:
                        continue
                    t = dict(self.db.execute('SELECT * FROM post_contract WHERE id=?', (row['contract'],)).fetchone())
                    if self.recovery_held(t) or t['route'] == 'debit':
                        # Throne debit/refund: never inferred from a departure. The city's own receipt settles it when it
                        # comes back; a refund stays owed to it (no waiver, nobody else is paid).
                        continue
                    waived = row['step'] in ('pay', 'refund_goods', 'refund_money')
                    if not waived and not t['received']:
                        self.db.execute('UPDATE post_contract SET cancel=1 WHERE id=?', (t['id'],))
                        t['cancel'] = 1
                    elif not waived:
                        continue  # a receive for goods already received cannot be undone
                    self.db.execute('INSERT OR IGNORE INTO post_forgiven VALUES(?,?)', (row['id'], row['city']))
                    self._settle(t, dict(row), waived)
                    step_done = True
                for t in self.db.execute("SELECT * FROM post_contract WHERE phase NOT IN ('complete','cancelled')").fetchall():
                    t = dict(t)
                    if not gone & {t['sender'], t['receiver']} or self.recovery_held(t) or t['route'] == 'debit':
                        continue
                    if self.db.execute("SELECT 1 FROM post_command WHERE contract=? AND state='pending'", (t['id'],)).fetchone():
                        continue
                    phase = t['phase']
                    if phase.startswith('blocked:'):
                        step = phase.split(':', 1)[1]
                        owner = t['receiver'] if step in ('escrow', 'receive', 'refund_money') else t['sender']
                        if owner in gone:
                            self._queue(t, step); step_done = True  # voided on the next pass
                        continue
                    if t['received'] or t['cancel']:
                        continue
                    if phase == 'offered' or (phase == 'travel' and t['receiver'] in gone):
                        self.db.execute('UPDATE post_contract SET cancel=1 WHERE id=?', (t['id'],))
                        t['cancel'] = 1
                        self._refund(t); step_done = True
                if not step_done:
                    break
                changed = True
        return changed

    def status(self, city, tid):
        t = self._contract(city, tid)
        # Neither an issued command nor a transport drawing proves delivery.
        t['cargo_delivered'] = bool(t['received'])
        t['settled'] = t['phase'] == 'complete'
        return t

    def checkpoint(self, destination):
        """Database-only copy, NOT a game checkpoint. Caller must pair this with
        matching native receipts/SAVs before treating it as a recoverable game."""
        with closing(sqlite3.connect(destination)) as target:
            self.db.backup(target)

def stage_debit(db,cities,city,tid,amount):
    """One-sided money debit from `city` (Race for the Throne spending). Stage inside the caller transaction; never
    commit here. Same native command as a cash gift's first step ('export', asset 0): the city's engine applies it
    only if its treasury covers the amount, and writes the receipt in the same city snapshot. Nobody is credited:
    after the receipt the contract is complete (applied) or cancelled (unapplied), see Ledger._settle.
    Nobody receives the money, so the receipt names the city itself as its peer (2026-11-15: a struggle for the
    throne can be played alone; the engine and post_recovery accept a city's own slot for money only). Debits staged
    before that named the next city in the roster as a label; their resends and receipts are still matched.
    Idempotent: the same id with the same values changes nothing."""
    if city not in cities:raise ValueError('unknown city')
    if not isinstance(tid, str) or len(tid) != 32 or any(c not in '0123456789abcdef' for c in tid):raise ValueError('request identifier')
    if not integer(amount, 1, 1000000):raise ValueError('amount')
    peer = city
    old = db.execute('SELECT * FROM post_contract WHERE id=?', (tid,)).fetchone()
    if old:
        if (old['sender'], old['resource'], old['quantity'], old['money'], old['route']) != (city, 0, 0, amount, 'debit') or old['receiver'] not in cities:
            raise ValueError('conflicting duplicate debit')
        return
    db.execute("INSERT INTO post_contract(id,sender,receiver,resource,quantity,money,route,phase) VALUES(?,?,?,0,0,?,'debit','export')",(tid, city, peer, amount))
    key = tid + ':export:1'
    digest = hashlib.sha256(encode([key, city, 'export', 0, amount]).encode()).hexdigest()
    db.execute("INSERT INTO post_command VALUES(?,?,?,?,?,?,?,'pending',?)", (key, tid, city, 'export', 0, amount, 1, digest))

def _queue_debit_step(db, t, step):
    city = t['sender']
    attempt = db.execute('SELECT count(*) FROM post_command WHERE contract=? AND step=?', (t['id'], step)).fetchone()[0] + 1
    key = t['id'] + ':' + step + ':' + str(attempt)
    digest = hashlib.sha256(encode([key, city, step, 0, t['money']]).encode()).hexdigest()
    db.execute("INSERT INTO post_command VALUES(?,?,?,?,?,?,?,'pending',?)", (key, t['id'], city, step, 0, t['money'], attempt, digest))
    db.execute('UPDATE post_contract SET phase=? WHERE id=?', (step, t['id']))
    return key

def stage_refund(db, tid):
    """Pay a confirmed throne debit back to the same city, the same amount ('pay': credit, asset 0). Caller transaction.
    Allowed once per debit: only when the debit receipt confirmed the money left, and no refund was paid or is under
    way. A refund the city could not take (its receipt said unapplied, e.g. treasury at the limit) stays owed as
    'blocked:pay'; stage it again with a new command id (retry_refund). Never to another city."""
    t = db.execute('SELECT * FROM post_contract WHERE id=?', (tid,)).fetchone()
    if not t or t['route'] != 'debit' or not t['exported'] or t['paid']:raise ValueError('refund not owed')
    if db.execute("SELECT 1 FROM post_command WHERE contract=? AND state='pending'", (tid,)).fetchone():raise ValueError('refund under way')
    if not (t['phase'] == 'complete' or t['phase'] == 'blocked:pay'):raise ValueError('refund state')
    return _queue_debit_step(db, dict(t), 'pay')

def refund_state(db, tid):
    """'paid' | 'pending' (a refund command waits for its receipt) | 'blocked' (the city could not take it) | None."""
    t = db.execute('SELECT phase,paid FROM post_contract WHERE id=?', (tid,)).fetchone()
    if not t:return None
    if t['paid']:return 'paid'
    if t['phase'] == 'blocked:pay':return 'blocked'
    if t['phase'] == 'pay':return 'pending'
    return None

def withdraw_debit(db, tid):
    """Cancel a throne debit whose command was never handed to the city (no delivery attempt recorded): it is marked
    not applied and forgiven, so the city's receipts never have to show it. Returns False when the command may already
    be in the city's hands; then only the city's receipt can say what happened (nothing is assumed)."""
    t = db.execute('SELECT * FROM post_contract WHERE id=?', (tid,)).fetchone()
    if not t or t['route'] != 'debit' or t['phase'] != 'export':return False
    row = db.execute("SELECT id,city FROM post_command WHERE contract=? AND step='export' AND state='pending'", (tid,)).fetchone()
    if not row:return False
    if db.execute("SELECT 1 FROM sqlite_master WHERE name='cash_attempt'").fetchone() and db.execute('SELECT 1 FROM cash_attempt WHERE command=?', (row['id'],)).fetchone():
        return False
    db.execute("UPDATE post_command SET state='unapplied' WHERE id=?", (row['id'],))
    db.execute('INSERT OR IGNORE INTO post_forgiven VALUES(?,?)', (row['id'], row['city']))
    db.execute("UPDATE post_contract SET cancel=1,phase='cancelled' WHERE id=?", (tid,))
    return True

def stage_offer(db,cities,city,tid,receiver,resource,quantity,money,route='land'):
    """Validate and stage inside the caller transaction; never commit here."""
    if city not in cities or receiver not in cities:raise ValueError('unknown city')
    if not isinstance(tid, str) or len(tid) != 32 or any(c not in '0123456789abcdef' for c in tid):
        raise ValueError('request identifier')
    if city == receiver or route not in ('land', 'sea'):
        raise ValueError('recipient or route')
    if not integer(resource, 0, 63) or not integer(quantity, 0, 32) or not integer(money, 0, 1000000):
        raise ValueError('amount')
    if (resource == 0 and (quantity != 0 or money == 0)) or (resource != 0 and quantity == 0):
        raise ValueError('empty transfer')
    values = (city, receiver, resource, quantity, money, route)
    old = db.execute('SELECT * FROM post_contract WHERE id=?', (tid,)).fetchone()
    if old:
        if tuple(old[k] for k in ('sender','receiver','resource','quantity','money','route')) != values:
            raise ValueError('conflicting duplicate offer')
    else:
        db.execute('INSERT INTO post_contract(id,sender,receiver,resource,quantity,money,route,phase) '
                        "VALUES(?,?,?,?,?,?,?,'offered')", (tid, *values))
