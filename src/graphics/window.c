#include "multiplayer/visit.h"
#include "window/multiplayer_lobby.h"
#include "window.h"
#include "window/multiplayer_victory.h"
#include "window/multiplayer_chat.h"

#include "game/system.h"
#include "graphics/graphics.h"
#include "core/image.h"
#include "graphics/warning.h"
#include "input/cursor.h"
#include "input/hotkey.h"
#include "input/joystick.h"
#include "input/scroll.h"
#include "input/touch.h"
#include "window/city.h"

#define MAX_QUEUE 5

static struct {
    window_type window_queue[MAX_QUEUE];
    int queue_index;
    window_type *current_window;
    int refresh_immediate;
    int refresh_on_draw;
    int underlying_windows_redrawing;
} data;

static void noop(void)
{}

static void noop_input(const mouse *m, const hotkeys *h)
{}

static void noop_return(window_id from)
{}

static void increase_queue_index(void)
{
    data.queue_index++;
    if (data.queue_index >= MAX_QUEUE) {
        data.queue_index = 0;
    }
}

static void decrease_queue_index(void)
{
    data.queue_index--;
    if (data.queue_index < 0) {
        data.queue_index = MAX_QUEUE - 1;
    }
}

static void reset_input(void)
{
    mouse_reset_button_state();
    reset_touches(1);
    mouse_cancel_middle_click();
    scroll_stop();
}

void window_invalidate(void)
{
    data.refresh_immediate = 1;
    data.refresh_on_draw = 1;
}

int window_is_invalid(void)
{
    return data.refresh_immediate;
}

void window_request_refresh(void)
{
    data.refresh_on_draw = 1;
}

int window_is(window_id id)
{
    return data.current_window->id == id;
}

window_id window_get_id(void)
{
    return data.current_window->id;
}

void window_show(const window_type *window)
{
    window_city_visit_ui_hide();
    reset_input();
    increase_queue_index();
    data.window_queue[data.queue_index] = *window;
    data.current_window = &data.window_queue[data.queue_index];
    if (!data.current_window->draw_background) {
        data.current_window->draw_background = noop;
    }
    if (!data.current_window->draw_foreground) {
        data.current_window->draw_foreground = noop;
    }
    if (!data.current_window->handle_input) {
        data.current_window->handle_input = noop_input;
    }
    if (!data.current_window->on_return) {
        data.current_window->on_return = noop_return;
    }
    window_invalidate();
}

void window_go_back(void)
{
    reset_input();
    window_id from_id = window_get_id();
    decrease_queue_index();
    data.current_window = &data.window_queue[data.queue_index];
    data.current_window->on_return(from_id);
    window_invalidate();
}

static void update_input_before(void)
{
    int handled = touch_to_mouse();
    handled |= joystick_to_mouse_and_keyboard();
    if (!handled) {
        mouse_determine_button_state();  // touch and joystick override mouse
    }
    if (!mp_visit_active() && !window_city_visit_ui_active()) hotkey_handle_global_keys();
}

static void update_input_after(void)
{
    reset_touches(0);
    mouse_reset_scroll();
    input_cursor_update(data.current_window->id);
    hotkey_reset_state();
}

void window_draw(int force)
{
    window_multiplayer_room_poll();
    window_multiplayer_victory_poll();
    update_input_before();
    window_type *w = data.current_window;
    /* Alpha glyphs and translucent buttons cannot be composited repeatedly onto
       the preceding foreground. Rebuild static UI frames, including all dialog
       controls, regardless of whether pointer input invalidated the window.
       Live world/video views already own their full-frame rendering. */
    int rebuild_ui = image_has_korean_ascii() &&
        w->id != WINDOW_CITY && w->id != WINDOW_CITY_MILITARY &&
        w->id != WINDOW_EDITOR_MAP && w->id != WINDOW_VIDEO &&
        w->id != WINDOW_INTRO_VIDEO;
    if (force || data.refresh_on_draw || rebuild_ui) {
        data.refresh_on_draw = 0;
        data.refresh_immediate = 0;
        graphics_clear_screen();
        w->draw_background();
    }
    /* City status belongs below the open File/Options dropdown. Other modal
       windows own their foreground and must not be covered by this overlay. */
    if (w->id == WINDOW_TOP_MENU) window_multiplayer_overlay_draw();
    w->draw_foreground();
    if (w->id == WINDOW_CITY || w->id == WINDOW_CITY_MILITARY) {
        window_multiplayer_overlay_draw();
    }

    const mouse *m = mouse_get();
    const hotkeys *h = hotkey_state();
    w->handle_input(m, h);
    tooltip_handle(m, w->get_tooltip);
    warning_draw();
    update_input_after();
}

void window_draw_underlying_window(void)
{
    if (data.underlying_windows_redrawing < MAX_QUEUE) {
        ++data.underlying_windows_redrawing;
        decrease_queue_index();
        window_type *window_behind = &data.window_queue[data.queue_index];
        window_behind->draw_background();
        window_behind->draw_foreground();
        increase_queue_index();
        --data.underlying_windows_redrawing;
    }
}
