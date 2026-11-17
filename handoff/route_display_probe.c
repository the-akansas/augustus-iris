/* Test probe for src/multiplayer/route_display.h (built by handoff/test_empire_route_display.py).
 * parse <file>          -> "ok <routes> <points>" or "refused"
 * dashes <sea> x y x y.. -> one line per drawn piece: "x1 y1 x2 y2" */
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include "multiplayer/route_display.h"
static mp_route_display display;
static void print_piece(void *context, float x1, float y1, float x2, float y2)
{
    (void) context;
    printf("%.3f %.3f %.3f %.3f\n", x1, y1, x2, y2);
}
int main(int argc, char **argv)
{
    if (argc >= 3 && !strcmp(argv[1], "parse")) {
        FILE *f = fopen(argv[2], "rb");
        if (!f) return 2;
        static char text[1048577];
        size_t got = fread(text, 1, sizeof(text) - 1, f);
        fclose(f);
        text[got] = 0;
        if (mp_route_display_parse(text, &display)) printf("ok %d %d\n", display.routes, display.points);
        else printf("refused %d\n", display.routes);
        return 0;
    }
    if (argc >= 7 && !strcmp(argv[1], "dashes")) {
        int n = (argc - 3) / 2;
        static float xy[MP_ROUTE_MAX_PER_PATH * 2];
        for (int i = 0; i < n * 2; i++) xy[i] = (float) atof(argv[3 + i]);
        mp_route_display_dashes(xy, n, atoi(argv[2]), print_piece, 0);
        return 0;
    }
    return 2;
}
