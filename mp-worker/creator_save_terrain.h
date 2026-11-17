/* Saved city (.svx) -> terrain-only Augustus map (.mapx). Native loader and native scenario writer; no UI input.
 * Kept: the map itself - terrain, water, elevation and ramps, trees, rocks, shrubs, meadow, marsh, beach, native
 * villages and their land, entry/exit, river, fishing, herd and invasion points, earthquake point, climate.
 * Removed: everything the city built - buildings, roads, plazas, highways, walls and gates, aqueducts, gardens,
 * rubble - and the water-coverage ranges derived from them. A tile that was a tree before it was cleared for building
 * (TERRAIN_ORIGINALLY_TREE) becomes a tree again, as on the original map; any other freed tile becomes empty land.
 * The result is then checked by the existing mapx inspection (load, export, reload, compare). */
#ifndef CREATOR_SAVE_TERRAIN_H
#define CREATOR_SAVE_TERRAIN_H
#include "game/file.h"
#include "game/file_editor.h"
#include "building/building.h"
#include "map/building.h"
#include "map/grid.h"
#include "map/property.h"
#include "map/sprite.h"
#include "map/terrain.h"
#include "map/tiles.h"
#include "scenario/property.h"

#define CREATOR_SAVE_LIMIT (64 * 1024 * 1024)
#define CREATOR_BUILT_TERRAIN (TERRAIN_BUILDING | TERRAIN_ROAD | TERRAIN_HIGHWAY | TERRAIN_AQUEDUCT | \
    TERRAIN_WALL_OR_GATEHOUSE | TERRAIN_GARDEN | TERRAIN_RUBBLE | TERRAIN_RESERVOIR_RANGE | TERRAIN_FOUNTAIN_RANGE)

static int creator_native_village(building_type type)
{
    switch (type) {
        case BUILDING_NATIVE_HUT: case BUILDING_NATIVE_MEETING: case BUILDING_NATIVE_CROPS:
        case BUILDING_NATIVE_HUT_ALT: case BUILDING_NATIVE_WATCHTOWER: case BUILDING_NATIVE_MONUMENT:
        case BUILDING_NATIVE_DECORATION: case BUILDING_NATIVE_WELL: case BUILDING_NATIVE_LARGE_HUT_ALT:
        case BUILDING_NATIVE_HUT_ALT_2: case BUILDING_NATIVE_LARGE_HUT_ALT_2: case BUILDING_NATIVE_PALISADE:
            return 1;
        default:
            return 0;
    }
}

static int creator_save_terrain(const char *in, const char *out)
{
    char path[2048];
    snprintf(path, sizeof(path), "%s/city.svx", in);
    FILE *probe = fopen(path, "rb");
    if (!probe) return 0;
    long length = fseek(probe, 0, SEEK_END) ? -1 : ftell(probe);
    fclose(probe);
    if (length < 16 || length > CREATOR_SAVE_LIMIT) {
        fprintf(stderr, "Creator save terrain rejected: size\n");
        return 0;
    }
    if (game_file_load_saved_game(path) != 1) {
        fprintf(stderr, "Creator save terrain rejected: not a readable saved city\n");
        return 0;
    }
    int removed = 0, trees = 0, kept = 0;
    for (int y = 0; y < map_grid_height(); y++) {
        for (int x = 0; x < map_grid_width(); x++) {
            int offset = map_grid_offset(x, y);
            unsigned int id = map_building_at(offset);
            if (id) {
                const building *b = building_main(building_get(id));
                if (b && creator_native_village(b->type)) {
                    kept++;
                    continue;
                }
            }
            int terrain = map_terrain_get(offset);
            if (!id && !(terrain & CREATOR_BUILT_TERRAIN)) continue;
            int bare = terrain & ~CREATOR_BUILT_TERRAIN;
            if ((terrain & TERRAIN_ORIGINALLY_TREE) &&
                !(bare & (TERRAIN_WATER | TERRAIN_ROCK | TERRAIN_ELEVATION | TERRAIN_ACCESS_RAMP | TERRAIN_TREE))) {
                bare |= TERRAIN_TREE;
                trees++;
            }
            map_terrain_set(offset, bare);
            map_building_set(offset, 0);
            map_property_clear_multi_tile_xy(offset);
            map_property_set_multi_tile_size(offset, 1);
            map_property_mark_draw_tile(offset);
            map_property_clear_plaza_earthquake_or_overgrown_garden(offset);
            map_property_clear_constructing(offset);
            map_property_clear_deleted(offset);
            map_sprite_clear_tile(offset);
            removed++;
        }
    }
    for (unsigned int i = 1; i < building_count(); i++) {
        building *b = building_get(i);
        if (b->state != BUILDING_STATE_UNUSED && !creator_native_village(building_main(b)->type)) {
            b->state = BUILDING_STATE_UNUSED;
        }
    }
    map_tiles_update_all();
    snprintf(path, sizeof(path), "%s/save-terrain.json", out);
    FILE *report = fopen(path, "w");
    if (!report) return 0;
    fprintf(report, "{\"removed_tiles\":%d,\"restored_trees\":%d,\"native_tiles\":%d,\"width\":%d,\"height\":%d,\"climate\":%d}",
        removed, trees, kept, map_grid_width(), map_grid_height(), scenario_property_climate());
    if (fclose(report)) return 0;
    snprintf(path, sizeof(path), "%s/terrain.mapx", out);
    return game_file_editor_write_scenario(path);
}
#endif
