#include "language_select.h"

#include "core/encoding.h"
#include "core/mp_language.h"
#include "core/string.h"
#include "graphics/button.h"
#include "graphics/generic_button.h"
#include "graphics/graphics.h"
#include "graphics/panel.h"
#include "graphics/text.h"
#include "graphics/window.h"
#include "input/input.h"

#include <stdio.h>
#include <string.h>

#define PANEL_X 144
#define PANEL_Y 24
#define PANEL_W 22
#define BUTTON_X (PANEL_X + 40)
#define BUTTON_W (PANEL_W * 16 - 80)
#define BUTTON_H 30
#define FIRST_BUTTON_Y (PANEL_Y + 104)
#define BUTTON_STEP 42

static void button_language(const generic_button *button);

static generic_button buttons[MP_LANGUAGE_COUNT];

static struct {
    void (*done)(void);
    unsigned int focus;
    int failed;
    int count;   /* languages shipped with this edition (core/mp_language.c), in list order */
    uint8_t names[MP_LANGUAGE_COUNT][64];
    uint8_t title[160];
    uint8_t heading[64];
} data;

static void draw_background(void)
{
    window_draw_underlying_window();
    graphics_in_dialog();
    outer_panel_draw(PANEL_X, PANEL_Y, PANEL_W, (FIRST_BUTTON_Y - PANEL_Y + data.count * BUTTON_STEP + 75) / 16);   /* 26 rows for six */
    text_draw_centered(data.heading, PANEL_X, PANEL_Y + 24, PANEL_W * 16, FONT_LARGE_BLACK, 0);
    text_draw_centered(data.title, PANEL_X, PANEL_Y + 64, PANEL_W * 16, FONT_NORMAL_BLACK, 0);
    graphics_reset_dialog();
}

static void draw_foreground(void)
{
    graphics_in_dialog();
    for (int i = 0; i < data.count; i++) {
        const generic_button *b = &buttons[i];
        button_border_draw(b->x, b->y, b->width, b->height, data.focus == (unsigned int) (i + 1));
        text_draw_centered(data.names[i], b->x, b->y + 8, b->width, FONT_NORMAL_BLACK, 0);
    }
    if (data.failed) {
        text_draw_centered(string_from_ascii("?"), PANEL_X, FIRST_BUTTON_Y + data.count * BUTTON_STEP,
            PANEL_W * 16, FONT_NORMAL_RED, 0);
    }
    graphics_reset_dialog();
}

static void handle_input(const mouse *m, const hotkeys *h)
{
    generic_buttons_handle_mouse(mouse_in_dialog(m), 0, 0, buttons, data.count, &data.focus);
}

static void button_language(const generic_button *button)
{
    if (!mp_language_set(button->parameter1)) {
        data.failed = 1;
        window_invalidate();
        return;
    }
    void (*done)(void) = data.done;
    if (done) {
        done();
    }
}

void window_language_select_show(void (*done)(void))
{
    data.done = done;
    data.focus = 0;
    data.failed = 0;
    /* Only the languages this edition ships (user 2026-11-14: Korean first, then English, the rest later). */
    static const char *word[MP_LANGUAGE_COUNT] = {"언어", "Language", "Язык", "Sprache", "Idioma", "Langue"};
    char title[160] = "";
    data.count = 0;
    for (int i = 0; i < MP_LANGUAGE_COUNT; i++) {
        if (!mp_language_available(i)) continue;
        int k = data.count++;
        generic_button b = {BUTTON_X, FIRST_BUTTON_Y + k * BUTTON_STEP, BUTTON_W, BUTTON_H, button_language, 0, i};
        buttons[k] = b;
        encoding_from_utf8(mp_language_native_name(i), data.names[k], sizeof(data.names[k]));
        if (i) {
            size_t used = strlen(title);
            snprintf(title + used, sizeof(title) - used, "%s%s", used ? " / " : "", word[i]);
        }
    }
    /* Heading in the order of the list: Korean first, in every edition (user 2026-11-14, again 2026-11-16: "언어" large,
     * then the other languages' words small; only the language shown before choosing is English in the Global edition). */
    encoding_from_utf8(word[0], data.heading, sizeof(data.heading));
    /* Every other shipped language at once: nobody can read the others before choosing. */
    encoding_from_utf8(title, data.title, sizeof(data.title));
    window_type window = {
        WINDOW_POPUP_DIALOG,
        draw_background,
        draw_foreground,
        handle_input
    };
    window_show(&window);
}
