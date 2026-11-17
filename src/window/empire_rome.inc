/* Rome on the multiplayer empire map (user requests 2026-11-13: Rome was missing in the game itself; clicking it
 * should show its description as on the scenario screen). Rome is the fixed capital of every scenario: it is not a
 * city object and nothing in the simulation reads it. Clicking it shows its name and its description (two lines) in
 * the bottom panel; it cannot be traded with or visited. A city under the same spot is clicked first.
 * Its red flag waves like the neutral cities' flags (same frames, same speed rule).
 * File empire-rome.txt in the bridge folder (game_bridge.py, text from rome_capital.py, the same as the waiting room
 * and the scenario screen):  line 1 "<x> <y>", line 2 name, lines 3 and 4 the description split in two.
 * No file or a bad first line draws nothing. The file is looked at once a second. */
#include "game/animation.h"

static struct {
    unsigned checked_at;
    int x, y, known, selected, flag;
    int left, top, right, bottom; /* where the picture was last drawn (screen), 0 width = not drawn */
    char name[64], text[512], text2[512];
    int throne, coup, gift;       /* throne-box.txt: 0 none, 2 peace, 3 active; whether each button can be pressed */
    int button[2][4];             /* where the buttons were last drawn (x, y, w, h), w 0 = not drawn */
} mp_empire_rome;

static void mp_empire_rome_line(const char **cursor, char *out, size_t size)
{
    const char *s = *cursor, *end = strchr(s, '\n');
    size_t length = end ? (size_t) (end - s) : strlen(s);
    if (length && s[length - 1] == '\r') {
        length--;
    }
    if (length >= size) {
        length = size - 1;
    }
    memcpy(out, s, length);
    out[length] = 0;
    *cursor = end ? end + 1 : s + strlen(s);
}

/* Race for the Throne: Rome's panel carries the same buttons as the box in the city view (throne-box.txt, written
 * by throne_client.py): peace "끌어내리기", after the emperor woke up "쿠데타 지원" and "충성선물". */
static void mp_empire_rome_throne(void)
{
    mp_empire_rome.throne = mp_empire_rome.coup = mp_empire_rome.gift = 0;
    const char *dir = getenv("AUGUSTUS_MP_BRIDGE");
    if (!dir) {
        return;
    }
    char path[2048], line[1024];
    snprintf(path, sizeof(path), "%s/throne-box.txt", dir);
    FILE *f = fopen(path, "rb");
    if (!f) {
        return;
    }
    while (fgets(line, sizeof(line), f)) {
        line[strcspn(line, "\r\n")] = 0;
        char *value = strchr(line, '\t');
        if (!value) {
            continue;
        }
        *value++ = 0;
        if (!strcmp(line, "state")) {
            mp_empire_rome.throne = !strcmp(value, "peace") ? 2 : !strcmp(value, "active") ? 3 : 0;
        } else if (!strcmp(line, "coup")) {
            mp_empire_rome.coup = atoi(value);
        } else if (!strcmp(line, "gift")) {
            mp_empire_rome.gift = atoi(value);
        }
    }
    fclose(f);
}

static void mp_empire_rome_reload(void)
{
    unsigned now = time_get_millis();
    if (mp_empire_rome.checked_at && now - mp_empire_rome.checked_at < 1000) {
        return;
    }
    mp_empire_rome.checked_at = now ? now : 1;
    mp_empire_rome.known = 0;
    mp_empire_rome_throne();
    const char *dir = getenv("AUGUSTUS_MP_BRIDGE");
    if (!dir) {
        mp_empire_rome.selected = 0;
        return;
    }
    char path[2048], text[2048] = { 0 }, first[64], extra;
    snprintf(path, sizeof(path), "%s/empire-rome.txt", dir);
    FILE *f = fopen(path, "rb");
    if (!f) {
        mp_empire_rome.selected = 0;
        return;
    }
    size_t got = fread(text, 1, sizeof(text) - 1, f);
    fclose(f);
    text[got] = 0;
    const char *cursor = text;
    mp_empire_rome_line(&cursor, first, sizeof(first));
    int x, y;
    if (sscanf(first, "%d %d %c", &x, &y, &extra) != 2 || x < 0 || x > 2000 || y < 0 || y > 1000) {
        mp_empire_rome.selected = 0;
        return;
    }
    mp_empire_rome.x = x;
    mp_empire_rome.y = y;
    mp_empire_rome.known = 1;
    mp_empire_rome_line(&cursor, mp_empire_rome.name, sizeof(mp_empire_rome.name));
    mp_empire_rome_line(&cursor, mp_empire_rome.text, sizeof(mp_empire_rome.text));
    mp_empire_rome_line(&cursor, mp_empire_rome.text2, sizeof(mp_empire_rome.text2));
    if (!mp_empire_rome.name[0]) {
        snprintf(mp_empire_rome.name, sizeof(mp_empire_rome.name), "%s", "로마");
    }
}

#define MP_EMPIRE_ROME_ANCHOR 9 /* file x,y = where a city object would stand + 16; city pictures are centred at + 25 */
static void draw_mp_empire_rome(void)
{
    mp_empire_rome.right = mp_empire_rome.left;
    if (!mp_clock_active()) {
        return;
    }
    mp_empire_rome_reload();
    if (!mp_empire_rome.known) {
        return;
    }
    int id = assets_get_image_id("UI", "Empire_Icon_Roman_05");
    const image *img = id ? image_get(id) : 0;
    if (!img || !img->width) {
        return;
    }
    /* like the cities: the place follows the zoom, the picture keeps its size */
    int cx = data.x_draw_offset + ezx(mp_empire_rome.x + MP_EMPIRE_ROME_ANCHOR);
    int cy = data.y_draw_offset + ezy(mp_empire_rome.y + MP_EMPIRE_ROME_ANCHOR);
    int left = cx - img->width / 2, top = cy - img->height / 2;
    image_draw(id, left, top, COLOR_MASK_NONE, SCALE_NONE);
    mp_empire_rome.left = left;
    mp_empire_rome.top = top;
    mp_empire_rome.right = left + img->width;
    mp_empire_rome.bottom = top + img->height;
    int trade = image_group(GROUP_EMPIRE_CITY_TRADE);
    const image *icon = image_get(trade);
    if (icon && icon->animation && icon->animation->num_sprites) {
        /* the neutral cities' red flag, next frame by the same rule as empire/object.c get_animation_offset */
        int count = icon->animation->num_sprites, frame = mp_empire_rome.flag & 0x7f, back = mp_empire_rome.flag & 0x80;
        if (frame < 1 || frame > count) {
            frame = 1;
            back = 0;
        }
        if (icon->animation->speed_id && game_animation_should_advance(icon->animation->speed_id)) {
            if (!icon->animation->can_reverse) {
                frame = frame >= count ? 1 : frame + 1;
            } else if (back) {
                if (--frame < 1) {
                    frame = 1;
                    back = 0;
                }
            } else if (++frame > count) {
                frame = count;
                back = 0x80;
            }
        }
        mp_empire_rome.flag = frame | back;
        image_draw(trade + frame, left + 16, top + 6, COLOR_MASK_NONE, SCALE_NONE);
    }
    uint8_t name[96];
    encoding_from_utf8(mp_empire_rome.name, name, sizeof(name));
    int width = text_get_width(name, FONT_NORMAL_WHITE) + 8;
    /* name to the left, as on the scenario screen: Capua lies just south-east of Rome and must stay clear */
    graphics_fill_rect(left - width - 2, cy - 9, width, 18, 0xe0402a14);
    text_draw(name, left - width + 2, cy - 6, FONT_NORMAL_WHITE, 0);
}

/* Screen point on the drawn Rome picture (the caller has already checked that no city is there). */
static int mp_empire_rome_hit(int x, int y)
{
    return mp_clock_active() && mp_empire_rome.known && mp_empire_rome.right > mp_empire_rome.left &&
        x >= mp_empire_rome.left && x < mp_empire_rome.right && y >= mp_empire_rome.top && y < mp_empire_rome.bottom;
}

/* Bottom panel while Rome is selected: its name on the city badge, then the description as two centred lines.
 * Returns 0 (nothing drawn) when Rome is not the selection. */
static void mp_empire_rome_buttons(int count)
{
    static const char *labels[2][2] = { { "끌어내리기", "" }, { "쿠데타 지원", "충성선물" } };
    mp_empire_rome.button[0][2] = mp_empire_rome.button[1][2] = 0;
    const mouse *m = mouse_get();
    int bw = 160, cx = (data.panel.x_min + data.panel.x_max) / 2, by = data.y_max - 42;
    for (int k = 0; k < count; k++) {
        int bx = count == 1 ? cx - bw / 2 : cx - bw - 6 + k * (bw + 12);
        int on = k ? mp_empire_rome.gift : mp_empire_rome.coup;
        int over = m->x >= bx && m->x < bx + bw && m->y >= by && m->y < by + 24;
        button_border_draw(bx, by, bw, 24, on && over);
        uint8_t label[128];
        encoding_from_utf8(labels[count - 1][k], label, sizeof(label));
        text_draw_centered(label, bx, by + 5, bw, on ? FONT_NORMAL_BLACK : FONT_SMALL_PLAIN, 0);
        mp_empire_rome.button[k][0] = bx;
        mp_empire_rome.button[k][1] = by;
        mp_empire_rome.button[k][2] = bw;
        mp_empire_rome.button[k][3] = 24;
    }
}

/* A click on one of Rome's throne buttons: back to the city, where the dialog opens (the same command as the box). */
static int mp_empire_rome_button_click(const mouse *m)
{
    if (!mp_empire_rome.selected || !mp_empire_rome.throne) {
        return 0;
    }
    for (int k = 0; k < 2; k++) {
        const int *b = mp_empire_rome.button[k];
        if (!b[2] || m->x < b[0] || m->x >= b[0] + b[2] || m->y < b[1] || m->y >= b[1] + b[3]) {
            continue;
        }
        if (m->left.went_up && (k ? mp_empire_rome.gift : mp_empire_rome.coup)) {
            char text[64];
            snprintf(text, sizeof(text), "%s\n%d", k ? "gift" : "coup", (int) city_finance_treasury());
            window_city_show();
            mp_client_command("throne", text);
        }
        return 1;
    }
    return 0;
}

static int draw_mp_empire_rome_info(void)
{
    if (!mp_empire_rome.selected || !mp_empire_rome.known || !mp_clock_active()) {
        mp_empire_rome.selected = 0;
        return 0;
    }
    if (empire_selected_object()) {
        mp_empire_rome.selected = 0; /* a city was chosen meanwhile (map or side list) */
        return 0;
    }
    static uint8_t text[1024];
    encoding_from_utf8(mp_empire_rome.name, text, sizeof(text));
    text_draw_centered_ellipsized(text, (data.panel.x_min + data.panel.x_max - 332) / 2 + 64, data.y_max - 118, 268,
        FONT_LARGE_BLACK, 0);
    int width = data.panel.x_max - data.panel.x_min - 160;
    if (width > 600) {
        width = 600;
    }
    int x = (data.panel.x_min + data.panel.x_max - width) / 2;
    int buttons = mp_empire_rome.throne ? (mp_empire_rome.throne == 3 ? 2 : 1) : 0;
    int y = data.y_max - (buttons ? 88 : 80);
    /* The description comes as two lines of one text. The catalog knows the whole text, not its halves (user
     * 2026-11-17: the Spanish game showed it in Korean): the halves are joined, translated, and split again at the
     * blank nearest the middle. */
    char first[1024], second[1024];
    snprintf(first, sizeof(first), "%s", mp_empire_rome.text);
    snprintf(second, sizeof(second), "%s", mp_empire_rome.text2);
    if (first[0] && second[0]) {
        char whole[2048];
        snprintf(whole, sizeof(whole), "%s %s", first, second);
        const char *shown = mp_i18n_translate(whole);
        if (shown && strcmp(shown, whole)) {
            /* at the sentence end nearest the middle, as the lines came (game_bridge.py); any blank without one */
            size_t length = strlen(shown), middle = length / 2, cut = 0;
            for (int ends = 1; ends >= 0 && !cut; ends--) {
                for (size_t d = 0; d <= middle && !cut; d++) {
                    size_t at[2] = { middle + d, middle - d };
                    for (int k = 0; k < 2 && !cut; k++) {
                        size_t i = at[k];
                        if (i > 0 && i < length && shown[i] == ' ' &&
                            (!ends || shown[i - 1] == '.' || shown[i - 1] == '!' || shown[i - 1] == '?')) {
                            cut = i;
                        }
                    }
                }
            }
            if (cut && cut < sizeof(first) && length - cut - 1 < sizeof(second)) {
                memcpy(first, shown, cut); first[cut] = 0;
                snprintf(second, sizeof(second), "%s", shown + cut + 1);
            }
        }
    }
    mp_i18n_suspend(1);   /* the lines are in the reader's language already */
    if (first[0]) {
        encoding_from_utf8(first, text, sizeof(text));
        text_draw_centered(text, x, y, width, FONT_NORMAL_GREEN, 0);
    }
    if (second[0]) {
        encoding_from_utf8(second, text, sizeof(text));
        text_draw_centered(text, x, y + (buttons ? 20 : 22), width, FONT_NORMAL_GREEN, 0);
    }
    mp_i18n_suspend(0);
    mp_empire_rome_buttons(buttons);
    return 1;
}
