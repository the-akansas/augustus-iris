"""Bounded chat delivery on existing authenticated replies. No extra network poll."""
def attach(room, request, response):
    after=request.get('_chat_after')
    if not response.get('ok') or request.get('op')=='chat_read' or type(after) is not int or not 0<=after<=9223372036854775807:
        return response
    try:
        query={k:request.get(k) for k in ('protocol','build','session','scenario','city','token')}
        query.update(op='chat_read',after=after)
        response['chat_messages']=room.request(query)['messages'][:16]
    except Exception:
        # Optional delivery must never change an already committed primary result.
        pass
    return response
