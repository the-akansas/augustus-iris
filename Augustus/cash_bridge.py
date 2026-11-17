"""One outstanding mailbox exchange. No waiting for native or disk retry loop."""
import base64,time,os,struct
import post_ipc

def active_settlement(bridge):
    # A throne spend under way counts too (user 2026-11-15: the money left only after up to 5 s, even alone, because
    # with no trade under way the exchange with the city's engine ran every 5 s). throne_client sets the flag.
    if getattr(bridge,'throne_charging',False):return True
    return any(t.get('cash_live') and t.get('state') not in ('offered','finished','rejected') for t in getattr(bridge,'fleet_rows',[]))

def poll(bridge,saving=False):
    if saving:return
    now=time.monotonic();state=getattr(bridge,'cash_exchange',None)
    active=active_settlement(bridge)
    if active and not getattr(bridge,'cash_was_active',False):bridge.cash_next=0
    bridge.cash_was_active=active
    if state and now-state['created']>20:
        # Never invent success; acquire fresh proof. Native command IDs dedupe.
        bridge.cash_exchange=None;bridge.cash_next=now+10;return
    if not state:
        if now<getattr(bridge,'cash_next',0):return
        ch=bridge.client.call('cash_challenge');scope=ch['roster'];owner=ch['slot']
        bridge.write_changed('post-identity.txt',f'{scope} {owner}')
        try:cap=(bridge.root/'post-capability.bin').read_bytes()
        except OSError:return
        if len(cap)!=84 or cap[16:80]!=scope.encode() or struct.unpack_from('<I',cap,80)[0]!=owner:return
        run=cap[:16].hex()
        if run!=getattr(bridge,'cash_run',None):bridge.cash_run=run;bridge.cash_seq=0;bridge.cash_commands=[]
        commands=getattr(bridge,'cash_commands',[]);command=commands.pop(0) if commands else None
        native=None
        if command and not command.get("compact"):
            native=dict(id=command['id'],peer=ch['cities'].index(command['peer']),step=('export','escrow','receive','pay','refund_goods','refund_money').index(command['step'])+1,resource=command['asset'],amount=command['amount'])
        if command and command.get('compact'):native=dict(id=command['hash'],peer=command['epoch']+1,step=0,resource=0,amount=0,compact=True)
        if command and command.get('transport'):native['transport']=command['transport']
        bridge.cash_seq+=1;packet=post_ipc.request(run,ch['epoch'],ch['nonce'],scope,owner,bridge.cash_seq,native,receipt_epoch=command.get('epoch',0) if command else 0)
        tmp=bridge.root/'post-request.tmp';tmp.write_bytes(packet);os.replace(tmp,bridge.root/'post-request.bin')
        state=bridge.cash_exchange=dict(ch=ch,packet=packet,created=now)
        return
    try:data=(bridge.root/'post-response.bin').read_bytes()
    except OSError:return
    try:result,piece=post_ipc.response(data,state['packet'])
    except ValueError:return
    ch=state['ch'];reply=bridge.client.call('cash_report',epoch=ch['epoch'],nonce=ch['nonce'],piece=base64.b64encode(piece).decode())
    if reply['state']=='saving':return
    bridge.cash_commands=[c for c in reply.get('resend',[]) if result!=-2 or c.get('compact')]
    bridge.cash_exchange=None;bridge.cash_next=now+(0 if bridge.cash_commands else 0.1 if active else 5)
