/* Native check for test_chat_affiliation.py: compiles the game's REAL multiplayer/chat.c (archive key colour,
 * toast colour, colour mark) and the REAL widget/city/multiplayer_affiliation.inc (bridge files, figure chain,
 * trade post binding, tooltip text) against small stand-ins for the engine's figure/building/message stores.
 * Usage: probe <bridge folder>. Prints ALL OK or the failed check. No window, no input. */
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include "graphics/tooltip.h"
#include "multiplayer/chat.c"
#include "widget/city/multiplayer_affiliation.inc"

static int failures;
#define CHECK(c, ...) do { if (!(c)) { failures++; printf("FAIL %s:%d ", __FILE__, __LINE__); printf(__VA_ARGS__); printf("\n"); } } while (0)

/* ---- stand-ins ---- */
static time_millis now_ms = 1000;
time_millis time_get_millis(void) { return now_ms; }
int window_is(window_id id) { return 1; }
int mp_clock_active(void) { return 1; }
/* chat.c translates system lines and leaves typed text alone (core/mp_i18n.c): here every text stays as it is */
void mp_i18n_suspend(int on) { (void) on; }
const char *mp_i18n_translate(const char *text) { return text; }
uint32_t mp_player_color(int index)
{
    static const uint32_t colors[8] = {0xff62b9ff,0xfff4f4f0,0xff65db91,0xffffbd61,0xffc8a0ff,0xff60e0da,0xffff97d3,0xffdedf6d};
    return index >= 0 && index < 8 ? colors[index] : 0xffcbd1d7;
}
static struct { int x, y, w, h; uint32_t c; } fills[16], rects[16];
static int fill_count, rect_count;
void graphics_fill_rect(int x, int y, int w, int h, color_t c) { if (fill_count < 16) { fills[fill_count].x = x; fills[fill_count].c = c; fill_count++; } }
void graphics_draw_rect(int x, int y, int w, int h, color_t c) { if (rect_count < 16) { rects[rect_count].x = x; rects[rect_count].c = c; rect_count++; } }
void city_message_pin_chat(int custom_id, int unread) {}
const char *dir_get_file_at_location(const char *filepath, int location) { return 0; }
const char *dir_append_location(const char *filename, int location) { return "/nonexistent/x"; }
FILE *file_open(const char *filename, const char *mode) { return 0; }
int file_close(FILE *stream) { return 0; }
#ifdef _WIN32
int augustus_move_file(const char *from, const char *to, unsigned long flags) { return 0; }
#endif

static text_blob_string_t blobs[256];
static int blob_count;
const text_blob_string_t *message_media_text_blob_add_encoded(const char *text)
{
    text_blob_string_t *b = &blobs[blob_count++];
    b->text = (uint8_t *) strdup(text);
    return b;
}
static const text_blob_string_t *blob(const char *text) { return message_media_text_blob_add_encoded(text); }
static custom_message_t messages[128];
static int message_count;
int custom_messages_count(void) { return message_count; }
custom_message_t *custom_messages_get(int id) { return id >= 1 && id <= message_count ? &messages[id - 1] : 0; }
int custom_messages_get_id_by_uid(const uint8_t *uid)
{
    for (int i = 0; i < message_count; i++) if (messages[i].linked_uid && !strcmp((const char *) messages[i].linked_uid->text, (const char *) uid)) return i + 1;
    return 0;
}
custom_message_t *custom_messages_create(const uint8_t *uid)
{
    if (custom_messages_get_id_by_uid(uid)) return 0;
    custom_message_t *m = &messages[message_count++];
    memset(m, 0, sizeof(*m));
    m->id = message_count; m->in_use = 1; m->linked_uid = blob((const char *) uid);
    return m;
}
void encoding_from_utf8(const char *input, uint8_t *output, int output_length) { snprintf((char *) output, output_length, "%s", input); }

static figure figures[16];
static formation formations[8];
static building buildings[8];
static unsigned tile_figure;
unsigned int map_figure_at(int grid_offset) { return tile_figure; }
figure *figure_get(unsigned int id) { return &figures[id < 16 ? id : 0]; }
unsigned int figure_count(void) { return 16; }
int figure_is_dead(const figure *f) { return f->state != FIGURE_STATE_ALIVE; }
formation *formation_get(int id) { return &formations[id >= 0 && id < 8 ? id : 0]; }
int formation_count(void) { return 8; }
building *building_get(unsigned int id) { return &buildings[id < 8 ? id : 0]; }
building *building_main(const building *b) { return (building *) b; }

/* ---- helpers ---- */
static char dir[1024];
static void write_file(const char *name, const char *text)
{
    char path[1200];
    snprintf(path, sizeof(path), "%s/%s", dir, name);
    FILE *f = fopen(path, "wb");
    fputs(text, f);
    fclose(f);
    now_ms += 1000; /* past the 500 ms re-read interval */
}
static const char *tip(int grid, int building_id)
{
    static char text[600];
    text[0] = 0;
    if (!mp_affiliation_text(grid, building_id, text, sizeof(text))) return "";
    return text;
}
static void soldier(int id, int type, int formation_id, int next)
{
    figures[id].state = FIGURE_STATE_ALIVE; figures[id].type = type;
    figures[id].formation_id = formation_id; figures[id].next_figure_id_on_same_tile = next;
}

int main(int argc, char **argv)
{
    snprintf(dir, sizeof(dir), "%s", argc > 1 ? argv[1] : ".");
#ifdef _WIN32
    _putenv_s("AUGUSTUS_MP_BRIDGE", dir);
#else
    setenv("AUGUSTUS_MP_BRIDGE", dir, 1);
#endif

    /* ---- chat: colour on the archive key ---- */
    const char *keys[] = {"mpchat:aaaa:1:c0", "mpchat:aaaa:2:c1", "mpchat:aaaa:3:c2", "mpchat:aaaa:4:c3", "mpchat:aaaa:5:c4",
        "mpchat:aaaa:6:c5", "mpchat:aaaa:7:c6", "mpchat:aaaa:8:c7", "mpchat:aaaa:9", "mpchat:aaaa:10:c8",
        "mpchat:aaaa:11:cx", "mpchat:aaaa:c3", "mpchat:aaaa:12:c1x"};
    const int expect[] = {0, 1, 2, 3, 4, 5, 6, 7, -1, -1, -1, -1, -1};
    for (int i = 0; i < 13; i++) CHECK(uid_color(keys[i]) == expect[i], "uid_color(%s)", keys[i]);
    char journal[4096] = "";
    for (int i = 0; i < 9; i++) { char line[256]; snprintf(line, sizeof(line), "%s\tP%d\t본문 %d\n", keys[i], i, i); strcat(journal, line); }
    strcat(journal, "mpchat:aaaa:20\t시스템\t알림\thistory-only\n");
    write_file("chat-events.txt", journal);
    mp_chat_poll();
    CHECK(mp_chat_count() == 10, "chat records %d", mp_chat_count());
    for (int i = 0; i < 9; i++) CHECK(mp_chat_color(mp_chat_record(i)) == expect[i], "archived colour %d", i);
    CHECK(mp_chat_color(mp_chat_record(9)) == -1, "system colour");
    /* toasts: the last three shown lines carry their sender's colour (system line shows no toast) */
    CHECK(mp_chat_toast_color(0) == 6 && mp_chat_toast_color(1) == 7 && mp_chat_toast_color(2) == -1, "toast colours %d %d %d",
        mp_chat_toast_color(0), mp_chat_toast_color(1), mp_chat_toast_color(2));
    /* reload keeps the colour (it is in the saved key, not in a lookup of the current roster) */
    mp_chat_reload();
    CHECK(mp_chat_count() == 10 && mp_chat_color(mp_chat_record(1)) == 1, "after reload");
    /* colour mark: fill + dark edge for 0-7 (white too), nothing for -1 */
    fill_count = rect_count = 0;
    mp_chat_draw_chip(10, 10, 7, 10, 1);
    CHECK(fill_count == 1 && fills[0].c == 0xfff4f4f0 && rect_count == 1 && rects[0].c == 0xff000000, "white mark with edge");
    for (int c = 0; c < 8; c++) { fill_count = 0; mp_chat_draw_chip(0, 0, 7, 10, c); CHECK(fill_count == 1 && fills[0].c == mp_player_color(c), "mark %d", c); }
    fill_count = rect_count = 0;
    mp_chat_draw_chip(10, 10, 7, 10, -1);
    CHECK(fill_count == 0 && rect_count == 0, "no mark without colour");

    /* Saved messages and a regenerated journal may use different colour suffixes.
     * Their session/message identity must still be deduplicated in the native archive. */
    write_file("chat-events.txt", "mpchat:aaaa:1\tP0\treplayed old format\nmpchat:aaaa:2:c7\tP1\treplayed different colour\nmpchat:aaaa:9:c3\tP8\treplayed new format\n");
    mp_chat_reload();
    mp_chat_poll();
    CHECK(mp_chat_count() == 10, "mixed archive keys duplicated: %d", mp_chat_count());
    CHECK(mp_chat_color(mp_chat_record(0)) == 0 && mp_chat_color(mp_chat_record(1)) == 1 && mp_chat_color(mp_chat_record(8)) == -1,
        "existing saved colours changed");
    CHECK(!mp_chat_toast(0) && !mp_chat_toast(1) && !mp_chat_toast(2), "replayed duplicate produced a toast");

    /* ---- trade posts: partner by the post's own route slot ---- */
    write_file("post-partners.txt", "AUGPOST1\n2\t타렌툼\tAurelia\n3\t네아폴리스\tAurelia\n4\t브룬디시움\tBob (연결 끊김)\n5\t스파르타\t담당자 없음\n");
    buildings[1].type = BUILDING_PLAYER_TRADE_POST; buildings[1].state = BUILDING_STATE_IN_USE; buildings[1].subtype.orientation = 2;
    buildings[2].type = BUILDING_PLAYER_TRADE_POST; buildings[2].state = BUILDING_STATE_IN_USE; buildings[2].subtype.orientation = 3;
    buildings[3].type = BUILDING_PLAYER_TRADE_POST; buildings[3].state = BUILDING_STATE_IN_USE; buildings[3].subtype.orientation = 7;
    buildings[4].type = BUILDING_PLAYER_TRADE_POST; buildings[4].state = BUILDING_STATE_IN_USE; buildings[4].subtype.orientation = 4;
    buildings[5].type = BUILDING_WAREHOUSE; buildings[5].state = BUILDING_STATE_IN_USE; buildings[5].subtype.orientation = 2;
    tile_figure = 0;
    CHECK(!strcmp(tip(100, 1), "전용 교역소\n교역 상대: 타렌툼 · Aurelia"), "post 1: %s", tip(100, 1));
    CHECK(!strcmp(tip(100, 2), "전용 교역소\n교역 상대: 네아폴리스 · Aurelia"), "post 2: %s", tip(100, 2));
    CHECK(!strcmp(tip(100, 3), "전용 교역소\n교역 상대: 상대 정보 미확인"), "post with unknown slot: %s", tip(100, 3));
    CHECK(!strcmp(tip(100, 4), "전용 교역소\n교역 상대: 브룬디시움 · Bob (연결 끊김)"), "disconnected: %s", tip(100, 4));
    CHECK(!strcmp(tip(100, 5), ""), "a warehouse has no partner text");
    write_file("post-partners.txt", "AUGPOST1\n2\t타렌툼\tNewbie\n");            /* the partner changed hands */
    CHECK(!strcmp(tip(100, 1), "전용 교역소\n교역 상대: 타렌툼 · Newbie"), "refreshed: %s", tip(100, 1));
    CHECK(!strcmp(tip(100, 2), "전용 교역소\n교역 상대: 상대 정보 미확인"), "line gone -> unknown, never another name");
    write_file("post-partners.txt", "garbage\n2\t타렌툼\tX\n");
    CHECK(!strcmp(tip(100, 1), "전용 교역소\n교역 상대: 상대 정보 미확인"), "foreign file ignored");

    /* ---- soldiers ---- */
    write_file("army-owners.txt", "AUGARMY1\nown\t카푸아\tAurelia\n11\t타렌툼\t김철수\n12\t네아폴리스\tAurelia\n");
    formations[1].in_use = 1; formations[1].is_legion = 1;                                       /* my legion */
    formations[2].in_use = 1; formations[2].is_legion = 1; formations[2].mp_expedition_id = 11; formations[2].mp_expedition_role = 1;
    formations[3].in_use = 1; formations[3].mp_expedition_id = 12; formations[3].mp_expedition_role = 2;
    formations[4].in_use = 1; formations[4].is_legion = 1; formations[4].mp_expedition_id = 99; formations[4].mp_expedition_role = 1;
    formations[5].in_use = 1;                                                                    /* an enemy army */
    soldier(1, FIGURE_FORT_LEGIONARY, 1, 0);
    tile_figure = 1;
    CHECK(!strcmp(tip(200, 0), "소속: 카푸아 · Aurelia"), "own: %s", tip(200, 0));
    soldier(2, FIGURE_FORT_JAVELIN, 2, 0); tile_figure = 2;
    CHECK(!strcmp(tip(200, 0), "방문 지원군\n소속: 타렌툼 · 김철수"), "support: %s", tip(200, 0));
    soldier(3, FIGURE_FORT_MOUNTED, 3, 0); tile_figure = 3;
    CHECK(!strcmp(tip(200, 0), "방문 공격군\n소속: 네아폴리스 · Aurelia"), "attacker: %s", tip(200, 0));
    soldier(4, FIGURE_FORT_LEGIONARY, 4, 0); tile_figure = 4;
    CHECK(!strcmp(tip(200, 0), "방문 지원군\n소속 정보 미확인"), "unknown token: %s", tip(200, 0));
    /* non-player forces: natives, barbarians, the emperor's legionaries -> no owner text */
    soldier(5, FIGURE_ENEMY_CAESAR_LEGIONARY, 5, 0); tile_figure = 5;
    CHECK(!strcmp(tip(200, 0), ""), "emperor's troops");
    soldier(6, FIGURE_ENEMY43_SPEAR, 5, 0); tile_figure = 6;
    CHECK(!strcmp(tip(200, 0), ""), "barbarians");
    soldier(7, FIGURE_INDIGENOUS_NATIVE, 0, 0); tile_figure = 7;
    CHECK(!strcmp(tip(200, 0), ""), "natives");
    /* a tile with an enemy first and a visiting legion behind it: the soldier is found on the chain */
    soldier(8, FIGURE_ENEMY43_SPEAR, 5, 2); tile_figure = 8;
    CHECK(!strcmp(tip(200, 1), "방문 지원군\n소속: 타렌툼 · 김철수"), "chain: %s", tip(200, 1));
    /* soldier wins over a post under it; dead soldier is skipped */
    figures[2].state = FIGURE_STATE_DEAD; tile_figure = 2;
    CHECK(!strcmp(tip(200, 1), "전용 교역소\n교역 상대: 상대 정보 미확인"), "dead soldier skipped: %s", tip(200, 1));
    figures[2].state = FIGURE_STATE_ALIVE;
    /* the legion went home / the expedition was cleared */
    formations[2].in_use = 0; tile_figure = 2;
    CHECK(!strcmp(tip(200, 0), ""), "cleared formation");
    formations[2].in_use = 1;
    write_file("army-owners.txt", "AUGARMY1\nown\t카푸아\tAurelia\n");        /* token no longer listed */
    CHECK(!strcmp(tip(200, 0), "방문 지원군\n소속 정보 미확인"), "stale owner not kept: %s", tip(200, 0));
    write_file("army-owners.txt", "AUGARMY1\n");                              /* not joined yet */
    tile_figure = 1;
    CHECK(!strcmp(tip(200, 0), "소속 정보 미확인"), "own unknown: %s", tip(200, 0));

    /* ---- tooltip context ---- */
    write_file("army-owners.txt", "AUGARMY1\nown\t카푸아\tAurelia\n");
    tooltip_context c = { 0, 0 };
    CHECK(mp_affiliation_tooltip(&c, 200, 0) && c.type == TOOLTIP_OVERLAY && c.high_priority && c.precomposed_text &&
        !strcmp((const char *) c.precomposed_text, "소속: 카푸아 · Aurelia"), "tooltip context");
    tooltip_context none = { 0, 0 };
    tile_figure = 0;
    CHECK(!mp_affiliation_tooltip(&none, 200, 5) && none.type == TOOLTIP_NONE && !none.precomposed_text, "no tooltip elsewhere");

    if (failures) { printf("%d FAILED\n", failures); return 1; }
    printf("ALL OK\n");
    return 0;
}
