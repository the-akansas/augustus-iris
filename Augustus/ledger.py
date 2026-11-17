"""Local-only transport/ledger prototype. Balances are test escrow, NOT game inventories."""
import hashlib, json, secrets, socketserver, sqlite3
from pathlib import Path
from contextlib import closing

PROTOCOL = 1
BUILD = '63813587869eda5557fe5f1e0e8cea024ff8bef7-mp-lab1'
LIMIT = 8192

def encode(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',', ':'))

def positive(value):
    if type(value) is not int or not 1 <= value <= 1000000:
        raise ValueError('invalid_amount')
    return value

class Ledger:
    def __init__(self, path):
        self.path = str(path)
        with closing(self.connect()) as db:
            db.executescript('''
            CREATE TABLE IF NOT EXISTS cities(id TEXT PRIMARY KEY, token TEXT NOT NULL, map_id TEXT NOT NULL, money INTEGER NOT NULL, pottery INTEGER NOT NULL);
            CREATE TABLE IF NOT EXISTS requests(city TEXT, id TEXT, payload TEXT NOT NULL, result TEXT NOT NULL, PRIMARY KEY(city,id));
            CREATE TABLE IF NOT EXISTS events(seq INTEGER PRIMARY KEY AUTOINCREMENT, body TEXT NOT NULL);
            ''')
    def connect(self):
        db = sqlite3.connect(self.path, timeout=10)
        db.row_factory = sqlite3.Row
        db.execute('PRAGMA synchronous=FULL')
        return db
    def provision_test_city(self, city, map_id, money, pottery):
        token = secrets.token_hex(32)
        with closing(self.connect()) as db:
            db.execute('INSERT INTO cities VALUES(?,?,?,?,?)', (city, hashlib.sha256(token.encode()).hexdigest(), map_id, money, pottery))
            db.commit()
        return token
    def request(self, r):
        if not isinstance(r, dict) or r.get('protocol') != PROTOCOL or r.get('build') != BUILD:
            raise ValueError('incompatible_protocol_or_build')
        city, token = r.get('city'), r.get('token')
        if not isinstance(city, str) or not isinstance(token, str): raise ValueError('unauthorized')
        db = self.connect()
        try:
            db.execute('BEGIN IMMEDIATE')
            actor = db.execute('SELECT * FROM cities WHERE id=?', (city,)).fetchone()
            if actor is None or not secrets.compare_digest(actor['token'], hashlib.sha256(token.encode()).hexdigest()):
                raise ValueError('unauthorized')
            op = r.get('op')
            if op == 'state':
                result = {'cities':[dict(x) for x in db.execute('SELECT id,map_id,money,pottery FROM cities')],
                          'events':[{'seq':x['seq'], **json.loads(x['body'])} for x in db.execute('SELECT * FROM events ORDER BY seq DESC LIMIT 100')]}
                db.commit(); return result
            rid = r.get('id')
            if not isinstance(rid, str) or not 1 <= len(rid) <= 64: raise ValueError('invalid_request_id')
            payload = encode({k:v for k,v in r.items() if k != 'token'})
            prior = db.execute('SELECT * FROM requests WHERE city=? AND id=?', (city,rid)).fetchone()
            if prior:
                if prior['payload'] != payload: raise ValueError('request_id_reused')
                db.commit(); return json.loads(prior['result'])
            if op == 'chat':
                message = r.get('text')
                if not isinstance(message,str) or not 1 <= len(message.encode('utf-8')) <= 1024 or any(ord(c)<32 for c in message):
                    raise ValueError('invalid_chat')
                event = {'type':'chat','city':city,'text':message}
            elif op == 'sell_pottery':
                # Seller explicitly authorizes quantity and price; only the named buyer can accept.
                buyer, qty, price = r.get('buyer'), positive(r.get('quantity')), positive(r.get('price'))
                if buyer == city or not db.execute('SELECT 1 FROM cities WHERE id=?',(buyer,)).fetchone(): raise ValueError('invalid_buyer')
                event = {'type':'offer','seller':city,'buyer':buyer,'quantity':qty,'price':price}
            elif op == 'accept':
                offer_id = positive(r.get('offer'))
                row = db.execute('SELECT body FROM events WHERE seq=?',(offer_id,)).fetchone()
                offer = json.loads(row[0]) if row else {}
                if offer.get('type') != 'offer' or offer.get('buyer') != city: raise ValueError('invalid_offer')
                for old in db.execute('SELECT body FROM events'):
                    e=json.loads(old[0])
                    if e.get('type')=='trade' and e.get('offer')==offer_id: raise ValueError('offer_already_filled')
                qty, price, seller = offer['quantity'], offer['price'], offer['seller']
                cost = qty * price
                stock = db.execute('SELECT pottery FROM cities WHERE id=?',(seller,)).fetchone()[0]
                if stock < qty or actor['money'] < cost: raise ValueError('insufficient_stock_or_money')
                db.execute('UPDATE cities SET pottery=pottery-?,money=money+? WHERE id=?',(qty,cost,seller))
                db.execute('UPDATE cities SET pottery=pottery+?,money=money-? WHERE id=?',(qty,cost,city))
                event = {'type':'trade','offer':offer_id,'seller':seller,'buyer':city,'quantity':qty,'cost':cost}
            else: raise ValueError('unknown_operation')
            seq = db.execute('INSERT INTO events(body) VALUES(?)',(encode(event),)).lastrowid
            result = {'seq':seq, **event}
            db.execute('INSERT INTO requests VALUES(?,?,?,?)',(city,rid,payload,encode(result)))
            db.commit(); return result
        except BaseException:
            db.rollback(); raise
        finally: db.close()

class Handler(socketserver.StreamRequestHandler):
    def handle(self):
        self.connection.settimeout(5)
        try:
            data=self.rfile.readline(LIMIT+1)
            if len(data)>LIMIT or not data.endswith(b'\n'): raise ValueError('invalid_frame')
            request=json.loads(data.decode('utf-8'))
            response={'ok':True,'result':self.server.ledger.request(request)}
        except (ValueError,TypeError,KeyError,UnicodeError): response={'ok':False,'error':'invalid_request'}
        except (TimeoutError,ConnectionError): return
        except Exception: response={'ok':False,'error':'internal_error'}
        self.wfile.write((encode(response)+'\n').encode('utf-8'))

class Server(socketserver.ThreadingTCPServer):
    daemon_threads=True
    def __init__(self, ledger):
        self.ledger=ledger
        super().__init__(('127.0.0.1',0),Handler)

