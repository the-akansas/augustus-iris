#ifndef MULTIPLAYER_ARMY_SEAL_H
#define MULTIPLAYER_ARMY_SEAL_H

/* Sending legions to other players' cities (support and attack) is sealed (user 2026-11-13 23:32):
 * the game plays like the original Caesar III for armies. The code stays for later; the room refuses new
 * dispatches as well (Augustus/army_seal.py). What an older save still holds of it is released when the save
 * is loaded (2026-11-14), so nothing of it acts in the game. Set to 0 to bring the feature back. */
#define MP_ARMY_DISPATCH_SEALED 1

/* Removes what the dispatch left in an older save (visiting legions, legions that were away); see army_seal.c.
 * Returns how many legions it released. */
int mp_army_seal_release(void);

#endif
