"""Display-only saved-game grouping: never removes or rewrites saved data."""
from network_preferences import display_line

def save_choices(entries,project):
 result=[];seen=set()
 for saved in sorted(entries,key=lambda r:(r['sort_time'],r['id']),reverse=True):
  if not saved['available']:continue
  key=saved['database'];latest=key not in seen;seen.add(key)
  category='이어하기' if latest else '이전 저장'
  # When it was saved comes first, to the second (user 2026-11-13): the list row is narrow and cut at the end.
  when=display_line(saved['modified']);when=when[5:] if len(when)==19 and when[4]=='-' else when   # '2026-11-13 11:11:50' -> '11-13 11:11:50'
  label='['+category+'] '+when+' · '+display_line(saved.get('title','공동 게임'))+' · '+display_line(saved['date'])+' #'+str(saved['id'])
  if saved['status'].startswith('남은 도시'):label+=' · 남은 도시'
  import maker_room
  if maker_room.is_maker(key):label+=' · 제작자 방'   # continued only with 시나리오 제작자 모드 ticked (maker_room.check)
  result.append(dict(label=label,project=project,restore=key,save_id=saved['id']))
 return result
