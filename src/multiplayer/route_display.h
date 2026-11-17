#ifndef MP_ROUTE_DISPLAY_H
#define MP_ROUTE_DISPLAY_H
/* Display-only trade paths for the in-game empire map (header only, no engine state).
 * Written by Augustus/empire_route_display.py into the bridge folder as empire-routes.txt:
 *   AUGROUTES2
 *   <count>
 *   <kind 0 player|1 neutral> <sea 0|1> <name a> <name b> <mine 0|1> <active -1|0|1> <shape 0|1> <points n>
 *   x y x y ...            (n points, map pixels, from a to b; first and last are the two cities)
 * shape 0: a path along the terrain; shape 1: a straight stand-in between the two cities (no terrain path).
 * A path only says where a line is drawn. Trade relations, transport time, arrival and the caravan/ship icons
 * never read it. A malformed file is refused as a whole (nothing is drawn from it). */
#include <math.h>
#include <stdio.h>
#include <string.h>

#define MP_ROUTE_MAX 320
#define MP_ROUTE_MAX_POINTS 24000
#define MP_ROUTE_MAX_PER_PATH 600

typedef struct { int kind, sea, a, b, mine, active, shape, first, count; } mp_route_path;
typedef struct { int routes, points; mp_route_path route[MP_ROUTE_MAX]; short xy[MP_ROUTE_MAX_POINTS * 2]; } mp_route_display;

/* Parses the whole text into out. Returns 1 when every line is valid, else 0 (out then holds no routes). */
static int mp_route_display_parse(const char *text, mp_route_display *out)
{
    out->routes = out->points = 0;
    if (!text || strncmp(text, "AUGROUTES2", 10) || (text[10] != '\n' && text[10] != '\r')) {
        return 0;
    }
    const char *p = text + 10;
    int count, used;
    if (sscanf(p, "%d%n", &count, &used) != 1 || count < 0 || count > MP_ROUTE_MAX) {
        return 0;
    }
    p += used;
    for (int i = 0; i < count; i++) {
        mp_route_path r;
        if (sscanf(p, "%d %d %d %d %d %d %d %d%n", &r.kind, &r.sea, &r.a, &r.b, &r.mine, &r.active, &r.shape, &r.count, &used) != 8 ||
            r.kind < 0 || r.kind > 1 || r.sea < 0 || r.sea > 1 || r.a < 1 || r.a > 255 || r.b < 1 || r.b > 255 || r.a == r.b ||
            r.mine < 0 || r.mine > 1 || r.active < -1 || r.active > 1 || r.shape < 0 || r.shape > 1 ||
            (r.shape == 1 && r.count != 2) || r.count < 2 || r.count > MP_ROUTE_MAX_PER_PATH ||
            out->points + r.count > MP_ROUTE_MAX_POINTS) {
            out->routes = out->points = 0;
            return 0;
        }
        p += used;
        r.first = out->points;
        for (int k = 0; k < r.count; k++) {
            int x, y;
            if (sscanf(p, "%d %d%n", &x, &y, &used) != 2 || x < 0 || x > 2000 || y < 0 || y > 1000) {
                out->routes = out->points = 0;
                return 0;
            }
            p += used;
            out->xy[(r.first + k) * 2] = (short) x;
            out->xy[(r.first + k) * 2 + 1] = (short) y;
        }
        out->points += r.count;
        out->route[out->routes++] = r;
    }
    while (*p == ' ' || *p == '\r' || *p == '\n' || *p == '\t') {
        p++;
    }
    if (*p) {
        out->routes = out->points = 0;
        return 0;
    }
    return 1;
}

/* Long dashes with gaps (land); a long dash, a short dash, gaps (sea). Lengths in screen pixels. No dots. */
static const float MP_ROUTE_LAND_PATTERN[] = { 11.0f, 6.0f };
static const float MP_ROUTE_SEA_PATTERN[] = { 14.0f, 4.0f, 5.0f, 4.0f };

typedef void (*mp_route_emit)(void *context, float x1, float y1, float x2, float y2);

/* Walks the polyline once and emits every drawn piece ("on" part of the pattern), carrying the pattern
 * across corners so a bend never restarts it. */
static void mp_route_display_dashes(const float *xy, int n, int sea, mp_route_emit emit, void *context)
{
    const float *pattern = sea ? MP_ROUTE_SEA_PATTERN : MP_ROUTE_LAND_PATTERN;
    int parts = sea ? 4 : 2, index = 0;
    float left = pattern[0];
    for (int i = 1; i < n; i++) {
        float x1 = xy[(i - 1) * 2], y1 = xy[(i - 1) * 2 + 1], x2 = xy[i * 2], y2 = xy[i * 2 + 1];
        float length = sqrtf((x2 - x1) * (x2 - x1) + (y2 - y1) * (y2 - y1)), done = 0;
        while (length > 0 && done < length) {
            float step = left < length - done ? left : length - done;
            if (index % 2 == 0) {
                float t1 = done / length, t2 = (done + step) / length;
                emit(context, x1 + (x2 - x1) * t1, y1 + (y2 - y1) * t1, x1 + (x2 - x1) * t2, y1 + (y2 - y1) * t2);
            }
            done += step;
            left -= step;
            if (left <= 0.0001f) {
                index = (index + 1) % parts;
                left = pattern[index];
            }
        }
    }
}
#endif
