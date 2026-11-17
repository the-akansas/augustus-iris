"""Outcome for the single native command mailbox; no transport authority."""
from mailbox_io import publish_text

def tracked(text):
    verb,_,body=text.partition('\n')
    return verb.startswith('speed') or verb=='trade' and body.split(' ',1)[0] in ('route_offer','route_accept','route_reject','offer','accept','reject','contract_offer','contract_counter','contract_accept','contract_stop','contract_resume')

def begin(bridge,text):
    bridge.feedback_command=text if tracked(text) else None

def finish(bridge,error=None):
    text=getattr(bridge,'feedback_command',None)
    if text is None:return
    if error is not None:message='요청 실패: '+str(error).replace('\n',' ')[:180]
    elif text.startswith('speed'):message='게임 속도 변경이 적용되었습니다.'
    elif text.startswith(('trade\naccept ','trade\ncontract_accept ')):message='수락이 반영되었습니다.'
    elif text.startswith(('trade\noffer ','trade\ncontract_offer ')):message='제안을 보냈습니다. 상대의 수락을 기다립니다.'
    else:message='요청이 반영되었습니다.'
    publish_text(bridge.root/'command-outcome.txt','-1' if error is not None else '1')
    publish_text(bridge.root/'command-result.txt',message)
    bridge.feedback_command=None
