"""Experimental durable military manifest ledger; NOT wired to live city SAVs.

Only a future trusted engine adapter may supply army manifests. These transactions
prove manifest ownership, not that a SAV has removed/created the corresponding
figures. Never expose this as a gameplay RPC until paired SAV commit is connected.
"""
import hashlib
import json
import sqlite3
from contextlib import contextmanager, closing

ACTIVE = ('reserved', 'outbound', 'stationed', 'returning')


def publish(stage, destination):
    import os
    # Windows rename fails when destination exists; POSIX rename overwrites.
    if os.name == 'nt': os.rename(stage, destination)
    else: os.link(stage, destination)


def encode(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'), ensure_ascii=False)


def identifier(value):
    if not isinstance(value, str) or not 1 <= len(value) <= 64 or any(
            c not in 'abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789-_' for c in value):
        raise ValueError('invalid identifier')
    return value


def integer(value, low, high):
    if type(value) is not int or not low <= value <= high:
        raise ValueError('invalid integer')


def manifest(value):
    fields = {'army_id', 'owner', 'unit_type', 'soldiers', 'morale', 'trained',
              'total_damage', 'months_from_home'}
    if not isinstance(value, dict) or set(value) != fields:
        raise ValueError('invalid army manifest')
    identifier(value['army_id']); identifier(value['owner'])
    integer(value['unit_type'], 1, 255)
    integer(value['soldiers'], 1, 16)
    # Trained legionaries: 90 + mess-hall modifier (up to 15).
    integer(value['morale'], 0, 105)
    integer(value['trained'], 0, 1)
    integer(value['total_damage'], 0, 2**31-1)
    integer(value['months_from_home'], 0, 2**31-1)
    return json.loads(encode(value))


class ExpeditionStore:
    """One SQLite transaction per action; callers authenticate city separately.

    Epoch fences old room leaders. Revision fences late phase commands. Action
    IDs survive restarts; an identical retry returns its original receipt.
    Copies of this DB are NOT a consensus or host-election implementation.
    """
    def __init__(self, path, cities):
        self.path = str(path)
        cities = sorted(cities)
        if not 2 <= len(cities) <= 8 or len(set(cities)) != len(cities):
            raise ValueError('cities')
        for city in cities: identifier(city)
        with self.connection() as db:
            db.executescript('''
                CREATE TABLE IF NOT EXISTS metadata(id INTEGER PRIMARY KEY CHECK(id=1),
                    version INTEGER NOT NULL, cities TEXT NOT NULL, epoch INTEGER NOT NULL);
                CREATE TABLE IF NOT EXISTS army(id TEXT PRIMARY KEY, city TEXT NOT NULL,
                    payload TEXT NOT NULL, reservation TEXT UNIQUE);
                CREATE TABLE IF NOT EXISTS expedition(id TEXT PRIMARY KEY, origin TEXT NOT NULL,
                    destination TEXT NOT NULL, army_id TEXT NOT NULL, phase TEXT NOT NULL,
                    revision INTEGER NOT NULL, initial TEXT NOT NULL, current TEXT NOT NULL,
                    losses INTEGER NOT NULL);
                CREATE UNIQUE INDEX IF NOT EXISTS active_army ON expedition(army_id)
                    WHERE phase IN ('reserved','outbound','stationed','returning');
                CREATE TABLE IF NOT EXISTS action(id TEXT PRIMARY KEY,
                    fingerprint TEXT NOT NULL, receipt TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS army_source(id TEXT PRIMARY KEY,
                    save BLOB NOT NULL, hash TEXT NOT NULL, detail TEXT NOT NULL);
            ''')
            db.execute('INSERT OR IGNORE INTO metadata VALUES(1,1,?,1)', (encode(cities),))
            row = db.execute('SELECT * FROM metadata').fetchone()
            if row['version'] not in (1, 2) or row['cities'] != encode(cities):
                raise ValueError('incompatible ledger')
        self.cities = cities

    @contextmanager
    def connection(self):
        db = sqlite3.connect(self.path, timeout=10)
        db.row_factory = sqlite3.Row
        db.execute('PRAGMA synchronous=FULL')
        try:
            yield db
            db.commit()
        except BaseException:
            db.rollback()
            raise
        finally:
            db.close()

    def seed(self, value, *, source=None, detail=None):
        """Trusted initial import only. Existing IDs cannot be overwritten."""
        value = manifest(value)
        if value['owner'] not in self.cities: raise ValueError('owner')
        if (source is None) != (detail is None): raise ValueError('incomplete source evidence')
        if source is not None:
            if not isinstance(source,bytes) or not 0<len(source)<=8*1024*1024:
                raise ValueError('source size')
            if not isinstance(detail,dict) or detail.get('manifest') != value or detail.get('source_hash') != hashlib.sha256(source).hexdigest():
                raise ValueError('source binding')
            encoded_detail=encode(detail)
        with self.connection() as db:
            db.execute('BEGIN IMMEDIATE')
            if db.execute('SELECT version FROM metadata').fetchone()[0] == 2:
                raise ValueError('paired ledger requires native enrollment')
            if db.execute('SELECT 1 FROM expedition WHERE army_id=?', (value['army_id'],)).fetchone():
                raise ValueError('army already has expedition history')
            db.execute('INSERT INTO army VALUES(?,?,?,NULL)',
                       (value['army_id'], value['owner'], encode(value)))
            if source is not None:
                db.execute('INSERT INTO army_source VALUES(?,?,?,?)',
                           (value['army_id'],source,detail['source_hash'],encoded_detail))

    def takeover(self, expected_epoch):
        """Internal fencing primitive; external leader election is required."""
        integer(expected_epoch, 1, 2**53-2)
        with self.connection() as db:
            db.execute('BEGIN IMMEDIATE')
            if db.execute('SELECT epoch FROM metadata').fetchone()[0] != expected_epoch:
                raise ValueError('stale epoch')
            db.execute('UPDATE metadata SET epoch=epoch+1')
        return expected_epoch + 1

    def apply(self, action_id, actor, epoch, expedition_id, revision, op, **args):
        with self.connection() as db:
            db.execute('BEGIN IMMEDIATE')
            # A paired ledger must never allow manifest-only mutations.
            if db.execute('SELECT version FROM metadata').fetchone()[0] == 2:
                raise ValueError('paired ledger requires paired coordinator')
            return self._apply_in_transaction(db, action_id, actor, epoch,
                                              expedition_id, revision, op, **args)

    def _apply_in_transaction(self, db, action_id, actor, epoch, expedition_id, revision, op, **args):
        for key in (action_id, actor, expedition_id): identifier(key)
        integer(epoch, 1, 2**53-1); integer(revision, 0, 2**53-1)
        if actor not in self.cities: raise ValueError('actor')
        shapes = {'reserve': {'army_id', 'destination'}, 'depart': set(),
                  'arrive': set(), 'recall': set(), 'home': set(),
                  'cancel': set(), 'battle': {'soldiers', 'morale', 'total_damage'}}
        if op not in shapes or set(args) != shapes[op]: raise ValueError('operation fields')
        fingerprint = hashlib.sha256(encode([actor, expedition_id, revision, op, args]).encode()).hexdigest()

        if db.execute('SELECT epoch FROM metadata').fetchone()[0] != epoch:
            raise ValueError('stale epoch')
        old = db.execute('SELECT * FROM action WHERE id=?', (action_id,)).fetchone()
        if old:
            if old['fingerprint'] != fingerprint: raise ValueError('conflicting replay')
            return json.loads(old['receipt'])
        row = db.execute('SELECT * FROM expedition WHERE id=?', (expedition_id,)).fetchone()
        if op == 'reserve':
            identifier(args['army_id']); identifier(args['destination'])
            if row or revision != 0 or args['destination'] not in self.cities or args['destination'] == actor:
                raise ValueError('invalid reservation')
            army = db.execute('SELECT * FROM army WHERE id=?', (args['army_id'],)).fetchone()
            if not army or army['city'] != actor or army['reservation']:
                raise ValueError('army unavailable')
            payload = json.loads(army['payload'])
            if payload['owner'] != actor: raise ValueError('not army owner')
            db.execute('INSERT INTO expedition VALUES(?,?,?,?,?,1,?,?,0)',
                       (expedition_id, actor, args['destination'], army['id'], 'reserved',
                        army['payload'], army['payload']))
            db.execute('UPDATE army SET reservation=? WHERE id=?', (expedition_id, army['id']))
        else:
            if not row or row['revision'] != revision: raise ValueError('stale revision')
            phase = row['phase']; origin = row['origin']; dest = row['destination']
            payload = json.loads(row['current']); losses = row['losses']
            next_phase = None
            if op == 'cancel' and phase == 'reserved' and actor in (origin, dest):
                next_phase = 'cancelled'
                db.execute('UPDATE army SET reservation=NULL WHERE id=?', (row['army_id'],))
            elif op == 'depart' and phase == 'reserved' and actor == origin:
                next_phase = 'outbound'
                db.execute('DELETE FROM army WHERE id=?', (row['army_id'],))
            elif op == 'arrive' and phase == 'outbound' and actor == dest:
                next_phase = 'stationed'
                db.execute('INSERT INTO army VALUES(?,?,?,?)',
                           (row['army_id'], dest, row['current'], expedition_id))
            elif op == 'recall' and phase in ('outbound', 'stationed') and actor in (origin, dest):
                next_phase = 'returning'
                if phase == 'stationed': db.execute('DELETE FROM army WHERE id=?', (row['army_id'],))
            elif op == 'home' and phase == 'returning' and actor == origin:
                next_phase = 'returned'
                db.execute('INSERT INTO army VALUES(?,?,?,NULL)', (row['army_id'], origin, row['current']))
            elif op == 'battle' and phase == 'stationed' and actor == dest:
                integer(args['soldiers'], 0, payload['soldiers'])
                integer(args['morale'], 0, 105)
                # Native total_damage is the current living soldiers' sum,
                # not cumulative battle damage; casualties can lower it.
                integer(args['total_damage'], 0, 2**31-1)
                losses += payload['soldiers'] - args['soldiers']
                payload.update(args)
                next_phase = 'stationed' if payload['soldiers'] else 'lost'
                if next_phase == 'lost': db.execute('DELETE FROM army WHERE id=?', (row['army_id'],))
                else: db.execute('UPDATE army SET payload=? WHERE id=?', (encode(payload), row['army_id']))
            else: raise ValueError('phase or authority')
            db.execute('UPDATE expedition SET phase=?,revision=revision+1,current=?,losses=? WHERE id=?',
                       (next_phase, encode(payload), losses, expedition_id))
        self._check(db)
        result = dict(db.execute('SELECT * FROM expedition WHERE id=?', (expedition_id,)).fetchone())
        db.execute('INSERT INTO action VALUES(?,?,?)', (action_id, fingerprint, encode(result)))
        return result

    def _check(self, db):
        for row in db.execute('SELECT * FROM expedition'):
            initial, current = json.loads(row['initial']), json.loads(row['current'])
            if initial['soldiers'] != current['soldiers'] + row['losses']:
                raise ValueError('soldier conservation')
            for key in ('army_id', 'owner', 'unit_type', 'trained', 'months_from_home'):
                if initial[key] != current[key]: raise ValueError('identity or retained metric changed')
            if row['phase'] in ACTIVE:
                army = db.execute('SELECT * FROM army WHERE id=?', (row['army_id'],)).fetchone()
                located = row['phase'] in ('reserved', 'stationed')
                if bool(army) != located: raise ValueError('duplicate or missing army')
                if located and (army['city'] != (row['origin'] if row['phase']=='reserved' else row['destination'])
                                or army['payload'] != row['current'] or army['reservation'] != row['id']):
                    raise ValueError('army location mismatch')

    def inspect(self):
        with self.connection() as db:
            db.execute('BEGIN')
            self._check(db)
            return {table: [dict(row) for row in db.execute('SELECT * FROM '+table+' ORDER BY id')]
                    for table in ('metadata', 'army', 'expedition', 'action')}

    def backup(self, destination):
        """Publish only a completed SQLite backup; refuse existing destinations."""
        from pathlib import Path
        import os
        import uuid
        path = Path(destination)
        if path.exists(): raise FileExistsError(path)
        stage = path.with_name(path.name+'.'+uuid.uuid4().hex+'.preparing')
        try:
            with stage.open('xb'): pass
            with self.connection() as db:
                with closing(sqlite3.connect(str(stage))) as target:
                    target.execute('PRAGMA synchronous=FULL')
                    db.backup(target)
                    if target.execute('PRAGMA integrity_check').fetchone()[0] != 'ok':
                        raise ValueError('backup integrity')
            # Same-directory atomic publication, never overwrite a saved backup.
            publish(stage, path)
        finally:
            if stage.exists(): stage.unlink()
