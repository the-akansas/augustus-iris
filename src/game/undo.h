#ifndef GAME_UNDO_H
#define GAME_UNDO_H

#include "building/building.h"

int game_can_undo(void);

void game_undo_disable(void);

/* Call BEFORE a world event changes map/building ownership. Multiplayer can
 * advance while a construction drag holds a snapshot of the old map. */
void game_undo_prepare_world_change(void);

void game_undo_add_building(building *b);

void game_undo_adjust_building(building *b);

void game_undo_record_building_type(building *b);

void game_undo_restore_building_types(void);

int game_undo_contains_building(int building_id);

void game_undo_restore_building_state(void);

void game_undo_restore_map(int include_properties);

int game_undo_start_build(building_type type);

void game_undo_finish_build(int cost);

void game_undo_perform(void);

void game_undo_reduce_time_available(void);

#endif // GAME_UNDO_H
