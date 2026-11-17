"""시나리오 제작자 방 on a player's PC (LAN, both editions; user 2026-11-17: "다 똑같이 가는거 아니야?").

The game hall keeps a room's maker flag in its note (game_hall.py). A room on a player's PC keeps it as a file in the
room's own folder, next to room.sqlite: its saves then say themselves whether they were made in a maker room.
  * mark(): the new room is a maker room (the room answers the maker tools, dev_tools.py; the lobby status says
    'dev', and the game shows the panel, multiplayer_dev.inc)
  * check(): a maker room's save continues only with 시나리오 제작자 모드 ticked, a normal one only without it
  * is_maker(): for the save list (start_catalog.py marks such saves) and for a new host taking a room over"""
from pathlib import Path
MARK='maker-room.txt'

def is_maker(database):
    """`database`: a room's room.sqlite (or anything in the room's folder)."""
    try:return (Path(database).parent/MARK).is_file()
    except (OSError,TypeError,ValueError):return False

def check(wanted,restore):
    """Whether the new room is a maker room: what was ticked, which must be what the save was."""
    if not restore:return bool(wanted)
    saved=is_maker(restore)
    if saved!=bool(wanted):raise ValueError('제작자 방의 저장은 제작자 방에서만 이어할 수 있습니다.' if saved else '일반 방의 저장은 제작자 방에서 이어할 수 없습니다.')
    return saved

def mark(server,folder,dev):
    server.coordinator.dev_mode=bool(dev)
    if dev:(Path(folder)/MARK).write_text('1\n',encoding='ascii')
