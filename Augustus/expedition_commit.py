"""Native SAV + military ledger coordinator; authenticated RPCs live in army_install.

SQLite BLOBs are authoritative. Files used by Engine are disposable drafts, never
live saves. One writer transaction covers SAV, phase and retry receipt. No external
city file is part of that commit. This service must own all writes before live use.
"""
from pathlib import Path
import json, uuid
from expedition_state import ExpeditionStore, encode, identifier, integer
from expedition_adapter import inspect_snapshot, inspect_bytes, select_army, sha
from expedition_draft import prepare_departure, transform
from city_client import Engine


class PairedExpeditions:
    def __init__(self, path, cities, scratch):
        self.store = ExpeditionStore(path, cities)
        self.scratch = Path(scratch)
        self.scratch.mkdir(parents=True, exist_ok=True)
        with self.store.connection() as db:
            db.executescript('''
                CREATE TABLE IF NOT EXISTS army_install(id TEXT PRIMARY KEY, city TEXT NOT NULL,
                    revision INTEGER NOT NULL, hash TEXT NOT NULL, ticks INTEGER NOT NULL,
                    state TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS city_snapshot(
                    id TEXT PRIMARY KEY, revision INTEGER NOT NULL,
                    sav BLOB NOT NULL, receipt BLOB NOT NULL, hash TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS native_army(
                    id TEXT PRIMARY KEY, city TEXT NOT NULL, formation INTEGER NOT NULL,
                    UNIQUE(city, formation));
                CREATE TABLE IF NOT EXISTS paired_binding(
                    id TEXT PRIMARY KEY, selection TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS paired_action(
                    id TEXT PRIMARY KEY, fingerprint TEXT NOT NULL, receipt TEXT NOT NULL);
            ''')
            db.execute('BEGIN IMMEDIATE')
            if db.execute('SELECT version FROM metadata').fetchone()[0] == 1:
                if db.execute('SELECT 1 FROM army UNION SELECT 1 FROM expedition LIMIT 1').fetchone():
                    raise ValueError('use a fresh paired ledger; existing manifests need native migration')
                db.execute('UPDATE metadata SET version=2')

    def _input(self, sav, receipt):
        folder=self.scratch/('paired-input-'+uuid.uuid4().hex);folder.mkdir()
        (folder/'city.sav').write_bytes(sav);(folder/'receipt.bin').write_bytes(receipt)
        return folder

    def enroll(self, city, source, formation, army_id):
        """Trusted initial import. Never overwrite an existing city or army."""
        identifier(city);identifier(army_id)
        if city not in self.store.cities:raise ValueError('city')
        view=inspect_snapshot(source,self.scratch)
        choice=select_army(view,formation,city,army_id)
        with self.store.connection() as db:
            db.execute('BEGIN IMMEDIATE')
            db.execute('INSERT INTO city_snapshot VALUES(?,0,?,?,?)',
                       (city,view['source'],view['receipt'],sha(view['source'])))
            db.execute('INSERT INTO army VALUES(?,?,?,NULL)',(army_id,city,encode(choice['manifest'])))
            db.execute('INSERT INTO army_source VALUES(?,?,?,?)',
                       (army_id,view['source'],view['source_hash'],encode(choice)))
            db.execute('INSERT INTO native_army VALUES(?,?,?)',(army_id,city,formation))
        return choice

    def snapshot(self, city):
        with self.store.connection() as db:
            db.execute('BEGIN')
            row=db.execute('SELECT * FROM city_snapshot WHERE id=?',(city,)).fetchone()
            if not row:raise ValueError('unknown city')
            return dict(row)

    def adopt_checkpoint(self, city, source, epoch, expected_revision, formation=None):
        """Trusted server checkpoint only, never arbitrary client SAV bytes.

        The room lock fences the joint checkpoint. CAS/epoch fence this ledger.
        Inspect the newest city rather than replaying an old city over new work.
        Optional selection and city adoption commit together. Identical retries
        keep the revision. Active departures must retain empty reserved forts.
        """
        view=inspect_snapshot(source,self.scratch)
        return self.adopt_inspected(city,view,epoch,expected_revision,formation)

    def adopt_inspected(self, city, view, epoch, expected_revision, formation=None, prior=None):
        """Internal engine results only; never deserialize these from an RPC."""
        identifier(city);integer(epoch,1,2**53-2)
        if city not in self.store.cities:raise ValueError('city')
        if expected_revision is not None:integer(expected_revision,0,2**53-1)
        if formation is not None:integer(formation,1,2**31-1)
        if sha(view['source'])!=view['source_hash'] or sha(view['receipt'])!=view['receipt_hash']:
            raise ValueError('inspection bytes changed')
        with self.store.connection() as db:
            db.execute('BEGIN IMMEDIATE')
            if db.execute('SELECT epoch FROM metadata').fetchone()[0]!=epoch:raise ValueError('stale epoch')
            if db.execute("SELECT 1 FROM army_install WHERE state='pending'").fetchone():raise ValueError('army install pending')
            old=db.execute('SELECT * FROM city_snapshot WHERE id=?',(city,)).fetchone()
            if (old['revision'] if old else None)!=expected_revision:raise ValueError('stale city snapshot')
            changed=not old or old['hash']!=view['source_hash'] or bytes(old['receipt'])!=view['receipt']
            if old and changed:
                if prior is None:prior=inspect_bytes(bytes(old['sav']),bytes(old['receipt']),self.scratch)
                if prior['source']!=bytes(old['sav']) or prior['receipt']!=bytes(old['receipt']):
                    raise ValueError('stale prior inspection')
                if view['clock']<prior['clock']:raise ValueError('checkpoint time moved backwards')
            rows={r['formation_id']:r for r in view['report']['legions']}
            cancelled=[]
            for exp in list(db.execute("SELECT e.*,n.formation FROM expedition e JOIN native_army n ON n.id=e.army_id WHERE e.origin=? AND e.phase IN ('reserved','outbound','stationed','returning')",(city,))):
                if exp['phase']=='reserved':
                    try:
                        selected=select_army(view,exp['formation'],city,exp['army_id'])
                        unchanged=encode(selected['manifest'])==exp['current']
                    except ValueError:unchanged=False
                    if not unchanged:
                        # A reservation has not removed any native soldiers.
                        # Expire it atomically instead of blocking all joint saves.
                        action='expire-'+sha((exp['id']+':'+str(exp['revision'])+':'+view['source_hash']).encode())[:48]
                        self.store._apply_in_transaction(db,action,city,epoch,exp['id'],exp['revision'],'cancel')
                        cancelled.append(exp['id'])
                elif exp['phase'] in ('outbound','stationed','returning'):
                    binding=db.execute('SELECT selection FROM paired_binding WHERE id=?',(exp['id'],)).fetchone()
                    if not binding:raise ValueError('missing departure')
                    native=json.loads(binding[0])['native'];row=rows.get(exp['formation'])
                    if not row or row['fort_id']!=native['fort_id'] or row['unit_type']!=native['unit_type'] or row['mp_expedition_id']!=native['vacancy_token'] or row['soldiers'] or row['empire_service'] or row['distant_battle']:
                        raise ValueError('departed army vacancy changed')
                else:raise ValueError('unsupported stationed checkpoint')
            revision=old['revision']+(1 if changed else 0) if old else 0
            if changed:
                db.execute('INSERT OR REPLACE INTO city_snapshot VALUES(?,?,?,?,?)',(city,revision,view['source'],view['receipt'],view['source_hash']))
            selected=None
            if formation is not None:
                native=db.execute('SELECT id FROM native_army WHERE city=? AND formation=?',(city,formation)).fetchone()
                army_id=native[0] if native else 'army-'+uuid.uuid4().hex
                if db.execute("SELECT 1 FROM expedition WHERE army_id=? AND phase IN ('reserved','outbound','stationed','returning')",(army_id,)).fetchone():raise ValueError('army already active')
                selected=select_army(view,formation,city,army_id)
                db.execute('INSERT OR REPLACE INTO army VALUES(?,?,?,NULL)',(army_id,city,encode(selected['manifest'])))
                db.execute('INSERT OR REPLACE INTO army_source VALUES(?,?,?,?)',(army_id,view['source'],view['source_hash'],encode(selected)))
                if not native:db.execute('INSERT INTO native_army VALUES(?,?,?)',(army_id,city,formation))
            self._checkpoint('after_checkpoint_adoption')
            return dict(city_revision=revision,save_hash=view['source_hash'],selection=selected,cancelled=cancelled)

    def _checkpoint(self, stage):
        """Failure-injection seam; never enabled by gameplay or request fields."""
        pass

    def apply(self, action_id, actor, epoch, expedition, revision, city_revision, op, *, install_ticks=None, **args):
        for value in (action_id,actor,expedition):identifier(value)
        for value in (epoch,revision,city_revision):integer(value,0,2**53-1)
        if actor not in self.store.cities:raise ValueError('actor')
        shapes={'reserve':{'army_id','destination'},'depart':set(),'recall':set(),'home':set(),'cancel':set(),'step':{'ticks'}}
        if op not in shapes or set(args)!=shapes[op]:raise ValueError('unsupported paired operation')
        if op=='step':integer(args['ticks'],1,10000)
        if install_ticks is not None:
            integer(install_ticks,0,2**53-1)
            if op not in ('depart','home'):raise ValueError('install operation')
        fields=[actor,expedition,revision,city_revision,op,args]
        if install_ticks is not None:fields.append(install_ticks)
        fingerprint=sha(encode(fields).encode())
        with self.store.connection() as db:
            db.execute('BEGIN IMMEDIATE')
            if db.execute('SELECT epoch FROM metadata').fetchone()[0]!=epoch:raise ValueError('stale epoch')
            old=db.execute('SELECT * FROM paired_action WHERE id=?',(action_id,)).fetchone()
            if old:
                if old['fingerprint']!=fingerprint:raise ValueError('conflicting paired replay')
                return json.loads(old['receipt'])
            if db.execute('SELECT 1 FROM action WHERE id=?',(action_id,)).fetchone():
                raise ValueError('unpaired action ID')
            if db.execute("SELECT 1 FROM army_install WHERE state='pending'").fetchone():raise ValueError('army install pending')
            city=db.execute('SELECT * FROM city_snapshot WHERE id=?',(actor,)).fetchone()
            if not city or city['revision']!=city_revision:raise ValueError('stale city snapshot')
            row=db.execute('SELECT * FROM expedition WHERE id=?',(expedition,)).fetchone()
            draft=None
            if op in ('depart','home','recall','cancel'):
                if not row or row['revision']!=revision or row['origin']!=actor:
                    raise ValueError('stale expedition or wrong owner')
                expected={'depart':('reserved',),'recall':('outbound',),'home':('returning',),'cancel':('reserved',)}[op]
                if row['phase'] not in expected:raise ValueError('unsupported paired phase')
            if op=='depart':
                native=db.execute('SELECT * FROM native_army WHERE id=?',(row['army_id'],)).fetchone()
                if not native or native['city']!=actor:raise ValueError('native binding')
                view=inspect_bytes(bytes(city['sav']),bytes(city['receipt']),self.scratch)
                selection=select_army(view,native['formation'],actor,row['army_id'])
                if encode(selection['manifest'])!=row['current']:raise ValueError('army changed since reservation')
                draft=prepare_departure(view,selection,self.scratch)
                db.execute('INSERT INTO paired_binding VALUES(?,?)',(expedition,encode(draft['selection'])))
            elif op=='home':
                binding=db.execute('SELECT selection FROM paired_binding WHERE id=?',(expedition,)).fetchone()
                if not binding:raise ValueError('missing departure')
                selection=json.loads(binding[0])
                # Destination combat is not connected yet: never fabricate losses.
                if encode(selection['manifest'])!=row['current']:raise ValueError('native survivor record required')
                draft=transform(city['sav'],city['receipt'],selection['native'],self.scratch,'expedition-restore')
            elif op=='step':
                source=self._input(city['sav'],city['receipt']);out=source.parent/(source.name+'-out')
                sav,receipt=Engine().run('military-ticks',source,out,qty=args['ticks'])
                draft=dict(save=sav,receipt=receipt,hash=sha(sav))
            self._checkpoint('after_native')
            if draft:
                db.execute('UPDATE city_snapshot SET revision=revision+1,sav=?,receipt=?,hash=? WHERE id=?',
                           (draft['save'],draft['receipt'],sha(draft['save']),actor))
            self._checkpoint('after_sav')
            if op=='step':result={'step':args['ticks']}
            else:
                result=self.store._apply_in_transaction(db,action_id,actor,epoch,expedition,revision,op,**args)
            self._checkpoint('after_ledger')
            current=db.execute('SELECT revision,hash FROM city_snapshot WHERE id=?',(actor,)).fetchone()
            result={'expedition':result,'city_revision':current['revision'],'save_hash':current['hash']}
            db.execute('INSERT INTO paired_action VALUES(?,?,?)',(action_id,fingerprint,encode(result)))
            if install_ticks is not None:
                db.execute("INSERT INTO army_install VALUES(?,?,?,?,?,'pending')",(action_id,actor,current['revision'],current['hash'],install_ticks))
            self._checkpoint('after_receipt')
            return result
