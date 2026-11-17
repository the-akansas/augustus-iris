"""Cash ledger carried by the existing explicit joint checkpoint."""
import sqlite3,json
from contextlib import closing
from trade_post_ledger import Ledger
TABLES=('post_meta','post_binding','post_contract','post_command','post_recovery_hold','cash_transfer','cash_scope','cash_attempt','cash_retry','cash_archive','goods_motion','fleet_site','fleet_order','post_forgiven','post_sequence')

def schema(db):
    with closing(sqlite3.connect(':memory:')) as target:
        # Reuse the exact current schema, never executable SQL from a snapshot.
        ledger=Ledger(':memory:',['x','y'])
        try:
            for row in ledger.db.execute("SELECT sql FROM sqlite_master WHERE sql IS NOT NULL AND name NOT LIKE 'sqlite_%' ORDER BY type DESC"):
                target.execute(row[0]);db.execute(row[0])
        finally:ledger.close()
    import cash_live
    cash_live.initialize(db)

def current(db):
    if not db.execute("SELECT 1 FROM sqlite_master WHERE name='post_meta'").fetchone():return None
    # Throne spending (one-sided 'debit' contracts) has no transfer row but its receipts are in the city saves too.
    if not db.execute('SELECT 1 FROM cash_transfer').fetchone() and not db.execute("SELECT 1 FROM post_contract WHERE route='debit'").fetchone():return None
    db.execute('CREATE TABLE IF NOT EXISTS post_sequence(id INTEGER PRIMARY KEY CHECK(id=1), value INTEGER NOT NULL)')
    return dict(tables={name:[dict(row) for row in db.execute('SELECT * FROM '+name)] for name in TABLES},transfers=[dict(row) for row in db.execute('SELECT * FROM live_transfer WHERE id IN (SELECT id FROM cash_transfer)')])

def validate(data,cities):
    if data is None:return
    if isinstance(data,dict) and isinstance(data.get('tables'),dict):
        for name in ('fleet_site','fleet_order','cash_retry','cash_archive','post_forgiven','post_sequence'):data['tables'].setdefault(name,[])
    if isinstance(data,dict) and isinstance(data.get('tables'),dict) and 'goods_motion' not in data['tables']:data['tables']['goods_motion']=[]
    if not isinstance(data,dict) or set(data)!= {'tables','transfers'} or set(data['tables'])!=set(TABLES):raise ValueError('cash checkpoint schema')
    if len(json.dumps(data))>4000000:raise ValueError('cash checkpoint size')
    if len(data['tables']['post_meta'])!=1 or json.loads(data['tables']['post_meta'][0]['cities'])!=list(cities):raise ValueError('cash roster')
    if len(data['tables']['cash_scope'])!=1:raise ValueError('cash scope')
    import re
    if not re.fullmatch('[0-9a-f]{64}',data['tables']['cash_scope'][0]['value']):raise ValueError('cash scope')
    for row in data['tables']['post_contract']:
        if not (0<=row['resource']<22 and 0<=row['quantity']<=32) or row['sender'] not in cities or row['receiver'] not in cities or (row['sender']==row['receiver'] and not (row.get('route')=='debit' and row['resource']==0)):raise ValueError('cash contract')   # a throne debit names its own city (2026-11-15)
    for row in data['tables']['post_contract']:
        if type(row['resource']) is not int or type(row['quantity']) is not int or type(row['money']) is not int or not 0<=row['money']<=1000000:raise ValueError('trade amount')
        if row['resource']==0 and (row['quantity']!=0 or row['money']==0) or row['resource']!=0 and not 1<=row['quantity']<=32:raise ValueError('trade resource quantity')
    sequence=data['tables']['post_sequence']
    if not isinstance(sequence,list) or len(sequence)>1:raise ValueError('cash sequence')
    for row in sequence:
        if not isinstance(row,dict) or set(row)!={'id','value'} or type(row['id']) is not int or row['id']!=1 or type(row['value']) is not int or not 0<=row['value']<2**63:raise ValueError('cash sequence')
    contracts={row['id'] for row in data['tables']['post_contract']}
    for row in data['tables']['post_command']:
        if row['contract'] not in contracts or row['city'] not in cities or not 0<=row['asset']<22:raise ValueError('cash command')
    for row in data['transfers']:
        if not (0<=row['resource']<22 and 0<=row['quantity']<=32) or row['request'] not in contracts:raise ValueError('cash transfer')
    if {row['id'] for row in data['transfers']}!={row['id'] for row in data['tables']['cash_transfer']}:raise ValueError('cash mapping')
    by_id={row['id']:row for row in data['transfers']}
    occupied={}
    for row in data['tables']['fleet_site']:
        if row['city'] not in cities or type(row['building']) is not int or not 0<row['building']<100000 or type(row['generation']) is not int or not 0<=row['generation']<65536 or row['active'] not in (0,1):raise ValueError('fleet site')
    for row in data['tables']['fleet_order']:
        row.setdefault('shipment',0) # Saves before shared caravans: one order per caravan.
        row.setdefault('origin',0)
        if type(row['origin'])!=int or row['origin']<0:raise ValueError('fleet order origin')
        t=by_id.get(row['id'])
        if not t or not t['resource'] or row['city']!=t['sender'] or row['assigned'] not in (0,1) or row['home'] not in (0,1) or type(row['shipment'])!=int or row['shipment']<0:raise ValueError('fleet order')
        key=(row['city'],row['building'],row['generation'])
        if row['assigned'] and not row['home']:
            # One caravan per post; its orders all belong to the same shipment.
            if key in occupied and (not row['shipment'] or occupied[key]!=row['shipment']):raise ValueError('two contracts own one caravan')
            occupied[key]=row['shipment']
    by_contract={row['id']:row for row in data['tables']['post_contract']}
    for row in data['tables']['cash_transfer']:
        t=by_id[row['id']]
        if row['contract']!=t['request']:raise ValueError('cash mapping identity')
        c=by_contract[row['contract']]
        if any(t[k]!=c[k] for k in ('sender','receiver','money','resource','quantity')) or t['kind'] not in ('gift','sale'):raise ValueError('cash mapping payload')
    motions=data['tables']['goods_motion']
    if {row['id'] for row in motions}!={t['id'] for t in data['transfers'] if t['resource']}:raise ValueError('goods mapping')
    for row in motions:
        row.setdefault('source_ok',0);row.setdefault('destination_ok',0)
        row.setdefault('map_depart_tick',0);row.setdefault('map_arrive_tick',0)
        row.setdefault('map_progress',0)
        if type(row['map_progress'])!=int or not 0<=row['map_progress']<=1000:raise ValueError('goods map progress')
        start,end=row['map_depart_tick'],row['map_arrive_tick']
        if type(start)!=int or type(end)!=int or start<0 or end<0 or (end and (end<=start or not row['departed'])):raise ValueError('goods map timeline')
        if row['source_ok'] not in (0,1) or row['destination_ok'] not in (0,1):raise ValueError('preflight flags')
        if row['counted'] not in (0,1) or row['route'] not in (2,3) or row['accepted'] not in (0,1) or row['departed'] not in (0,1) or not 0<=row['source']<100000 or not 0<=row['destination']<100000:raise ValueError('goods motion')
    for row in motions:
        contract=by_contract[by_id[row['id']]['request']]
        if contract['route']!=('sea' if row['route']==3 else 'land'):raise ValueError('goods route identity')
    commands={row['id'] for row in data['tables']['post_command']}
    for row in data['tables']['cash_retry']:
        if row['command'] not in commands or type(row['next_time']) not in (int,float) or not 0<=row['next_time']<1e12:raise ValueError('cash retry')
    for row in data['tables']['cash_archive']:
        if row['city'] not in cities or type(row['epoch'])!=int or not 0<=row['epoch']<2**32 or not isinstance(row['payload'],str) or not re.fullmatch('[0-9a-f]{64}',row['hash']):raise ValueError('cash archive')
        proof=json.loads(row['payload'])
        if not isinstance(proof,dict) or not set(proof)<=commands:raise ValueError('cash archive commands')
    for row in data['tables']['post_forgiven']:
        if row['command'] not in commands or row['city'] not in cities:raise ValueError('cash forgiven')
    for row in data['tables']['cash_attempt']:
        if row['command'] not in commands or type(row['attempts']) is not int or not 0<=row['attempts']<=6:raise ValueError('cash attempts')

def restore(db,data,cities):
    if data is None:return
    if isinstance(data,dict) and isinstance(data.get('tables'),dict) and 'goods_motion' not in data['tables']:data['tables']['goods_motion']=[]
    validate(data,cities);schema(db)
    for name in TABLES:
        columns=[row[1] for row in db.execute('PRAGMA table_info('+name+')')]
        for row in data['tables'][name]:
            if set(row)!=set(columns):raise ValueError('cash row columns')
            db.execute('INSERT INTO '+name+'('+','.join(columns)+') VALUES('+','.join('?' for _ in columns)+')',[row[k] for k in columns])
    columns=[row[1] for row in db.execute('PRAGMA table_info(live_transfer)')]
    for row in data['transfers']:
        if set(row)!=set(columns):raise ValueError('cash transfer columns')
        db.execute('INSERT INTO live_transfer VALUES('+','.join('?' for _ in columns)+')',[row[k] for k in columns])
