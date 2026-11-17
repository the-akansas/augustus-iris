/* Player-to-player trade links on the multiplayer empire map, in the game's own route style: evenly spaced route
 * dots with one pulse travelling along them (user request 2026-11-13: without them the cities do not feel connected).
 * Display only: trade relations, transport time, arrival and the caravan/ship icons never read this.
 *
 * Source: empire-routes.txt (multiplayer/route_display.h, written by Augustus/empire_route_display.py). Only its
 * player-to-player rows are used; neutral trade routes keep the game's own dotted display.
 *   my relation, contract in force      full dots + travelling pulse
 *   my relation, no contract yet        faint dots, no pulse
 *   another player's relation           faint dots, only while that city is selected
 * A missing or refused file draws nothing; no relation is guessed. The file is read at most once a second. */
#include "multiplayer/route_display.h"
static mp_route_display player_links;
static struct { unsigned checked_at; int loaded; size_t size; } player_links_state;

static void player_links_reload(void)
{
    unsigned now = time_get_millis();
    if (player_links_state.checked_at && now - player_links_state.checked_at < 1000) {
        return;
    }
    player_links_state.checked_at = now ? now : 1;
    static char text[262145], previous[262145];
    const char *dir = getenv("AUGUSTUS_MP_BRIDGE");
    char path[2048];
    FILE *f = 0;
    if (dir) {
        snprintf(path, sizeof(path), "%s/empire-routes.txt", dir);
        f = fopen(path, "rb");
    }
    if (!f) {
        player_links.routes = 0;
        player_links_state.loaded = 0;
        return;
    }
    size_t got = fread(text, 1, sizeof(text) - 1, f);
    int too_long = fgetc(f) != EOF;
    fclose(f);
    if (too_long) {
        player_links.routes = 0;
        player_links_state.loaded = 0;
        return;
    }
    text[got] = 0;
    if (player_links_state.loaded && got == player_links_state.size && !memcmp(text, previous, got)) {
        return; /* unchanged since the last look */
    }
    memcpy(previous, text, got + 1);
    player_links_state.size = got;
    player_links_state.loaded = 1;
    if (!mp_route_display_parse(text, &player_links)) {
        player_links.routes = 0; /* a refused file draws nothing */
    }
}

#define PLAYER_LINK_CITY_ANCHOR 9 /* file x,y = city object position + 16; route dots and icons meet the city at + 25 */
static float player_link_point(const mp_route_path *r, int k, int y)
{
    int end = k == 0 || k == r->count - 1;
    return (float) (player_links.xy[(r->first + k) * 2 + y] + (end ? PLAYER_LINK_CITY_ANCHOR : 0));
}

/* Map position at a distance along the path; returns 0 past the end. */
static int player_link_at(const mp_route_path *r, float distance, int *x, int *y)
{
    for (int k = 1; k < r->count; k++) {
        float x1 = player_link_point(r, k - 1, 0), y1 = player_link_point(r, k - 1, 1);
        float x2 = player_link_point(r, k, 0), y2 = player_link_point(r, k, 1);
        float length = sqrtf((x2 - x1) * (x2 - x1) + (y2 - y1) * (y2 - y1));
        if (distance <= length && length > 0) {
            *x = (int) lroundf(x1 + (x2 - x1) * distance / length);
            *y = (int) lroundf(y1 + (y2 - y1) * distance / length);
            return 1;
        }
        distance -= length;
    }
    return 0;
}

static void draw_player_link_dots(void)
{
    if (!mp_clock_active() || data.sidebar.trade_year) {
        return;
    }
    player_links_reload();
    if (!player_links.routes) {
        return;
    }
    static unsigned char known[256];
    memset(known, 0, sizeof(known));
    int own = 0, selected = 0;
    for (int i = 0; i < empire_object_count(); i++) {
        const full_empire_object *f = empire_object_get_full(i);
        if (!f->in_use || f->obj.type != EMPIRE_OBJECT_CITY || f->city_name_id < 1 || f->city_name_id > 255) {
            continue;
        }
        const empire_city *city = empire_city_get(empire_city_get_for_object(f->obj.id));
        if (!city || !city->in_use) {
            continue;
        }
        known[f->city_name_id] = 1;
        if (city->type == EMPIRE_CITY_OURS) {
            own = f->city_name_id;
        }
    }
    unsigned picked = empire_selected_object();
    if (picked) {
        const full_empire_object *f = empire_object_get_full(picked - 1);
        if (f->in_use && f->obj.type == EMPIRE_OBJECT_CITY) {
            selected = f->city_name_id;
        }
    }
    int land_dot = assets_get_image_id("UI", "LandRouteDot"), sea_dot = assets_get_image_id("UI", "SeaRouteDot");
    int animate = config_get(CONFIG_UI_ANIMATE_TRADE_ROUTES);
    for (int i = 0; i < player_links.routes; i++) {
        const mp_route_path *r = &player_links.route[i];
        if (r->kind != 0 || !known[r->a] || !known[r->b]) {
            continue; /* neutral routes keep the game's own display; a city the map does not show has no line */
        }
        int mine = own && (r->a == own || r->b == own);
        int shown_for_selection = selected && selected != own && (r->a == selected || r->b == selected);
        if (!mine && !shown_for_selection) {
            continue;
        }
        int in_force = mine && r->active == 1;
        int dot = r->sea ? sea_dot : land_dot;
        color_t mask = in_force ? COLOR_MASK_NONE : ALPHA_MASK_SEMI_TRANSPARENT;
        int x, y, dots = 0;
        while (dots < 4000 && player_link_at(r, (float) dots * TRADE_DOT_SPACING, &x, &y)) {
            image_draw(dot, data.x_draw_offset + ezx(x), data.y_draw_offset + ezy(y), mask, SCALE_NONE);
            dots++;
        }
        if (in_force && animate && dots > 1) {
            /* the same pulse as the game's routes: the other dot picture, larger, one dot further every 180 ms */
            int index = (int) ((time_get_millis() - data.trade_route_anim_start) / TRADE_PULSE_DOT_MS) % dots;
            if (player_link_at(r, (float) index * TRADE_DOT_SPACING, &x, &y)) {
                image_draw_scaled_centered(r->sea ? land_dot : sea_dot, data.x_draw_offset + ezx(x), data.y_draw_offset + ezy(y),
                    COLOR_MASK_NONE, TRADE_DOT_ANIMATION_SCALE);
            }
        }
    }
}
