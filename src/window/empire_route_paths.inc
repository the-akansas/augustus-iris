/* Trade lines on the multiplayer empire map (display only). Drawn under the cities, flags and caravan/ship icons;
 * the icons keep their own straight movement, and nothing here touches trade, transport time or arrival.
 *
 * Sources, in order:
 *  1. empire-routes.txt (multiplayer/route_display.h, written by Augustus/empire_route_display.py): every trade
 *     relation of the scenario, as a terrain path (shape 0) or a straight stand-in between the two cities (shape 1).
 *  2. Relations the game itself knows when the file has none for them (no file, an old scenario, a refused file):
 *     open/closeable trade routes of this city (its own route objects and their original legs) and player contracts
 *     in force (route-state.txt + empire-player-slots.txt). They are drawn straight, as stand-ins.
 *  Nothing else is drawn: no relation is guessed. In multiplayer the original dotted route display is replaced by
 *  these dashed lines, so the two never show together.
 * Files are checked at most once a second; changed content is parsed, and no path is computed here. */
#include "multiplayer/route_display.h"
#include <sys/stat.h>
static mp_route_display route_paths;
static struct {
    unsigned checked_at, levels_at;
    long long stamp;
    int own, selected, peers, peer_name[8], peer_active[8];
    signed char open[256], known[256];
} route_paths_state;

static long long route_paths_stamp(const char *path, long long *size)
{
    struct stat info;
    if (stat(path, &info) != 0) {
        return 0;
    }
    *size = (long long) info.st_size;
    return (long long) info.st_mtime * 1000003LL + (long long) info.st_size + 1;
}

/* Player contracts in force: route-state.txt "<index> <city id> <state> <revision>" (1 = in force) and
 * empire-player-slots.txt "<name id>\t<city id>\t<name>". Anything unreadable simply gives no contract line. */
static void route_paths_read_contracts(const char *dir)
{
    char path[2048], id[64], slot_id[64], line[256];
    int names[8], count = 0;
    char ids[8][64];
    route_paths_state.peers = 0;
    snprintf(path, sizeof(path), "%s/empire-player-slots.txt", dir);
    FILE *f = fopen(path, "rb");
    if (!f) {
        return;
    }
    while (count < 8 && fgets(line, sizeof(line), f)) {
        int name;
        if (sscanf(line, "%d\t%63[^\t\r\n]", &name, slot_id) == 2 && name > 0 && name < 256) {
            names[count] = name;
            snprintf(ids[count], sizeof(ids[count]), "%s", slot_id);
            count++;
        }
    }
    fclose(f);
    snprintf(path, sizeof(path), "%s/route-state.txt", dir);
    f = fopen(path, "rb");
    if (!f) {
        return;
    }
    int peer, state, revision;
    while (route_paths_state.peers < 8 && fscanf(f, "%d %63s %d %d", &peer, id, &state, &revision) == 4) {
        for (int i = 0; i < count; i++) {
            if (!strcmp(ids[i], id)) {
                route_paths_state.peer_name[route_paths_state.peers] = names[i];
                route_paths_state.peer_active[route_paths_state.peers++] = state == 1;
            }
        }
    }
    fclose(f);
}

static void route_paths_reload(void)
{
    unsigned now = time_get_millis();
    if (route_paths_state.checked_at && now - route_paths_state.checked_at < 1000) {
        return;
    }
    route_paths_state.checked_at = now;
    const char *dir = getenv("AUGUSTUS_MP_BRIDGE");
    if (!dir || !mp_clock_active()) {
        route_paths.routes = 0;
        route_paths_state.stamp = 0;
        route_paths_state.peers = 0;
        return;
    }
    route_paths_read_contracts(dir);
    char path[2048];
    snprintf(path, sizeof(path), "%s/empire-routes.txt", dir);
    long long size = 0, stamp = route_paths_stamp(path, &size);
    if (!stamp || size <= 0 || size > 1048576) {
        route_paths.routes = 0;
        route_paths_state.stamp = 0;
        return;
    }
    FILE *f = fopen(path, "rb");
    if (!f) {
        route_paths.routes = 0;
        route_paths_state.stamp = 0;
        return;
    }
    static char text[1048577], previous[1048577];
    static size_t previous_size;
    size_t got = fread(text, 1, (size_t) size, f);
    fclose(f);
    if (got != (size_t) size) {
        route_paths.routes = 0;
        route_paths_state.stamp = 0;
        return;
    }
    text[got] = 0;
    /* stat timestamps can have one-second precision. Equal-size contract updates or a
     * replacement room file may share that timestamp: compare bytes before reusing it.
     * Reads remain limited to once a second; parsing runs only when content changes. */
    if (stamp == route_paths_state.stamp && got == previous_size && !memcmp(text, previous, got)) {
        return;
    }
    memcpy(previous, text, got + 1);
    previous_size = got;
    route_paths_state.stamp = stamp;
    route_paths.routes = 0;
    if (!mp_route_display_parse(text, &route_paths)) {
        route_paths.routes = 0; /* a refused file draws nothing from it; the game's own relations still show */
    }
}

/* Own city, selected city and which trade routes are open: looked up at most 4 times a second. */
static void route_paths_levels(void)
{
    unsigned now = time_get_millis();
    if (route_paths_state.levels_at && now - route_paths_state.levels_at < 250) {
        return;
    }
    route_paths_state.levels_at = now;
    route_paths_state.own = 0;
    memset(route_paths_state.known, 0, sizeof(route_paths_state.known));
    for (int i = 0; i < empire_object_count(); i++) {
        const full_empire_object *f = empire_object_get_full(i);
        if (!f->in_use || f->obj.type != EMPIRE_OBJECT_CITY || f->city_name_id < 1 || f->city_name_id > 255) {
            continue;
        }
        const empire_city *city = empire_city_get(empire_city_get_for_object(f->obj.id));
        if (!city || !city->in_use) {
            continue;
        }
        if (city->type == EMPIRE_CITY_OURS) {
            route_paths_state.own = f->city_name_id;
        }
        route_paths_state.known[f->city_name_id] = 1;
        route_paths_state.open[f->city_name_id] = city->type == EMPIRE_CITY_TRADE && empire_city_is_trade_route_open(city->route_id);
    }
    unsigned selected = empire_selected_object();
    route_paths_state.selected = 0;
    if (selected) {
        const full_empire_object *f = empire_object_get_full(selected - 1);
        if (f->in_use && f->obj.type == EMPIRE_OBJECT_CITY) {
            route_paths_state.selected = f->city_name_id;
        }
    }
}

/* 0 hidden, 1 subtle (own relation not in use yet / another city's relation while that city is selected),
 * 2 normal (own relation in use), 3 strong (own relation with the selected city). */
static int route_line_level(int a, int b, int in_use)
{
    int selected = route_paths_state.selected, own = route_paths_state.own;
    int mine = own && (a == own || b == own);
    if (selected && selected != own && (a == selected || b == selected)) {
        return mine ? 3 : 1;
    }
    if (mine) {
        return in_use ? 2 : 1;
    }
    return 0;
}

static int route_path_level(const mp_route_path *r)
{
    if (!route_paths_state.known[r->a] || !route_paths_state.known[r->b]) {
        return 0; /* a city the map does not show */
    }
    int in_use;
    if (r->kind == 1) {
        int neutral = r->a == route_paths_state.own ? r->b : r->a;
        in_use = route_paths_state.open[neutral];
    } else {
        in_use = r->active == 1;
    }
    return route_line_level(r->a, r->b, in_use);
}

typedef struct { color_t color; int width; } route_pen;
static void route_paths_emit(void *context, float x1, float y1, float x2, float y2)
{
    /* A thick dash as a stack of 1-pixel lines shifted along the minor axis: no gaps and no pixel drawn twice,
     * so a translucent colour stays even. */
    const route_pen *pen = (const route_pen *) context;
    int ax = (int) lroundf(x1), ay = (int) lroundf(y1), bx = (int) lroundf(x2), by = (int) lroundf(y2);
    int steep = abs(by - ay) > abs(bx - ax);
    for (int k = 0; k < pen->width; k++) {
        int offset = k - pen->width / 2;
        if (steep) {
            graphics_draw_line(ax + offset, bx + offset, ay, by, pen->color);
        } else {
            graphics_draw_line(ax, bx, ay + offset, by + offset, pen->color);
        }
    }
}

/* Land: light dirt-road dashes; sea: teal long-short dashes. A dark edge under a light core keeps both readable on
 * light land and on dark sea. The same pens for terrain paths and stand-ins. */
static void route_line_draw(const float *line, int count, int sea, int level)
{
    unsigned alpha = level == 1 ? 0x80 : level == 2 ? 0xe0 : 0xff;
    color_t tone = sea ? 0x0046d2dc : 0x00e6bc7a;
    route_pen edge = { (alpha * 7 / 10) << 24 | 0x00201408, level == 3 ? 4 : 3 };
    route_pen body = { alpha << 24 | tone, level == 3 ? 2 : 1 };
    mp_route_display_dashes(line, count, sea, route_paths_emit, &edge);
    mp_route_display_dashes(line, count, sea, route_paths_emit, &body);
}

static const empire_object *route_city_object(int name)
{
    for (int i = 0; i < empire_object_count(); i++) {
        const full_empire_object *f = empire_object_get_full(i);
        if (f->in_use && f->obj.type == EMPIRE_OBJECT_CITY && f->city_name_id == name) {
            return &f->obj;
        }
    }
    return 0;
}

#define ROUTE_CITY_ANCHOR 9 /* project x,y = city object position + 16; caravan icons and original legs use + 25 */
static void draw_route_paths(void)
{
    if (!mp_clock_active() || data.sidebar.trade_year) {
        return;
    }
    route_paths_reload();
    route_paths_levels();
    static float line[MP_ROUTE_MAX_PER_PATH * 2];
    static unsigned char file_neutral[256], file_player[256];
    memset(file_neutral, 0, sizeof(file_neutral));
    memset(file_player, 0, sizeof(file_player));
    int own = route_paths_state.own;
    for (int i = 0; i < route_paths.routes; i++) {
        const mp_route_path *r = &route_paths.route[i];
        if (own && (r->a == own || r->b == own)) {
            (r->kind == 1 ? file_neutral : file_player)[r->a == own ? r->b : r->a] = 1;
        }
    }
    for (int level = 1; level <= 3; level++) {
        /* 1. the file: terrain paths and the scenario's own straight stand-ins */
        for (int i = 0; i < route_paths.routes; i++) {
            const mp_route_path *r = &route_paths.route[i];
            if (route_path_level(r) != level) {
                continue;
            }
            for (int k = 0; k < r->count; k++) {
                int end = k == 0 || k == r->count - 1;
                line[k * 2] = data.x_draw_offset + route_paths.xy[(r->first + k) * 2] + (end ? ROUTE_CITY_ANCHOR : 0);
                line[k * 2 + 1] = data.y_draw_offset + route_paths.xy[(r->first + k) * 2 + 1] + (end ? ROUTE_CITY_ANCHOR : 0);
            }
            route_line_draw(line, r->count, r->sea, level);
        }
        if (!own) {
            continue;
        }
        /* 2a. this city's trade routes the file does not cover: the route's own legs, straight */
        for (int i = 0; i < empire_object_count(); i++) {
            const empire_object *route = empire_object_get(i);
            if (!empire_object_get_full(i)->in_use ||
                (route->type != EMPIRE_OBJECT_LAND_TRADE_ROUTE && route->type != EMPIRE_OBJECT_SEA_TRADE_ROUTE) ||
                route->trade_route_id < 0 || route->trade_route_id >= MAX_SIDEBAR_CITIES) {
                continue;
            }
            const empire_city *city = empire_city_get(empire_city_get_for_trade_route(route->trade_route_id));
            if (!city || !city->in_use || city->type != EMPIRE_CITY_TRADE || city->name_id < 1 || city->name_id > 255 ||
                file_neutral[city->name_id]) {
                continue;
            }
            if (route_line_level(own, city->name_id, route_paths_state.open[city->name_id]) != level) {
                continue;
            }
            int count = 0;
            for (int k = 0; k < MAX_TRADE_EDGES && count < MP_ROUTE_MAX_PER_PATH - 1; k++) {
                int e = trade_city_edges[route->trade_route_id][k];
                if (e < 0 || e >= g_trade_edge_count) {
                    break;
                }
                if (!count) {
                    line[0] = data.x_draw_offset + g_trade_edges[e].x1;
                    line[1] = data.y_draw_offset + g_trade_edges[e].y1;
                    count = 1;
                }
                line[count * 2] = data.x_draw_offset + g_trade_edges[e].x2;
                line[count * 2 + 1] = data.y_draw_offset + g_trade_edges[e].y2;
                count++;
            }
            if (count >= 2) {
                route_line_draw(line, count, route->type == EMPIRE_OBJECT_SEA_TRADE_ROUTE, level);
            }
            file_neutral[city->name_id] = 1; /* one line per route even if a city has two route objects */
        }
        /* 2b. player contracts in force the file does not cover: straight between the two cities */
        const empire_object *from = route_city_object(own);
        for (int i = 0; from && i < route_paths_state.peers; i++) {
            int peer = route_paths_state.peer_name[i];
            if (!route_paths_state.peer_active[i] || peer == own || file_player[peer] || route_line_level(own, peer, 1) != level) {
                continue;
            }
            const empire_object *to = route_city_object(peer);
            if (!to) {
                continue;
            }
            line[0] = data.x_draw_offset + from->x + 25;
            line[1] = data.y_draw_offset + from->y + 25;
            line[2] = data.x_draw_offset + to->x + 25;
            line[3] = data.y_draw_offset + to->y + 25;
            const empire_city *peer_city = empire_city_get(empire_city_get_for_object(to->id));
            route_line_draw(line, 2, peer_city && peer_city->is_sea_trade, level);
        }
    }
}
