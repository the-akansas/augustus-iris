"""Prepare local Korean game resources for creator tools; never edit user settings or original assets."""
import json,os
from pathlib import Path
def valid_data(path):
    return bool(path) and all((Path(path)/n).is_file() for n in ('c3.sg2','mission1.pak','c3.emp','c3_model.txt'))
def environment(app,environ=None):
    app=Path(app);env=dict(os.environ if environ is None else environ)
    explicit=env.get('AUGUSTUS_C3_DATA')
    if explicit and not valid_data(explicit):raise ValueError('AUGUSTUS_C3_DATA 폴더에 시저 3 본편 자료가 없습니다.')
    settings={}
    try:settings=json.loads((app/'network-settings.json').read_text(encoding='utf-8-sig'))
    except (OSError,ValueError):pass
    choices=[explicit,settings.get('game_data'),r'C:\Program Files (x86)\Steam\steamapps\common\Caesar 3\C3',app.parent/'engine-test-rc20/game-data']
    source=next((Path(x) for x in choices if valid_data(x)),None)
    if source is None:raise ValueError('시저 3 본편 폴더를 찾지 못했습니다. 본편 경로를 지정해 주세요.')
    # Reuse the original source of an existing prepared copy, avoiding nested private copies.
    try:
        original=json.loads((source/'prepared.json').read_text(encoding='utf8')).get('source')
        if valid_data(original):source=Path(original)
    except (OSError,ValueError):pass
    from prepare_network_data import prepare
    env['AUGUSTUS_C3_DATA']=str(prepare(source,app/'private-game-data',app/'korean'))
    # Flag cloth and post office roof pictures, made from the player's own game when missing (caesar3_tints.py). The Global
    # edition does not ship them: opening the editor before ever starting multiplayer left the engine without them and
    # its log with ERROR lines, so every engine check failed (2026-11-17). Never fatal.
    try:
        import caesar3_tints;caesar3_tints.ensure(source)
    except Exception:pass
    return env
