"""Keep lobby history without replaying obsolete preparation notices over the city."""
COUNTDOWN_TEXTS = {f'{i}초 후 게임을 시작합니다.' for i in range(1, 6)} | {'게임을 시작합니다.'}
PREPARATION_PREFIXES = ('참가하지 않은 도시를 중립도시로 전환합니다.', '중립도시 전환 완료:', '저장 도시와 새 도시 준비 완료.', '도시별 목표는 참가 도시만 적용합니다.')
def journal_key(session, message):
    """Message key for the game's chat archive. The sender's player colour AT SENDING (server chat record) rides on
    the key, so the archived message keeps it after a reload, a city change or a colour reassignment. No colour
    (system, participant without a city, old record): no suffix, the game draws no mark."""
    color = message.get('player_color', -1)
    key = f"mpchat:{session}:{message['id']}"
    return key + (f':c{color}' if type(color) is int and 0 <= color < 8 else '')
def key_base(key):
    """The key without the colour suffix: one message is archived once, whatever its key carried before."""
    head, sep, tail = key.rpartition(':')
    return head if sep and head.count(':') == 2 and len(tail) == 2 and tail[0] == 'c' and tail[1] in '01234567' else key
def journal_line(key, sender, message, phase='started'):
    history_only = phase != 'started' or (message['city'] == 'system' and (message['text'] in COUNTDOWN_TEXTS or message['text'].startswith(PREPARATION_PREFIXES)))
    return key + '\t' + sender + '\t' + message['text'] + ('\thistory-only' if history_only else '') + '\n'
