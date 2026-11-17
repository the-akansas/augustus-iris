"""Revision-checked quantity negotiation. No inventory is exposed or debited here."""
import json

DEFAULTS=dict(revision=0,allow_partial=0,offer_payload='',action_key='',action_payload='',due_tick=0,expired=0)
# due_tick: seller game tick by which the waiting round must leave (0 = not counting); expired: stopped by that deadline.

def initialize(db):
 columns={r[1] for r in db.execute('PRAGMA table_info(trade_agreement)')}
 for name,value in DEFAULTS.items():
  if name not in columns:
   kind='INTEGER NOT NULL DEFAULT 0' if isinstance(value,int) else "TEXT NOT NULL DEFAULT ''"
   db.execute(f'ALTER TABLE trade_agreement ADD COLUMN {name} {kind}')

def normalized(a):
 return dict(DEFAULTS,**a)

def payload(city,seller,buyer,res,qty,money,repeat,selected,partial):
 return json.dumps([city,seller,buyer,res,qty,money,repeat,selected,partial],separators=(',',':'))

def check(a,city,r):
 key=r.get('request_id','')
 if not isinstance(key,str) or (key and (len(key)!=32 or any(c not in '0123456789abcdef' for c in key))):raise ValueError('요청 번호 오류')
 body=json.dumps([city,r['op'],r.get('revision'),r.get('quantity'),r.get('post')]+([r['money']] if r.get('money') is not None else []),separators=(',',':'))
 if key and key==a['action_key']:
  if body!=a['action_payload']:raise ValueError('중복 요청 내용이 다릅니다.')
  return key,body,True
 revision=r.get('revision',0)
 if type(revision)!=int or revision!=a['revision']:raise ValueError('제안이 변경되었습니다. 최신 내용을 확인하세요.')
 return key,body,False

def counter(db,room,city,a,r):
 """The city answering an offer proposes other terms: same goods, its own quantity and total.
 Either side may answer; the other side must confirm again. Only a smaller quantity at the
 same unit price on a partial-allowed purchase is concluded at once (the buyer allowed it)."""
 from trade_agreements import post
 import city_trade_routes
 qty=r.get('quantity');money=r.get('money',None)
 if a['state']!='offered' or city not in (a['seller'],a['buyer']) or city==a['proposer']:raise ValueError('받은 제안만 조건을 조정할 수 있습니다.')
 if type(qty)!=int or not 1<=qty<=32:raise ValueError('수량은 1~32포대로 입력하세요.')
 if money is None:
  if a['money']%a['quantity']:raise ValueError('단가가 일정한 제안만 수량을 수정할 수 있습니다.')
  money=qty*(a['money']//a['quantity'])
 if type(money)!=int or not 1<=money<=1000000:raise ValueError('가격을 확인하세요.')
 if (qty,money)==(a['quantity'],a['money']):raise ValueError('수량이나 가격을 바꿔 주세요.')
 if city==a['seller']:selected=post(db,city,r.get('post'),ready=False)
 else:selected=[a['post'],a['generation']]
 city_trade_routes.require_posts(db,room.coordinator.scenario['cities'],a['seller'],a['buyer'],selected)
 same_unit=money*a['quantity']==a['money']*qty
 partial=a['allow_partial'] and city==a['seller'] and a['proposer']==a['buyer'] and qty<a['quantity'] and same_unit
 if partial:
  db.execute("UPDATE trade_agreement SET quantity=?,money=?,proposer=?,state='active',post=?,generation=?,due_tick=0 WHERE id=?",(qty,money,city,*selected,a['id']))
  return
 # New terms: the offer record follows them, so a later restore validates the counter itself.
 original=payload(city,a['seller'],a['buyer'],a['resource'],qty,money,a['repeat'],selected,0)
 db.execute("UPDATE trade_agreement SET quantity=?,money=?,proposer=?,state='offered',post=?,generation=?,allow_partial=0,offer_payload=? WHERE id=?",
            (qty,money,city,*selected,original,a['id']))

def validate(a,cities):
 for name in ('revision','allow_partial','due_tick','expired'):
  if type(a[name])!=int:raise ValueError('협상 숫자 오류')
 if a['due_tick']<0 or a['due_tick']>=2**53 or a['expired'] not in (0,1):raise ValueError('납기 기록 오류')
 if a['revision']<0 or a['allow_partial'] not in (0,1):raise ValueError('협상 상태 오류')
 for name in ('offer_payload','action_key','action_payload'):
  if not isinstance(a[name],str) or len(a[name])>2048:raise ValueError('협상 기록 오류')
 if a['action_key'] and (len(a['action_key'])!=32 or any(c not in '0123456789abcdef' for c in a['action_key'])):raise ValueError('협상 요청 오류')
 if a['offer_payload']:
  try:
   origin,seller,buyer,res,qty,money,repeat,selected,partial=json.loads(a['offer_payload'])
   valid=(origin in (seller,buyer) and (seller,buyer,res,repeat,partial)==(a['seller'],a['buyer'],a['resource'],a['repeat'],a['allow_partial'])
    and type(qty)==int and 1<=qty<=32 and type(money)==int and 1<=money<=1000000
    and isinstance(selected,list) and len(selected)==2 and all(type(n)==int for n in selected)
    and (not partial or origin==buyer) and a['quantity']<=qty and a['money']*qty==money*a['quantity'])
  except (ValueError,TypeError):valid=False
  if not valid:raise ValueError('협상 원본 조건 오류')
 elif a['allow_partial']:raise ValueError('일부 수락 원본 조건 누락')
