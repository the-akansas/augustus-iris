/* Multiplayer hover text (included by widget/city/city.c, city view without an overlay):
 *   player trade post  ->  "전용 교역소" / "교역 상대: <city> · <player>"
 *   player soldier      ->  "소속: <city> · <player>" (a visiting legion: its sender's city, not the host city)
 * The partner of a post is its own binding (building orientation = route slot); a visiting legion is known by its
 * expedition token. Names come from post-partners.txt / army-owners.txt written by the bridge (affiliation.py) from
 * the authenticated room roster and army overview. Nothing is guessed from colour, position or list order, and
 * natives, barbarians, the original emperor's troops and any other non-player force get no owner text.
 * The two small files are re-read at most twice a second; the text is built from the figure chain of the hovered
 * tile only (no scan of all figures). No colour mark here: roofs and flags already carry the player colour. */
#include "building/building.h"
#include "core/encoding.h"
#include "core/time.h"
#include "graphics/tooltip.h"
#include "figure/figure.h"
#include "figure/formation.h"
#include "figure/type.h"
#include "map/figure.h"
#include "multiplayer/clock.h"
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#define MP_OWNER_ROWS 72
typedef struct { unsigned key; char city[160], player[160]; } mp_owner_row;
typedef struct {
    const char *file, *magic;
    unsigned read_at;
    int initialized, count, has_own;
    mp_owner_row rows[MP_OWNER_ROWS], own;
} mp_owner_table;
static mp_owner_table mp_posts = { "post-partners.txt", "AUGPOST1" };
static mp_owner_table mp_armies = { "army-owners.txt", "AUGARMY1" };

static void mp_owner_copy(char *dst, size_t size, const char *src)
{
    snprintf(dst, size, "%s", src);
    dst[strcspn(dst, "\r\n")] = 0;
}

/* A missing, partial or foreign file leaves the table empty: the text then says the owner is not known. */
static void mp_owner_refresh(mp_owner_table *t)
{
    unsigned now = time_get_millis();
    if (t->initialized && now - t->read_at < 500) {
        return;
    }
    t->initialized = 1;
    t->read_at = now;
    t->count = 0;
    t->has_own = 0;
    const char *dir = getenv("AUGUSTUS_MP_BRIDGE");
    if (!dir) {
        return;
    }
    char path[2048], line[512];
    snprintf(path, sizeof(path), "%s/%s", dir, t->file);
    FILE *f = fopen(path, "rb");
    if (!f) {
        return;
    }
    if (!fgets(line, sizeof(line), f) || strncmp(line, t->magic, 8)) {
        fclose(f);
        return;
    }
    while (fgets(line, sizeof(line), f)) {
        if (!strchr(line, '\n')) {
            break; /* half-written line */
        }
        char *city = strchr(line, '\t');
        if (!city) {
            continue;
        }
        *city++ = 0;
        char *player = strchr(city, '\t');
        if (!player) {
            continue;
        }
        *player++ = 0;
        mp_owner_row row = { 0 };
        mp_owner_copy(row.city, sizeof(row.city), city);
        mp_owner_copy(row.player, sizeof(row.player), player);
        if (!strcmp(line, "own")) {
            t->own = row;
            t->has_own = 1;
            continue;
        }
        char *end;
        unsigned long key = strtoul(line, &end, 10);
        if (*end || !key || t->count >= MP_OWNER_ROWS) {
            continue;
        }
        row.key = (unsigned) key;
        t->rows[t->count++] = row;
    }
    fclose(f);
}

static const mp_owner_row *mp_owner_find(mp_owner_table *t, unsigned key)
{
    mp_owner_refresh(t);
    for (int i = 0; i < t->count; i++) {
        if (t->rows[i].key == key) {
            return &t->rows[i];
        }
    }
    return 0;
}

static int mp_is_soldier_type(int type)
{
    return type == FIGURE_FORT_JAVELIN || type == FIGURE_FORT_MOUNTED || type == FIGURE_FORT_LEGIONARY ||
        type == FIGURE_FORT_INFANTRY || type == FIGURE_FORT_ARCHER;
}

/* 0: no player soldier on the tile. Otherwise the owner text, in UTF-8. */
static int mp_soldier_text(int grid_offset, char *text, size_t size)
{
    unsigned figure_id = map_figure_at(grid_offset);
    for (int guard = 0; figure_id > 0 && figure_id < figure_count() && guard < 64; guard++) {
        const figure *f = figure_get(figure_id);
        figure_id = (unsigned) f->next_figure_id_on_same_tile;
        if (figure_is_dead(f) || !mp_is_soldier_type(f->type) || !f->formation_id ||
            f->formation_id >= (unsigned) formation_count()) {
            continue;
        }
        const formation *m = formation_get(f->formation_id);
        if (!m->in_use) {
            continue;
        }
        if (m->mp_expedition_id && (m->mp_expedition_role == 1 || m->mp_expedition_role == 2)) {
            const mp_owner_row *row = mp_owner_find(&mp_armies, m->mp_expedition_id);
            const char *kind = m->mp_expedition_role == 2 ? "방문 공격군" : "방문 지원군";
            if (row) {
                snprintf(text, size, "%s\n소속: %s · %s", kind, row->city, row->player);
            } else {
                snprintf(text, size, "%s\n소속 정보 미확인", kind);
            }
            return 1;
        }
        if (m->is_legion && !m->mp_expedition_role) {
            mp_owner_refresh(&mp_armies);
            if (mp_armies.has_own) {
                snprintf(text, size, "소속: %s · %s", mp_armies.own.city, mp_armies.own.player);
            } else {
                snprintf(text, size, "소속 정보 미확인");
            }
            return 1;
        }
    }
    return 0;
}

static int mp_post_text(int building_id, char *text, size_t size)
{
    if (!building_id) {
        return 0;
    }
    building *b = building_main(building_get(building_id));
    if (!b || b->type != BUILDING_PLAYER_TRADE_POST || b->state != BUILDING_STATE_IN_USE) {
        return 0;
    }
    int slot = b->subtype.orientation;
    const mp_owner_row *row = slot >= 1 && slot <= 8 ? mp_owner_find(&mp_posts, (unsigned) slot) : 0;
    if (row) {
        snprintf(text, size, "전용 교역소\n교역 상대: %s · %s", row->city, row->player);
    } else {
        snprintf(text, size, "전용 교역소\n교역 상대: 상대 정보 미확인");
    }
    return 1;
}

/* Exposed for the off-screen check (handoff/affiliation_probe.c). */
int mp_affiliation_text(int grid_offset, int building_id, char *text, size_t size)
{
    if (!mp_clock_active() || !grid_offset) {
        return 0;
    }
    return mp_soldier_text(grid_offset, text, size) || mp_post_text(building_id, text, size);
}

static int mp_affiliation_tooltip(tooltip_context *c, int grid_offset, int building_id)
{
    static uint8_t encoded[1024];
    char text[600];
    if (!mp_affiliation_text(grid_offset, building_id, text, sizeof(text))) {
        return 0;
    }
    encoding_from_utf8(text, encoded, sizeof(encoded));
    c->precomposed_text = encoded;
    c->type = TOOLTIP_OVERLAY;
    c->high_priority = 1;
    return 1;
}
