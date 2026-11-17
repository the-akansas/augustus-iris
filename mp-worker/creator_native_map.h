/* Private map conversion, using the native serializer and editor. No UI input. */
#ifndef CREATOR_NATIVE_MAP_H
#define CREATOR_NATIVE_MAP_H
#include "game/file_io.h"
#include "game/file_editor.h"
#include "game/game.h"
#include "editor/editor.h"
#include "editor/tool.h"
#include "core/file.h"

#define CREATOR_MAP_LIMIT (8 * 1024 * 1024)
static int creator_load_native_map(const char *path)
{
    FILE *f = file_open(path, "rb");
    if (!f) return 0;
    if (fseek(f, 0, SEEK_END)) { fclose(f); return 0; }
    long length = ftell(f);
    if (length < 16 || length > CREATOR_MAP_LIMIT || fseek(f, 0, SEEK_SET)) { fclose(f); return 0; }
    uint8_t *bytes = malloc((size_t) length);
    if (!bytes) { fclose(f); return 0; }
    int ok = fread(bytes, 1, (size_t) length, f) == (size_t) length;
    fclose(f);
    saved_game_info info = {0}; buffer buf;
    buffer_init(&buf, bytes, length);
    ok = ok && !memcmp(bytes, "VERSION", 8) && game_file_io_read_scenario_info_from_buffer(&buf, &info) == 1 &&
        info.map_size >= 40 && info.map_size <= 160 && info.climate >= 0 && info.climate <= 2;
    if (ok) {
        /* A freshly cleared schema3 scenario has no campaign descriptor. The native
         * importer expects one while initializing; reset it after importing. */
        ok = game_campaign_load(CAMPAIGN_ORIGINAL_NAME);
        scenario_set_campaign_mission(0); scenario_set_campaign_rank(0);
        if (ok) ok = game_file_start_scenario_from_buffer(bytes, (int) length, 0);
    }
    free(bytes);
    if (!ok) fprintf(stderr, "Creator native map rejected: invalid or unsupported mapx\n");
    return ok;
}
static int creator_native_roundtrip(const char *input, const char *output, int probe)
{
    char path[2048];
    snprintf(path, sizeof(path), "%s/terrain.mapx", input);
    if (!editor_is_present() || !game_init_editor() || !game_file_editor_load_scenario(path)) return 0;
    if (probe) {
        /* Exercise the real native tools via their C API: never synthesize user
         * mouse/key events. Use interior unoccupied areas and an existing river. */
        map_tile hill={0}, meadow={0}, fish={0};
        int w=map_grid_width(),h=map_grid_height();
        for(int y=8;y<h-8;y++)for(int x=8;x<w-8;x++){
            int p=map_grid_offset(x,y);
            if(!fish.grid_offset && map_terrain_is(p,TERRAIN_WATER))fish=(map_tile){x,y,p};
            if(map_elevation_at(p))continue;
            int clear=1;for(int yy=-3;yy<=3;yy++)for(int xx=-3;xx<=3;xx++)if(map_terrain_is(map_grid_offset(x+xx,y+yy),TERRAIN_WATER|TERRAIN_ROCK|TERRAIN_BUILDING|TERRAIN_ROAD|TERRAIN_ELEVATION|TERRAIN_AQUEDUCT|TERRAIN_WALL_OR_GATEHOUSE))clear=0;
            if(!clear)continue;
            if(!hill.grid_offset)hill=(map_tile){x,y,p};
            else if(!meadow.grid_offset && abs(x-hill.x)+abs(y-hill.y)>16)meadow=(map_tile){x,y,p};
        }
        if(!hill.grid_offset || !meadow.grid_offset || !fish.grid_offset)return 0;
        editor_tool_set_brush_size(3);editor_tool_set_type(TOOL_GRASS);
        editor_tool_start_use(&hill);editor_tool_update_use(&hill);editor_tool_end_use(&hill);
        editor_tool_start_use(&meadow);editor_tool_update_use(&meadow);editor_tool_end_use(&meadow);
        editor_tool_set_type(TOOL_RAISE_LAND);
        editor_tool_start_use(&hill);editor_tool_update_use(&hill);editor_tool_end_use(&hill);
        editor_tool_set_type(TOOL_MEADOW);
        editor_tool_start_use(&meadow);editor_tool_update_use(&meadow);editor_tool_end_use(&meadow);
        editor_tool_set_with_id(TOOL_FISHING_POINT,0);
        editor_tool_start_use(&fish);editor_tool_update_use(&fish);editor_tool_end_use(&fish);
        snprintf(path,sizeof(path),"%s/tool-probe.json",output);FILE *f=fopen(path,"w");if(!f)return 0;
        fprintf(f,"{\"hill\":[%d,%d],\"meadow\":[%d,%d],\"fish\":[%d,%d]}",hill.x,hill.y,meadow.x,meadow.y,fish.x,fish.y);fclose(f);
    }
    if (!creator_export_terrain(output)) return 0;
    snprintf(path, sizeof(path), "%s/terrain.mapx", output);
    return game_file_editor_write_scenario(path);
}
#endif
