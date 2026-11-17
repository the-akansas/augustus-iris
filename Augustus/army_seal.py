"""Sending legions to other players' cities (support and attack) is sealed (user 2026-11-13 23:32): armies play like
the original Caesar III. The room refuses every army order and closes what an older room still had open; the games release their side of it
when a save is loaded (src/multiplayer/army_seal.h / army_seal.c, 2026-11-14): nothing of it acts in the game. The code
stays for later: set SEALED=False here and MP_ARMY_DISPATCH_SEALED 0 there to bring it back."""
SEALED=True
REASON='군단 파견(지원군·공격)은 지금 쓰지 않습니다. 군대는 원래 시저 3 방식입니다.'
