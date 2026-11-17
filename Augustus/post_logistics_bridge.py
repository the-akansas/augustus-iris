"""Bounded native collection targets; these hints never mutate cargo or money."""
def publish(b,data):
 sites={p['peer']:(p['building'],p['generation']) for p in data['routes']['posts'] if p['city']==b.client.city and p['active']}
 needs={}
 def demand(peer,res,qty,contract=0):
  if peer in sites:
   key=(*sites[peer],res,contract);needs[key]=min(32,needs.get(key,0)+qty)
 for a in data['agreements']['agreements']:
  if a['seller']==b.client.city and a['state'] in ('offered','active') and not a['transfer']:
   demand(a['buyer'],a['resource'],a['quantity'])
 for t in data['rows']:
  if t['sender']==b.client.city and t['resource'] and t['state'] in ('offered','queued','collecting'):
   demand(t['receiver'],t['resource'],t['quantity'],t['id'])
 b.write_changed('post-demand.txt',''.join(f'{site} {generation} {res} {qty} {contract}\n' for (site,generation,res,contract),qty in sorted(needs.items())))
 return sites
