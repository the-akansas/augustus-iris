#ifndef BUILDING_TILE_REPAIR_H
#define BUILDING_TILE_REPAIR_H

/* Repairs map tiles that point at a building that is no longer there (2026-11-14, multiplayer saves).
 * Returns the number of tiles changed. */
int building_tile_repair_all(void);

#endif
