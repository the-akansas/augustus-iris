#include "building/tile_repair.h"

#include "building/building.h"
#include "building/house.h"
#include "building/image.h"
#include "map/building_tiles.h"
#include <stdlib.h>
#include "building/properties.h"
#include "city/view.h"
#include "core/log.h"
#include "core/image.h"
#include "map/aqueduct.h"
#include "map/bridge.h"
#include "map/building.h"
#include "map/grid.h"
#include "map/image.h"
#include "map/property.h"
#include "map/random.h"
#include "map/routing_terrain.h"
#include "map/sprite.h"
#include "map/terrain.h"
#include "map/tiles.h"

/* Seen in real multiplayer saves (2026-11-14):
 *  - building tiles left behind by a building whose record was deleted: drawn black (no image) and, once the
 *    number is reused, the clear tool deleted the unrelated new building (a tower across the map) - then a crash;
 *  - tiles of a burned ruin that had already turned to rubble but still counted as a building: black, and the
 *    clear tool could not remove them;
 *  - rubble markers pointing at a building that is not a ruin: clearing that rubble deleted a live building.
 * Each tile is put back the way the game would have left it: an empty tile, or rubble. Nothing that is still a
 * consistent building is touched. Runs after a save is loaded and before the clear and repair tools act. */

static int covers(const building *b, int x, int y)
{
    return b->size > 0 && x >= b->x && x < b->x + b->size && y >= b->y && y < b->y + b->size;
}

static void detach_tile(int grid_offset)
{
    map_property_clear_constructing(grid_offset);
    map_property_set_multi_tile_size(grid_offset, 1);
    map_property_set_multi_tile_xy(grid_offset, 0, 0, 1);
    map_building_set(grid_offset, 0);
    map_building_damage_clear(grid_offset);
    map_sprite_clear_tile(grid_offset);
}

/* Restore only unambiguous residential footprints. The forward pass removes
 * stale references, but cannot replace missing tiles of an occupied merged
 * house (real joint save #3/player2). Preserve its population and inventory. */
static int repair_house_footprints(int *x_min, int *y_min, int *x_max, int *y_max)
{
    int count = building_count(), fixed = 0, conflicts = 0;
    int *claims = calloc(GRID_SIZE * GRID_SIZE, sizeof(int));
    if (!claims) {
        log_info("House footprint repair skipped: allocation failed", 0, 0);
        return 0;
    }
    /* A record with missing map tiles still owns its footprint. Do not let
     * iteration order decide which of two overlapping live records wins. */
    for (int i = 1; i < count; i++) {
        const building *b = building_get(i);
        if ((b->state != BUILDING_STATE_IN_USE && b->state != BUILDING_STATE_MOTHBALLED &&
                b->state != BUILDING_STATE_CREATED) || b->size <= 0 ||
            building_properties_for_type(b->type)->shared ||
            !map_grid_is_inside(b->x, b->y, b->size)) {
            continue;
        }
        for (int y = b->y; y < b->y + b->size; y++) {
            for (int x = b->x; x < b->x + b->size; x++) {
                int g = map_grid_offset(x, y);
                claims[g] = claims[g] && claims[g] != i ? -1 : i;
            }
        }
    }
    for (int i = 1; i < count; i++) {
        building *b = building_get(i);
        if (b->state != BUILDING_STATE_IN_USE || !b->house_size || b->size <= 0) {
            continue;
        }
        if (!map_grid_is_inside(b->x, b->y, b->size) ||
            b->grid_offset != map_grid_offset(b->x, b->y) ||
            map_building_at(b->grid_offset) != (unsigned) i ||
            !map_terrain_is(b->grid_offset, TERRAIN_BUILDING)) {
            conflicts++;
            continue;
        }
        int missing = 0, blocked = 0;
        for (int y = b->y; y < b->y + b->size; y++) {
            for (int x = b->x; x < b->x + b->size; x++) {
                int g = map_grid_offset(x, y);
                unsigned int owner = map_building_at(g);
                if (owner != (unsigned) i || !map_terrain_is(g, TERRAIN_BUILDING)) {
                    missing++;
                }
                if (claims[g] != i || (owner && owner != (unsigned) i) ||
                    map_terrain_is(g, TERRAIN_NOT_CLEAR & ~TERRAIN_BUILDING) ||
                    map_building_rubble_building_id(g)) {
                    blocked = 1;
                }
            }
        }
        if (!missing) {
            continue;
        }
        if (blocked) {
            conflicts++;
            continue;
        }
        for (int y = b->y; y < b->y + b->size; y++) {
            for (int x = b->x; x < b->x + b->size; x++) {
                int g = map_grid_offset(x, y);
                if (map_building_at(g) != (unsigned) i || !map_terrain_is(g, TERRAIN_BUILDING)) {
                    map_sprite_clear_tile(g);
                }
            }
        }
        map_building_tiles_add(i, b->x, b->y, b->size, building_image_get(b), TERRAIN_BUILDING);
        if (!b->house_population && b->type == BUILDING_HOUSE_VACANT_LOT) {
            building_house_vacant_lot_mark_draw(i);
        }
        fixed += missing;
        if (b->x < *x_min) *x_min = b->x;
        if (b->y < *y_min) *y_min = b->y;
        if (b->x + b->size - 1 > *x_max) *x_max = b->x + b->size - 1;
        if (b->y + b->size - 1 > *y_max) *y_max = b->y + b->size - 1;
    }
    free(claims);
    if (conflicts) {
        log_info("Unresolved house footprint conflicts (left unchanged):", 0, conflicts);
    }
    return fixed;
}

int building_tile_repair_all(void)
{
    int width = map_grid_width(), height = map_grid_height();
    int count = building_count(), fixed = 0;
    int x_min = width, y_min = height, x_max = -1, y_max = -1;
    for (int y = 0; y < height; y++) {
        for (int x = 0; x < width; x++) {
            int grid_offset = map_grid_offset(x, y);
            unsigned int rubble_id = map_building_rubble_building_id(grid_offset);
            if (rubble_id) {
                const building *r = (int) rubble_id < count ? building_get(rubble_id) : 0;
                /* Walls/aqueducts share one live record with surviving tiles.
                 * Their collapsed tiles legitimately keep that record for repair. */
                if (!r || r->state == BUILDING_STATE_UNUSED ||
                    (r->state != BUILDING_STATE_RUBBLE && r->type != BUILDING_BURNING_RUIN &&
                     !building_properties_for_type(r->type)->shared)) {
                    map_building_set_rubble_grid_building_id(grid_offset, 0, 1);
                }
            }
            if (!map_terrain_is(grid_offset, TERRAIN_BUILDING) || map_is_bridge(grid_offset)) {
                continue;
            }
            unsigned int id = map_building_at(grid_offset);
            if (!id) {
                continue;
            }
            const building *b = (int) id < count ? building_get(id) : 0;
            int ghost = !b || b->state == BUILDING_STATE_UNUSED;
            int burnt_out = !ghost && b->type == BUILDING_BURNING_RUIN && b->state == BUILDING_STATE_RUBBLE;
            if (!ghost && !burnt_out && b->type != BUILDING_HIPPODROME && !building_type_is_bridge(b->type) &&
                !building_properties_for_type(b->type)->shared && !covers(b, x, y) && !covers(building_main((building *) b), x, y)) {
                ghost = 1;
            }
            if (!ghost && !burnt_out) {
                continue;
            }
            detach_tile(grid_offset);
            map_aqueduct_remove(grid_offset);
            map_terrain_remove(grid_offset, TERRAIN_BUILDING);
            if (burnt_out) {
                /* What map_building_tiles_set_rubble() does when a ruin burns out. */
                map_building_set_rubble_grid_building_id(grid_offset, id, 1);
                map_terrain_remove(grid_offset, TERRAIN_CLEARABLE);
                map_terrain_add(grid_offset, TERRAIN_RUBBLE);
                map_image_set(grid_offset, image_group(GROUP_TERRAIN_RUBBLE) + (map_random_get(grid_offset) & 7));
            }
            fixed++;
            if (x < x_min) x_min = x;
            if (y < y_min) y_min = y;
            if (x > x_max) x_max = x;
            if (y > y_max) y_max = y;
        }
    }
    fixed += repair_house_footprints(&x_min, &y_min, &x_max, &y_max);
    if (fixed) {
        map_tiles_update_region_empty_land(x_min, y_min, x_max, y_max);
        map_tiles_update_region_meadow(x_min, y_min, x_max, y_max);
        map_tiles_update_region_rubble(x_min, y_min, x_max, y_max);
        map_routing_update_land();
        city_view_restore_lookup(); /* the view skips tiles that had no image when it was built; these have one now */
        log_info("Repaired map/building ownership tiles:", 0, fixed);
    }
    return fixed;
}
